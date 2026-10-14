from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Settings
from .data import KEY, angle_diff


LEAD_BUCKETS = ("0-3h", "3-6h", "6-12h", "12-24h", "24-36h")


def lead_bucket(hours):
    return np.select([hours <= 3, hours <= 6, hours <= 12, hours <= 24], list(LEAD_BUCKETS[:-1]), default=LEAD_BUCKETS[-1])


def residual_history(forecasts: pd.DataFrame, targets: pd.DataFrame, cfg: Settings) -> pd.DataFrame:
    eligible = forecasts.loc[(forecasts.available_at < forecasts.valid_at) &
                             ((forecasts.valid_at - forecasts.available_at) <= pd.Timedelta(hours=24))]
    verified = eligible.merge(targets[KEY + ["speed", "temperature", "direction", "label_available_at"]],
                              on=KEY, suffixes=("", "_actual"), validate="many_to_one")
    verified = verified.sort_values("available_at").drop_duplicates(KEY, keep="last")
    verified["error_speed"] = verified.speed_actual - verified.speed
    verified["error_temperature"] = verified.temperature_actual - verified.temperature
    delta = np.radians(angle_diff(verified.direction_actual, verified.direction))
    valid_direction = verified.speed_actual >= cfg.calm_speed
    verified["error_sin"] = np.where(valid_direction, np.sin(delta), np.nan)
    verified["error_cos"] = np.where(valid_direction, np.cos(delta), np.nan)
    verified["available_at"] = verified.label_available_at
    verified["observed_at"] = verified.valid_at
    columns = ["farm", "available_at", "error_speed", "error_temperature", "error_sin", "error_cos"]
    if cfg.feature_version >= 2:
        columns += ["observed_at"]
    return verified[columns]


def history_features(query: pd.DataFrame, history: pd.DataFrame, columns: list[str], prefix: str,
                     observation_windows=True, include_std=True) -> pd.DataFrame:
    """Zapytania as-of i średnie czasowe; żadnych przesunięć względem przyszłego targetu."""
    result = pd.DataFrame(index=query.index)
    names = [f"{prefix}_age_minutes"] + [f"{prefix}_last_{c}" for c in columns]
    names += [f"{prefix}_{hours}h_{c}" for hours in (1, 6, 24) for c in columns]
    if include_std:
        names += [f"{prefix}_{hours}h_std_{c}" for hours in (1, 6, 24) for c in columns]
    names += [f"{prefix}_{hours}h_count" for hours in (1, 6, 24)]
    for name in names:
        result[name] = np.nan
    for farm, rows in query.groupby("farm", sort=False):
        hist = history.loc[history.farm == farm].sort_values("available_at")
        if hist.empty:
            continue
        stamps = hist.available_at.array.asi8
        queries = rows.available_at.array.asi8
        stop = np.searchsorted(stamps, queries, side="right")
        last = np.maximum(stop - 1, 0)
        age_stamps = stamps
        if "observed_at" in hist:
            age_stamps = hist.observed_at.array.asi8
            previous_max = np.r_[np.iinfo(np.int64).min, np.maximum.accumulate(age_stamps)[:-1]]
            latest_observed = np.maximum.accumulate(np.where(age_stamps >= previous_max, np.arange(len(hist)), -1))
            last = latest_observed[last]
        present = stop > 0
        age = (queries - age_stamps[last]) / 60e9
        result.loc[rows.index, f"{prefix}_age_minutes"] = np.where(present, age, np.nan)
        values = hist[columns].to_numpy(dtype=float)
        latest = values[last].copy()
        latest[~present] = np.nan
        for i, col in enumerate(columns):
            result.loc[rows.index, f"{prefix}_last_{col}"] = latest[:, i]
        finite = np.isfinite(values)
        sums = np.vstack([np.zeros(len(columns)), np.cumsum(np.where(finite, values, 0.0), axis=0)])
        squares = np.vstack([np.zeros(len(columns)), np.cumsum(np.where(finite, values ** 2, 0.0), axis=0)])
        counts = np.vstack([np.zeros(len(columns)), np.cumsum(finite, axis=0)])
        for hours in (1, 6, 24):
            window_stamps = age_stamps if observation_windows else stamps
            if np.all(np.diff(window_stamps) >= 0):
                start = np.minimum(np.searchsorted(window_stamps, queries - hours * 3600e9, side="right"), stop)
                denominator = counts[stop] - counts[start]
                mean = np.divide(sums[stop] - sums[start], denominator,
                                 out=np.full((len(rows), len(columns)), np.nan), where=denominator > 0)
                second = np.divide(squares[stop] - squares[start], denominator,
                                   out=np.full_like(mean, np.nan), where=denominator > 0)
                std = np.sqrt(np.maximum(second - mean ** 2, 0))
                window_counts = stop - start
            else:
                # Opóźnione odczyty poza kolejnością: okno czasu pomiaru + warunek dostępności.
                unique, inverse = np.unique(queries, return_inverse=True)
                order = np.argsort(window_stamps)
                observation_times = window_stamps[order]
                means = np.full((len(unique), len(columns)), np.nan)
                deviations = means.copy()
                nrows = np.zeros(len(unique))
                for i, moment in enumerate(unique):
                    lower = np.searchsorted(observation_times, moment - hours * 3600e9, side="right")
                    upper = np.searchsorted(observation_times, moment, side="right")
                    chosen = order[lower:upper]
                    chosen = chosen[stamps[chosen] <= moment]
                    nrows[i] = len(chosen)
                    if len(chosen):
                        valid = finite[chosen]
                        denominator = valid.sum(axis=0)
                        summed = np.where(valid, values[chosen], 0).sum(axis=0)
                        means[i] = np.divide(summed, denominator, out=np.full(len(columns), np.nan), where=denominator > 0)
                        squared = np.where(valid, values[chosen] ** 2, 0).sum(axis=0)
                        second = np.divide(squared, denominator, out=np.full(len(columns), np.nan), where=denominator > 0)
                        deviations[i] = np.sqrt(np.maximum(second - means[i] ** 2, 0))
                mean, std, window_counts = means[inverse], deviations[inverse], nrows[inverse]
            for i, col in enumerate(columns):
                result.loc[rows.index, f"{prefix}_{hours}h_{col}"] = mean[:, i]
                if include_std:
                    result.loc[rows.index, f"{prefix}_{hours}h_std_{col}"] = std[:, i]
            result.loc[rows.index, f"{prefix}_{hours}h_count"] = window_counts
    return result.astype("float32")


def trajectory_features(query: pd.DataFrame, context: pd.DataFrame) -> pd.DataFrame:
    keys = ["farm", "issued_at", "valid_at"]
    lookup = context.set_index(keys)[["speed", "temperature", "direction", "available_at"]]
    if not lookup.index.is_unique:
        raise ValueError("Kontekst trajektorii zawiera duplikaty wydania/czasu.")
    result = pd.DataFrame(index=query.index)
    for hours in (-3, -1, 1, 3):
        times = query.valid_at + pd.Timedelta(hours=hours)
        index = pd.MultiIndex.from_arrays([query.farm, query.issued_at, times], names=keys)
        neighbors = lookup.reindex(index).reset_index(drop=True)
        available = neighbors.available_at.notna() & (neighbors.available_at <= query.available_at)
        label = f"{'past' if hours < 0 else 'future'}_{abs(hours)}h"
        for col in ("speed", "temperature"):
            result[f"forecast_{label}_delta_{col}"] = (neighbors[col] - query[col]).where(available)
        result[f"forecast_{label}_delta_direction"] = np.where(available,
            angle_diff(neighbors.direction, query.direction), np.nan)
    return result.astype("float32")


def build_features(query: pd.DataFrame, obs: pd.DataFrame, errors: pd.DataFrame, cfg: Settings,
                   forecast_context: pd.DataFrame | None = None) -> pd.DataFrame:
    query = query.reset_index(drop=True)
    result = query[["farm", "speed", "temperature", "dir_sin", "dir_cos", "u", "v"]].copy()
    result["lead_hours"] = (query.valid_at - query.available_at).dt.total_seconds() / 3600.0
    local = query.valid_at.dt.tz_convert(cfg.timezone)
    hour = local.dt.hour + local.dt.minute / 60.0
    issue_local = query.available_at.dt.tz_convert(cfg.timezone)
    issue_hour = issue_local.dt.hour + issue_local.dt.minute / 60.0
    for name, value, period in (("hour", hour, 24), ("day", local.dt.dayofyear, 365.25),
                                ("issue_hour", issue_hour, 24)):
        result[f"{name}_sin"] = np.sin(2 * np.pi * value / period)
        result[f"{name}_cos"] = np.cos(2 * np.pi * value / period)
    result["speed_squared"] = query.speed ** 2
    modern = cfg.feature_version >= 2
    recent = history_features(query, obs, ["speed", "temperature", "u", "v", "dir_sin", "dir_cos"], "obs", modern, modern)
    stale = recent.obs_age_minutes > cfg.max_recent_observation_age_minutes
    recent.loc[stale, [c for c in recent if "_last_" in c]] = np.nan
    bias = history_features(query, errors, ["error_speed", "error_temperature", "error_sin", "error_cos"], "bias", modern, modern)
    result = pd.concat([result, recent, bias], axis=1)
    if not modern:
        return result.astype({col: "float32" for col in result.columns if col != "farm"})
    if cfg.use_forecast_trajectory:
        result = pd.concat([result, trajectory_features(query, forecast_context if forecast_context is not None else query)], axis=1)
    result = result.copy()
    for tau in (3, 12):
        decay = np.exp(-result.lead_hours.clip(lower=0) / tau)
        for col in ("error_speed", "error_temperature", "error_sin", "error_cos"):
            result[f"bias_decay_{tau}h_{col}"] = bias[f"bias_1h_{col}"] * decay
    result["observed_speed_departure"] = recent.obs_last_speed - query.speed
    result["observed_temperature_departure"] = recent.obs_last_temperature - query.temperature
    result["observed_direction_departure"] = angle_diff(
        np.degrees(np.arctan2(recent.obs_last_dir_sin, recent.obs_last_dir_cos)), query.direction)
    for col in result.columns.difference(["farm"]):
        result[col] = result[col].astype("float32")
    return result
