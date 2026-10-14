from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from threadpoolctl import threadpool_limits

from weather_correction.cli import predict_main, train_main
from weather_correction.config import Settings
from weather_correction.data import (angle_diff, observation_targets, prepare_forecasts,
                                     prepare_observations, select_forecast_run)
from weather_correction.demo import synthetic_sources
from weather_correction.features import build_features, history_features, residual_history, trajectory_features
from weather_correction.models import (Family, blend_prediction, choose_routes, evaluate_route,
                                     fit_family, metrics, required_families, route_quality)
from weather_correction.pipeline import chronological_split, predict, train
from weather_correction.storage import load_bundle, save_bundle
from weather_correction.sources import load_sources


@pytest.fixture
def cfg():
    return replace(Settings(), farms=("GAL",), observation_delay_minutes=0)


def observation(times, speed=6.0, direction=0.0, temperature=10.0, farm="GAL"):
    return pd.DataFrame({"farm": farm, "observed_at": pd.to_datetime(times, utc=True),
                         "speed": speed, "direction": direction, "temperature": temperature})


def forecast(times, issue="2026-01-01T00:00:00Z", speed=7.0, direction=359.0, temperature=11.0, farm="GAL"):
    return pd.DataFrame({"farm": farm, "valid_at": pd.to_datetime(times, utc=True),
        "issued_at": pd.Timestamp(issue), "speed": speed, "direction": direction, "temperature": temperature})


def test_direction_average_around_north(cfg):
    raw = observation(["2026-01-01T00:10:00Z"] * 2, direction=[359.0, 1.0])
    obs = prepare_observations(raw, cfg)
    assert abs(angle_diff(obs.direction.iloc[0], 0)) < 1e-8
    assert abs(angle_diff(1, 359)) == 2


def test_opposing_directions_are_missing_not_south(cfg):
    raw = observation(["2026-01-01T00:10:00Z"] * 2, direction=[90.0, 270.0])
    assert np.isnan(prepare_observations(raw, cfg).direction.iloc[0])


def test_ten_to_fifteen_minutes_uses_overlap_weights(cfg):
    raw = observation(["2026-01-01T00:10:00Z", "2026-01-01T00:20:00Z", "2026-01-01T00:30:00Z"], speed=[3.0, 9.0, 12.0])
    targets = observation_targets(prepare_observations(raw, cfg), cfg)
    assert targets.speed.tolist() == pytest.approx([5.0, 11.0])
    assert targets.coverage_speed.tolist() == pytest.approx([1.0, 1.0])
    assert targets.valid_at.iloc[0] == pd.Timestamp("2026-01-01T00:15:00Z")
    assert targets.label_available_at.iloc[0] == pd.Timestamp("2026-01-01T00:20:00Z")


def test_incomplete_quarter_is_not_fabricated(cfg):
    targets = observation_targets(prepare_observations(observation(["2026-01-01T00:10:00Z"]), cfg), cfg)
    assert np.isnan(targets.speed.iloc[0])
    assert targets.coverage_speed.iloc[0] == pytest.approx(2 / 3)


def test_start_timestamps_shift_by_native_period(cfg):
    end = prepare_observations(observation(["2026-01-01T00:10:00Z"]), cfg)
    beginning = prepare_observations(observation(["2026-01-01T00:00:00Z"]), replace(cfg, observation_timestamp_position="start"))
    pd.testing.assert_frame_equal(end, beginning)


def test_recorded_observation_availability_is_respected(cfg):
    raw = observation(["2026-01-01T00:10:00Z"])
    raw["available_at"] = "2026-01-01T03:00:00Z"
    obs = prepare_observations(raw, cfg)
    assert obs.available_at.iloc[0] == pd.Timestamp("2026-01-01T03:00:00Z")


def test_instant_target_does_not_skip_missing_measurement(cfg):
    settings = replace(cfg, observation_timestamp_position="instant")
    raw = observation(pd.date_range("2026-01-01T00:00:00Z", periods=4, freq="10min"), speed=[3., np.nan, 9., 12.])
    target = observation_targets(prepare_observations(raw, settings), settings)
    assert np.isnan(target.loc[target.valid_at == pd.Timestamp("2026-01-01T00:15:00Z"), "speed"].iloc[0])


def test_late_old_observation_does_not_replace_newer_known_weather(cfg):
    query = pd.DataFrame({"farm": ["GAL"], "available_at": pd.to_datetime(["2026-01-01T06:00:00Z"])})
    history = pd.DataFrame({"farm": ["GAL"] * 2,
        "observed_at": pd.to_datetime(["2026-01-01T05:40:00Z", "2026-01-01T01:00:00Z"]),
        "available_at": pd.to_datetime(["2026-01-01T05:50:00Z", "2026-01-01T05:55:00Z"]), "speed": [7., 70.]})
    result = history_features(query, history, ["speed"], "obs")
    assert result.obs_last_speed.iloc[0] == 7.
    assert result.obs_age_minutes.iloc[0] == 20.
    assert result.obs_1h_speed.iloc[0] == 7.
    assert result.obs_1h_std_speed.iloc[0] == 0.


def test_utc_preserves_both_autumn_hours(cfg):
    raw = observation(["2025-10-26T00:10:00Z", "2025-10-26T01:10:00Z"])
    assert len(prepare_observations(raw, cfg)) == 2


def test_ambiguous_local_times_are_counted_and_dropped(cfg):
    raw = observation(["2025-10-26T00:10:00Z", "2025-10-26T03:10:00Z"])
    raw = raw.drop(columns="observed_at")
    raw["observed_at_local"] = ["2025-10-26 02:10:00", "2025-10-26 04:10:00"]
    with pytest.warns(RuntimeWarning, match="niejednoznacznych"):
        prepared = prepare_observations(raw, cfg)
    assert len(prepared) == 1
    assert prepared.attrs["dropped_timezone_rows"] == 1


def test_all_forecast_editions_are_retained(cfg):
    raw = pd.concat([forecast(["2026-01-01T12:00:00Z"]), forecast(["2026-01-01T12:00:00Z"], issue="2026-01-01T06:00:00Z")])
    assert len(prepare_forecasts(raw, cfg)) == 2


def test_missing_issue_time_rejects_old_sql_export(cfg):
    raw = forecast(["2026-01-01T12:00:00Z"]).drop(columns="issued_at")
    with pytest.raises(ValueError, match="kolumny czasu"):
        prepare_forecasts(raw, cfg)


def test_conflicting_same_issue_duplicates_are_rejected(cfg):
    raw = pd.concat([forecast(["2026-01-01T12:00:00Z"]), forecast(["2026-01-01T12:00:00Z"], speed=20)])
    with pytest.raises(ValueError, match="Sprzeczne duplikaty"):
        prepare_forecasts(raw, cfg)


def test_forecast_interpolation_crosses_north(cfg):
    raw = forecast(["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"], direction=[359.0, 1.0])
    prepared = prepare_forecasts(raw, cfg)
    middle = prepared.loc[prepared.valid_at == pd.Timestamp("2026-01-01T00:30:00Z")].iloc[0]
    assert abs(angle_diff(middle.direction, 0)) < 1e-8
    assert len(prepared) == 5


def test_forecast_does_not_interpolate_large_gaps(cfg):
    raw = forecast(["2026-01-01T00:00:00Z", "2026-01-01T03:00:00Z"])
    assert len(prepare_forecasts(raw, cfg)) == 2


def test_prediction_uses_latest_available_complete_edition(cfg):
    times = pd.date_range("2026-01-01T06:15:00Z", periods=96, freq="15min")
    old = forecast(times, speed=4)
    new = forecast(times, issue="2026-01-01T06:00:00Z", speed=8)
    future = forecast(times, issue="2026-01-01T12:00:00Z", speed=20)
    prepared = prepare_forecasts(pd.concat([old, new, future]), cfg)
    selected = select_forecast_run(prepared, pd.Timestamp("2026-01-01T06:00:00Z"), cfg)
    assert len(selected) == 96 and (selected.speed == 8).all()


def test_missing_farm_or_incomplete_edition_fails(cfg):
    prepared = prepare_forecasts(forecast(["2026-01-01T00:15:00Z"]), cfg)
    with pytest.raises(ValueError, match="96 kwadransów"):
        select_forecast_run(prepared, pd.Timestamp("2026-01-01T00:00:00Z"), cfg)


def test_history_is_anchored_at_issue_not_future_target(cfg):
    queries = pd.DataFrame({"farm": ["GAL"] * 2, "available_at": pd.to_datetime(["2026-01-01T06:00:00Z"] * 2)})
    history = pd.DataFrame({"farm": ["GAL"] * 2, "available_at": pd.to_datetime(["2026-01-01T05:50:00Z", "2026-01-02T05:50:00Z"]), "speed": [5, 70]})
    features = history_features(queries, history, ["speed"], "obs")
    assert features.obs_last_speed.tolist() == [5, 5]
    assert features.obs_1h_speed.tolist() == [5, 5]


def test_unavailable_late_measurement_never_enters_features(cfg):
    query = pd.DataFrame({"farm": ["GAL"], "available_at": pd.to_datetime(["2026-01-01T06:00:00Z"])})
    history = pd.DataFrame({"farm": ["GAL"], "available_at": pd.to_datetime(["2026-01-01T06:20:00Z"]), "speed": [9]})
    assert np.isnan(history_features(query, history, ["speed"], "obs").obs_last_speed.iloc[0])


def test_history_does_not_cross_farms(cfg):
    query = pd.DataFrame({"farm": ["GAL"], "available_at": pd.to_datetime(["2026-01-01T06:00:00Z"])})
    history = pd.DataFrame({"farm": ["KAM"], "available_at": pd.to_datetime(["2026-01-01T05:50:00Z"]), "speed": [9]})
    assert np.isnan(history_features(query, history, ["speed"], "obs").obs_last_speed.iloc[0])


def test_history_windows_use_elapsed_time_not_row_count(cfg):
    query = pd.DataFrame({"farm": ["GAL"], "available_at": pd.to_datetime(["2026-01-01T06:00:00Z"])})
    history = pd.DataFrame({"farm": ["GAL"] * 2, "available_at": pd.to_datetime(["2026-01-01T01:00:00Z", "2026-01-01T05:50:00Z"]), "speed": [1, 9]})
    result = history_features(query, history, ["speed"], "obs")
    assert result.obs_1h_speed.iloc[0] == 9 and result.obs_6h_speed.iloc[0] == 5


def test_held_out_labels_cannot_cross_training_cutoff(cfg):
    dates = pd.date_range("2026-01-01", periods=90, freq="D", tz="UTC")
    rows = pd.DataFrame({"available_at": dates, "label_available_at": dates + pd.Timedelta(days=1)})
    settings = replace(cfg, validation_days=3, test_days=3, backtest_folds=1, min_training_days=10)
    a, b, c, split = chronological_split(rows, dates[-1], settings, 0)
    assert (rows.loc[a, "label_available_at"] < pd.Timestamp(split["validation_start"])).all()
    assert (rows.loc[b, "label_available_at"] < pd.Timestamp(split["test_start"])).all()
    assert (rows.loc[c, "label_available_at"] <= pd.Timestamp(split["test_end"])).all()


def test_metrics_use_shortest_direction_distance():
    measured = metrics([1, 359], [359, 1], angular=True)
    assert measured["mae"] == 2 and measured["rmse"] == 2


def test_bad_correction_keeps_raw(cfg):
    settings = replace(cfg, min_route_rows=2, min_route_issues=2, min_route_days=2)
    dates = pd.date_range("2026-01-01", periods=4, freq="D", tz="UTC")
    rows = pd.DataFrame({"farm": "GAL", "available_at": dates, "actual_speed": 6., "actual_temperature": 10., "actual_direction": 0.})
    features = pd.DataFrame({"lead_hours": [1.] * 4})
    candidates = {t: {"raw|0.0": np.full(4, value), "bad|1.0": np.full(4, value + 20)}
                  for t, value in (("speed", 7.), ("temperature", 11.), ("direction", 1.))}
    routes, _ = choose_routes(candidates, features, rows, settings)
    assert all(route == "raw|0.0" for target in routes.values() for route in target.values())


def test_farm_encoder_does_not_depend_on_prediction_batch(cfg):
    settings = replace(cfg, farms=("GAL", "KAM"), min_training_rows=2)
    features = pd.DataFrame({"farm": ["GAL", "KAM"] * 4, "lead_hours": np.arange(8.), "obs_age_minutes": 0.})
    rows = pd.DataFrame({"farm": features.farm, "speed": 7., "actual_speed": np.where(features.farm == "GAL", 6., 4.),
        "available_at": pd.date_range("2026-01-01", periods=8, freq="h", tz="UTC")})
    model = fit_family("ridge", "speed", features, rows, settings)
    full = model.predict(features, rows)
    part = model.predict(features.iloc[[1]], rows.iloc[[1]])
    assert part[0] == pytest.approx(full[1])


def test_rejected_candidate_does_not_replace_active_pointer(tmp_path):
    bundle = {"format_version": 1, "routes": {}}
    first = save_bundle(tmp_path, bundle, {}, [], [], True)
    save_bundle(tmp_path, bundle, {}, [], [], False)
    _, version = load_bundle(tmp_path)
    assert version == first.name


def test_manifest_detects_partial_or_modified_artifact(tmp_path):
    folder = save_bundle(tmp_path, {"format_version": 1, "routes": {}}, {}, [], [], True)
    (folder / "model.joblib").write_bytes(b"damaged")
    with pytest.raises(ValueError, match="Suma kontrolna"):
        load_bundle(tmp_path)


@pytest.mark.parametrize("backend", ["hist", "xgboost"])
def test_real_training_and_prediction_pipeline_on_synthetic_data(tmp_path, backend):
    forecasts, observations, as_of = synthetic_sources(days=35)
    settings = replace(Settings(), farms=("GAL", "KAM"), history_days=35, min_training_days=7,
        validation_days=3, test_days=3, backtest_folds=2, trees=4, max_fit_rows=1200,
        min_training_rows=40, min_route_rows=8, min_route_issues=2, min_route_days=2,
        route_bootstrap_samples=40, backend=backend, n_jobs=1)
    with threadpool_limits(limits=1):
        result = train(forecasts, observations, as_of, settings, tmp_path / "models", log=lambda _: None)
        assert result["published"]
        assert all(pd.Timestamp(fold["validation_start"]) < pd.Timestamp(fold["calibration_start"]) < pd.Timestamp(fold["test_start"])
                   for fold in result["report"]["folds"])
        assert result["report"]["selected_correcting_cells"] > 0
        production = result["report"]["production_selection"]
        assert pd.Timestamp(production["validation_start"]) == as_of - pd.Timedelta(days=settings.validation_days)
        assert pd.Timestamp(production["calibration_start"]) > pd.Timestamp(result["report"]["folds"][-1]["test_start"])
        assert pd.Timestamp(production["end"]) == as_of
        assert (result["folder"] / "test_metrics.csv").exists()
        output = predict(forecasts, observations, as_of, tmp_path / "models", tmp_path / "output.csv", log=lambda _: None)
    assert len(output) == 192 and output.groupby("lokalizacja").size().tolist() == [96, 96]
    assert output.skorygowana_predkoscWiatru.ge(0).all()
    assert output.skorygowany_kierunekWiatru.between(0, 360, inclusive="left").all()
    assert np.isfinite(output[["skorygowana_predkoscWiatru", "skorygowana_temperatura", "skorygowany_kierunekWiatru"]]).all().all()
    with pytest.raises(ValueError, match="powstał po"):
        predict(forecasts, observations, as_of - pd.Timedelta(hours=1), tmp_path / "models", tmp_path / "invalid.csv", log=lambda _: None)
    assert not (tmp_path / "invalid.csv").exists()


def test_cli_fails_without_model_and_rejects_half_csv_inputs(tmp_path):
    assert predict_main(["--artifacts", str(tmp_path / "missing")]) == 1
    assert train_main(["--forecast-csv", str(tmp_path / "one.csv")]) == 1


def test_sql_requires_explicit_connection_configuration(monkeypatch, cfg):
    monkeypatch.delenv("PGE_WEATHER_FORECAST_CONNECTION", raising=False)
    monkeypatch.delenv("PGE_WEATHER_OBSERVATION_CONNECTION", raising=False)
    args = SimpleNamespace(forecast_csv=None, observation_csv=None)
    with pytest.raises(ValueError, match="PGE_WEATHER_FORECAST_CONNECTION i PGE_WEATHER_OBSERVATION_CONNECTION"):
        load_sources(args, cfg, pd.Timestamp("2026-01-01T00:00:00Z"), training=True)


def test_trajectory_uses_same_known_edition(cfg):
    first = forecast(["2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z"], speed=[7., 9.])
    later = forecast(["2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z"], issue="2026-01-01T00:30:00Z", speed=70.)
    context = prepare_forecasts(pd.concat([first, later]), cfg)
    query = context.loc[(context.issued_at == pd.Timestamp("2026-01-01T00:00:00Z")) & (context.valid_at == pd.Timestamp("2026-01-01T01:00:00Z"))].reset_index(drop=True)
    trajectory = trajectory_features(query, context)
    assert trajectory.forecast_future_1h_delta_speed.iloc[0] == 2.


def test_trajectory_rejects_neighbor_received_later(cfg):
    context = prepare_forecasts(forecast(["2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z"], speed=[7., 9.]), cfg)
    query = context.iloc[[0]].reset_index(drop=True)
    context.loc[context.valid_at == pd.Timestamp("2026-01-01T02:00:00Z"), "available_at"] += pd.Timedelta(minutes=30)
    assert np.isnan(trajectory_features(query, context).forecast_future_1h_delta_speed.iloc[0])


def test_adaptive_recent_error_decays_with_horizon():
    family = Family("adaptive_3h", "speed", offsets={}, global_offset=0., trained_farms=("GAL",))
    features = pd.DataFrame({"lead_hours": [.25, 24.], "bias_1h_error_speed": 2.4,
        "bias_6h_error_speed": 2.4, "bias_1h_count": 4., "bias_age_minutes": 20.})
    rows = pd.DataFrame({"farm": "GAL", "speed": [6., 6.]})
    correction = family.predict(features, rows) - rows.speed
    assert correction.iloc[0] > 1.5
    assert correction.iloc[1] < 0.01


def test_adaptive_missing_history_keeps_learned_bias():
    family = Family("adaptive_12h", "speed", offsets={}, global_offset=1., trained_farms=("GAL",))
    features = pd.DataFrame({"lead_hours": [1.], "bias_1h_error_speed": np.nan,
        "bias_6h_error_speed": np.nan, "bias_1h_count": 0., "bias_age_minutes": np.nan})
    assert family.predict(features, pd.DataFrame({"farm": ["GAL"], "speed": [7.]}))[0] == 8.


def test_ensemble_direction_is_circular():
    result = blend_prediction(np.array([359.]), np.array([1.]), .5, angular=True)
    assert abs(angle_diff(result[0], 0)) < 1e-8 and 0 <= result[0] < 360


def test_route_rejects_gain_concentrated_in_one_day(cfg):
    days = np.repeat(np.arange(8), 20)
    raw = np.ones(len(days))
    correction = np.where(days == 0, 0., 1.05)
    assert correction.mean() < raw.mean()
    assert not route_quality(np.zeros(len(days)), correction, raw, days, cfg)["accepted"]


def test_route_accepts_gain_consistent_across_weather_days(cfg):
    days = np.repeat(np.arange(8), 20)
    result = route_quality(np.zeros(len(days)), np.full(len(days), .6), np.ones(len(days)), days, cfg)
    assert result["accepted"] and result["lower_gain"] > 0 and result["day_win_rate"] == 1.


def test_route_rejects_large_tail_errors_despite_lower_mae(cfg):
    days = np.repeat(np.arange(8), 20)
    corrected = np.tile([.2] * 18 + [8.] * 2, 8)
    assert corrected.mean() < 1
    assert not route_quality(np.zeros(len(days)), corrected, np.ones(len(days)), days, cfg)["accepted"]


def test_selection_can_choose_complementary_models_as_ensemble(cfg):
    settings = replace(cfg, min_route_rows=2, min_route_issues=2, min_route_days=4)
    dates = pd.date_range("2026-01-01", periods=8, freq="D", tz="UTC").repeat(8)
    rows = pd.DataFrame({"farm": "GAL", "available_at": dates, "actual_speed": 2.,
        "actual_temperature": 0., "actual_direction": 0.})
    alternation = np.tile([-1., 1.], 32)
    candidates = {target: {"raw|0.0": np.full(64, actual + 5),
        "left|1.0": actual + alternation, "right|1.0": actual - alternation}
        for target, actual in (("speed", 2.), ("temperature", 0.), ("direction", 0.))}
    features = pd.DataFrame({"lead_hours": np.ones(64)})
    routes, _ = choose_routes(candidates, features, rows, settings)
    key = routes["temperature"]["GAL|0-3h"]
    assert key.startswith("blend::")
    assert np.max(np.abs(evaluate_route(key, candidates["temperature"], "temperature"))) < 1e-8
    assert {"left", "right"} <= set(required_families(routes)["temperature"])
