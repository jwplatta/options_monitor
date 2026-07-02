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


@st.cache_data(ttl=1800)
def find_all_snapshots_for_lookback(
    symbol: str,
    lookback_days: int,
    days_out: int = 90,
    include_0dte: bool = True,
    data_dir: Path = OPTIONS_DIR,
    metadata_db_path: Path | None = None,
) -> dict[date, dict[date, list[tuple[datetime, Path]]]]:
    """Return all snapshots per (sample_date, expiry) over a historical lookback window.

    Single SQL query — avoids per-date round-trips. Caller can downsample as needed.

    Returns:
        {sample_date: {expiry_date: [(fetch_datetime, path), ...]}} sorted by time.
    """
    del data_dir
    today = date.today()
    lookback_start = today - timedelta(days=lookback_days * 2)

    rows = _fetch_metadata_rows(
        """
        SELECT
            DATE(last_observed_at) AS sample_date,
            expiration_date,
            last_observed_at,
            path
        FROM file_metadata_cache
        WHERE dataset_type = ?
          AND provider_name = ?
          AND ticker = ?
          AND last_observed_at >= ?
          AND last_observed_at < ?
          AND last_observed_at IS NOT NULL
        ORDER BY sample_date ASC, expiration_date ASC, last_observed_at ASC
        """,
        (
            _OPTIONS_DATASET_TYPE,
            _OPTIONS_PROVIDER,
            symbol,
            lookback_start.isoformat(),
            today.isoformat(),
        ),
        metadata_db_path,
    )

    result: dict[date, dict[date, list[tuple[datetime, Path]]]] = {}
    for row in rows:
        sample_dt = date.fromisoformat(str(row["sample_date"]))
        expiry_dt = date.fromisoformat(str(row["expiration_date"]))
        dte = (expiry_dt - sample_dt).days
        if dte < 0:
            continue
        if not include_0dte and dte == 0:
            continue
        if dte > days_out:
            continue
        fetch_dt = datetime.fromisoformat(str(row["last_observed_at"]))
        result.setdefault(sample_dt, {}).setdefault(expiry_dt, []).append(
            (fetch_dt, Path(str(row["path"])))
        )

    # Keep only the last lookback_days sample dates
    all_sample_dates = sorted(result)
    if len(all_sample_dates) > lookback_days:
        keep = set(all_sample_dates[-lookback_days:])
        result = {d: v for d, v in result.items() if d in keep}

    return result


@st.cache_data(ttl=1800)
def find_downsampled_snapshots_for_lookback(
    symbol: str,
    lookback_days: int,
    interval_minutes: int,
    days_out: int = 90,
    include_0dte: bool = True,
    data_dir: Path = OPTIONS_DIR,
    metadata_db_path: Path | None = None,
) -> dict[date, dict[date, list[tuple[datetime, Path]]]]:
    """Return interval-downsampled snapshots per (sample_date, expiry) over a lookback window.

    Downsampling is performed in SQL: keeps the latest snapshot per
    (sample_date, expiry, N-minute interval bucket). This avoids loading all raw
    metadata into Python before downsampling.

    Args:
        symbol: Option symbol (e.g. "SPXW").
        lookback_days: Number of calendar days to look back from today.
        interval_minutes: Bucket width in minutes. Must divide evenly into 60.
        days_out: Max DTE to include on each sample date.
        include_0dte: Whether to include same-day expirations.
        data_dir: Unused (kept for API consistency).
        metadata_db_path: Override for metadata DB path.

    Returns:
        {sample_date: {expiry_date: [(fetch_datetime, path)]}} — one entry per interval
        bucket, sorted by time ascending.
    """
    del data_dir
    today = date.today()
    lookback_start = today - timedelta(days=lookback_days * 2)

    # Interval bucket: integer division of (hour*60 + minute) by interval_minutes.
    # SQLite strftime('%H') returns zero-padded hour string; CAST to int for arithmetic.
    rows = _fetch_metadata_rows(
        """
        SELECT sample_date, expiration_date, last_observed_at, path
        FROM (
            SELECT
                DATE(last_observed_at)  AS sample_date,
                expiration_date,
                last_observed_at,
                path,
                ROW_NUMBER() OVER (
                    PARTITION BY
                        DATE(last_observed_at),
                        expiration_date,
                        (CAST(strftime('%H', last_observed_at) AS INTEGER) * 60
                         + CAST(strftime('%M', last_observed_at) AS INTEGER))
                        / ?
                    ORDER BY last_observed_at DESC, path DESC
                ) AS row_num
            FROM file_metadata_cache
            WHERE dataset_type = ?
              AND provider_name = ?
              AND ticker      = ?
              AND last_observed_at >= ?
              AND last_observed_at <  ?
              AND last_observed_at IS NOT NULL
        )
        WHERE row_num = 1
        ORDER BY sample_date ASC, expiration_date ASC, last_observed_at ASC
        """,
        (
            interval_minutes,
            _OPTIONS_DATASET_TYPE,
            _OPTIONS_PROVIDER,
            symbol,
            lookback_start.isoformat(),
            today.isoformat(),
        ),
        metadata_db_path,
    )

    result: dict[date, dict[date, list[tuple[datetime, Path]]]] = {}
    for row in rows:
        sample_dt = date.fromisoformat(str(row["sample_date"]))
        expiry_dt = date.fromisoformat(str(row["expiration_date"]))
        dte = (expiry_dt - sample_dt).days
        if dte < 0:
            continue
        if not include_0dte and dte == 0:
            continue
        if dte > days_out:
            continue
        fetch_dt = datetime.fromisoformat(str(row["last_observed_at"]))
        result.setdefault(sample_dt, {}).setdefault(expiry_dt, []).append(
            (fetch_dt, Path(str(row["path"])))
        )

    all_sample_dates = sorted(result)
    if len(all_sample_dates) > lookback_days:
        keep = set(all_sample_dates[-lookback_days:])
        result = {d: v for d, v in result.items() if d in keep}

    return result


# NOTE: unused — kept for potential EOD historical analysis features
@st.cache_data(ttl=1800)
def find_eod_snapshots_for_lookback(
    symbol: str,
    lookback_days: int,
    days_out: int = 90,
    include_0dte: bool = True,
    data_dir: Path = OPTIONS_DIR,
    metadata_db_path: Path | None = None,
) -> dict[date, dict[date, Path]]:
    """Return end-of-day snapshots for all expiries over a historical lookback window.

    Uses a single SQL query to fetch the latest snapshot per (sample_date, expiry)
    across the full lookback period, avoiding per-date round-trips to the metadata DB.

    Args:
        symbol: Option symbol (e.g. "SPXW").
        lookback_days: Number of trading days to look back from today.
        days_out: Max DTE to include on each sample date.
        include_0dte: Whether to include same-day expirations.
        data_dir: Unused (kept for API consistency).
        metadata_db_path: Override for metadata DB path.

    Returns:
        {sample_date: {expiry_date: path}} — one path per (sample_date, expiry).
    """
    del data_dir
    today = date.today()
    lookback_start = today - timedelta(days=lookback_days * 2)  # 2x buffer for weekends/holidays

    rows = _fetch_metadata_rows(
        """
        SELECT sample_date, expiration_date, path
        FROM (
            SELECT
                DATE(last_observed_at) AS sample_date,
                expiration_date,
                path,
                ROW_NUMBER() OVER (
                    PARTITION BY DATE(last_observed_at), expiration_date
                    ORDER BY last_observed_at DESC, path DESC
                ) AS row_num
            FROM file_metadata_cache
            WHERE dataset_type = ?
              AND provider_name = ?
              AND ticker = ?
              AND last_observed_at >= ?
              AND last_observed_at < ?
        )
        WHERE row_num = 1
        ORDER BY sample_date ASC, expiration_date ASC
        """,
        (
            _OPTIONS_DATASET_TYPE,
            _OPTIONS_PROVIDER,
            symbol,
            lookback_start.isoformat(),
            today.isoformat(),
        ),
        metadata_db_path,
    )

    result: dict[date, dict[date, Path]] = {}
    for row in rows:
        sample_dt = date.fromisoformat(str(row["sample_date"]))
        expiry_dt = date.fromisoformat(str(row["expiration_date"]))

        # Filter: expiry must be within days_out of sample date
        dte = (expiry_dt - sample_dt).days
        if dte < 0:
            continue
        if not include_0dte and dte == 0:
            continue
        if dte > days_out:
            continue

        if sample_dt not in result:
            result[sample_dt] = {}
        result[sample_dt][expiry_dt] = Path(str(row["path"]))

    # Keep only the last lookback_days sample dates
    all_sample_dates = sorted(result)
    if len(all_sample_dates) > lookback_days:
        keep = set(all_sample_dates[-lookback_days:])
        result = {d: v for d, v in result.items() if d in keep}

    return result


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


@st.cache_data(ttl=30)
def find_snapshots_for_window_on_date(
    symbol: str,
    sample_date: date,
    expiries: tuple[date, ...],
    data_dir: Path = OPTIONS_DIR,
    metadata_db_path: Path | None = None,
) -> dict[date, list[tuple[datetime, Path]]]:
    """Return per-expiry snapshots for a symbol/sample_date, sorted by timestamp."""
    del data_dir
    grouped: dict[date, list[tuple[datetime, Path]]] = {}
    for expiry in expiries:
        snapshots = find_snapshots_for_expiry_on_date(
            symbol,
            expiry=expiry,
            sample_date=sample_date,
            metadata_db_path=metadata_db_path,
        )
        if snapshots:
            grouped[expiry] = snapshots
    return grouped


def select_window_snapshots_at_or_before(
    grouped_snapshots: dict[date, list[tuple[datetime, Path]]],
    replay_time: datetime,
) -> dict[date, Path]:
    """Select one snapshot per expiry using latest snapshot at or before replay_time."""
    selected: dict[date, Path] = {}
    for expiry, snapshots in grouped_snapshots.items():
        chosen_path: Path | None = None
        for ts, path in snapshots:
            if ts <= replay_time:
                chosen_path = path
            else:
                break
        if chosen_path is not None:
            selected[expiry] = chosen_path
    return selected


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

    Filters to expiry_range and downsamples to rows where sampled_at falls on an
    interval_minutes boundary (minute-of-day % interval_minutes == 0).
    """
    start_str = expiry_range[0].isoformat()
    end_str = expiry_range[1].isoformat()
    query = f"""
        SELECT * FROM read_parquet('{parquet_glob}')
        WHERE expiration_date BETWEEN '{start_str}' AND '{end_str}'
          AND (
            CAST(strftime('%H', CAST(sampled_at AS TIMESTAMPTZ)) AS INTEGER) * 60
            + CAST(strftime('%M', CAST(sampled_at AS TIMESTAMPTZ)) AS INTEGER)
          ) % {interval_minutes} = 0
        ORDER BY sampled_at, expiration_date
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
