import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from weather_correction import runner
from weather_correction.cli import train_main
from weather_correction.config import Settings
from weather_correction.demo import synthetic_sources
from weather_correction.sources import load_sources


@pytest.fixture
def settings_file(tmp_path):
    data = json.loads((runner.ROOT / "ustawienia_uruchomienia.json").read_text())
    data["konfiguracja_modelu"] = "model.json"
    (tmp_path / "model.json").write_text(json.dumps(Settings().to_dict()))
    path = tmp_path / "run.json"

    def save():
        path.write_text(json.dumps(data))
        return path

    return data, save


def argument(args, name):
    return args[args.index(name) + 1]


def test_default_combined_run_shares_one_clock_and_resolves_paths(settings_file, monkeypatch):
    _, save = settings_file
    path = save()
    monkeypatch.chdir(path.parent.parent)
    commands = runner.build_commands(path, now="2026-02-05T06:00:00Z")
    assert [mode for mode, _ in commands] == ["trening", "prognoza"]
    assert argument(commands[0][1], "--as-of") == argument(commands[1][1], "--as-of")
    assert Path(argument(commands[0][1], "--config")) == path.parent / "model.json"
    assert Path(argument(commands[1][1], "--output")).parent == path.parent / "weather_output/prognozy"


@pytest.mark.parametrize("start,end,count", [
    ("2026-03-29T00:00:00+01:00", "2026-03-30T00:00:00+02:00", 4),
    ("2026-10-25T00:00:00+02:00", "2026-10-26T00:00:00+01:00", 5),
])
def test_prediction_period_uses_elapsed_time_at_dst_and_unique_files(settings_file, start, end, count):
    data, save = settings_file
    data["tryb"] = "prognoza"
    data["prognoza"].update(start=start, koniec=end, krok_godziny=6)
    commands = runner.build_commands(save())
    times = [pd.Timestamp(argument(args, "--as-of")) for _, args in commands]
    assert len(times) == count
    assert times[0] == pd.Timestamp(start) and times[-1] < pd.Timestamp(end)
    assert all(b - a == pd.Timedelta(hours=6) for a, b in zip(times, times[1:]))
    assert len({argument(args, "--output") for _, args in commands}) == count


@pytest.mark.parametrize("section,changes,message", [
    ("trening", {"start": "2026-02-02", "koniec": "2026-02-01"}, "trening.start"),
    ("trening", {"start": "2026-01-01", "koniec": "2026-01-02"}, "za krótka"),
    ("trening", {"start": "NaT"}, "Niepoprawna data"),
    ("trening", {"start": 1234}, "Niepoprawna data"),
    ("prognoza", {"start": "2026-02-05", "koniec": "2026-02-04"}, "prognoza.start"),
    ("prognoza", {"start": "2020-01-01"}, "po zakończeniu uczenia"),
    ("prognoza", {"krok_godziny": 0}, "krok_godziny"),
    ("prognoza", {"start": "2026-10-25T02:30:00"}, "Niepoprawna data"),
    ("dane", {"prognozy_csv": "one.csv"}, "oba pola"),
])
def test_invalid_settings_are_rejected_before_any_training(settings_file, monkeypatch, section, changes, message, capsys):
    data, save = settings_file
    data[section].update(changes)
    calls = []
    monkeypatch.setattr(runner, "train_main", lambda args: calls.append(args))
    assert runner.main(["--settings", str(save())]) == 1
    assert not calls
    assert message in capsys.readouterr().err


def test_rejected_training_stops_combined_run(settings_file, monkeypatch):
    _, save = settings_file
    calls = []
    monkeypatch.setattr(runner, "train_main", lambda args: 2)
    monkeypatch.setattr(runner, "predict_main", lambda args: calls.append(args))
    assert runner.main(["--settings", str(save())]) == 2
    assert not calls


def test_check_does_not_run_training_or_connect_to_sql(settings_file, monkeypatch):
    _, save = settings_file
    monkeypatch.setattr(runner, "train_main", lambda args: pytest.fail("Training must not run"))
    assert runner.main(["--settings", str(save()), "--check"]) == 0


def test_explicit_history_start_reaches_sql_with_context(monkeypatch):
    calls = []
    monkeypatch.setenv("PGE_WEATHER_FORECAST_CONNECTION", "forecast-test")
    monkeypatch.setenv("PGE_WEATHER_OBSERVATION_CONNECTION", "observation-test")
    monkeypatch.setattr("weather_correction.sources.query", lambda path, conn, params: calls.append(params) or pd.DataFrame())
    start = pd.Timestamp("2025-01-01T00:00:00Z")
    args = SimpleNamespace(forecast_csv=None, observation_csv=None, start=start,
                           forecast_sql="f.sql", observation_sql="o.sql")
    load_sources(args, Settings(history_days=1), pd.Timestamp("2026-02-05T00:00:00Z"), True)
    assert calls[0][0] == (start - pd.Timedelta(days=3)).to_pydatetime().replace(tzinfo=None)
    assert calls[1][0] < start.date()


def test_training_cli_rejects_reversed_dates_before_loading_data(monkeypatch):
    monkeypatch.setattr("weather_correction.cli.load_sources", lambda *args: pytest.fail("Must validate dates first"))
    assert train_main(["--start", "2026-02-02", "--as-of", "2026-02-01"]) == 1


def test_full_launcher_training_batch_prediction_and_filtered_assessment(settings_file):
    data, save = settings_file
    path = save()
    forecasts, observations, as_of = synthetic_sources(days=35, farm_codes=("GAL",))
    forecasts.to_csv(path.parent / "forecasts.csv", index=False)
    observations.to_csv(path.parent / "observations.csv", index=False)
    cfg = replace(Settings(), farms=("GAL",), history_days=3, min_training_days=7,
                  validation_days=3, test_days=3, backtest_folds=1, trees=3, tuning_trials=1,
                  max_fit_rows=1000, min_training_rows=40, min_route_rows=8, min_route_days=2,
                  min_route_issues=2, route_bootstrap_samples=40, backend="hist", n_jobs=1)
    (path.parent / "model.json").write_text(json.dumps(cfg.to_dict()))
    data["dane"].update(prognozy_csv="forecasts.csv", pomiary_csv="observations.csv", rodzaj="synthetic")
    start = as_of - pd.Timedelta(days=35)
    data["trening"].update(start=start.isoformat(), koniec=as_of.isoformat(),
                           dni_walidacji=3, dni_testu=3, liczba_testow=1)
    data["prognoza"].update(start=as_of.isoformat(), koniec=(as_of + pd.Timedelta(hours=12)).isoformat())
    assert runner.main(["--settings", str(save())]) == 0

    files = sorted((path.parent / "weather_output/prognozy").glob("*.csv"))
    assert len(files) == 2
    assert all(len(pd.read_csv(file)) == 96 for file in files)
    report = json.loads(next((path.parent / "weather_artifacts").glob("model-*/report.json")).read_text())
    assert report["training_window"] == {"start_utc": start.isoformat(), "end_utc": as_of.isoformat()}
    assert report["settings"]["history_days"] == 35
    assert report["quality"]["training_rows"] > 10000  # Explicit start overrides the old 3-day window.

    data["tryb"] = "ocena"
    data["ocena"].update(start=(as_of + pd.Timedelta(minutes=15)).isoformat(),
                         koniec=(as_of + pd.Timedelta(hours=1)).isoformat(),
                         pomiary_dostepne_do=(as_of + pd.Timedelta(days=2)).isoformat())
    assert runner.main(["--settings", str(save())]) == 0
    assessment = json.loads((path.parent / "weather_output/evaluation/model_statistics.json").read_text())
    assert assessment["metadata"]["forecast_rows"] == 3
    assert assessment["metadata"]["valid_start"] == (as_of + pd.Timedelta(minutes=15)).isoformat()
    assert assessment["metadata"]["valid_end"] == (as_of + pd.Timedelta(minutes=45)).isoformat()
