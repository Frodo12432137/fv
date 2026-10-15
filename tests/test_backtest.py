from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from threadpoolctl import threadpool_limits

from weather_correction import backtest as module
from weather_correction.backtest import BacktestSpec, prediction_times, run_backtest
from weather_correction.config import Settings
from weather_correction.demo import synthetic_sources
from weather_correction.runner import build_commands
from weather_correction.weather_data import PreparedWeather
from ocen_prognoze_pogody import main as evaluate_main
from backtest_pogody import main as backtest_main


@pytest.fixture
def cfg():
    return replace(Settings(), farms=("GAL",), history_days=35, min_training_days=7, validation_days=3,
        test_days=3, backtest_folds=1, min_training_rows=40, min_route_rows=8, min_route_issues=2,
        min_route_days=2, route_bootstrap_samples=40, backend="hist", trees=4, tuning_trials=1,
        max_fit_rows=1200, n_jobs=1)


@pytest.fixture
def data(cfg):
    forecasts, observations, as_of = synthetic_sources(days=35, farm_codes=cfg.farms)
    return forecasts, observations, as_of


def specification(as_of, strategy="staly", days=2):
    start = as_of - pd.Timedelta(days=days)
    return BacktestSpec(as_of - pd.Timedelta(days=35), start, start, as_of,
                        as_of + pd.Timedelta(days=1), strategy)


@pytest.mark.parametrize("field,value", [
    ("training_end", pd.Timestamp("2026-02-05T01:00:00Z")),
    ("end", pd.Timestamp("2026-02-01T00:00:00Z")),
    ("step_hours", 0), ("retrain_days", -1), ("strategy", "unknown"),
    ("assessment_as_of", pd.Timestamp("2026-01-01T00:00:00Z")),
])
def test_invalid_backtest_ranges_are_rejected(cfg, field, value):
    spec = specification(pd.Timestamp("2026-02-05T00:00:00Z"))
    with pytest.raises(ValueError):
        replace(spec, **{field: value}).validate(cfg)


def test_rolling_history_must_end_at_first_prediction(cfg):
    spec = specification(pd.Timestamp("2026-02-05T00:00:00Z"), "kroczacy")
    with pytest.raises(ValueError, match="koniec pierwszego uczenia"):
        replace(spec, training_end=spec.start - pd.Timedelta(days=1)).validate(cfg)


def test_schedule_uses_elapsed_hours_across_dst():
    spec = BacktestSpec(pd.Timestamp("2024-01-01T00:00:00Z"), pd.Timestamp("2026-10-24T22:00:00Z"),
        pd.Timestamp("2026-10-24T22:00:00Z"), pd.Timestamp("2026-10-25T23:00:00Z"), pd.Timestamp("2026-10-27T00:00:00Z"))
    times = prediction_times(spec)
    assert len(times) == 5 and all(b - a == pd.Timedelta(hours=6) for a, b in zip(times, times[1:]))


def test_prepared_weather_recomputes_partial_labels_from_known_readings(cfg):
    settings = replace(cfg, min_coverage=.5, observation_delay_minutes=0)
    forecasts = pd.DataFrame({"farm": "GAL", "issued_at": "2026-01-01T00:00:00Z",
        "valid_at": ["2026-01-01T00:15:00Z", "2026-01-01T00:30:00Z"], "speed": 7., "direction": 0., "temperature": 10.})
    obs = pd.DataFrame({"farm": "GAL", "observed_at": ["2026-01-01T00:10:00Z", "2026-01-01T00:20:00Z"],
        "available_at": ["2026-01-01T00:10:00Z", "2026-01-01T01:00:00Z"], "speed": [3., 9.], "direction": 0., "temperature": 10.})
    prepared = PreparedWeather.prepare(forecasts, obs, settings)
    _, known, labels, errors = prepared.known_at(pd.Timestamp("2026-01-01T00:15:00Z"), settings)
    assert len(known) == 1 and labels.speed.iloc[0] == 3.
    assert errors.error_speed.iloc[0] == -4.


def test_frozen_backtest_records_out_of_sample_predictions_and_future_truth(cfg, data, tmp_path):
    forecasts, observations, as_of = data
    prepared = PreparedWeather.prepare(forecasts, observations, cfg)
    spec = specification(as_of)
    production_pointer = tmp_path / "current.json"
    production_pointer.write_text("production-pointer-sentinel")
    with threadpool_limits(1):
        result = run_backtest(prepared, cfg, spec, tmp_path, "synthetic", log=lambda _: None)
    assert result["code"] == 0
    folder = result["folder"]
    trained = pd.read_csv(folder / "training_runs.csv")
    jobs = pd.read_csv(folder / "prediction_runs.csv")
    compared = pd.read_csv(folder / "backtest_predictions.csv")
    assert len(trained) == 1 and len(jobs) == 8
    assert jobs.model_version.nunique() == 1
    assert (pd.to_datetime(jobs.model_trained_as_of_utc, utc=True) <= pd.to_datetime(jobs.prediction_as_of_utc, utc=True)).all()
    assert pd.to_datetime(compared.valid_at, utc=True).ge(spec.start).all()
    assert pd.to_datetime(compared.valid_at, utc=True).lt(spec.end).all()
    assert result["assessment"]["metadata"]["generation_coverage_pct"] == 100.
    assert production_pointer.read_text() == "production-pointer-sentinel"
    assert (folder / "models/current.json").exists() and (folder / "BACKTEST.md").exists()
    assert (folder / "model_statistics.html").exists() and (folder / "model_versions_statistics.csv").exists()


def test_later_rejected_model_keeps_previous_model_in_rolling_backtest(cfg, data, tmp_path, monkeypatch):
    forecasts, observations, as_of = data
    spec = specification(as_of, "kroczacy")
    real_train = module.train
    def fit(raw_forecasts, raw_observations, cutoff, config, artifacts, **kwargs):
        if cutoff > spec.training_end:
            return {"published": False, "folder": artifacts / "rejected-candidate", "report": {"publication_failures": ["test"]}}
        return real_train(raw_forecasts, raw_observations, cutoff, config, artifacts, **kwargs)
    monkeypatch.setattr(module, "train", fit)
    with threadpool_limits(1):
        result = run_backtest(PreparedWeather.prepare(forecasts, observations, cfg), cfg, spec, tmp_path, log=lambda _: None)
    attempts = pd.read_csv(result["folder"] / "training_runs.csv")
    jobs = pd.read_csv(result["folder"] / "prediction_runs.csv")
    assert len(attempts) == 2 and attempts.accepted.tolist() == [True, False]
    assert jobs.model_version.nunique() == 1 and len(jobs) == 8
    assert result["code"] == 0


def test_rolling_backtest_retrains_at_each_next_day_and_keeps_history_cutoffs(cfg, data, tmp_path):
    forecasts, observations, as_of = data
    spec = specification(as_of, "kroczacy")
    with threadpool_limits(1):
        result = run_backtest(PreparedWeather.prepare(forecasts, observations, cfg), cfg, spec, tmp_path,
                              "synthetic", log=lambda _: None)
    attempts = pd.read_csv(result["folder"] / "training_runs.csv")
    assert len(attempts) == 2
    assert pd.to_datetime(attempts.trained_as_of_utc, utc=True).tolist() == [spec.start, spec.start + pd.Timedelta(days=1)]
    for report in (result["folder"] / "models").glob("model-*/report.json"):
        saved = json.loads(report.read_text())
        assert saved["training_window"]["start_utc"] == spec.training_start.isoformat()
        assert pd.Timestamp(saved["training_window"]["end_utc"]) <= spec.end
    assert result["code"] == 0


def test_first_prediction_is_invariant_to_measurements_received_after_training_cutoff(cfg, data, tmp_path):
    forecasts, observations, as_of = data
    spec = specification(as_of, days=1)
    altered = observations.copy()
    future = pd.to_datetime(altered.observed_at, utc=True) + pd.Timedelta(minutes=cfg.observation_delay_minutes) > spec.training_end
    altered.loc[future, "speed"] += 10.
    altered.loc[future, "temperature"] -= 5.
    altered.loc[future, "direction"] = (altered.loc[future, "direction"] + 60.) % 360
    outputs = []
    with threadpool_limits(1):
        for name, obs in (("original", observations), ("future_changed", altered)):
            result = run_backtest(PreparedWeather.prepare(forecasts, obs, cfg), cfg, spec, tmp_path / name,
                                  "synthetic", log=lambda _: None)
            first = sorted((result["folder"] / "predictions").glob("*.csv"))[0]
            outputs.append(pd.read_csv(first)[["skorygowana_predkoscWiatru", "skorygowana_temperatura", "skorygowany_kierunekWiatru"]])
    pd.testing.assert_frame_equal(outputs[0], outputs[1])


def test_failed_forecast_jobs_remain_visible_in_backtest_coverage(cfg, data, tmp_path):
    forecasts, observations, as_of = data
    spec = specification(as_of, days=1)
    prepared = PreparedWeather.prepare(forecasts, observations, cfg)
    broken_issue = spec.start + pd.Timedelta(hours=6)
    missing = (prepared.forecasts.issued_at == broken_issue) & (prepared.forecasts.valid_at <= broken_issue + pd.Timedelta(hours=2))
    prepared.forecasts = prepared.forecasts.loc[~missing].copy()
    with threadpool_limits(1):
        result = run_backtest(prepared, cfg, spec, tmp_path, log=lambda _: None)
    assert result["code"] == 2 and result["assessment"] is not None
    assert result["assessment"]["metadata"]["failed_prediction_jobs"] == 1
    assert result["assessment"]["metadata"]["generation_coverage_pct"] < 100.
    assert "Nieudane uruchomienia: 1" in (result["folder"] / "model_statistics.html").read_text()


def test_initial_quality_rejection_does_not_use_an_unpublished_model(cfg, data, tmp_path, monkeypatch):
    forecasts, observations, as_of = data
    monkeypatch.setattr(module, "train", lambda *a, **k: {"published": False,
        "folder": Path("rejected-candidate"), "report": {"publication_failures": ["test"]}})
    result = run_backtest(PreparedWeather.prepare(forecasts, observations, cfg), cfg, specification(as_of), tmp_path, log=lambda _: None)
    assert result["code"] == 2 and result["assessment"] is None
    assert json.loads((result["folder"] / "backtest.json").read_text())["status"] == "no_accepted_initial_model"


def test_backtest_launcher_uses_separate_output_and_explicit_bounds(tmp_path):
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "ustawienia_backtest.example.json").read_text())
    data["konfiguracja_modelu"] = str(root / "weather_config.example.json")
    path = tmp_path / "run.json"
    path.write_text(json.dumps(data))
    commands = build_commands(path, now="2026-10-15T00:00:00Z")
    assert len(commands) == 1 and commands[0][0] == "backtest"
    args = commands[0][1]
    assert "--artifacts" not in args
    assert args[args.index("--training-start") + 1] == "2024-06-30T22:00:00+00:00"
    assert args[args.index("--end") + 1] == "2026-07-31T22:00:00+00:00"


def test_legacy_run_settings_without_backtest_section_still_work(tmp_path):
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "ustawienia_uruchomienia.json").read_text())
    data.pop("backtest")
    data["konfiguracja_modelu"] = str(root / "weather_config.example.json")
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(data))
    assert [mode for mode, _ in build_commands(path, now="2026-10-15T00:00:00Z")] == ["trening", "prognoza"]


def test_backtest_check_validates_dates_without_reading_data(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr("backtest_pogody.load_sources", lambda *a, **k: pytest.fail("Must not read data"))
    config = tmp_path / "cfg.json"
    config.write_text(json.dumps(cfg.to_dict()))
    assert backtest_main(["--config", str(config), "--training-start", "2026-01-01T00:00:00Z",
        "--training-end", "2026-02-01T00:00:00Z", "--start", "2026-02-01T00:00:00Z",
        "--end", "2026-02-03T00:00:00Z", "--assessment-as-of", "2026-02-04T00:00:00Z", "--check"]) == 0


def test_overlap_is_rejected_before_data_access(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr("backtest_pogody.load_sources", lambda *a, **k: pytest.fail("Must not read data"))
    config = tmp_path / "cfg.json"
    config.write_text(json.dumps(cfg.to_dict()))
    assert backtest_main(["--config", str(config), "--training-start", "2026-01-01T00:00:00Z",
        "--training-end", "2026-02-02T00:00:00Z", "--start", "2026-02-01T00:00:00Z",
        "--end", "2026-02-03T00:00:00Z", "--assessment-as-of", "2026-02-04T00:00:00Z"]) == 1
