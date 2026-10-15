"""Odtworzenie pracy modelu z historycznym odcięciem danych w każdym uruchomieniu."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import uuid

import pandas as pd

from .config import Settings
from .evaluation import TARGET_NAMES, build_assessment, comparison_metrics, number, snapshot_samples, table
from .pipeline import predict, train
from .storage import atomic_csv, atomic_json, atomic_text, load_bundle, save_assessment
from .weather_data import PreparedWeather


@dataclass(frozen=True)
class BacktestSpec:
    training_start: pd.Timestamp
    training_end: pd.Timestamp
    start: pd.Timestamp
    end: pd.Timestamp
    assessment_as_of: pd.Timestamp
    strategy: str = "staly"
    step_hours: int = 6
    retrain_days: int = 1

    def validate(self, cfg):
        for name in ("training_start", "training_end", "start", "end", "assessment_as_of"):
            value = getattr(self, name)
            if pd.isna(value) or value.tzinfo is None:
                raise ValueError(f"Niepoprawna data backtestu: {name}.")
        if not self.training_start < self.training_end <= self.start < self.end:
            raise ValueError("Wymagane: początek uczenia < koniec uczenia <= początek backtestu < koniec backtestu. "
                             "Nie wolno uczyć modelu na okresie, którego błąd ma ocenić backtest.")
        if self.end - self.start < pd.Timedelta(minutes=30):
            raise ValueError("Backtest musi obejmować co najmniej 30 minut.")
        if self.end > self.assessment_as_of:
            raise ValueError("Koniec backtestu nie może leżeć po chwili dostępności pomiarów do oceny.")
        if self.strategy not in ("staly", "kroczacy"):
            raise ValueError("Strategia backtestu: staly albo kroczacy.")
        if self.strategy == "kroczacy" and self.training_end != self.start:
            raise ValueError("W backteście kroczącym koniec pierwszego uczenia musi być początkiem backtestu.")
        if type(self.step_hours) is not int or self.step_hours <= 0:
            raise ValueError("Krok backtestu musi być dodatnią liczbą całkowitą godzin.")
        if type(self.retrain_days) is not int or self.retrain_days <= 0:
            raise ValueError("Odstęp ponownego uczenia musi być dodatnią liczbą całkowitą dni.")
        minimum = cfg.min_training_days + cfg.validation_days + cfg.test_days * cfg.backtest_folds
        if self.training_end - self.training_start < pd.Timedelta(days=minimum):
            raise ValueError(f"Historia pierwszego modelu jest za krótka: potrzeba co najmniej {minimum} dni.")

    def to_dict(self):
        return {key: value.isoformat() if isinstance(value, pd.Timestamp) else value for key, value in asdict(self).items()}


def prediction_times(spec):
    return pd.date_range(spec.start, spec.end, freq=pd.Timedelta(hours=spec.step_hours), inclusive="left")


def run_backtest(data: PreparedWeather, cfg: Settings, spec: BacktestSpec, output: Path,
                 data_kind="unspecified", log=print):
    spec.validate(cfg)
    times = prediction_times(spec)
    run_id = "run-" + pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    folder = output / run_id
    models_dir = folder / "models"
    folder.mkdir(parents=True, exist_ok=False)
    truth = data.targets_at(spec.assessment_as_of, cfg)
    attempts, jobs, samples = [], [], []
    expected_rows = 0
    metadata = {"specification": spec.to_dict(), "data_kind": data_kind, "settings": cfg.to_dict(),
        "run_id": run_id, "planned_predictions": len(times), "status": "running",
        "policy": "Pierwszy model i każde ponowne uczenie używają wyłącznie danych znanych do odcięcia. "
                  "Kandydat odrzucony przez historyczną bramkę nie zastępuje poprzedniego modelu. "
                  "Backtest ma własny katalog modeli, niezależny od modeli produkcyjnych."}

    def checkpoint():
        atomic_json(folder / "backtest.json", {**metadata, "training_attempts": attempts, "prediction_jobs": jobs})
        atomic_csv(folder / "training_runs.csv", pd.DataFrame(attempts))
        atomic_csv(folder / "prediction_runs.csv", pd.DataFrame(jobs))

    def fit(cutoff):
        log(f"Uczenie {len(attempts) + 1}: {spec.training_start.isoformat()} – {cutoff.isoformat()}.")
        log_path = folder / f"training_{len(attempts) + 1:04d}.log"
        with log_path.open("w", encoding="utf-8") as stream:
            result = train(None, None, cutoff, cfg, models_dir, start=spec.training_start,
                           data_kind=data_kind, prepared=data, log=lambda line: print(line, file=stream, flush=True))
        attempts.append({"training_start_utc": spec.training_start.isoformat(), "trained_as_of_utc": cutoff.isoformat(),
                         "candidate_version": result["folder"].name, "accepted": result["published"],
                         "failures": "; ".join(result["report"]["publication_failures"]), "log": log_path.name})
        checkpoint()
        return (models_dir / "current.json").exists()

    checkpoint()
    try:
        if not fit(spec.training_end):
            metadata["status"] = "no_accepted_initial_model"
            checkpoint()
            log("Pierwszy model nie przeszedł bramki jakości. Raport jego testów zapisano w models; backtest nie ma aktywnego modelu.")
            return {"code": 2, "folder": folder, "assessment": None}
        refresh = spec.training_end + pd.Timedelta(days=spec.retrain_days)
        for index, moment in enumerate(times, 1):
            if spec.strategy == "kroczacy" and moment >= refresh:
                fit(moment)
                refresh = moment + pd.Timedelta(days=spec.retrain_days)
            bundle, version = load_bundle(models_dir)
            cutoff = pd.Timestamp(bundle["trained_as_of"])
            if cutoff > moment:
                raise ValueError("Model backtestu zna dane późniejsze niż oceniane uruchomienie.")
            grid = pd.date_range(moment.floor("15min") + pd.Timedelta(minutes=15), periods=96, freq="15min")
            expected = int(((grid >= spec.start) & (grid < spec.end)).sum()) * len(cfg.farms)
            expected_rows += expected
            path = folder / "predictions" / f"prognoza_{moment.strftime('%Y%m%dT%H%M%S%fZ')}.csv"
            log(f"Prognoza {index}/{len(times)}: {moment.isoformat()}, model z {cutoff.isoformat()}.")
            record = {"prediction_as_of_utc": moment.isoformat(), "model_version": version,
                      "model_trained_as_of_utc": cutoff.isoformat(), "expected_rows_in_window": expected,
                      "prediction_file": str(path.relative_to(folder))}
            try:
                predicted = predict(None, None, moment, models_dir, path, prepared=data, log=lambda _: None)
                scored, _ = snapshot_samples(predicted, None, spec.assessment_as_of, cfg,
                    start=spec.start, end=spec.end, prepared_targets=truth)
                scored["fold"] = "backtest"
                scored["model_trained_as_of"] = cutoff
                samples.append(scored)
                record.update(status="ok", generated_rows_in_window=len(scored), error="")
            except ValueError as exc:
                record.update(status="failed", generated_rows_in_window=0, error=str(exc))
                log(f"Brak poprawnej prognozy: {exc}")
            jobs.append(record)
            checkpoint()
        metadata.update(expected_forecast_rows=expected_rows,
                        successful_predictions=sum(job["status"] == "ok" for job in jobs),
                        failed_predictions=sum(job["status"] != "ok" for job in jobs))
        if not samples:
            metadata["status"] = "no_predictions"
            checkpoint()
            return {"code": 2, "folder": folder, "assessment": None}
        combined = pd.concat(samples, ignore_index=True)
        overall_meta = {"data_kind": data_kind, "assessment_type": "Backtest historyczny: " + spec.strategy,
            "model_version": "Jeden zamrożony model" if spec.strategy == "staly" else "Kolejne wersje tej samej procedury uczenia",
            "backtest": spec.to_dict(), "training_attempts": len(attempts),
            "accepted_models": sum(row["accepted"] for row in attempts),
            "failed_prediction_jobs": metadata["failed_predictions"], "expected_forecast_rows": expected_rows,
            "generated_forecast_rows": len(combined),
            "generation_coverage_pct": 100 * len(combined) / expected_rows if expected_rows else None,
            "note": "Ocena obejmuje wyłącznie prognozowane kwadranse w wybranym okresie backtestu. "
                    "Modele nie znają przyszłych pomiarów; późniejsze wykonanie służy wyłącznie ocenie. "
                    "Błędy liczymy dla udanych prognoz, a brakujące uruchomienia osobno w prediction_runs.csv. "
                    "Ponowne uczenie jest symulowane w chwili odcięcia danych, bez modelowania czasu obliczeń."}
        assessment = build_assessment(combined, cfg, overall_meta)
        save_assessment(folder, assessment)
        atomic_csv(folder / "backtest_predictions.csv", combined)
        version_stats = []
        for version, group in combined.groupby("model_version", sort=False):
            for target in ("speed", "temperature", "direction"):
                version_stats.append({"model_version": version, **comparison_metrics(group, target, cfg)})
        atomic_csv(folder / "model_versions_statistics.csv", pd.DataFrame(version_stats))
        scored_rows = sum(r["rows"] for r in assessment["metrics"]
                          if r["fold"] == "pooled" and r["farm"] == "ALL" and r["horizon"] == "ALL")
        code = 2 if metadata["failed_predictions"] or not scored_rows else 0
        metadata["status"] = "partial" if code else "completed"
        checkpoint()
        summary = ("# Wynik backtestu\n\n" + f"Strategia: **{spec.strategy}**. Rodzaj danych: **{data_kind}**.\n\n"
            f"Uczenie pierwszego modelu: {spec.training_start.isoformat()} – {spec.training_end.isoformat()}.\n\n"
            f"Backtest: {spec.start.isoformat()} – {spec.end.isoformat()} (koniec wyłączny).\n\n"
            f"Udane uruchomienia: {metadata['successful_predictions']}/{len(times)}. "
            f"Pokrycie generowania prognoz: {overall_meta['generation_coverage_pct']:.2f}%.\n\n"
            "[Statystyki błędu](model_statistics.md) · [HTML](model_statistics.html) · "
            "[Historia uczenia](training_runs.csv) · [Historia prognoz](prediction_runs.csv)\n\n"
            "Porównuj MAE/RMSE korekty z prognozą surową, sprawdzając również P95, bias, "
            "pokrycie pomiarów i liczbę dni. Wynik tego backtestu nie służy do wyboru parametrów "
            "na tym samym okresie; kolejne zmiany wymagają kolejnego niezależnego okresu.\n")
        rows = [row for row in assessment["metrics"] if row["fold"] == "pooled" and row["farm"] == "ALL" and row["horizon"] == "ALL"]
        summary += "\n" + table(["Parametr", "Jednostka", "N", "MAE surowe", "MAE modelu", "Poprawa %", "RMSE modelu", "P95 modelu"],
            [[TARGET_NAMES[row["target"]], row["unit"], row["rows"], number(row["raw_mae"]), number(row["corrected_mae"]),
              number(row["mae_improvement_pct"]), number(row["corrected_rmse"]), number(row["corrected_p95_absolute_error"])] for row in rows]) + "\n"
        atomic_text(folder / "BACKTEST.md", summary)
        log(f"Raport backtestu: {folder / 'BACKTEST.md'}")
        return {"code": code, "folder": folder, "assessment": assessment}
    except Exception as exc:
        metadata.update(status="error", error=str(exc))
        checkpoint()
        raise
