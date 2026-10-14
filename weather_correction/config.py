from __future__ import annotations

import json
import unicodedata
from dataclasses import asdict, dataclass, fields
from pathlib import Path


FARM_NAMES = {
    "GAL": "Galicja", "KAM": "Kamieńsk", "KAR": "Karnice", "KAR2": "Karnice II",
    "KIS": "Kisielice", "KIS2": "Kisielice II", "KRW": "Karwice",
    "LOS": "Jagniątkowo", "LOT": "Lotnisko", "MAL": "Malbork", "PEL": "Pelplin",
    "RES": "Resko I", "RES2": "Resko II", "RYB": "Rybice", "SKO": "Skoczykłody",
    "STA": "Starza", "WOJ": "Wojciechowo", "ZAL": "Zalesie", "ZUR": "Żuromin",
}


def name_key(value: str) -> str:
    value = str(value).strip().replace("–", "-").replace("—", "-")
    value = unicodedata.normalize("NFKD", value.replace("ł", "l").replace("Ł", "L"))
    return " ".join("".join(c for c in value if not unicodedata.combining(c)).casefold().split())


ALIASES = {name_key(name): code for code, name in FARM_NAMES.items()}
ALIASES.update({name_key(code): code for code in FARM_NAMES})
ALIASES.update({
    name_key("Galicja (Hnatkowice - Orzechowce)"): "GAL",
    name_key("Jagniątkowo (Lake Ostrowo)"): "LOS",
    name_key("Jagniątkowo (Ląk Ostrów)"): "LOS",
    name_key("Malbork (Koniecwałd)"): "MAL",
    name_key("Malbork (Konieczwałd)"): "MAL",
})


@dataclass(frozen=True)
class Settings:
    feature_version: int = 2
    timezone: str = "Europe/Warsaw"
    history_days: int = 365
    horizon_hours: int = 24
    max_model_lead_hours: int = 36
    step_minutes: int = 15
    native_observation_minutes: int = 10
    observation_timestamp_position: str = "end"
    observation_delay_minutes: int = 20
    forecast_delivery_delay_minutes: int = 0
    min_coverage: float = 0.8
    min_direction_resultant: float = 0.2
    calm_speed: float = 1.0
    max_forecast_gap_minutes: int = 60
    max_forecast_age_hours: int = 12
    max_recent_observation_age_minutes: int = 120
    validation_days: int = 21
    test_days: int = 21
    backtest_folds: int = 2
    min_training_days: int = 60
    min_training_rows: int = 200
    min_route_rows: int = 96
    min_route_issues: int = 4
    min_route_days: int = 7
    min_improvement: float = 0.01
    route_bootstrap_samples: int = 200
    route_confidence_level: float = 0.9
    min_route_day_win_rate: float = 0.55
    max_route_rmse_increase: float = 0.01
    max_route_p95_increase: float = 0.02
    max_test_cell_mae_increase: float = 0.03
    tuning_trials: int = 4
    tuning_validation_fraction: float = 0.3333333333
    use_forecast_trajectory: bool = True
    enable_adaptive_bias: bool = True
    enable_ensembles: bool = True
    max_fit_rows: int = 200000
    recency_half_life_days: float = 180.0
    backend: str = "xgboost"
    trees: int = 250
    n_jobs: int = 4
    random_state: int = 42
    farms: tuple[str, ...] = tuple(FARM_NAMES)

    def __post_init__(self):
        if self.feature_version not in (1, 2):
            raise ValueError("Nieobsługiwana wersja cech.")
        positive = ("history_days", "horizon_hours", "max_model_lead_hours", "step_minutes", "native_observation_minutes",
                    "validation_days", "test_days", "backtest_folds", "min_training_days",
                    "min_training_rows", "min_route_rows", "min_route_issues", "min_route_days", "route_bootstrap_samples", "max_fit_rows",
                    "trees", "n_jobs", "max_forecast_gap_minutes", "max_forecast_age_hours",
                    "max_recent_observation_age_minutes", "recency_half_life_days")
        for key in positive:
            if getattr(self, key) <= 0:
                raise ValueError(f"{key} musi być dodatnie.")
        if self.step_minutes != 15 or self.horizon_hours != 24:
            raise ValueError("Ta wersja obsługuje kwadranse i horyzont 24 h.")
        if self.max_model_lead_hours < self.horizon_hours + self.max_forecast_age_hours:
            raise ValueError("max_model_lead_hours musi pokrywać 24 h plus dopuszczalny wiek prognozy.")
        if self.observation_timestamp_position not in ("start", "end", "instant"):
            raise ValueError("observation_timestamp_position: start, end albo instant.")
        if self.backend not in ("xgboost", "hist"):
            raise ValueError("backend: xgboost albo hist.")
        if not 0 < self.min_coverage <= 1 or not 0 < self.min_direction_resultant <= 1:
            raise ValueError("Pokrycie i wypadkowa kierunku muszą należeć do (0, 1].")
        if not 0 <= self.min_improvement < 1 or self.calm_speed < 0:
            raise ValueError("Niepoprawny próg poprawy albo ciszy wiatru.")
        if not 1 <= self.tuning_trials <= 4:
            raise ValueError("tuning_trials musi należeć do 1..4.")
        if not 0 < self.tuning_validation_fraction < 0.75:
            raise ValueError("tuning_validation_fraction musi należeć do (0, 0.75).")
        if not 0.5 < self.route_confidence_level < 1 or not 0 <= self.min_route_day_win_rate <= 1:
            raise ValueError("Niepoprawny poziom ufności albo odsetek lepszych dni.")
        if min(self.max_route_rmse_increase, self.max_route_p95_increase, self.max_test_cell_mae_increase) < 0:
            raise ValueError("Tolerancje RMSE/P95 nie mogą być ujemne.")
        if min(self.observation_delay_minutes, self.forecast_delivery_delay_minutes) < 0:
            raise ValueError("Opóźnienia nie mogą być ujemne.")
        if not self.farms or len(set(self.farms)) != len(self.farms) or set(self.farms) - set(FARM_NAMES):
            raise ValueError("farms musi zawierać unikalne kody farm z FARM_NAMES.")

    @classmethod
    def load(cls, path: Path | str | None = None) -> Settings:
        if path is None:
            return cls()
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"Nieznane ustawienia: {sorted(unknown)}")
        if "farms" in data:
            data["farms"] = tuple(data["farms"])
        return cls(**data)

    def to_dict(self) -> dict:
        return asdict(self)
