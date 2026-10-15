from __future__ import annotations

import importlib.metadata
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from .config import FARM_NAMES, Settings
from .data import KEY, angle_diff, observation_targets, prepare_forecasts, prepare_observations, select_forecast_run
from .evaluation import build_assessment, test_samples
from .features import build_features, lead_bucket, residual_history
from .models import (TARGETS, candidate_predictions, choose_routes, fit_candidates, metric_report,
                     required_families, route_components, route_predictions, tune_families)
from .storage import atomic_csv, load_bundle, save_bundle


def chronological_split(rows: pd.DataFrame, as_of: pd.Timestamp, cfg: Settings, fold: int):
    test_end = as_of - pd.Timedelta(days=cfg.test_days * (cfg.backtest_folds - fold - 1))
    test_start = test_end - pd.Timedelta(days=cfg.test_days)
    validation_start = test_start - pd.Timedelta(days=cfg.validation_days)
    train = (rows.available_at < validation_start) & (rows.label_available_at < validation_start)
    validation = ((rows.available_at >= validation_start) & (rows.available_at < test_start) &
                  (rows.label_available_at < test_start))
    test = ((rows.available_at >= test_start) & (rows.available_at < test_end) &
            (rows.label_available_at <= test_end))
    if min(int(train.sum()), int(validation.sum()), int(test.sum())) == 0:
        raise ValueError("Za mało historii na chronologiczny trening, walidację i test. Zwiększ historię albo zmniejsz okresy w konfiguracji.")
    duration = validation_start - rows.loc[train, "available_at"].min()
    if duration < pd.Timedelta(days=cfg.min_training_days):
        raise ValueError(f"Trening obejmuje mniej niż {cfg.min_training_days} dni.")
    return train.to_numpy(), validation.to_numpy(), test.to_numpy(), {
        "fold": fold + 1, "validation_start": validation_start.isoformat(),
        "test_start": test_start.isoformat(), "test_end": test_end.isoformat(),
        "train_rows": int(train.sum()), "validation_rows": int(validation.sum()), "test_rows": int(test.sum()),
    }


def select_methods(features, rows, train_mask, val_mask, validation_start, cfg, log):
    """Strojenie i kalibracja korzystają z dwóch kolejnych, oddzielnych okresów."""
    family = fit_candidates(features.loc[train_mask].reset_index(drop=True),
                            rows.loc[train_mask].reset_index(drop=True), cfg, log)
    val_rows = rows.loc[val_mask].reset_index(drop=True)
    val_features = features.loc[val_mask].reset_index(drop=True)
    calibration_start = validation_start + pd.Timedelta(
        hours=max(1, round(cfg.validation_days * 24 * cfg.tuning_validation_fraction)))
    tuning_mask = (val_rows.available_at < calibration_start) & (val_rows.label_available_at < calibration_start)
    calibration_mask = val_rows.available_at >= calibration_start
    if not tuning_mask.any() or not calibration_mask.any():
        raise ValueError("Walidacja jest za krótka na niezależne strojenie i wybór korekt. Zwiększ validation_days.")
    tuning_rows = val_rows.loc[tuning_mask].reset_index(drop=True)
    tuning_features = val_features.loc[tuning_mask].reset_index(drop=True)
    tuning_predictions = candidate_predictions(family, tuning_features, tuning_rows, cfg)
    family, tuning_scores = tune_families(family, tuning_predictions, tuning_rows, cfg)
    calibration_rows = val_rows.loc[calibration_mask].reset_index(drop=True)
    calibration_features = val_features.loc[calibration_mask].reset_index(drop=True)
    calibration_predictions = candidate_predictions(family, calibration_features, calibration_rows, cfg)
    routes, candidates = choose_routes(calibration_predictions, calibration_features, calibration_rows, cfg)
    periods = {"validation_start": validation_start.isoformat(), "calibration_start": calibration_start.isoformat(),
               "tuning_rows": len(tuning_rows), "calibration_rows": len(calibration_rows)}
    return family, routes, candidates, tuning_scores, periods


def train(raw_forecasts: pd.DataFrame, raw_observations: pd.DataFrame, as_of: pd.Timestamp,
          cfg: Settings, artifacts: Path, log=print, data_kind="unspecified", start: pd.Timestamp | None = None) -> dict:
    history_start = start if start is not None else as_of - pd.Timedelta(days=cfg.history_days)
    if pd.isna(history_start) or pd.isna(as_of) or history_start >= as_of:
        raise ValueError("Początek historii uczenia musi być wcześniejszy niż koniec.")
    if start is not None:
        cfg = replace(cfg, history_days=max(1, int((as_of - history_start).ceil("D").days)))
    log(f"Historia uczenia UTC: {history_start.isoformat()} – {as_of.isoformat()} (koniec wyłączny).")
    log("Przygotowanie wszystkich wydań prognoz i pomiarów.")
    forecasts = prepare_forecasts(raw_forecasts, cfg)
    time_drops_forecast = forecasts.attrs.get("dropped_timezone_rows", 0)
    forecasts = forecasts.loc[forecasts.available_at <= as_of].reset_index(drop=True)
    obs = prepare_observations(raw_observations, cfg)
    time_drops_obs = obs.attrs.get("dropped_timezone_rows", 0)
    # Etykiety i cechy nie zawierają obserwacji otrzymanych po czasie uczenia.
    obs = obs.loc[obs.available_at <= as_of].reset_index(drop=True)
    if obs.empty:
        raise ValueError("Brak dostępnych pomiarów przed as_of.")
    targets = observation_targets(obs, cfg)
    targets = targets.loc[targets.label_available_at <= as_of].reset_index(drop=True)
    errors = residual_history(forecasts, targets, cfg)
    eligible = forecasts.loc[(forecasts.available_at >= history_start) & (forecasts.available_at < as_of) &
        (forecasts.valid_at > forecasts.available_at) &
        ((forecasts.valid_at - forecasts.available_at) <= pd.Timedelta(hours=cfg.max_model_lead_hours))]
    target_cols = targets[KEY + ["speed", "temperature", "direction", "label_available_at"]].rename(
        columns={c: f"actual_{c}" for c in TARGETS})
    rows = eligible.merge(target_cols, on=KEY, how="inner", validate="many_to_one").sort_values(
        ["available_at", "farm", "valid_at"]).reset_index(drop=True)
    if rows.empty:
        raise ValueError("Prognozy i pomiary nie mają wspólnych kwadransów w zadanym okresie.")
    log(f"Budowa cech dostępnych przy wydaniu prognozy: {len(rows):,} wierszy.")
    features = build_features(rows, obs, errors, cfg, forecast_context=forecasts)
    test_reports, selection_reports, fold_reports, tuning_reports = [], [], [], []
    evaluation_samples = []
    latest_test_metrics = None
    for fold in range(cfg.backtest_folds):
        train_mask, val_mask, test_mask, split = chronological_split(rows, as_of, cfg, fold)
        log(f"Test chronologiczny {fold + 1}/{cfg.backtest_folds}: {split['test_start']} – {split['test_end']}.")
        family, routes, candidates, tuning_scores, periods = select_methods(
            features, rows, train_mask, val_mask, pd.Timestamp(split["validation_start"]), cfg, log)
        tuning_reports.append({"fold": fold + 1, "calibration_start": periods["calibration_start"], "profiles": tuning_scores})
        split.update(periods)
        test_rows, test_features = rows.loc[test_mask].reset_index(drop=True), features.loc[test_mask].reset_index(drop=True)
        predictions = candidate_predictions(family, test_features, test_rows, cfg)
        corrected = route_predictions(predictions, routes, test_features, test_rows)
        measured = metric_report(test_rows, corrected, cfg)
        test_grid = eligible.loc[(eligible.available_at >= pd.Timestamp(split["test_start"])) &
                                 (eligible.available_at < pd.Timestamp(split["test_end"])) &
                                 (eligible.valid_at <= pd.Timestamp(split["test_end"]))]
        evaluation_samples.append(test_samples(test_rows, corrected, fold + 1, test_grid))
        for record in measured:
            record["fold"] = fold + 1
        for record in candidates:
            record["fold"] = fold + 1
        test_reports.extend(measured)
        selection_reports.extend(candidates)
        fold_reports.append(split)
        latest_test_metrics = measured
    # Test służy tylko do oceny i bramki publikacji. Nie wybieramy na nim korekt/parametrów.
    overall = [row for row in latest_test_metrics if row["farm"] == "ALL"]
    failures = []
    for row in overall:
        if (row["rows"] == 0 or row["corrected_mae"] > row["raw_mae"] + 1e-9 or
            row["corrected_rmse"] > row["raw_rmse"] * (1 + cfg.max_route_rmse_increase) + 1e-9 or
            row["corrected_p95_absolute_error"] > row["raw_p95_absolute_error"] * (1 + cfg.max_route_p95_increase) + 1e-9):
            failures.append(f"Najnowszy test: {row['target']} — MAE/RMSE/P95.")
    for target in TARGETS:
        folds = [row for row in test_reports if row["target"] == target and row["farm"] == "ALL" and row["rows"]]
        if sum(row["rows"] * row["corrected_mae"] for row in folds) > sum(row["rows"] * row["raw_mae"] for row in folds) + 1e-9:
            failures.append(f"Łączne MAE z testów: {target}.")
    for row in latest_test_metrics:
        if row["farm"] != "ALL" and row["rows"] >= cfg.min_route_rows and row["corrected_mae"] > row["raw_mae"] * (1 + cfg.max_test_cell_mae_increase) + 1e-9:
            failures.append(f"Regresja farmy/horyzontu: {row['target']}/{row['farm']}/{row['horizon']}.")
    publish = not failures
    # Po zakończeniu oceny odświeżamy dobór metod na najnowszej dostępnej historii.
    # Dawne testy pozostają oceną wcześniejszych modeli; nie przeliczamy ich wyniku.
    production_start = as_of - pd.Timedelta(days=cfg.validation_days)
    production_train = ((rows.available_at < production_start) & (rows.label_available_at < production_start)).to_numpy()
    production_val = ((rows.available_at >= production_start) & (rows.label_available_at <= as_of)).to_numpy()
    log("Odświeżenie wyboru metod na najnowszej historii przed uczeniem produkcyjnym.")
    _, production_routes, production_candidates, production_tuning, production_periods = select_methods(
        features, rows, production_train, production_val, production_start, cfg, log)
    for record in production_candidates:
        record["fold"] = "production"
    selection_reports.extend(production_candidates)
    log("Ponowne uczenie pakietu produkcyjnego na całej dostępnej historii.")
    final_models = fit_candidates(features, rows, cfg, log, names=required_families(production_routes))
    versions = {}
    for package in ("numpy", "pandas", "scikit-learn", "joblib", "xgboost"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    report = {
        "as_of_utc": as_of.isoformat(), "settings": cfg.to_dict(), "library_versions": versions,
        "training_window": {"start_utc": history_start.isoformat(), "end_utc": as_of.isoformat()},
        "feature_columns": features.columns.tolist(),
        "published": publish, "folds": fold_reports, "publication_failures": failures,
        "tuning": tuning_reports, "model_version": "2.1.0", "data_kind": data_kind,
        "production_selection": {**production_periods, "end": as_of.isoformat(), "profiles": production_tuning},
        "assessment": "Trening → strojenie profili → oddzielna kalibracja korekt/zespołów → niezależny test. Stabilność korekt sprawdzana blokami dni. Pakiet produkcyjny ponownie uczony na całej dostępnej historii.",
        "quality": {"raw_forecast_rows": len(raw_forecasts), "prepared_forecast_rows": len(forecasts),
            "raw_observation_rows": len(raw_observations), "native_observation_rows": len(obs),
            "quarter_targets": len(targets), "training_rows": len(rows),
            "ambiguous_forecast_time_rows_dropped": time_drops_forecast,
            "ambiguous_observation_time_rows_dropped": time_drops_obs,
            "missing_target_counts": {t: int(rows[f"actual_{t}"].isna().sum()) for t in TARGETS},
            "farms_with_labels": sorted(rows.farm.unique().tolist()),
            "missing_configured_farms": sorted(set(cfg.farms) - set(rows.farm)),
            "matched_forecast_fraction": float(len(rows) / len(eligible)) if len(eligible) else 0.0},
        "latest_test_overall": overall,
        "selected_correcting_cells": sum(route != "raw|0.0" for target in production_routes.values() for route in target.values()),
    }
    bundle = {"format_version": 1, "settings": cfg.to_dict(), "models": final_models,
              "routes": production_routes, "trained_as_of": as_of.isoformat(), "library_versions": versions}
    assessment = build_assessment(pd.concat(evaluation_samples, ignore_index=True), cfg, {
        "data_kind": data_kind, "assessment_type": "Chronologiczne testy poza treningiem i walidacją",
        "model_version": report["model_version"], "trained_as_of": as_of.isoformat(),
        "published": publish, "folds": fold_reports,
        "note": "Ocena wcześniejszych modeli testowych. Pakiet produkcyjny ponownie uczony na całej historii wymaga późniejszej oceny zapisanych prognoz."})
    folder = save_bundle(artifacts, bundle, report, test_reports, selection_reports, publish, assessment)
    log(f"Zapisano pakiet i raport: {folder}")
    if not publish:
        log("Kandydat nie przeszedł niezależnej oceny jakości. Aktywny model pozostał bez zmian.")
        for failure in failures:
            log(failure)
    return {"published": publish, "folder": folder, "report": report}


def predict(raw_forecasts: pd.DataFrame, raw_observations: pd.DataFrame, as_of: pd.Timestamp,
            artifacts: Path, output: Path, log=print) -> pd.DataFrame:
    bundle, version = load_bundle(artifacts)
    settings = dict(bundle["settings"])
    settings.setdefault("feature_version", 1)
    settings["farms"] = tuple(settings["farms"])
    cfg = Settings(**settings)
    if as_of < pd.Timestamp(bundle["trained_as_of"]):
        raise ValueError("Model powstał po as_of. Takie uruchomienie byłoby niepoprawnym testem historycznym.")
    forecasts = prepare_forecasts(raw_forecasts, cfg)
    forecasts = forecasts.loc[forecasts.available_at <= as_of].reset_index(drop=True)
    obs = prepare_observations(raw_observations, cfg)
    obs = obs.loc[obs.available_at <= as_of].reset_index(drop=True)
    if obs.empty:
        raise ValueError("Brak dostępnych pomiarów; sprawdź pobranie wykonania.")
    targets = observation_targets(obs, cfg)
    targets = targets.loc[targets.label_available_at <= as_of]
    errors = residual_history(forecasts, targets, cfg)
    rows = select_forecast_run(forecasts, as_of, cfg)
    features = build_features(rows, obs, errors, cfg, forecast_context=forecasts)
    predictions = candidate_predictions(bundle["models"], features, rows, cfg)
    corrected = route_predictions(predictions, bundle["routes"], features, rows)
    out = pd.DataFrame({"lokalizacja": rows.farm, "nazwaFarmy": rows.farm.map(FARM_NAMES),
        "dataGodzinaUTC": rows.valid_at.dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataGodzinaCET": rows.valid_at.dt.tz_convert(cfg.timezone).map(lambda x: x.isoformat()),
        "czasWydaniaUTC": rows.issued_at.dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "czasDostepnosciUTC": rows.available_at.dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "czasPredykcjiUTC": as_of.isoformat(), "wyprzedzenieGodziny": features.lead_hours,
        "modelVersion": version, "wiekPomiaruMinuty": features.obs_age_minutes})
    output_names = {"speed": ("predkoscWiatru", "skorygowana_predkoscWiatru", "korekta_predkosci"),
                    "temperature": ("temperatura", "skorygowana_temperatura", "korekta_temperatury"),
                    "direction": ("kierunekWiatru", "skorygowany_kierunekWiatru", "korekta_kierunku")}
    buckets = lead_bucket(features.lead_hours)
    recent = features.obs_age_minutes.notna() & (features.obs_age_minutes <= cfg.max_recent_observation_age_minutes)
    for target, (raw_name, corrected_name, correction_name) in output_names.items():
        out[raw_name] = rows[target]
        out[corrected_name] = corrected[target]
        out[correction_name] = (angle_diff(corrected[target], rows[target]) if target == "direction" else corrected[target] - rows[target])
        chosen = [bundle["routes"][target].get(f"{farm}|{bucket}", "raw|0.0") for farm, bucket in zip(rows.farm, buckets)]
        statuses = []
        for i, choice in enumerate(chosen):
            names = [component.split("|")[0] for component in route_components(choice)]
            families = [bundle["models"][target][name] for name in names]
            if names == ["raw"]:
                status = "surowa_prognoza_wybor_walidacji_lub_malo_danych"
            elif all(name == "raw" or rows.farm.iloc[i] not in family.trained_farms for name, family in zip(names, families)):
                status = "surowa_prognoza_brak_treningu_farmy"
            elif not recent.iloc[i] and all(name not in ("farm_bias", "adaptive_3h", "adaptive_12h") for name in names):
                status = "surowa_prognoza_niedostepne_swieze_pomiary"
            else:
                status = "zespol_korekt" if choice.startswith("blend::") else "korekta"
            statuses.append(status)
        out[f"metoda_{target}"] = chosen
        out[f"status_{target}"] = statuses
    if not np.isfinite(out[[c[1] for c in output_names.values()]].to_numpy()).all():
        raise ValueError("Niepoprawne wartości w predykcji. Wynik nie został zapisany.")
    if out.duplicated(["lokalizacja", "dataGodzinaUTC"]).any() or len(out) != 96 * len(cfg.farms):
        raise ValueError("Niepoprawna liczba lub duplikaty kwadransów. Wynik nie został zapisany.")
    atomic_csv(output, out)
    log(f"Zapisano {len(out)} kwadransów ({len(cfg.farms)} farm): {output}")
    return out
