"""Wyłącznie dane syntetyczne do sprawdzenia instalacji i całego przepływu."""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Settings


def synthetic_sources(days=100, start="2026-01-01T00:00:00Z", farm_codes=("GAL", "KAM"), scenario="stable"):
    if scenario not in ("stable", "drifting", "fronts"):
        raise ValueError("Nieznany scenariusz syntetyczny.")
    start = pd.Timestamp(start)
    as_of = start + pd.Timedelta(days=days)
    rng = np.random.default_rng(20261014)
    forecasts, observations = [], []
    def truth(times, farm_index):
        hours = (times.asi8 - start.value) / 3600e9
        speed = 7 + 2 * np.sin(hours / 33) + 0.7 * np.cos(hours / 5) + farm_index * 0.8
        direction = (hours * 1.2 + 350 + farm_index * 55 + 20 * np.sin(hours / 12)) % 360
        temperature = 8 + 3 * np.sin(2 * np.pi * hours / 24) + 4 * np.sin(hours / 450) + farm_index
        if scenario == "fronts":
            front = np.tanh(4 * np.sin(2 * np.pi * hours / 96))
            speed += 1.8 * front
            temperature -= 3 * front
            direction = (direction + 35 * front) % 360
        return speed, direction, temperature
    obs_times = pd.date_range(start - pd.Timedelta(days=3), as_of + pd.Timedelta(days=2), freq="10min")
    issues = pd.date_range(start - pd.Timedelta(days=3), as_of, freq="6h")
    for i, farm in enumerate(farm_codes):
        speed, direction, temperature = truth(obs_times - pd.Timedelta(minutes=5), i)
        noise = 1. if scenario == "stable" else 4.
        observations.append(pd.DataFrame({"farm": farm, "observed_at": obs_times,
            "speed": speed + rng.normal(0, noise * 0.05, len(obs_times)),
            "direction": (direction + rng.normal(0, noise * 0.3, len(obs_times))) % 360,
            "temperature": temperature + rng.normal(0, noise * 0.03, len(obs_times))}))
        for issue in issues:
            times = pd.date_range(issue + pd.Timedelta(minutes=15), periods=144, freq="15min")
            shift = 90 + 20 * np.sin((issue.value - start.value) / 3600e9 / 96) if scenario == "fronts" else 0
            speed, direction, temperature = truth(times - pd.Timedelta(minutes=7.5 + shift), i)
            drift = np.sin(2 * np.pi * (times.asi8 - start.value) / (9 * 24 * 3600e9)) if scenario == "drifting" else 0.
            forecasts.append(pd.DataFrame({"farm": farm, "issued_at": issue, "available_at": issue,
                "valid_at": times, "speed": speed * 1.1 + 0.6 + 0.2 * np.sin(np.radians(direction)) + .8 * drift,
                "direction": (direction + 12 + i * 3 + 6 * drift) % 360,
                "temperature": temperature + 1.2 + i * 0.2 + .7 * drift}))
    return pd.concat(forecasts, ignore_index=True), pd.concat(observations, ignore_index=True), as_of


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("weather_demo"))
    parser.add_argument("--scenario", choices=["stable", "drifting", "fronts"], default="stable")
    args = parser.parse_args(argv)
    forecasts, observations, as_of = synthetic_sources(scenario=args.scenario)
    cfg = replace(Settings(), farms=("GAL", "KAM"), history_days=100, min_training_days=30,
                  validation_days=7, test_days=7, min_route_days=3, route_bootstrap_samples=100,
                  trees=30, max_fit_rows=10000, n_jobs=2)
    args.output.mkdir(parents=True, exist_ok=True)
    forecasts.to_csv(args.output / "forecasts.csv", index=False)
    observations.to_csv(args.output / "observations.csv", index=False)
    (args.output / "config.json").write_text(json.dumps(cfg.to_dict(), indent=2), encoding="utf-8")
    print(f"DANE SYNTETYCZNE. as-of: {as_of.isoformat()}; katalog: {args.output}")


if __name__ == "__main__":
    main()
