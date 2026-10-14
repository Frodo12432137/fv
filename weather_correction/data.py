from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from .config import ALIASES, Settings, name_key


STEP = pd.Timedelta(minutes=15)
KEY = ["farm", "valid_at"]
WEATHER = ["speed", "direction", "temperature"]


def utc_time(value, timezone: str = "Europe/Warsaw") -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize(timezone, ambiguous="raise", nonexistent="raise")
    return stamp.tz_convert("UTC")


def time_column(df: pd.DataFrame, choices: list[tuple[str, str]], timezone: str) -> pd.Series:
    for name, zone in choices:
        if name in df:
            result = pd.to_datetime(df[name], errors="raise")
            if result.isna().any():
                raise ValueError(f"Puste znaczniki czasu w {name}.")
            if result.dt.tz is None:
                # Nie wymyślamy offsetu dla powtarzanej godziny jesiennej.
                result = result.dt.tz_localize(zone or timezone, ambiguous="NaT", nonexistent="NaT")
                if result.isna().any():
                    warnings.warn(f"{name}: pominięto {int(result.isna().sum())} niejednoznacznych/nieistniejących czasów lokalnych. Eksport UTC pozwoli je zachować.", RuntimeWarning)
            return result.dt.tz_convert("UTC")
    raise ValueError(f"Brak kolumny czasu. Oczekiwano jednej z {[n for n, _ in choices]}.")


def numeric(df: pd.DataFrame, choices: list[str]) -> pd.Series:
    for col in choices:
        if col in df:
            return pd.to_numeric(df[col].astype(str).str.replace(",", ".", regex=False), errors="coerce").replace([np.inf, -np.inf], np.nan)
    raise ValueError(f"Brak parametru: oczekiwano jednej z {choices}.")


def farms(df: pd.DataFrame, cfg: Settings) -> pd.Series:
    col = next((c for c in ("farm", "lokalizacja", "punkt", "NazwaFarmy") if c in df), None)
    if col is None:
        raise ValueError("Brak kolumny farm/lokalizacja/punkt/NazwaFarmy.")
    values = df[col].map(lambda x: ALIASES.get(name_key(x)))
    if values.isna().any():
        raise ValueError(f"Nieznane nazwy farm: {df.loc[values.isna(), col].drop_duplicates().tolist()}")
    unexpected = set(values) - set(cfg.farms)
    if unexpected:
        raise ValueError(f"Farmy spoza konfiguracji: {sorted(unexpected)}")
    return values


def angle_diff(a, b):
    return (np.asarray(a) - np.asarray(b) + 180.0) % 360.0 - 180.0


def circular_direction(sine, cosine, minimum=0.2):
    magnitude = np.hypot(sine, cosine)
    direction = np.degrees(np.arctan2(sine, cosine)) % 360.0
    return np.where(magnitude >= minimum, direction, np.nan)


def add_vectors(df: pd.DataFrame) -> pd.DataFrame:
    angle = np.radians(df["direction"])
    df["dir_sin"], df["dir_cos"] = np.sin(angle), np.cos(angle)
    df["u"], df["v"] = -df["speed"] * df["dir_sin"], -df["speed"] * df["dir_cos"]
    return df


def prepare_forecasts(raw: pd.DataFrame, cfg: Settings) -> pd.DataFrame:
    raw = raw.reset_index(drop=True).copy()
    raw.columns = raw.columns.str.strip()
    df = pd.DataFrame({"farm": farms(raw, cfg)})
    df["valid_at"] = time_column(raw, [("valid_at", "UTC"), ("dataGodzinaUTC", "UTC"), ("dataGodzinaCET", "")], cfg.timezone)
    df["issued_at"] = time_column(raw, [("issued_at", "UTC"), ("czasDanychZrodlaUTC", "UTC"), ("czasDanychZrodlaCET", ""), ("issued_at_local", "")], cfg.timezone)
    if "available_at" in raw:
        df["available_at"] = time_column(raw, [("available_at", "UTC")], cfg.timezone)
    else:
        df["available_at"] = df["issued_at"] + pd.Timedelta(minutes=cfg.forecast_delivery_delay_minutes)
    dropped_times = int(df[["valid_at", "issued_at", "available_at"]].isna().any(axis=1).sum())
    if (df["available_at"] < df["issued_at"]).any():
        raise ValueError("available_at nie może być wcześniejsze niż issued_at.")
    df["speed"] = numeric(raw, ["speed", "predkoscWiatru"])
    df["direction"] = numeric(raw, ["direction", "kierunekWiatru"])
    df["temperature"] = numeric(raw, ["temperature", "temperatura"])
    if df[WEATHER].isna().any().any() or not df["speed"].between(0, 75).all() or not df["temperature"].between(-80, 65).all() or not df["direction"].between(0, 360).all():
        raise ValueError("Prognoza zawiera brakujące albo niepoprawne wartości meteorologiczne.")
    df["direction"] %= 360.0
    keys = ["farm", "issued_at", "valid_at"]
    duplicated = df[df.duplicated(keys, keep=False)]
    if not duplicated.empty and duplicated.groupby(keys)[WEATHER + ["available_at"]].nunique().gt(1).any().any():
        raise ValueError("Sprzeczne duplikaty jednego wydania prognozy. Rozdziel źródła/dostawców.")
    df = df.dropna(subset=["valid_at", "issued_at", "available_at"]).drop_duplicates(keys).sort_values(keys)
    pieces = []
    for (_, _), group in df.groupby(["farm", "issued_at"], sort=False):
        if group["available_at"].nunique() != 1:
            raise ValueError("Jedno wydanie prognozy ma różne available_at. Potrzebny czas dostępności całej paczki.")
        group = group.set_index("valid_at").sort_index()
        grid = pd.date_range(group.index.min().ceil("15min"), group.index.max().floor("15min"), freq="15min")
        if not len(grid):
            continue
        if group.index.isin(grid).all() and len(group) == len(grid):
            pieces.append(group.reset_index())
            continue
        # Interpolacja tylko wewnątrz jednego wydania, w u/v, bez ekstrapolacji.
        group = add_vectors(group)
        union = group.index.union(grid).sort_values()
        interp = group[["u", "v", "temperature"]].reindex(union).interpolate(method="time", limit_area="inside").reindex(grid)
        original_ns, grid_ns = group.index.asi8, grid.asi8
        right = np.searchsorted(original_ns, grid_ns, side="left")
        exact = np.isin(grid_ns, original_ns)
        left = np.maximum(right - 1, 0)
        right = np.minimum(right, len(original_ns) - 1)
        gaps = (original_ns[right] - original_ns[left]) / 60e9
        interp = interp.loc[exact | (gaps <= cfg.max_forecast_gap_minutes)].copy()
        interp["speed"] = np.hypot(interp.u, interp.v)
        interp["direction"] = np.degrees(np.arctan2(-interp.u, -interp.v)) % 360.0
        for col in ("farm", "issued_at", "available_at"):
            interp[col] = group[col].iloc[0]
        pieces.append(interp.rename_axis("valid_at").reset_index()[df.columns])
    if not pieces:
        raise ValueError("Brak prognoz po przygotowaniu kwadransów.")
    result = add_vectors(pd.concat(pieces, ignore_index=True).sort_values(keys).reset_index(drop=True))
    result.attrs["dropped_timezone_rows"] = dropped_times
    return result


def prepare_observations(raw: pd.DataFrame, cfg: Settings) -> pd.DataFrame:
    raw = raw.reset_index(drop=True).copy()
    raw.columns = raw.columns.str.strip()
    df = pd.DataFrame({"farm": farms(raw, cfg)})
    df["observed_at"] = time_column(raw, [("observed_at", "UTC"), ("observed_at_utc", "UTC"), ("DataiCzasOdczytuUTC", "UTC"), ("observed_at_local", ""), ("DataiCzasOdczytu", ""), ("dataGodzinaCET", "")], cfg.timezone)
    df["speed"] = numeric(raw, ["speed", "PredkoscWiatru", "predkoscWiatruLokalizacja_wykonanie"])
    if {"obs_direction_sin", "obs_direction_cos"}.issubset(raw.columns):
        df["direction"] = circular_direction(numeric(raw, ["obs_direction_sin"]), numeric(raw, ["obs_direction_cos"]), cfg.min_direction_resultant)
    else:
        df["direction"] = numeric(raw, ["direction", "KierunekWiatru", "kierunekWiatruLokalizacja_wykonanie"])
    df["temperature"] = numeric(raw, ["temperature", "Temperatura", "temperaturaLokalizacja_wykonanie"])
    explicit_availability = "available_at" in raw
    if explicit_availability:
        df["measured_available_at"] = time_column(raw, [("available_at", "UTC")], cfg.timezone)
    df.loc[~df.speed.between(0, 75), "speed"] = np.nan
    df.loc[~df.temperature.between(-80, 65), "temperature"] = np.nan
    df.loc[~df.direction.between(0, 360), "direction"] = np.nan
    df.direction %= 360.0
    df = add_vectors(df)
    # Różne turbiny w tej samej chwili: prędkość skalarna, kierunek kołowy.
    dropped_times = int(df.observed_at.isna().sum())
    aggregation = {c: "mean" for c in ("speed", "temperature", "dir_sin", "dir_cos")}
    if explicit_availability:
        aggregation["measured_available_at"] = "max"
    df = df.dropna(subset=["observed_at"]).groupby(["farm", "observed_at"], as_index=False).agg(aggregation)
    df["direction"] = circular_direction(df.dir_sin, df.dir_cos, cfg.min_direction_resultant)
    if cfg.observation_timestamp_position == "start":
        df["observed_at"] += pd.Timedelta(minutes=cfg.native_observation_minutes)
    df["available_at"] = (df.pop("measured_available_at") if explicit_availability else
                          df["observed_at"] + pd.Timedelta(minutes=cfg.observation_delay_minutes))
    if (df.available_at < df.observed_at).any():
        raise ValueError("Pomiar jest dostępny przed końcem jego okresu. Sprawdź pozycję znacznika czasu.")
    result = add_vectors(df).sort_values(["farm", "observed_at"]).reset_index(drop=True)
    result.attrs["dropped_timezone_rows"] = dropped_times
    return result


def observation_targets(obs: pd.DataFrame, cfg: Settings) -> pd.DataFrame:
    if cfg.observation_timestamp_position == "instant":
        return _instant_targets(obs, cfg)
    native_ns = pd.Timedelta(minutes=cfg.native_observation_minutes).value
    step_ns = STEP.value
    end = obs.observed_at.array.asi8
    start = end - native_ns
    # Każdy odczyt opisuje stały okres 10 min. Ważymy rzeczywistym przecięciem z kwadransem.
    parts = []
    for offset in range(int(np.ceil(native_ns / step_ns)) + 1):
        bucket = (start // step_ns + offset) * step_ns
        overlap = np.minimum(end, bucket + step_ns) - np.maximum(start, bucket)
        mask = overlap > 0
        part = obs.loc[mask, ["farm", "available_at", "speed", "temperature", "dir_sin", "dir_cos"]].copy()
        part["valid_at"] = pd.to_datetime(bucket[mask] + step_ns, utc=True)
        part["weight"] = overlap[mask] / step_ns
        parts.append(part)
    if not parts:
        raise ValueError("Brak pomiarów.")
    joined = pd.concat(parts, ignore_index=True)
    columns = ["speed", "temperature", "dir_sin", "dir_cos"]
    grouped = joined.groupby(KEY, sort=True)
    out = grouped.available_at.max().rename("label_available_at").to_frame()
    for col in columns:
        valid_weight = joined.weight.where(joined[col].notna(), 0.0)
        denominator = valid_weight.groupby([joined.farm, joined.valid_at]).sum()
        numerator = (joined[col].fillna(0.0) * valid_weight).groupby([joined.farm, joined.valid_at]).sum()
        out[col] = (numerator / denominator.where(denominator > 0)).where(denominator >= cfg.min_coverage)
        if col in ("speed", "temperature", "dir_sin"):
            out[f"coverage_{col}"] = denominator.clip(upper=1.0)
    out["direction"] = circular_direction(out.dir_sin, out.dir_cos, cfg.min_direction_resultant)
    out = out.reset_index()
    # Końcowy kwadrans jest dostępny dopiero po jego końcu, również przy krótszym pokryciu.
    out["label_available_at"] = pd.concat([out.label_available_at, out.valid_at], axis=1).max(axis=1)
    return out


def _instant_targets(obs: pd.DataFrame, cfg: Settings) -> pd.DataFrame:
    pieces = []
    for farm, group in obs.groupby("farm"):
        group = group.set_index("observed_at").sort_index()
        grid = pd.date_range(group.index.min().ceil("15min"), group.index.max().floor("15min"), freq="15min")
        if not len(grid):
            continue
        times, query = group.index.asi8, grid.asi8
        right = np.minimum(np.searchsorted(times, query), len(times) - 1)
        exact = times[right] == query
        left = np.where(exact, right, np.maximum(right - 1, 0))
        span = times[right] - times[left]
        valid = exact | (span <= 2 * cfg.native_observation_minutes * 60e9)
        fraction = np.divide(query - times[left], span, out=np.zeros(len(query), dtype=float), where=span > 0)
        values = pd.DataFrame(index=grid)
        for col in ("speed", "temperature", "dir_sin", "dir_cos"):
            data = group[col].to_numpy(float)
            # Tylko bezpośredni sąsiedzi; braków QC nie wypełniamy pomiarem z dalszej przyszłości.
            values[col] = data[left] * (1 - fraction) + data[right] * fraction
        values.loc[~valid] = np.nan
        values["direction"] = circular_direction(values.dir_sin, values.dir_cos, cfg.min_direction_resultant)
        available = group.available_at.array.asi8
        values["label_available_at"] = pd.to_datetime(np.maximum(available[left], available[right]), utc=True)
        values["farm"] = farm
        pieces.append(values.rename_axis("valid_at").reset_index())
    if not pieces:
        raise ValueError("Brak pomiarów chwilowych do weryfikacji kwadransów.")
    return pd.concat(pieces, ignore_index=True)


def select_forecast_run(forecasts: pd.DataFrame, as_of: pd.Timestamp, cfg: Settings) -> pd.DataFrame:
    eligible = forecasts.loc[(forecasts.available_at <= as_of) & (forecasts.issued_at <= as_of)].copy()
    first = as_of.floor("15min") + STEP
    grid = pd.date_range(first, periods=96, freq="15min")
    pieces = []
    for farm in cfg.farms:
        group = eligible.loc[eligible.farm == farm]
        if group.empty:
            raise ValueError(f"Brak dostępnej prognozy dla {farm}.")
        latest = group.issued_at.max()
        run = group.loc[group.issued_at == latest].set_index("valid_at")
        if as_of - run.available_at.iloc[0] > pd.Timedelta(hours=cfg.max_forecast_age_hours):
            raise ValueError(f"Prognoza dla {farm} jest starsza niż {cfg.max_forecast_age_hours} h.")
        missing = grid.difference(run.index)
        if len(missing):
            raise ValueError(f"Najnowsze wydanie dla {farm} nie obejmuje 96 kwadransów; brakuje {len(missing)} (pierwszy: {missing[0]}).")
        if grid[-1] - run.available_at.iloc[0] > pd.Timedelta(hours=cfg.max_model_lead_hours):
            raise ValueError(f"Wyprzedzenie prognozy {farm} przekracza zakres uczenia {cfg.max_model_lead_hours} h.")
        pieces.append(run.loc[grid].rename_axis("valid_at").reset_index())
    return pd.concat(pieces, ignore_index=True)
