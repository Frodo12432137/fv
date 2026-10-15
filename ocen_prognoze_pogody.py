"""Ocena zapisanej prognozy względem późniejszych, dostępnych pomiarów."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from weather_correction.config import Settings
from weather_correction.data import utc_time
from weather_correction.evaluation import build_assessment, snapshot_samples
from weather_correction.storage import save_assessment


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions-csv", type=Path, nargs="+", required=True)
    parser.add_argument("--observation-csv", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True, help="Konfiguracja użyta podczas treningu ocenianej prognozy.")
    parser.add_argument("--as-of", help="Chwila dostępności pomiarów, z offsetem; domyślnie teraz.")
    parser.add_argument("--start", help="Początek ocenianych kwadransów (włącznie).")
    parser.add_argument("--end", help="Koniec ocenianych kwadransów (wyłącznie).")
    parser.add_argument("--output", type=Path, default=Path("weather_output/evaluation"))
    parser.add_argument("--csv-separator", default=",")
    parser.add_argument("--predictions-separator", default=",", help="Separator plików wynikowych; program zapisuje je z przecinkiem.")
    parser.add_argument("--data-kind", choices=["unspecified", "measured", "synthetic"], default="unspecified")
    args = parser.parse_args(argv)
    try:
        cfg = Settings.load(args.config)
        as_of = utc_time(args.as_of, cfg.timezone) if args.as_of else pd.Timestamp.now(tz="UTC")
        start = utc_time(args.start, cfg.timezone) if args.start else None
        end = utc_time(args.end, cfg.timezone) if args.end else None
        if any(pd.isna(value) for value in (as_of, start, end) if value is not None):
            raise ValueError("Niepoprawna data oceny.")
        if start is not None and end is not None and start >= end:
            raise ValueError("Początek oceny musi być wcześniejszy niż koniec.")
        output = pd.concat([pd.read_csv(path, sep=args.predictions_separator, encoding="utf-8-sig") for path in args.predictions_csv], ignore_index=True)
        observations = pd.read_csv(args.observation_csv, sep=args.csv_separator, encoding="utf-8-sig")
        samples, metadata = snapshot_samples(output, observations, as_of, cfg, start=start, end=end)
        assessment = build_assessment(samples, cfg, {**metadata, "data_kind": args.data_kind,
            "assessment_type": "Ocena zapisanych prognoz po nadejściu wykonania", "prediction_files": [p.name for p in args.predictions_csv]})
        save_assessment(args.output, assessment)
        overall = [r for r in assessment["metrics"] if r["fold"] == "pooled" and r["farm"] == "ALL" and r["horizon"] == "ALL"]
        for row in overall:
            print(f"{row['target']}: N={row['rows']}, MAE surowe={row['raw_mae']}, MAE korekty={row['corrected_mae']}, poprawa %={row['mae_improvement_pct']}")
        print(f"Raport: {args.output / 'model_statistics.html'}")
        return 0 if any(r["rows"] for r in overall) else 2
    except Exception as exc:
        print(f"BŁĄD: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
