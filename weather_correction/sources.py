from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from .config import Settings


SQL_ROOT = Path(__file__).resolve().parent / "sql"


def query(sql_path: Path, connection: str, params: tuple) -> pd.DataFrame:
    try:
        import pyodbc
    except ImportError as exc:
        raise ImportError("Obsługa SQL wymaga pyodbc i sterownika ODBC SQL Server. Można też użyć wejść CSV.") from exc
    conn = pyodbc.connect(connection, timeout=30)
    try:
        cursor = conn.cursor()
        cursor.timeout = 300
        cursor.execute(sql_path.read_text(encoding="utf-8"), params)
        while cursor.description is None:
            if not cursor.nextset():
                raise ValueError("Zapytanie nie zwróciło tabeli.")
        columns = [desc[0] for desc in cursor.description]
        frames = []
        while True:
            chunk = cursor.fetchmany(50000)
            if not chunk:
                break
            frames.append(pd.DataFrame.from_records([tuple(row) for row in chunk], columns=columns))
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)
    finally:
        conn.close()


def load_sources(args, cfg: Settings, as_of: pd.Timestamp, training: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    if bool(args.forecast_csv) != bool(args.observation_csv):
        raise ValueError("Podaj oba wejścia CSV: --forecast-csv i --observation-csv, albo nie podawaj żadnego (SQL).")
    if args.forecast_csv:
        return (pd.read_csv(args.forecast_csv, sep=args.csv_separator, encoding="utf-8-sig"),
                pd.read_csv(args.observation_csv, sep=args.csv_separator, encoding="utf-8-sig"))
    start = as_of - pd.Timedelta(days=cfg.history_days + 3 if training else 3)
    if training and getattr(args, "start", None) is not None:
        start = args.start - pd.Timedelta(days=3)
    # Przyszłe wartości znanej prognozy są legalnymi cechami; przyszłe wykonanie nie jest.
    end = as_of.ceil("15min") + pd.Timedelta(hours=cfg.max_model_lead_hours, minutes=15)
    forecast_connection = os.environ.get("PGE_WEATHER_FORECAST_CONNECTION", "").strip()
    observation_connection = os.environ.get("PGE_WEATHER_OBSERVATION_CONNECTION", "").strip()
    if not forecast_connection or not observation_connection:
        raise ValueError("Ustaw PGE_WEATHER_FORECAST_CONNECTION i PGE_WEATHER_OBSERVATION_CONNECTION "
                         "dla połączeń SQL albo podaj oba wejścia CSV.")
    forecasts = query(Path(args.forecast_sql), forecast_connection,
        (start.to_pydatetime().replace(tzinfo=None), end.to_pydatetime().replace(tzinfo=None)))
    # Szerszy filtr dat lokalnych, dokładne odcięcie dostępności następuje w Pythonie.
    observations = query(Path(args.observation_sql), observation_connection,
        ((start.tz_convert(cfg.timezone) - pd.Timedelta(days=1)).date(),
         (as_of.tz_convert(cfg.timezone) + pd.Timedelta(days=1)).date()))
    return forecasts, observations
