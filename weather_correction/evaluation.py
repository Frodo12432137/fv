"""Statystyki prognozy i korekty liczone na identycznych dostępnych pomiarach."""
from __future__ import annotations

from html import escape

import numpy as np
import pandas as pd

from .config import ALIASES, Settings, name_key
from .data import angle_diff, observation_targets, prepare_observations
from .features import LEAD_BUCKETS, lead_bucket
from .models import TARGETS, metrics


TARGET_NAMES = {"speed": "Prędkość wiatru", "temperature": "Temperatura", "direction": "Kierunek wiatru"}
UNITS = {"speed": "m/s", "temperature": "°C", "direction": "°"}
TOLERANCES = {"speed": 1.0, "temperature": 1.0, "direction": 15.0}
DATA_NAMES = {"synthetic": "DANE SYNTETYCZNE — nie jest to ocena farm PGE",
              "measured": "Dane pomiarowe", "unspecified": "Rodzaj danych nie został określony"}


def test_samples(rows, corrected, fold, forecast_grid=None):
    result = rows[["farm", "issued_at", "valid_at"]].copy()
    result["forecast_at"] = rows.available_at
    result["lead_hours"] = (rows.valid_at - rows.available_at).dt.total_seconds() / 3600
    result["fold"] = str(fold)
    for target in TARGETS:
        result[f"actual_{target}"] = rows[f"actual_{target}"].to_numpy()
        result[f"raw_{target}"] = rows[target].to_numpy()
        result[f"corrected_{target}"] = corrected[target]
    if forecast_grid is not None:
        # Zachowujemy również kwadranse bez dopasowanego wykonania. Nie mogą poprawiać błędu
        # przez zniknięcie z mianownika pokrycia pomiarów.
        key = ["farm", "issued_at", "valid_at"]
        grid = forecast_grid[key + ["available_at", *TARGETS]].rename(
            columns={"available_at": "forecast_at", **{t: f"raw_{t}" for t in TARGETS}}).copy()
        grid["lead_hours"] = (grid.valid_at - grid.forecast_at).dt.total_seconds() / 3600
        grid["fold"] = str(fold)
        columns = [f"{prefix}_{t}" for t in TARGETS for prefix in ("actual", "corrected")]
        result = grid.merge(result[key + columns], on=key, how="left", validate="one_to_one")
    return result.reset_index(drop=True)


def snapshot_samples(output, observations, as_of, cfg):
    names = {"lokalizacja": "farm", "dataGodzinaUTC": "valid_at", "czasPredykcjiUTC": "forecast_at",
             "czasDostepnosciUTC": "available_at", "modelVersion": "model_version",
             "predkoscWiatru": "raw_speed", "skorygowana_predkoscWiatru": "corrected_speed",
             "temperatura": "raw_temperature", "skorygowana_temperatura": "corrected_temperature",
             "kierunekWiatru": "raw_direction", "skorygowany_kierunekWiatru": "corrected_direction"}
    missing = set(names) - set(output)
    if missing:
        raise ValueError(f"Brak kolumn zapisanej predykcji: {sorted(missing)}.")
    rows = output[list(names)].rename(columns=names).copy()
    if rows.empty:
        raise ValueError("Plik predykcji jest pusty.")
    if rows.model_version.isna().any() or rows.model_version.nunique() != 1:
        raise ValueError("Oceniaj jedną wersję modelu na raz; pliki mają różne modelVersion.")
    rows["farm"] = rows.farm.map(lambda value: ALIASES.get(name_key(value)))
    if rows.farm.isna().any() or set(rows.farm) - set(cfg.farms):
        raise ValueError("Nieznana farma albo konfiguracja nie odpowiada zapisanej predykcji.")
    for col in ("valid_at", "forecast_at", "available_at"):
        rows[col] = pd.to_datetime(rows[col], utc=True, errors="coerce")
        if rows[col].isna().any():
            raise ValueError(f"Niepoprawny czas predykcji: {col}.")
    if ((rows.available_at > rows.forecast_at) | (rows.valid_at <= rows.forecast_at) |
        (rows.forecast_at > as_of)).any():
        raise ValueError("Niespójne czasy: paczka musi być znana przed predykcją, a prognoza dotyczyć przyszłości.")
    for target in TARGETS:
        for prefix in ("raw", "corrected"):
            col = f"{prefix}_{target}"
            rows[col] = pd.to_numeric(rows[col], errors="coerce")
            if not np.isfinite(rows[col]).all():
                raise ValueError(f"Niepoprawne wartości prognozy: {col}.")
            if target == "speed" and rows[col].lt(0).any():
                raise ValueError("Prędkość prognozy nie może być ujemna.")
            if target == "direction" and not rows[col].between(0, 360, inclusive="left").all():
                raise ValueError("Kierunek prognozy musi należeć do [0, 360).")
    before = len(rows)
    rows = rows.drop_duplicates()
    key = ["farm", "forecast_at", "valid_at"]
    if rows.duplicated(key).any():
        raise ValueError("Sprzeczne predykcje dla tej samej farmy, chwili predykcji i kwadransa.")
    obs = prepare_observations(observations, cfg)
    obs = obs.loc[obs.available_at <= as_of]
    targets = observation_targets(obs, cfg)
    targets = targets.loc[targets.label_available_at <= as_of]
    targets = targets[["farm", "valid_at", *TARGETS]].rename(columns={t: f"actual_{t}" for t in TARGETS})
    rows = rows.merge(targets, on=["farm", "valid_at"], how="left", validate="many_to_one")
    rows["lead_hours"] = (rows.valid_at - rows.available_at).dt.total_seconds() / 3600
    rows["fold"] = "saved_forecasts"
    return rows, {"model_version": str(rows.model_version.iloc[0]), "duplicates_removed": before - len(rows),
                  "evaluation_as_of": as_of.isoformat()}


def detailed_metrics(actual, predicted, angular):
    measured = metrics(actual, predicted, angular)
    extras = {"median_absolute_error": None, "p90_absolute_error": None,
              "p99_absolute_error": None, "max_absolute_error": None, "r2": None}
    if len(actual):
        error = angle_diff(predicted, actual) if angular else predicted - actual
        absolute = np.abs(error)
        extras.update(median_absolute_error=float(np.median(absolute)),
                      p90_absolute_error=float(np.quantile(absolute, .9)),
                      p99_absolute_error=float(np.quantile(absolute, .99)),
                      max_absolute_error=float(absolute.max()))
        variance = float(np.sum((actual - np.mean(actual)) ** 2))
        if not angular and variance > 1e-12:
            extras["r2"] = float(1 - np.sum(error ** 2) / variance)
    return {**measured, **extras}


def daily_gain(raw_error, corrected_error, days, bootstrap=True):
    unique, inverse = np.unique(days, return_inverse=True)
    n = len(unique)
    result = {"days": n, "day_win_rate_pct": None, "mae_gain_ci_low": None, "mae_gain_ci_high": None}
    if not n:
        return result
    counts = np.bincount(inverse)
    gains = np.bincount(inverse, weights=raw_error - corrected_error)
    result["day_win_rate_pct"] = float(100 * np.mean(gains > 1e-9))
    if bootstrap and n >= 7:
        # Sparowane dwudniowe bloki zachowują zależności między horyzontami/paczkami tego samego dnia.
        starts = np.random.default_rng(42).integers(0, n - 1, size=(500, int(np.ceil(n / 2))))
        indices = (starts[..., None] + np.arange(2)).reshape(500, -1)[:, :n]
        draws = gains[indices].sum(axis=1) / counts[indices].sum(axis=1)
        low, high = np.quantile(draws, [.025, .975])
        result.update(mae_gain_ci_low=float(low), mae_gain_ci_high=float(high))
    return result


def comparison_metrics(rows, target, cfg, bootstrap=True):
    actual = rows[f"actual_{target}"].to_numpy(float)
    raw = rows[f"raw_{target}"].to_numpy(float)
    corrected = rows[f"corrected_{target}"].to_numpy(float)
    speed = rows.actual_speed.to_numpy(float)
    calm = (speed < cfg.calm_speed) if target == "direction" else np.zeros(len(rows), bool)
    missing_measurement = ~np.isfinite(actual)
    if target == "direction":
        missing_measurement |= ~np.isfinite(speed)
    valid = ~missing_measurement & np.isfinite(raw) & np.isfinite(corrected) & ~calm
    angular = target == "direction"
    a, r, c = actual[valid], raw[valid], corrected[valid]
    base, new = detailed_metrics(a, r, angular), detailed_metrics(a, c, angular)
    result = {"target": target, "unit": UNITS[target], "forecast_rows": len(rows), "rows": int(valid.sum()),
              "scored_fraction_pct": float(100 * valid.mean()) if len(rows) else None,
              "missing_measurement_rows": int((missing_measurement & ~calm).sum()),
              "invalid_prediction_rows": int((~missing_measurement & ~calm & (~np.isfinite(raw) | ~np.isfinite(corrected))).sum()),
              "excluded_calm_rows": int(calm.sum()), "tolerance": TOLERANCES[target]}
    for prefix, measured in (("raw", base), ("corrected", new)):
        result.update({f"{prefix}_{name}": value for name, value in measured.items() if name != "rows"})
    for metric in ("mae", "rmse"):
        result[f"{metric}_improvement_pct"] = (100 * (1 - new[metric] / base[metric]) if base[metric] else None)
    result["mae_gain"] = base["mae"] - new["mae"] if base["mae"] is not None else None
    raw_error = np.abs(angle_diff(r, a) if angular else r - a)
    error = np.abs(angle_diff(c, a) if angular else c - a)
    for name, mask in (("improved_rows_pct", error < raw_error - 1e-9),
                       ("worsened_rows_pct", error > raw_error + 1e-9),
                       ("tied_rows_pct", np.abs(error - raw_error) <= 1e-9),
                       ("raw_within_tolerance_pct", raw_error <= TOLERANCES[target]),
                       ("corrected_within_tolerance_pct", error <= TOLERANCES[target])):
        result[name] = float(100 * mask.mean()) if len(a) else None
    days = rows.loc[valid, "forecast_at"].dt.floor("D").array.asi8
    return {**result, **daily_gain(raw_error, error, days, bootstrap)}


def build_assessment(samples, cfg: Settings, metadata=None):
    metadata = dict(metadata or {})
    data_kind = metadata.get("data_kind", "unspecified")
    if data_kind not in DATA_NAMES:
        raise ValueError("data_kind: unspecified, measured albo synthetic.")
    samples = samples.copy()
    samples["horizon"] = lead_bucket(samples.lead_hours)
    samples["day"] = samples.forecast_at.dt.strftime("%Y-%m-%d")
    metrics_rows, daily_rows = [], []
    scopes = [("pooled", samples)]
    scopes += [(str(fold), group) for fold, group in samples.groupby("fold", sort=False)]
    for fold, group in scopes:
        cells = [("ALL", "ALL", group)]
        cells += [(farm, "ALL", group.loc[group.farm == farm]) for farm in cfg.farms]
        cells += [("ALL", horizon, group.loc[group.horizon == horizon]) for horizon in LEAD_BUCKETS]
        cells += [(farm, horizon, group.loc[(group.farm == farm) & (group.horizon == horizon)])
                  for farm in cfg.farms for horizon in LEAD_BUCKETS]
        for farm, horizon, cell in cells:
            for target in TARGETS:
                record = comparison_metrics(cell, target, cfg)
                metrics_rows.append({"fold": fold, "farm": farm, "horizon": horizon, **record})
        if fold == "pooled":
            for day, cell in group.groupby("day", sort=True):
                for target in TARGETS:
                    daily_rows.append({"day": day, "farm": "ALL", **comparison_metrics(cell, target, cfg, False)})
    return {"schema_version": 1, "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
            "metadata": {**metadata, "data_kind": data_kind,
                "forecast_rows": len(samples), "forecast_start": samples.forecast_at.min().isoformat(),
                "forecast_end": samples.forecast_at.max().isoformat(),
                "valid_start": samples.valid_at.min().isoformat(), "valid_end": samples.valid_at.max().isoformat(),
                "configured_farms": list(cfg.farms), "observed_prediction_farms": sorted(samples.farm.unique().tolist())},
            "method": {"comparison": "Te same poprawne etykiety dla prognozy surowej i skorygowanej.",
                "direction": f"Najkrótszy błąd na okręgu, od -180 do 180°. Pomijamy wiatr poniżej {cfg.calm_speed} m/s.",
                "bias": "Prognoza minus pomiar; dodatni bias oznacza zawyżanie (dla kierunku przesunięcie kątowe).",
                "confidence_interval": "95% przedział z 500 losowań dwudniowych bloków dni UTC wydania/predykcji; minimum 7 dni. Diagnostyczny, bez korekty na wiele porównań.",
                "counts": "Wiersz oznacza jedną ocenioną prognozę. Różne paczki mogą dotyczyć tego samego pomiaru; wiersze nie są niezależnymi pomiarami.",
                "pooled": "Statystyki łączne liczymy z błędów wszystkich testów, bez uśredniania percentyli lub R².",
                "r2": "Tylko prędkość i temperatura; brak przy stałych pomiarach. Dla kierunku nie stosujemy zwykłego R².",
                "tolerances": "Progi opisowe: 1 m/s, 1°C, 15°. Nie stanowią zatwierdzonych kryteriów biznesowych."},
            "metrics": metrics_rows, "daily_metrics": daily_rows}


def number(value):
    return "—" if value is None else f"{value:.3f}"


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"] +
                     ["| " + " | ".join(str(v).replace("|", "\\|").replace("\n", " ") for v in row) + " |" for row in rows])


def report_sections(assessment):
    records = assessment["metrics"]
    pooled = [r for r in records if r["fold"] == "pooled"]
    def results(records):
        return [[r["farm"], r["horizon"], TARGET_NAMES[r["target"]], r["unit"], r["rows"],
                 number(r["raw_mae"]), number(r["corrected_mae"]), number(r["mae_improvement_pct"]),
                 number(r["corrected_rmse"]), number(r["corrected_bias"]), number(r["corrected_p95_absolute_error"])]
                for r in records if r["forecast_rows"]]
    columns = ["Farma", "Horyzont", "Parametr", "Jednostka", "N", "MAE surowe", "MAE korekty", "Poprawa %",
               "RMSE korekty", "Bias korekty", "P95 korekty"]
    overall = [r for r in pooled if r["farm"] == "ALL" and r["horizon"] == "ALL"]
    sections = [("Wynik łączny", columns, results(overall))]
    sections.append(("Pokrycie, stabilność i duże błędy", ["Parametr", "Pokrycie %", "Brak pomiaru", "Cisza wiatru",
        "Lepsze wiersze %", "Lepsze dni %", "P99 korekty", "Max korekty", "95% CI poprawy MAE"],
        [[TARGET_NAMES[r["target"]], number(r["scored_fraction_pct"]), r["missing_measurement_rows"], r["excluded_calm_rows"],
          number(r["improved_rows_pct"]), number(r["day_win_rate_pct"]), number(r["corrected_p99_absolute_error"]),
          number(r["corrected_max_absolute_error"]), f"{number(r['mae_gain_ci_low'])} … {number(r['mae_gain_ci_high'])} {r['unit']}"] for r in overall]))
    sections.append(("Według farmy", columns, results([r for r in pooled if r["farm"] != "ALL" and r["horizon"] == "ALL"])))
    sections.append(("Według wyprzedzenia prognozy", columns, results([r for r in pooled if r["farm"] == "ALL" and r["horizon"] != "ALL"])))
    sections.append(("Farma i wyprzedzenie", columns, results([r for r in pooled if r["farm"] != "ALL" and r["horizon"] != "ALL"])))
    for fold in dict.fromkeys(r["fold"] for r in records if r["fold"] != "pooled"):
        sections.append((f"Test / zbiór: {fold}", columns,
                         results([r for r in records if r["fold"] == fold and r["farm"] == "ALL" and r["horizon"] == "ALL"])))
    sections.append(("Dzienna ocena", ["Dzień UTC", "Parametr", "N", "MAE surowe", "MAE korekty", "Poprawa %"],
        [[r["day"], TARGET_NAMES[r["target"]], r["rows"], number(r["raw_mae"]), number(r["corrected_mae"]),
          number(r["mae_improvement_pct"])] for r in assessment["daily_metrics"]]))
    return sections


def report_intro(assessment):
    meta = assessment["metadata"]
    lines = [DATA_NAMES[meta["data_kind"]], str(meta.get("assessment_type", "Ocena prognoz")),
            f"Wersja: {meta.get('model_version', 'niepodana')}",
            f"Prognozy od {meta['forecast_start']} do {meta['forecast_end']}. Wiersze prognoz: {meta['forecast_rows']}.",
            "Dodatnia poprawa oznacza mniejszy błąd korekty. Wartości — oznaczają brak danych lub niezdefiniowaną miarę."]
    if "published" in meta:
        lines.append("Bramka publikacji: " + ("zaliczona." if meta["published"] else "kandydat odrzucony."))
    if meta.get("note"):
        lines.append(str(meta["note"]))
    if not any(r["rows"] for r in assessment["metrics"]):
        lines.append("Brak dostępnych poprawnych pomiarów do oceny. Nie można jeszcze stwierdzić skuteczności korekty.")
    return lines


def render_markdown(assessment):
    parts = ["# Statystyki oceny modelu", *report_intro(assessment)]
    for title, headers, rows in report_sections(assessment):
        parts += [f"## {title}", table(headers, rows)]
    parts += ["## Interpretacja", *assessment["method"].values(),
              "Pełne statystyki (w tym R², mediany, percentyle i błędy surowe) są w model_statistics.csv i model_statistics.json."]
    return "\n\n".join(parts) + "\n"


def render_html(assessment):
    parts = ['<!doctype html><html lang="pl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
             '<title>Statystyki oceny modelu</title><style>body{font:15px system-ui,sans-serif;color:#172b40;background:#f5f7fa;margin:0;padding:24px}main{max-width:1440px;margin:auto}h1{font-size:28px}h2{font-size:19px}section{background:white;border:1px solid #dae2ec;border-radius:10px;padding:16px;margin:16px 0}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;white-space:nowrap;font-size:13px}th,td{text-align:right;padding:9px;border-bottom:1px solid #e3e8ee}th{background:#edf2f8}td:first-child,th:first-child{text-align:left}.kind{font-weight:700;color:#9c4a08}p{line-height:1.6}summary{cursor:pointer;font-weight:650}footer{line-height:1.6}@media(max-width:600px){body{padding:10px}}</style><main><h1>Statystyki oceny modelu</h1>']
    for i, line in enumerate(report_intro(assessment)):
        parts.append(f'<p class="{"kind" if i == 0 else ""}">{escape(line)}</p>')
    for i, (title, headers, rows) in enumerate(report_sections(assessment)):
        detail = i >= 4
        parts.append('<section>' + (f'<details><summary>{escape(title)}</summary>' if detail else f'<h2>{escape(title)}</h2>'))
        parts.append('<div class="scroll"><table><thead><tr>' + ''.join(f'<th>{escape(h)}</th>' for h in headers) + '</tr></thead><tbody>')
        for row in rows:
            parts.append('<tr>' + ''.join(f'<td>{escape(str(v))}</td>' for v in row) + '</tr>')
        parts.append('</tbody></table></div>' + ('</details>' if detail else '') + '</section>')
    parts.append('<footer><h2>Interpretacja</h2>' + ''.join(f'<p>{escape(v)}</p>' for v in assessment["method"].values()) + '</footer></main></html>')
    return '\n'.join(parts)
