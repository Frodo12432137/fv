import json
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from ocen_prognoze_pogody import main
from weather_correction.config import Settings
from weather_correction.evaluation import (build_assessment, comparison_metrics, daily_gain,
                                          render_html, snapshot_samples, test_samples as make_test_samples)
from weather_correction.storage import save_assessment


@pytest.fixture
def cfg():
    return replace(Settings(), farms=("GAL",), observation_delay_minutes=0)


def samples():
    frame = pd.DataFrame({"farm": "GAL", "forecast_at": pd.date_range("2026-01-01", periods=4, freq="D", tz="UTC"),
        "lead_hours": 1., "fold": ["1", "2", "2", "2"],
        "actual_speed": [1., 2., 3., np.nan], "raw_speed": [2., 3., 4., 5.], "corrected_speed": [1., 2.5, 3., 5.],
        "actual_temperature": [10., 11., 12., 13.], "raw_temperature": [12., 13., 14., 15.],
        "corrected_temperature": [10., 11.5, 12., 13.], "actual_direction": [1., 359., 90., 270.],
        "raw_direction": [359., 1., 105., 285.], "corrected_direction": [0., 0., 90., 270.]})
    frame["valid_at"] = frame.forecast_at + pd.Timedelta(hours=1)
    return frame


def snapshot():
    return pd.DataFrame({"lokalizacja": ["GAL"] * 2,
        "dataGodzinaUTC": ["2026-01-01T00:15:00Z", "2026-01-01T00:30:00Z"],
        "czasPredykcjiUTC": "2026-01-01T00:00:00Z", "czasDostepnosciUTC": "2026-01-01T00:00:00Z",
        "modelVersion": "test-model", "predkoscWiatru": 7., "skorygowana_predkoscWiatru": 6.,
        "temperatura": 12., "skorygowana_temperatura": 10., "kierunekWiatru": 359., "skorygowany_kierunekWiatru": 1.})


def observations():
    return pd.DataFrame({"farm": "GAL", "observed_at": pd.date_range("2026-01-01T00:10:00Z", periods=3, freq="10min"),
                         "speed": 6., "temperature": 10., "direction": 1.})


def test_assessment_uses_identical_paired_rows(cfg):
    frame = samples()
    frame.loc[2, "corrected_speed"] = np.nan
    result = comparison_metrics(frame, "speed", cfg)
    assert result["rows"] == 2 and result["forecast_rows"] == 4
    assert result["raw_mae"] == 1. and result["corrected_mae"] == .25
    assert result["corrected_rmse"] == pytest.approx(np.sqrt(.125))
    assert result["corrected_bias"] == .25
    assert result["raw_r2"] == -3. and result["corrected_r2"] == .5
    assert result["mae_improvement_pct"] == 75.


def test_circular_statistics_exclude_missing_speed_and_calm(cfg):
    frame = samples()
    frame.loc[2, "actual_speed"] = .5
    result = comparison_metrics(frame, "direction", cfg)
    assert result["rows"] == 2 and result["excluded_calm_rows"] == 1
    assert result["missing_measurement_rows"] == 1
    assert result["raw_mae"] == 2. and result["corrected_mae"] == 1.
    assert result["corrected_r2"] is None


def test_constant_truth_and_perfect_raw_have_no_false_r2_or_skill(cfg):
    frame = samples()
    frame["actual_speed"] = frame["raw_speed"] = 6.
    frame["corrected_speed"] = 7.
    result = comparison_metrics(frame, "speed", cfg)
    assert result["mae_improvement_pct"] is None and result["raw_r2"] is None
    assert result["mae_gain"] == -1. and result["worsened_rows_pct"] == 100.


def test_pooled_quantiles_and_rmse_are_computed_from_all_errors(cfg):
    frame = samples()
    frame["actual_speed"] = [1., 2., 3., 4.]
    frame["corrected_speed"] = [1., 12., 13., 14.]
    assessment = build_assessment(frame, cfg)
    pooled = next(r for r in assessment["metrics"] if r["fold"] == "pooled" and
                  r["farm"] == "ALL" and r["horizon"] == "ALL" and r["target"] == "speed")
    assert pooled["corrected_rmse"] == pytest.approx(np.sqrt(75.))
    assert pooled["corrected_p95_absolute_error"] == 10.


def test_completely_missing_measurement_quarters_remain_in_coverage(cfg):
    frame = samples()
    rows = frame.rename(columns={"forecast_at": "available_at", **{f"raw_{t}": t for t in ("speed", "temperature", "direction")}})
    rows["issued_at"] = rows.available_at
    grid = rows.copy()
    extra = rows.iloc[[0]].copy()
    extra["valid_at"] += pd.Timedelta(minutes=15)
    grid = pd.concat([grid, extra], ignore_index=True)
    corrected = {t: rows[f"corrected_{t}"].to_numpy() for t in ("speed", "temperature", "direction")}
    result = make_test_samples(rows, corrected, 1, grid)
    measured = comparison_metrics(result, "temperature", cfg)
    assert measured["forecast_rows"] == 5 and measured["rows"] == 4
    assert measured["missing_measurement_rows"] == 1 and measured["scored_fraction_pct"] == 80.


def test_gain_interval_uses_days_and_requires_week():
    raw, corrected = np.ones(24), np.zeros(24)
    days = np.repeat(np.arange(8), 3)
    result = daily_gain(raw, corrected, days)
    assert result["days"] == 8 and result["day_win_rate_pct"] == 100.
    assert result["mae_gain_ci_low"] == result["mae_gain_ci_high"] == 1.
    assert daily_gain(raw[:18], corrected[:18], days[:18])["mae_gain_ci_low"] is None


def test_saved_forecasts_wait_for_available_measurements(cfg):
    early, _ = snapshot_samples(snapshot(), observations(), pd.Timestamp("2026-01-01T00:15:00Z"), cfg)
    later, _ = snapshot_samples(snapshot(), observations(), pd.Timestamp("2026-01-01T00:20:00Z"), cfg)
    assert early.actual_speed.isna().all()
    assert later.actual_speed.notna().sum() == 1
    assert later.actual_speed.iloc[0] == 6.


def test_duplicate_snapshot_files_do_not_multiply_statistics(cfg):
    frame, metadata = snapshot_samples(pd.concat([snapshot()] * 2), observations(), pd.Timestamp("2026-01-01T01:00:00Z"), cfg)
    assert len(frame) == 2 and metadata["duplicates_removed"] == 2


def test_conflicting_duplicate_snapshot_is_rejected(cfg):
    duplicate = snapshot()
    duplicate.loc[0, "skorygowana_predkoscWiatru"] = 20.
    with pytest.raises(ValueError, match="Sprzeczne predykcje"):
        snapshot_samples(pd.concat([snapshot(), duplicate]), observations(), pd.Timestamp("2026-01-01T01:00:00Z"), cfg)


def test_mixed_model_versions_are_not_pooled(cfg):
    frame = snapshot()
    frame.loc[1, "modelVersion"] = "other-model"
    with pytest.raises(ValueError, match="jedną wersję"):
        snapshot_samples(frame, observations(), pd.Timestamp("2026-01-01T01:00:00Z"), cfg)


def test_report_escapes_text_and_writes_finite_json(cfg, tmp_path):
    assessment = build_assessment(samples(), cfg, {"data_kind": "synthetic", "assessment_type": "<script>evil</script>"})
    html = render_html(assessment)
    assert "<script>evil</script>" not in html and "&lt;script&gt;evil&lt;/script&gt;" in html
    assert "DANE SYNTETYCZNE" in html
    save_assessment(tmp_path, assessment)
    data = json.loads((tmp_path / "model_statistics.json").read_text())
    assert data["metadata"]["data_kind"] == "synthetic"
    assert (tmp_path / "model_statistics.csv").exists() and (tmp_path / "daily_statistics.csv").exists()
    assert "NaN" not in (tmp_path / "model_statistics.json").read_text()


def test_evaluation_cli_handles_completed_and_pending_forecasts(cfg, tmp_path):
    pred, obs, config = tmp_path / "pred.csv", tmp_path / "obs.csv", tmp_path / "cfg.json"
    snapshot().to_csv(pred, index=False)
    observations().to_csv(obs, index=False)
    config.write_text(json.dumps(cfg.to_dict()))
    args = ["--predictions-csv", str(pred), "--observation-csv", str(obs), "--config", str(config),
            "--output", str(tmp_path / "report"), "--data-kind", "synthetic"]
    assert main(args + ["--as-of", "2026-01-01T00:15:00Z"]) == 2
    assert main(args + ["--as-of", "2026-01-01T01:00:00Z"]) == 0
    assert (tmp_path / "report/model_statistics.html").exists()
