"""Options chain snapshot loader."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd
import streamlit as st

from trade_dash.config import OPTIONS_DIR, PARQUET_OPTIONS_DIR, TICKRAKE_DB_PATH

_OPTIONS_DTYPES: dict[str, Any] = {
    "strike": "float64",
    "open_interest": "float64",
    "gamma": "float64",
    "delta": "float64",
    "theta": "float64",
    "vega": "float64",
    "theoretical_volatility": "float64",
    "underlying_price": "float64",
    "volatility": "float64",
    "mark": "float64",
    "bid": "float64",
    "ask": "float64",
    "last": "float64",
    "last_size": "float64",
    "total_volume": "float64",
}

_OPTIONS_DATASET_TYPE = "options"
_OPTIONS_PROVIDER = "schwab"
_CHICAGO = ZoneInfo("America/Chicago")


def _parse_filename(path: Path) -> tuple[date, datetime] | None:
    """Parse expiration date and fetch datetime from filename stem.

    Pattern: {SYMBOL}_exp{YYYY-MM-DD}_{YYYY-MM-DD}_{HH-MM-SS}
    """
    parts = path.stem.split("_")
    if len(parts) < 4:
        return None
    try:
        exp_date = date.fromisoformat(parts[1].removeprefix("exp"))
        fetch_dt = datetime.strptime(f"{parts[2]}_{parts[3]}", "%Y-%m-%d_%H-%M-%S")
        return exp_date, fetch_dt
    except ValueError:
        return None


def _resolve_metadata_db_path(metadata_db_path: Path | None) -> Path:
    return metadata_db_path or TICKRAKE_DB_PATH


def _connect_metadata_db(metadata_db_path: Path | None) -> sqlite3.Connection:
    db_path = _resolve_metadata_db_path(metadata_db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Tickrake metadata DB not found: {db_path}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    has_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'file_metadata_cache'"
    ).fetchone()
    if has_table is None:
        conn.close()
        raise RuntimeError(
            f"Tickrake metadata DB missing required table 'file_metadata_cache': {db_path}"
        )
    return conn


def _fetch_metadata_rows(
    query: str,
    params: tuple[object, ...],
    metadata_db_path: Path | None,
) -> list[sqlite3.Row]:
    with closing(_connect_metadata_db(metadata_db_path)) as conn:
        rows = conn.execute(query, params).fetchall()
    return rows


def _snapshot_fetch_datetime(path_raw: object, ts_raw: object) -> datetime:
    path = Path(str(path_raw))
    parsed = _parse_filename(path)
    if parsed is not None:
        _, fetch_dt = parsed
        return fetch_dt.replace(tzinfo=UTC)
    return datetime.fromisoformat(str(ts_raw))


def _snapshot_fetch_chicago_date(path_raw: object, ts_raw: object) -> date:
    return _snapshot_fetch_datetime(path_raw, ts_raw).astimezone(_CHICAGO).date()


@st.cache_data(ttl=300)
def list_expirations(
    symbol: str,
    data_dir: Path = OPTIONS_DIR,
    metadata_db_path: Path | None = None,
) -> list[date]:
    """Return sorted list of available expiration dates from metadata."""
    del data_dir
    rows = _fetch_metadata_rows(
        """
        SELECT DISTINCT expiration_date
        FROM file_metadata_cache
        WHERE dataset_type = ?
          AND provider_name = ?
          AND ticker = ?
          AND expiration_date IS NOT NULL
        ORDER BY expiration_date ASC
        """,
        (_OPTIONS_DATASET_TYPE, _OPTIONS_PROVIDER, symbol),
        metadata_db_path,
    )
    return [date.fromisoformat(str(row["expiration_date"])) for row in rows]


@st.cache_data(ttl=300)
def list_snapshot_dates(
    symbol: str,
    data_dir: Path = OPTIONS_DIR,
    metadata_db_path: Path | None = None,
) -> list[date]:
    """Return sorted list of Chicago sample dates with snapshots for the symbol."""
    del data_dir
    rows = _fetch_metadata_rows(
        """
        SELECT last_observed_at, path
        FROM file_metadata_cache
        WHERE dataset_type = ?
          AND provider_name = ?
          AND ticker = ?
          AND last_observed_at IS NOT NULL
        ORDER BY last_observed_at ASC
        """,
        (_OPTIONS_DATASET_TYPE, _OPTIONS_PROVIDER, symbol),
        metadata_db_path,
    )
    return sorted(
        {_snapshot_fetch_chicago_date(row["path"], row["last_observed_at"]) for row in rows}
    )


@st.cache_data(ttl=300)
def list_snapshot_dates_for_expiry(
    symbol: str,
    expiry: date,
    data_dir: Path = OPTIONS_DIR,
    metadata_db_path: Path | None = None,
) -> list[date]:
    """Return sorted list of sample dates with snapshots for the given expiry."""
    del data_dir
    rows = _fetch_metadata_rows(
        """
        SELECT last_observed_at, path
        FROM file_metadata_cache
        WHERE dataset_type = ?
          AND provider_name = ?
          AND ticker = ?
          AND expiration_date = ?
          AND last_observed_at IS NOT NULL
        ORDER BY last_observed_at ASC
        """,
        (_OPTIONS_DATASET_TYPE, _OPTIONS_PROVIDER, symbol, expiry.isoformat()),
        metadata_db_path,
    )
    return sorted(
        {_snapshot_fetch_chicago_date(row["path"], row["last_observed_at"]) for row in rows}
    )


@st.cache_data(ttl=30)
def find_latest_snapshots(
    symbol: str,
    start_date: date,
    days_out: int,
    include_0dte: bool = True,
    data_dir: Path = OPTIONS_DIR,
    metadata_db_path: Path | None = None,
) -> dict[date, Path]:
    """Return {expiry_date: most_recent_snapshot_path} for expirations in window."""
    del data_dir
    target_start = start_date if include_0dte else start_date + timedelta(days=1)
    target_end = start_date + timedelta(days=days_out)
    if target_end < target_start:
        return {}

    rows = _fetch_metadata_rows(
        """
        SELECT expiration_date, path
        FROM (
            SELECT
                expiration_date,
                path,
                ROW_NUMBER() OVER (
                    PARTITION BY expiration_date
                    ORDER BY last_observed_at DESC, path DESC
                ) AS row_num
            FROM file_metadata_cache
            WHERE dataset_type = ?
              AND provider_name = ?
              AND ticker = ?
              AND expiration_date BETWEEN ? AND ?
        )
        WHERE row_num = 1
        ORDER BY expiration_date ASC
        """,
        (
            _OPTIONS_DATASET_TYPE,
            _OPTIONS_PROVIDER,
            symbol,
            target_start.isoformat(),
            target_end.isoformat(),
        ),
        metadata_db_path,
    )
    return {date.fromisoformat(str(row["expiration_date"])): Path(str(row["path"])) for row in rows}


@st.cache_data(ttl=30)
def find_all_snapshots_for_expiry(
    symbol: str,
    expiry: date,
    data_dir: Path = OPTIONS_DIR,
    metadata_db_path: Path | None = None,
) -> list[tuple[datetime, Path]]:
    """Return all (fetch_datetime, path) pairs for a given expiry, sorted by time."""
    del data_dir
    rows = _fetch_metadata_rows(
        """
        SELECT last_observed_at, path
        FROM file_metadata_cache
        WHERE dataset_type = ?
          AND provider_name = ?
          AND ticker = ?
          AND expiration_date = ?
        ORDER BY last_observed_at ASC, path ASC
        """,
        (_OPTIONS_DATASET_TYPE, _OPTIONS_PROVIDER, symbol, expiry.isoformat()),
        metadata_db_path,
    )
    return [
        (datetime.fromisoformat(str(row["last_observed_at"])), Path(str(row["path"])))
        for row in rows
    ]


@st.cache_data(ttl=30)
def find_snapshots_for_expiry_on_date(
    symbol: str,
    expiry: date,
    sample_date: date,
    data_dir: Path = OPTIONS_DIR,
    metadata_db_path: Path | None = None,
) -> list[tuple[datetime, Path]]:
    """Return all snapshots for a given symbol/expiry/Chicago sample date, sorted by time."""
    del data_dir
    rows = _fetch_metadata_rows(
        """
        SELECT last_observed_at, path
        FROM file_metadata_cache
        WHERE dataset_type = ?
          AND provider_name = ?
          AND ticker = ?
          AND expiration_date = ?
        ORDER BY last_observed_at ASC, path ASC
        """,
        (
            _OPTIONS_DATASET_TYPE,
            _OPTIONS_PROVIDER,
            symbol,
            expiry.isoformat(),
        ),
        metadata_db_path,
    )
    return [
        (_snapshot_fetch_datetime(row["path"], row["last_observed_at"]), Path(str(row["path"])))
        for row in rows
        if _snapshot_fetch_chicago_date(row["path"], row["last_observed_at"]) == sample_date
    ]


@st.cache_data(ttl=300)
def list_expirations_for_window_on_date(
    symbol: str,
    sample_date: date,
    days_out: int,
    include_0dte: bool = True,
    data_dir: Path = OPTIONS_DIR,
    metadata_db_path: Path | None = None,
) -> list[date]:
    """Return expirations in the historical window that have snapshots on sample_date."""
    del data_dir
    target_start = sample_date if include_0dte else sample_date + timedelta(days=1)
    target_end = sample_date + timedelta(days=days_out)
    if target_end < target_start:
        return []

    rows = _fetch_metadata_rows(
        """
        SELECT expiration_date, last_observed_at, path
        FROM file_metadata_cache
        WHERE dataset_type = ?
          AND provider_name = ?
          AND ticker = ?
          AND expiration_date BETWEEN ? AND ?
          AND last_observed_at IS NOT NULL
        ORDER BY expiration_date ASC, last_observed_at ASC
        """,
        (
            _OPTIONS_DATASET_TYPE,
            _OPTIONS_PROVIDER,
            symbol,
            target_start.isoformat(),
            target_end.isoformat(),
        ),
        metadata_db_path,
    )
    expiries: set[date] = set()
    for row in rows:
        if _snapshot_fetch_chicago_date(row["path"], row["last_observed_at"]) != sample_date:
            continue
        expiries.add(date.fromisoformat(str(row["expiration_date"])))
    return sorted(expiries)


# ---------------------------------------------------------------------------
# Parquet / DuckDB access — historical dates only (sample_date < today)
# ---------------------------------------------------------------------------


def parquet_path_for_date(symbol: str, sample_date: date) -> Path | None:
    """Return the parquet file path for a symbol and date, or None if not present.

    Returns None for today (live CSV path), weekends, or dates before compaction ran.
    """
    p = (
        PARQUET_OPTIONS_DIR
        / f"{sample_date.year:04d}"
        / f"{sample_date.month:02d}"
        / f"{sample_date.day:02d}"
        / f"{symbol}_samples_{sample_date.isoformat()}.parquet"
    )
    return p if p.exists() else None


@st.cache_data(ttl=300)
def find_historical_snapshot_times(expiry: date, parquet_path: Path) -> list[datetime]:
    """Return sorted distinct sampled_at datetimes for an expiry from a parquet file.

    Replaces find_snapshots_for_expiry_on_date() for historical dates — returns
    datetimes only (no per-file paths needed).
    """
    expiry_str = expiry.isoformat()
    result = duckdb.execute(
        "SELECT DISTINCT sampled_at FROM read_parquet(?)"
        " WHERE expiration_date = ? ORDER BY sampled_at",
        [str(parquet_path), expiry_str],
    ).fetchall()
    return [datetime.fromisoformat(str(row[0])) for row in result]


@st.cache_data(ttl=3600)
def load_historical_snapshot(
    symbol: str, expiry: date, sampled_at: datetime, parquet_path: Path
) -> pd.DataFrame:
    """Load a single snapshot for one expiry and sampled_at from a parquet file.

    Equivalent to load_options_snapshot() for historical dates.
    """
    expiry_str = expiry.isoformat()
    sampled_at_str = sampled_at.isoformat()
    df = duckdb.execute(
        "SELECT * FROM read_parquet(?)"
        " WHERE expiration_date = ?"
        " AND CAST(sampled_at AS TIMESTAMPTZ) = CAST(? AS TIMESTAMPTZ)",
        [str(parquet_path), expiry_str, sampled_at_str],
    ).df()
    df = df.astype({col: dtype for col, dtype in _OPTIONS_DTYPES.items() if col in df.columns})
    df["expiration_date"] = pd.to_datetime(df["expiration_date"])
    df["contract_type"] = df["contract_type"].str.upper()
    return df


@st.cache_data(ttl=3600)
def load_historical_expiry(
    symbol: str, expiry: date, sample_date: date, parquet_path: Path
) -> pd.DataFrame:
    """Load all snapshots for one expiry on one historical date from a parquet file.

    Returns a single DataFrame sorted by sampled_at. Caller can split on
    sampled_at in memory for per-snapshot iteration.
    """
    expiry_str = expiry.isoformat()
    df = duckdb.execute(
        "SELECT * FROM read_parquet(?) WHERE expiration_date = ? ORDER BY sampled_at",
        [str(parquet_path), expiry_str],
    ).df()
    df = df.astype({col: dtype for col, dtype in _OPTIONS_DTYPES.items() if col in df.columns})
    df["expiration_date"] = pd.to_datetime(df["expiration_date"])
    df["contract_type"] = df["contract_type"].str.upper()
    return df


@st.cache_data(ttl=1800)
def load_historical_lookback(
    symbol: str,
    parquet_glob: str,
    expiry_range: tuple[date, date],
    interval_minutes: int,
) -> pd.DataFrame:
    """Load downsampled historical data across multiple parquet files via DuckDB glob.

    Filters to expiry_range and downsamples to the latest snapshot per
    interval_minutes bucket (floor of sampled_at to the nearest interval boundary).
    """
    start_str = expiry_range[0].isoformat()
    end_str = expiry_range[1].isoformat()
    query = f"""
        WITH bucketed AS (
            SELECT *,
                epoch_ms(
                    CAST(floor(epoch_ms(sampled_at) / ({interval_minutes} * 60000))
                    * ({interval_minutes} * 60000) AS BIGINT)
                ) AS interval_bucket
            FROM read_parquet('{parquet_glob}')
            WHERE expiration_date BETWEEN '{start_str}' AND '{end_str}'
        ),
        ranked AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY interval_bucket, expiration_date, strike, contract_type
                    ORDER BY sampled_at DESC
                ) AS rn
            FROM bucketed
        )
        SELECT * EXCLUDE (interval_bucket, rn)
        FROM ranked
        WHERE rn = 1
        ORDER BY sampled_at, expiration_date
    """
    df = duckdb.execute(query).df()
    df = df.astype({col: dtype for col, dtype in _OPTIONS_DTYPES.items() if col in df.columns})
    df["expiration_date"] = pd.to_datetime(df["expiration_date"])
    df["contract_type"] = df["contract_type"].str.upper()
    return df


@st.cache_data(ttl=1800)
def load_historical_sample_window(
    symbol: str,
    parquet_glob: str,
    sample_start: date,
    interval_minutes: int,
) -> pd.DataFrame:
    """Load downsampled historical data across parquet files filtered by sample date.

    Unlike load_historical_lookback (which filters by expiration_date), this filters
    by sampled_at >= sample_start — the date the snapshot was taken. Intended for
    z-score history where we want all contracts sampled within a lookback window,
    including past-expiry contracts. Downsamples to the latest snapshot per
    interval_minutes bucket (floor of sampled_at to the nearest interval boundary).
    """
    start_str = sample_start.isoformat()
    query = f"""
        WITH bucketed AS (
            SELECT *,
                epoch_ms(
                    CAST(floor(epoch_ms(sampled_at) / ({interval_minutes} * 60000))
                    * ({interval_minutes} * 60000) AS BIGINT)
                ) AS interval_bucket
            FROM read_parquet('{parquet_glob}')
            WHERE CAST(sampled_at AS TIMESTAMPTZ) >= TIMESTAMPTZ '{start_str}'
        ),
        ranked AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY interval_bucket, expiration_date, strike, contract_type
                    ORDER BY sampled_at DESC
                ) AS rn
            FROM bucketed
        )
        SELECT * EXCLUDE (interval_bucket, rn)
        FROM ranked
        WHERE rn = 1
        ORDER BY sampled_at, expiration_date
    """
    df = duckdb.execute(query).df()
    df = df.astype({col: dtype for col, dtype in _OPTIONS_DTYPES.items() if col in df.columns})
    df["expiration_date"] = pd.to_datetime(df["expiration_date"])
    df["contract_type"] = df["contract_type"].str.upper()
    return df


@st.cache_data(ttl=1800)
def load_historical_expiry_lookback(
    symbol: str,
    expiry: date,
    parquet_glob: str,
    interval_minutes: int,
) -> pd.DataFrame:
    """Load downsampled data for a single expiry across multiple parquet files.

    Pulls every snapshot for `expiry` from all parquet files matched by
    `parquet_glob`, downsampled to the latest snapshot per interval_minutes bucket.
    Useful for vol history, skew evolution, and term-structure replay over a lookback
    window.

    Example glob: str(PARQUET_OPTIONS_DIR / "*/*/*/SPXW_samples_*.parquet")
    """
    expiry_str = expiry.isoformat()
    query = f"""
        WITH bucketed AS (
            SELECT *,
                epoch_ms(
                    CAST(floor(epoch_ms(sampled_at) / ({interval_minutes} * 60000))
                    * ({interval_minutes} * 60000) AS BIGINT)
                ) AS interval_bucket
            FROM read_parquet('{parquet_glob}')
            WHERE expiration_date = '{expiry_str}'
        ),
        ranked AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY interval_bucket, strike, contract_type
                    ORDER BY sampled_at DESC
                ) AS rn
            FROM bucketed
        )
        SELECT * EXCLUDE (interval_bucket, rn)
        FROM ranked
        WHERE rn = 1
        ORDER BY sampled_at
    """
    df = duckdb.execute(query).df()
    df = df.astype({col: dtype for col, dtype in _OPTIONS_DTYPES.items() if col in df.columns})
    df["expiration_date"] = pd.to_datetime(df["expiration_date"])
    df["contract_type"] = df["contract_type"].str.upper()
    return df


@st.cache_data(ttl=3600)
def load_options_snapshot(path: Path) -> pd.DataFrame:
    """Load a single options snapshot CSV with typed columns."""
    if not path.exists():
        raise FileNotFoundError(f"Options snapshot path from metadata DB does not exist: {path}")
    df = pd.read_csv(path, dtype=_OPTIONS_DTYPES)  # type: ignore[arg-type]
    df["expiration_date"] = pd.to_datetime(df["expiration_date"])
    return df
