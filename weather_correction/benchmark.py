"""Porównanie wersji na tych samych syntetycznych danych i okresach testowych."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import asdict, replace
from pathlib import Path

import pandas as pd

from .config import Settings
from .data import observation_targets, prepare_observations
from .demo import synthetic_sources
from .models import metrics


V1_FIELDS = {
    "timezone", "history_days", "horizon_hours", "max_model_lead_hours", "step_minutes",
    "native_observation_minutes", "observation_timestamp_position", "observation_delay_minutes",
    "forecast_delivery_delay_minutes", "min_coverage", "min_direction_resultant", "calm_speed",
    "max_forecast_gap_minutes", "max_forecast_age_hours", "max_recent_observation_age_minutes",
    "validation_days", "test_days", "backtest_folds", "min_training_days", "min_training_rows",
    "min_route_rows", "min_route_issues", "min_improvement", "max_fit_rows",
    "recency_half_life_days", "backend", "trees", "n_jobs", "random_state", "farms",
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-version", type=Path, required=True, help="ZIP wersji v1.")
    parser.add_argument("--output", type=Path, default=Path("weather_benchmark_v2"))
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--validation-days", type=int, default=21,
                        help="Długość strojenia i kalibracji; 21 dni jak w konfiguracji produkcyjnej.")
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    source_v2 = Path(__file__).resolve().parent.parent
    comparisons = []
    with tempfile.TemporaryDirectory(prefix="pge-weather-v1-") as temp:
        source_v1 = Path(temp)
        with zipfile.ZipFile(args.previous_version) as archive:
            for info in archive.infolist():
                destination = (source_v1 / info.filename).resolve()
                if not destination.is_relative_to(source_v1.resolve()):
                    raise ValueError("ZIP zawiera ścieżkę poza katalogiem rozpakowania.")
            archive.extractall(source_v1)
        for scenario in ("stable", "drifting", "fronts"):
            folder = args.output.resolve() / scenario
            folder.mkdir(exist_ok=True)
            forecasts, observations, as_of = synthetic_sources(days=args.days, scenario=scenario)
            forecasts.to_csv(folder / "forecasts.csv", index=False)
            observations.to_csv(folder / "observations.csv", index=False)
            cfg = replace(Settings(), farms=("GAL", "KAM"), history_days=args.days, min_training_days=21,
                          validation_days=args.validation_days, test_days=9, trees=50, max_fit_rows=8000, n_jobs=2,
                          min_route_rows=48, min_route_issues=4, route_bootstrap_samples=100)
            measured = {}
            targets = observation_targets(prepare_observations(observations, cfg), cfg)
            for version, source in (("v1", source_v1), ("v2", source_v2)):
                data = asdict(cfg)
                if version == "v1":
                    data = {key: value for key, value in data.items() if key in V1_FIELDS}
                config = folder / f"config_{version}.json"
                config.write_text(json.dumps(data, indent=2), encoding="utf-8")
                models = folder / f"models_{version}"
                command = [sys.executable, str(source / "uruchom_trening_pogody.py"), "--config", str(config),
                    "--forecast-csv", str(folder / "forecasts.csv"), "--observation-csv", str(folder / "observations.csv"),
                    "--as-of", as_of.isoformat(), "--artifacts", str(models)]
                if version == "v2":
                    command += ["--data-kind", "synthetic"]
                started = time.monotonic()
                with (folder / f"train_{version}.log").open("w", encoding="utf-8") as log:
                    result = subprocess.run(command, cwd=source, env=os.environ.copy(), stdout=log, stderr=subprocess.STDOUT)
                if result.returncode not in (0, 2):
                    raise RuntimeError(f"Błąd {scenario}/{version}: przeczytaj {folder / f'train_{version}.log'}")
                newest = max(models.glob("model-*"), key=lambda p: p.stat().st_mtime_ns)
                metrics = pd.read_csv(newest / "test_metrics.csv")
                metrics = metrics.loc[metrics.farm == "ALL"]
                forward_scores = {}
                if result.returncode == 0:
                    output = folder / f"forward_24h_{version}.csv"
                    command = [sys.executable, str(source / "uruchom_korekte_pogody.py"),
                        "--forecast-csv", str(folder / "forecasts.csv"), "--observation-csv", str(folder / "observations.csv"),
                        "--as-of", as_of.isoformat(), "--artifacts", str(models), "--output", str(output)]
                    with (folder / f"predict_{version}.log").open("w", encoding="utf-8") as log:
                        prediction = subprocess.run(command, cwd=source, env=os.environ.copy(), stdout=log, stderr=subprocess.STDOUT)
                    if prediction.returncode:
                        raise RuntimeError(f"Błąd predykcji {scenario}/{version}: {folder / f'predict_{version}.log'}")
                    forward_scores = forward_metrics(pd.read_csv(output), targets, cfg)
                elapsed = time.monotonic() - started
                measured[version] = {}
                for target, group in metrics.groupby("target"):
                    mae = float((group.corrected_mae * group.rows).sum() / group.rows.sum())
                    raw_mae = float((group.raw_mae * group.rows).sum() / group.rows.sum())
                    measured[version][target] = {"mae": mae, "raw_mae": raw_mae, "rows": int(group.rows.sum()),
                                                "published": result.returncode == 0, "seconds": elapsed,
                                                "forward_mae": forward_scores.get(target, {}).get("mae")}
                print(f"DANE SYNTETYCZNE: {scenario}/{version}, {elapsed:.1f} s, kod {result.returncode}.", flush=True)
            for target in ("speed", "temperature", "direction"):
                a, b = measured["v1"][target], measured["v2"][target]
                if a["rows"] != b["rows"] or abs(a["raw_mae"] - b["raw_mae"]) > 1e-7:
                    raise ValueError("Porównywane modele mają różne etykiety/okresy; wynik nie jest porównywalny.")
                comparisons.append({"scenario": scenario, "target": target, "rows": a["rows"],
                    "raw_mae": a["raw_mae"], "v1_mae": a["mae"], "v2_mae": b["mae"],
                    "v2_improvement_vs_v1_pct": 100 * (1 - b["mae"] / a["mae"]) if a["mae"] else 0,
                    "v1_next_24h_mae": a["forward_mae"], "v2_next_24h_mae": b["forward_mae"],
                    "v1_published": a["published"], "v2_published": b["published"]})
            pd.DataFrame(comparisons).to_csv(args.output / "comparison.csv", index=False)
    print(f"Porównanie zapisane: {args.output / 'comparison.csv'}. To nie jest ocena danych PGE.", flush=True)


def forward_metrics(output, targets, cfg):
    output = output.rename(columns={"lokalizacja": "farm", "dataGodzinaUTC": "valid_at"})
    output["valid_at"] = pd.to_datetime(output.valid_at, utc=True)
    joined = output.merge(targets, on=["farm", "valid_at"], how="left", validate="one_to_one")
    columns = {"speed": "skorygowana_predkoscWiatru", "temperature": "skorygowana_temperatura",
               "direction": "skorygowany_kierunekWiatru"}
    results = {}
    for target, col in columns.items():
        valid = joined[target].notna()
        if target == "direction":
            valid &= joined.speed >= cfg.calm_speed
        results[target] = metrics(joined.loc[valid, target], joined.loc[valid, col], target == "direction")
    return results


if __name__ == "__main__":
    main()
