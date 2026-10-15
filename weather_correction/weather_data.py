"""Wspólne przygotowanie danych do wielu historycznych uruchomień."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .config import Settings
from .data import observation_targets, prepare_forecasts, prepare_observations
from .features import residual_history


PREPARATION_FIELDS = ("timezone", "farms", "feature_version", "native_observation_minutes",
    "observation_timestamp_position", "observation_delay_minutes", "forecast_delivery_delay_minutes",
    "min_coverage", "min_direction_resultant", "calm_speed", "max_forecast_gap_minutes")


@dataclass
class PreparedWeather:
    forecasts: pd.DataFrame
    observations: pd.DataFrame
    settings: Settings
    raw_forecast_rows: int
    raw_observation_rows: int
    dropped_forecast_times: int
    dropped_observation_times: int

    @classmethod
    def prepare(cls, raw_forecasts, raw_observations, cfg):
        forecasts = prepare_forecasts(raw_forecasts, cfg)
        observations = prepare_observations(raw_observations, cfg)
        return cls(forecasts, observations, cfg, len(raw_forecasts), len(raw_observations),
                   forecasts.attrs.get("dropped_timezone_rows", 0), observations.attrs.get("dropped_timezone_rows", 0))

    def known_at(self, as_of, cfg, recent=False):
        if any(getattr(self.settings, key) != getattr(cfg, key) for key in PREPARATION_FIELDS):
            raise ValueError("Przygotowane dane mają inne ustawienia pomiarów/prognoz niż model.")
        forecasts = self.forecasts.loc[self.forecasts.available_at <= as_of]
        observations = self.observations.loc[self.observations.available_at <= as_of]
        if recent:
            start = as_of - pd.Timedelta(days=3)
            forecasts = forecasts.loc[forecasts.valid_at >= start]
            observations = observations.loc[observations.observed_at >= start]
        if observations.empty:
            raise ValueError("Brak dostępnych pomiarów przed as_of.")
        targets = observation_targets(observations, cfg)
        targets = targets.loc[targets.label_available_at <= as_of]
        errors = residual_history(forecasts, targets, cfg)
        return tuple(frame.reset_index(drop=True) for frame in (forecasts, observations, targets, errors))

    def targets_at(self, as_of, cfg):
        observations = self.observations.loc[self.observations.available_at <= as_of]
        targets = observation_targets(observations, cfg)
        return targets.loc[targets.label_available_at <= as_of].reset_index(drop=True)
