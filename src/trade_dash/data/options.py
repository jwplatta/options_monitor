"""Options chain snapshot loader."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from trade_dash.config import OPTIONS_DIR, TICKRAKE_DB_PATH

_OPTIONS_DTYPES: dict[str, Any] = {
    "strike": "float64",
    "open_interest": "float64",
    "gamma": "float64",
    "delta": "float64",
    "theta": "float64",
    "vega": "float64",
    "theoretical_volatility": "float64",
    "underlying_price": "float64",
    "mark": "float64",
    "bid": "float64",
    "ask": "float64",
    "last": "float64",
    "last_size": "float64",
    "total_volume": "float64",
}

_OPTIONS_DATASET_TYPE = "options"
_OPTIONS_PROVIDER = "schwab"


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
    return {
        date.fromisoformat(str(row["expiration_date"])): Path(str(row["path"])) for row in rows
    }


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


@st.cache_data(ttl=3600)
def load_options_snapshot(path: Path) -> pd.DataFrame:
    """Load a single options snapshot CSV with typed columns."""
    if not path.exists():
        raise FileNotFoundError(f"Options snapshot path from metadata DB does not exist: {path}")
    df = pd.read_csv(path, dtype=_OPTIONS_DTYPES)  # type: ignore[arg-type]
    df["expiration_date"] = pd.to_datetime(df["expiration_date"])
    return df
