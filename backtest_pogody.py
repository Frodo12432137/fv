"""Wyucz model na wybranej historii i oceń późniejsze prognozy bez wiedzy o przyszłości."""
from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys

import pandas as pd
from threadpoolctl import threadpool_limits

from weather_correction.backtest import BacktestSpec, run_backtest
from weather_correction.backtest import prediction_times
from weather_correction.config import Settings
from weather_correction.data import utc_time
from weather_correction.sources import SQL_ROOT, load_sources
from weather_correction.weather_data import PreparedWeather


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--training-start", required=True)
    parser.add_argument("--training-end", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--strategy", choices=["staly", "kroczacy"], default="staly")
    parser.add_argument("--step-hours", type=int, default=6)
    parser.add_argument("--retrain-days", type=int, default=1)
    parser.add_argument("--assessment-as-of")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "weather_output/backtest")
    parser.add_argument("--forecast-csv", type=Path)
    parser.add_argument("--observation-csv", type=Path)
    parser.add_argument("--csv-separator", default=",")
    parser.add_argument("--forecast-sql", type=Path, default=SQL_ROOT / "forecasts.sql")
    parser.add_argument("--observation-sql", type=Path, default=SQL_ROOT / "observations.sql")
    parser.add_argument("--validation-days", type=int)
    parser.add_argument("--test-days", type=int)
    parser.add_argument("--backtest-folds", type=int)
    parser.add_argument("--data-kind", choices=["unspecified", "measured", "synthetic"], default="unspecified")
    parser.add_argument("--check", action="store_true", help="Sprawdź daty i pokaż plan bez odczytu danych i uczenia.")
    args = parser.parse_args(argv)
    try:
        cfg = Settings.load(args.config)
        cfg = replace(cfg, **{name: getattr(args, name) for name in ("validation_days", "test_days", "backtest_folds")
                             if getattr(args, name) is not None})
        stamp = lambda value: utc_time(value, cfg.timezone)
        spec = BacktestSpec(stamp(args.training_start), stamp(args.training_end), stamp(args.start), stamp(args.end),
            stamp(args.assessment_as_of) if args.assessment_as_of else pd.Timestamp.now(tz="UTC"),
            args.strategy, args.step_hours, args.retrain_days)
        spec.validate(cfg)
        print(f"Uczenie: {spec.training_start.isoformat()} – {spec.training_end.isoformat()}", flush=True)
        print(f"Backtest: {spec.start.isoformat()} – {spec.end.isoformat()}; strategia {spec.strategy}; "
              f"prognozy co {spec.step_hours} h; uruchomień: {len(prediction_times(spec))}.", flush=True)
        if args.check:
            return 0
        # Jedno pobranie obejmuje historię i cały okres odtwarzania; poszczególne modele
        # i predykcje odcinają tę tabelę według własnej historycznej chwili dostępności.
        args.start = spec.training_start
        raw_forecasts, raw_observations = load_sources(args, cfg, spec.end, training=True)
        print("Przygotowanie danych backtestu; żaden model nie zobaczy danych późniejszych od swojego odcięcia.", flush=True)
        prepared = PreparedWeather.prepare(raw_forecasts, raw_observations, cfg)
        del raw_forecasts, raw_observations
        with threadpool_limits(limits=cfg.n_jobs):
            result = run_backtest(prepared, cfg, spec, args.output, args.data_kind,
                                  log=lambda line: print(line, flush=True))
        return result["code"]
    except Exception as exc:
        print(f"BŁĄD backtestu: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
