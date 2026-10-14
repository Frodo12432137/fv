from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .config import Settings
from .data import angle_diff
from .features import LEAD_BUCKETS, lead_bucket


TARGETS = ("speed", "temperature", "direction")


def label_mask(rows: pd.DataFrame, target: str, cfg: Settings):
    mask = rows[f"actual_{target}"].notna()
    if target == "direction":
        mask &= rows.actual_speed >= cfg.calm_speed
    return mask.to_numpy()


def labels(rows: pd.DataFrame, target: str):
    if target == "direction":
        angle = np.radians(rows.actual_direction)
        return np.column_stack([np.sin(angle) - rows.dir_sin, np.cos(angle) - rows.dir_cos])
    return (rows[f"actual_{target}"] - rows[target]).to_numpy()


def metrics(actual, prediction, angular=False) -> dict:
    actual, prediction = np.asarray(actual, float), np.asarray(prediction, float)
    mask = np.isfinite(actual) & np.isfinite(prediction)
    if not mask.any():
        return {"rows": 0, "mae": None, "rmse": None, "bias": None, "p95_absolute_error": None}
    error = angle_diff(prediction[mask], actual[mask]) if angular else prediction[mask] - actual[mask]
    return {"rows": int(mask.sum()), "mae": float(np.mean(np.abs(error))),
            "rmse": float(np.sqrt(np.mean(error ** 2))), "bias": float(np.mean(error)),
            "p95_absolute_error": float(np.quantile(np.abs(error), 0.95))}


def candidate_names(cfg: Settings) -> list[str]:
    names = ["farm_bias", "ridge_compact", "ridge", cfg.backend]
    names += [f"{cfg.backend}_{suffix}" for suffix in ("shallow", "absolute", "recent")[:cfg.tuning_trials - 1]]
    if cfg.enable_adaptive_bias:
        names += ["adaptive_3h", "adaptive_12h"]
    return names


def boost_profile(name: str, cfg: Settings) -> dict:
    profile = {"depth": 5, "learning_rate": 0.04, "regularization": 15.0,
               "min_child_weight": 10, "loss": "squared", "half_life": cfg.recency_half_life_days,
               "fit_days": cfg.history_days}
    if name.endswith("_shallow"):
        profile.update(depth=3, regularization=30.0, min_child_weight=25)
    elif name.endswith("_absolute"):
        profile.update(loss="absolute", learning_rate=0.035, regularization=10.0)
    elif name.endswith("_recent"):
        profile.update(fit_days=min(cfg.history_days, 90), half_life=45.0)
    return profile


@dataclass
class Family:
    name: str
    target: str
    transformer: object = None
    regressors: object = None
    offsets: dict = None
    global_offset: float = 0.0
    trained_farms: tuple = ()
    profile: dict = None

    def correction(self, features: pd.DataFrame, rows: pd.DataFrame) -> np.ndarray:
        if self.name == "farm_bias" or self.name.startswith("adaptive_"):
            buckets = lead_bucket(features.lead_hours)
            correction = np.array([self.offsets.get(f"{farm}|{bucket}", self.global_offset)
                                   for farm, bucket in zip(rows.farm, buckets)])
            if self.name.startswith("adaptive_"):
                tau = float(self.name.split("_")[1].removesuffix("h"))
                if self.target == "direction":
                    sine = 0.7 * features.bias_1h_error_sin + 0.3 * features.bias_6h_error_sin
                    cosine = 0.7 * features.bias_1h_error_cos + 0.3 * features.bias_6h_error_cos
                    recent = np.where(np.hypot(sine, cosine) >= 0.2, np.degrees(np.arctan2(sine, cosine)), np.nan)
                    delta = angle_diff(recent, correction)
                else:
                    col = f"error_{self.target}"
                    recent = (0.7 * features[f"bias_1h_{col}"] + 0.3 * features[f"bias_6h_{col}"]).to_numpy()
                    delta = recent - correction
                confidence = np.minimum(features.bias_1h_count.fillna(0).to_numpy() / 3.0, 1.0)
                fresh = features.bias_age_minutes.notna().to_numpy() & (features.bias_age_minutes.to_numpy() <= 120)
                influence = confidence * np.exp(-features.lead_hours.clip(lower=0).to_numpy() / tau)
                correction += np.where(fresh & np.isfinite(delta), delta * influence, 0.0)
            return correction
        if len(features) == 0:
            return np.empty((0, 2)) if self.target == "direction" else np.empty(0)
        chunks = []
        for start in range(0, len(features), 20000):
            transformed = self.transformer.transform(features.iloc[start:start + 20000])
            if not np.isfinite(transformed).all():
                raise ValueError(f"Nieskończone cechy po przetwarzaniu: {self.name}/{self.target}.")
            with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
                if isinstance(self.regressors, list):
                    chunks.append(np.column_stack([model.predict(transformed) for model in self.regressors]))
                else:
                    chunks.append(self.regressors.predict(transformed))
        correction = np.concatenate(chunks, axis=0)
        if not np.isfinite(correction).all():
            raise ValueError(f"Nieskończona korekta: {self.name}/{self.target}.")
        return correction

    def predict(self, features: pd.DataFrame, rows: pd.DataFrame, alpha=1.0, correction=None) -> np.ndarray:
        raw = rows[self.target].to_numpy(float)
        if self.name == "raw" or alpha == 0:
            return raw.copy()
        correction = self.correction(features, rows) if correction is None else correction
        if self.target == "direction":
            if correction.ndim == 2:
                sine = rows.dir_sin.to_numpy() + alpha * correction[:, 0]
                cosine = rows.dir_cos.to_numpy() + alpha * correction[:, 1]
                value = np.degrees(np.arctan2(sine, cosine)) % 360.0
                value = np.where(np.hypot(sine, cosine) < 1e-6, raw, value)
            else:
                value = raw + alpha * correction
        else:
            value = raw + alpha * correction
        if self.target == "direction":
            value %= 360.0
        elif self.target == "speed":
            value = np.maximum(value, 0.0)
        return value


def fit_family(name: str, target: str, features: pd.DataFrame, rows: pd.DataFrame, cfg: Settings) -> Family:
    mask = label_mask(rows, target, cfg)
    profile = boost_profile(name, cfg)
    if name.endswith("_recent"):
        mask &= (rows.available_at >= rows.available_at.max() - pd.Timedelta(days=profile["fit_days"])).to_numpy()
    selected = np.flatnonzero(mask)
    if len(selected) < cfg.min_training_rows:
        raise ValueError(f"Za mało poprawnych etykiet dla {target}: {len(selected)}.")
    family = Family(name, target, trained_farms=tuple(sorted(rows.loc[mask, "farm"].unique())), profile=profile)
    if name == "farm_bias" or name.startswith("adaptive_"):
        working = rows.loc[mask, ["farm", target, f"actual_{target}"]].copy()
        working["bucket"] = lead_bucket(features.loc[mask, "lead_hours"])
        working["delta"] = (angle_diff(working[f"actual_{target}"], working[target]) if target == "direction"
                            else working[f"actual_{target}"] - working[target])
        def center(values):
            if target == "direction":
                radians = np.radians(values)
                return float(np.degrees(np.arctan2(np.sin(radians).mean(), np.cos(radians).mean())))
            return float(np.median(values))
        family.global_offset = center(working.delta)
        family.offsets = {}
        for (farm, bucket), group in working.groupby(["farm", "bucket"]):
            local = center(group.delta)
            weight = len(group) / (len(group) + 100.0)
            delta = float(angle_diff(local, family.global_offset)) if target == "direction" else local - family.global_offset
            family.offsets[f"{farm}|{bucket}"] = family.global_offset + weight * delta
        return family
    if len(selected) > cfg.max_fit_rows:
        selected = np.sort(np.random.default_rng(cfg.random_state).choice(selected, cfg.max_fit_rows, replace=False))
    train_features, train_rows = features.iloc[selected], rows.iloc[selected]
    family.trained_farms = tuple(sorted(train_rows.farm.unique()))
    numeric_cols = features.columns.difference(["farm"]).tolist()
    if name == "ridge_compact":
        numeric_cols = [col for col in numeric_cols if not ("_std_" in col or col.startswith(("forecast_", "bias_decay_", "observed_")))]
    numeric_pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)),
        ("scale", StandardScaler()),
    ])
    family.transformer = ColumnTransformer([
        ("numeric", numeric_pipeline, numeric_cols),
        ("farm", OneHotEncoder(categories=[list(cfg.farms)], handle_unknown="ignore", sparse_output=False), ["farm"]),
    ])
    x = family.transformer.fit_transform(train_features).astype("float32")
    y = labels(train_rows, target)
    age_days = (rows.available_at.max() - train_rows.available_at).dt.total_seconds().to_numpy() / 86400.0
    weights = 0.5 ** (age_days / profile["half_life"])
    if name.startswith("ridge"):
        with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
            family.regressors = Ridge(alpha=100.0).fit(x, y, sample_weight=weights)
        if not np.isfinite(family.regressors.coef_).all():
            raise ValueError(f"Nieskończone współczynniki Ridge dla {target}.")
    else:
        def estimator():
            if cfg.backend == "hist":
                return HistGradientBoostingRegressor(max_iter=cfg.trees,
                    max_leaf_nodes=7 if profile["depth"] == 3 else 31,
                    loss="absolute_error" if profile["loss"] == "absolute" and target != "direction" else "squared_error",
                    learning_rate=profile["learning_rate"], l2_regularization=profile["regularization"], min_samples_leaf=30,
                    early_stopping=False, random_state=cfg.random_state)
            try:
                from xgboost import XGBRegressor
            except ImportError as exc:
                raise ImportError("Zainstaluj requirements-weather.txt albo ustaw backend=hist.") from exc
            return XGBRegressor(n_estimators=cfg.trees, max_depth=profile["depth"], learning_rate=profile["learning_rate"],
                reg_lambda=profile["regularization"], min_child_weight=profile["min_child_weight"], subsample=0.85, colsample_bytree=0.85,
                tree_method="hist", objective="reg:absoluteerror" if profile["loss"] == "absolute" and target != "direction" else "reg:squarederror", n_jobs=cfg.n_jobs,
                random_state=cfg.random_state)
        if y.ndim == 2:
            family.regressors = [estimator().fit(x, y[:, i], sample_weight=weights) for i in range(y.shape[1])]
        else:
            family.regressors = estimator().fit(x, y, sample_weight=weights)
    return family


def fit_candidates(features: pd.DataFrame, rows: pd.DataFrame, cfg: Settings, log=print, names: dict | None = None) -> dict:
    result = {}
    for target in TARGETS:
        result[target] = {"raw": Family("raw", target)}
        for name in (names[target] if names is not None else candidate_names(cfg)):
            if name == "raw":
                continue
            log(f"Uczenie: {target} / {name} ({len(rows):,} wierszy przed filtrem).")
            result[target][name] = fit_family(name, target, features, rows, cfg)
    return result


def candidate_predictions(families: dict, features: pd.DataFrame, rows: pd.DataFrame, cfg: Settings) -> dict:
    result = {}
    recent = features.obs_age_minutes.notna() & (features.obs_age_minutes <= cfg.max_recent_observation_age_minutes)
    for target in TARGETS:
        result[target] = {}
        for name, family in families[target].items():
            correction = None if name == "raw" else family.correction(features, rows)
            for alpha in ([0.0] if name == "raw" else [0.25, 0.5, 0.75, 1.0]):
                value = family.predict(features, rows, alpha, correction=correction)
                if name != "raw":
                    known = rows.farm.isin(family.trained_farms).to_numpy()
                    if name not in ("farm_bias", "adaptive_3h", "adaptive_12h"):
                        known &= recent.to_numpy()
                    value = np.where(known, value, rows[target])
                result[target][f"{name}|{alpha}"] = value
    return result


def tune_families(families: dict, predictions: dict, rows: pd.DataFrame, cfg: Settings) -> tuple[dict, list]:
    retained, report = {}, []
    for target in TARGETS:
        mask = label_mask(rows, target, cfg)
        ranking = []
        for name in families[target]:
            if name in ("raw", "farm_bias", "ridge", "ridge_compact", "adaptive_3h", "adaptive_12h"):
                continue
            scores = [metrics(rows.loc[mask, f"actual_{target}"], values[mask], target == "direction")["mae"]
                      for key, values in predictions[target].items() if key.startswith(name + "|")]
            score = min((s for s in scores if s is not None), default=float("inf"))
            ranking.append((score, name))
        best = {name for score, name in sorted(ranking)[:2] if np.isfinite(score)}
        retained[target] = {name: family for name, family in families[target].items()
                            if name in best or name in ("raw", "farm_bias", "ridge", "ridge_compact", "adaptive_3h", "adaptive_12h")}
        for score, name in ranking:
            report.append({"target": target, "candidate": name, "mae": score if np.isfinite(score) else None,
                           "retained": name in best, "profile": families[target][name].profile})
    return retained, report


def blend_prediction(a, b, weight, angular=False, fallback=None):
    if not angular:
        return weight * a + (1 - weight) * b
    sine = weight * np.sin(np.radians(a)) + (1 - weight) * np.sin(np.radians(b))
    cosine = weight * np.cos(np.radians(a)) + (1 - weight) * np.cos(np.radians(b))
    value = np.degrees(np.arctan2(sine, cosine)) % 360
    value = np.where(value >= 360.0, 0.0, value)
    return np.where(np.hypot(sine, cosine) >= 1e-6, value, a if fallback is None else fallback)


def route_components(key: str) -> list[str]:
    return key.split("::")[2:] if key.startswith("blend::") else [key]


def evaluate_route(key: str, predictions: dict, target: str):
    if not key.startswith("blend::"):
        return predictions[key]
    _, weight, a, b = key.split("::")
    return blend_prediction(predictions[a], predictions[b], float(weight), target == "direction", predictions["raw|0.0"])


def required_families(routes: dict) -> dict:
    return {target: sorted({component.split("|")[0] for key in cells.values() for component in route_components(key)} | {"raw"})
            for target, cells in routes.items()}


def route_quality(actual, prediction, raw, days, cfg: Settings, angular=False) -> dict:
    error = np.abs(angle_diff(prediction, actual) if angular else prediction - actual)
    base_error = np.abs(angle_diff(raw, actual) if angular else raw - actual)
    unique, inverse = np.unique(days, return_inverse=True)
    counts = np.bincount(inverse)
    improvement = np.bincount(inverse, weights=base_error - error)
    daily = improvement / counts
    n = len(unique)
    if n < cfg.min_route_days:
        return {"accepted": False, "days": n, "lower_gain": None, "day_win_rate": None}
    length = min(2, n)
    rng = np.random.default_rng(cfg.random_state)
    starts = rng.integers(0, n - length + 1, size=(cfg.route_bootstrap_samples, int(np.ceil(n / length))))
    indices = (starts[..., None] + np.arange(length)).reshape(cfg.route_bootstrap_samples, -1)[:, :n]
    gains = improvement[indices].sum(axis=1) / counts[indices].sum(axis=1)
    lower = float(np.quantile(gains, 1 - cfg.route_confidence_level))
    wins = float(np.mean(daily > 0))
    recent = inverse >= n - max(1, int(np.ceil(n / 3)))
    base = metrics(actual, raw, angular)
    new = metrics(actual, prediction, angular)
    accepted = (new["mae"] <= base["mae"] * (1 - cfg.min_improvement) and lower > 0 and
        wins >= cfg.min_route_day_win_rate and
        new["rmse"] <= base["rmse"] * (1 + cfg.max_route_rmse_increase) + 1e-9 and
        new["p95_absolute_error"] <= base["p95_absolute_error"] * (1 + cfg.max_route_p95_increase) + 1e-9 and
        error[recent].mean() <= base_error[recent].mean() * (1 + cfg.max_route_rmse_increase) + 1e-9)
    return {"accepted": bool(accepted), "days": n, "lower_gain": lower, "day_win_rate": wins}


def choose_routes(predictions: dict, features: pd.DataFrame, rows: pd.DataFrame, cfg: Settings) -> tuple[dict, list]:
    routes, scores = {}, []
    buckets = lead_bucket(features.lead_hours)
    for target in TARGETS:
        mask = label_mask(rows, target, cfg)
        actual = rows[f"actual_{target}"].to_numpy(float)
        def best(subset, cell):
            base = metrics(actual[subset], predictions[target]["raw|0.0"][subset], target == "direction")
            winner, best_mae = "raw|0.0", base["mae"]
            if best_mae is None:
                return winner
            pool = dict(predictions[target])
            single_scores = {candidate: metrics(actual[subset], values[subset], target == "direction")
                             for candidate, values in pool.items()}
            valid_singles = [(score["mae"], candidate) for candidate, score in single_scores.items() if score["rows"] == base["rows"]]
            best_single = min(valid_singles)[1]
            if cfg.enable_ensembles:
                by_family = {}
                for candidate, values in pool.items():
                    score = metrics(actual[subset], values[subset], target == "direction")
                    name = candidate.split("|")[0]
                    if score["rows"] == base["rows"] and (name not in by_family or score["mae"] < by_family[name][0]):
                        by_family[name] = (score["mae"], candidate)
                top = [candidate for _, candidate in sorted(by_family.values())[:3]]
                for a, b in combinations(top, 2):
                    for weight in (0.25, 0.5, 0.75):
                        key = f"blend::{weight}::{a}::{b}"
                        pool[key] = blend_prediction(pool[a], pool[b], weight, target == "direction", pool["raw|0.0"])
            days = rows.loc[subset, "available_at"].dt.floor("D").array.asi8
            for candidate, values in pool.items():
                score = metrics(actual[subset], values[subset], target == "direction")
                if score["rows"] != base["rows"]:
                    quality = {"accepted": False, "days": len(np.unique(days)), "lower_gain": None, "day_win_rate": None}
                elif candidate == "raw|0.0":
                    quality = {"accepted": True, "days": len(np.unique(days)), "lower_gain": 0.0, "day_win_rate": None}
                else:
                    quality = route_quality(actual[subset], values[subset], pool["raw|0.0"][subset], days, cfg, target == "direction")
                    if candidate.startswith("blend::") and quality["accepted"]:
                        versus_single = route_quality(actual[subset], values[subset], pool[best_single][subset], days, cfg, target == "direction")
                        quality["accepted"] &= versus_single["accepted"]
                        quality["lower_gain_vs_best_single"] = versus_single["lower_gain"]
                scores.append({"target": target, "cell": cell, "candidate": candidate, **score, **quality})
                if quality["accepted"] and score["mae"] is not None and score["mae"] < best_mae - 1e-9:
                    winner, best_mae = candidate, score["mae"]
            return winner
        # Brak wystarczającej walidacji danej farmy/horyzontu -> surowa prognoza.
        routes[target] = {}
        for farm in cfg.farms:
            for bucket in LEAD_BUCKETS:
                subset = mask & (rows.farm.to_numpy() == farm) & (buckets == bucket)
                cell = f"{farm}|{bucket}"
                enough = (subset.sum() >= cfg.min_route_rows and rows.loc[subset, "available_at"].nunique() >= cfg.min_route_issues and
                          rows.loc[subset, "available_at"].dt.floor("D").nunique() >= cfg.min_route_days)
                routes[target][cell] = best(subset, cell) if enough else "raw|0.0"
    return routes, scores


def route_predictions(predictions: dict, routes: dict, features: pd.DataFrame, rows: pd.DataFrame) -> dict:
    buckets = lead_bucket(features.lead_hours)
    result = {}
    for target in TARGETS:
        keys = np.array([routes[target].get(f"{farm}|{bucket}", "raw|0.0") for farm, bucket in zip(rows.farm, buckets)])
        value = rows[target].to_numpy(float).copy()
        for key in np.unique(keys):
            mask = keys == key
            value[mask] = evaluate_route(key, predictions[target], target)[mask]
        result[target] = value
    return result


def metric_report(rows: pd.DataFrame, corrected: dict, cfg: Settings) -> list:
    result = []
    buckets = lead_bucket((rows.valid_at - rows.available_at).dt.total_seconds() / 3600)
    for target in TARGETS:
        valid = label_mask(rows, target, cfg)
        cells = [("ALL", "ALL", valid)]
        cells += [(farm, bucket, valid & (rows.farm.to_numpy() == farm) & (buckets == bucket))
                  for farm in cfg.farms for bucket in LEAD_BUCKETS]
        for farm, bucket, mask in cells:
            raw = metrics(rows.loc[mask, f"actual_{target}"], rows.loc[mask, target], target == "direction")
            new = metrics(rows.loc[mask, f"actual_{target}"], corrected[target][mask], target == "direction")
            improvement = 100 * (1 - new["mae"] / raw["mae"]) if raw["mae"] else None
            result.append({"target": target, "farm": farm, "horizon": bucket, "rows": raw["rows"],
                "raw_mae": raw["mae"], "corrected_mae": new["mae"], "raw_rmse": raw["rmse"],
                "corrected_rmse": new["rmse"], "raw_bias": raw["bias"], "corrected_bias": new["bias"],
                "raw_p95_absolute_error": raw["p95_absolute_error"], "corrected_p95_absolute_error": new["p95_absolute_error"],
                "mae_improvement_pct": improvement})
    return result
