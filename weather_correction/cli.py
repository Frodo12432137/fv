from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd
from threadpoolctl import threadpool_limits

from .config import Settings
from .data import utc_time
from .pipeline import predict, train
from .sources import SQL_ROOT, load_sources
from .storage import load_bundle


ROOT = Path(__file__).resolve().parent.parent


def parser(training: bool) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=("Uczenie korekty pogody dla farm wiatrowych" if training else "Korekta pogody: 96 kwadransów dla każdej farmy"))
    result.add_argument("--config", type=Path, help="Ustawienia JSON; w predykcji muszą odpowiadać ustawieniom modelu.")
    result.add_argument("--artifacts", type=Path, default=ROOT / "weather_artifacts")
    result.add_argument("--as-of", help="Czas uruchomienia z offsetem, np. 2026-10-14T06:00:00+02:00. Domyślnie teraz.")
    result.add_argument("--forecast-csv", type=Path)
    result.add_argument("--observation-csv", type=Path)
    result.add_argument("--csv-separator", default=",")
    result.add_argument("--forecast-sql", type=Path, default=SQL_ROOT / "forecasts.sql")
    result.add_argument("--observation-sql", type=Path, default=SQL_ROOT / "observations.sql")
    if training:
        result.add_argument("--start", help="Początek historii uczenia (włącznie); koniec wyznacza --as-of. Zastępuje history_days.")
        result.add_argument("--validation-days", type=int, help="Długość walidacji; nadpisuje konfigurację modelu.")
        result.add_argument("--test-days", type=int, help="Długość jednego testu chronologicznego.")
        result.add_argument("--backtest-folds", type=int, help="Liczba kolejnych testów chronologicznych.")
        result.add_argument("--data-kind", choices=["unspecified", "measured", "synthetic"], default="unspecified",
                            help="Opis rodzaju danych w raporcie statystyk; nie zmienia uczenia.")
    if not training:
        result.add_argument("--output", type=Path, default=ROOT / "weather_output" / "prognoza_pogody_korekta_24h.csv")
    return result


def run(training: bool, argv=None) -> int:
    args = parser(training).parse_args(argv)
    try:
        if training:
            cfg = Settings.load(args.config)
            overrides = {key: getattr(args, key) for key in ("validation_days", "test_days", "backtest_folds")
                         if getattr(args, key) is not None}
            cfg = replace(cfg, **overrides)
        else:
            bundle, _ = load_bundle(args.artifacts)
            data = dict(bundle["settings"])
            data.setdefault("feature_version", 1)
            data["farms"] = tuple(data["farms"])
            cfg = Settings(**data)
            if args.config and Settings.load(args.config) != cfg:
                raise ValueError("Ustawienia predykcji różnią się od ustawień modelu. Użyj konfiguracji z treningu.")
        as_of = utc_time(args.as_of, cfg.timezone) if args.as_of else pd.Timestamp.now(tz="UTC")
        if pd.isna(as_of):
            raise ValueError("Niepoprawny czas --as-of.")
        start = utc_time(args.start, cfg.timezone) if training and args.start else None
        if start is not None and (pd.isna(start) or start >= as_of):
            raise ValueError("Początek historii uczenia musi być wcześniejszy niż koniec (--as-of).")
        if training:
            args.start = start
        print(f"Czas uruchomienia UTC: {as_of.isoformat()}", flush=True)
        raw_forecasts, raw_observations = load_sources(args, cfg, as_of, training)
        # Ograniczenie wątków jest istotne dla bibliotek BLAS/OpenMP i jobów dzielących serwer.
        with threadpool_limits(limits=cfg.n_jobs):
            if training:
                result = train(raw_forecasts, raw_observations, as_of, cfg, args.artifacts,
                               log=lambda message: print(message, flush=True), data_kind=args.data_kind, start=start)
                return 0 if result["published"] else 2
            predict(raw_forecasts, raw_observations, as_of, args.artifacts, args.output,
                    log=lambda message: print(message, flush=True))
        return 0
    except Exception as exc:
        print(f"BŁĄD: {exc}", file=sys.stderr, flush=True)
        return 1


def train_main(argv=None):
    return run(True, argv)


def predict_main(argv=None):
    return run(False, argv)
