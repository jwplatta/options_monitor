"""Options chain snapshot loader."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from trade_dash.config import OPTIONS_DIR

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


def _iter_snapshot_dirs(data_dir: Path, reverse: bool = False) -> list[tuple[date, Path]]:
    """Return valid dated snapshot directories under the provider root."""
    snapshot_dirs: list[tuple[date, Path]] = []
    for year_dir in data_dir.iterdir() if data_dir.exists() else []:
        if not year_dir.is_dir():
            continue
        for month_dir in year_dir.iterdir():
            if not month_dir.is_dir():
                continue
            for day_dir in month_dir.iterdir():
                if not day_dir.is_dir():
                    continue
                try:
                    folder_date = date(
                        int(year_dir.name),
                        int(month_dir.name),
                        int(day_dir.name),
                    )
                except ValueError:
                    continue
                snapshot_dirs.append((folder_date, day_dir))
    return sorted(snapshot_dirs, key=lambda item: item[0], reverse=reverse)


def _iter_symbol_snapshots(directory: Path, symbol: str) -> list[tuple[date, datetime, Path]]:
    """Return parsed snapshot metadata for one symbol within a dated directory."""
    snapshots: list[tuple[date, datetime, Path]] = []
    for path in directory.glob(f"{symbol}_exp*.csv"):
        parsed = _parse_filename(path)
        if parsed is None:
            continue
        exp_date, fetch_dt = parsed
        snapshots.append((exp_date, fetch_dt, path))
    return snapshots


@st.cache_data(ttl=300)
def list_expirations(
    symbol: str,
    data_dir: Path = OPTIONS_DIR,
) -> list[date]:
    """Return sorted list of all available expiration dates from filenames (no CSV reads)."""
    seen: set[date] = set()
    for _, snapshot_dir in _iter_snapshot_dirs(data_dir):
        for exp_date, _, _ in _iter_symbol_snapshots(snapshot_dir, symbol):
            seen.add(exp_date)
    return sorted(seen)


@st.cache_data(ttl=30)
def find_latest_snapshots(
    symbol: str,
    start_date: date,
    days_out: int,
    include_0dte: bool = True,
    data_dir: Path = OPTIONS_DIR,
) -> dict[date, Path]:
    """Return {expiry_date: most_recent_snapshot_path} for expirations in window."""
    target_expiries = {
        date.fromordinal(start_date.toordinal() + offset)
        for offset in range(days_out + 1)
        if include_0dte or offset > 0
    }
    best: dict[date, Path] = {}

    for _, snapshot_dir in _iter_snapshot_dirs(data_dir, reverse=True):
        latest_for_day: dict[date, tuple[datetime, Path]] = {}
        for exp_date, fetch_dt, path in _iter_symbol_snapshots(snapshot_dir, symbol):
            if exp_date not in target_expiries:
                continue
            if exp_date in best:
                continue
            current = latest_for_day.get(exp_date)
            if current is None or fetch_dt > current[0]:
                latest_for_day[exp_date] = (fetch_dt, path)
        for exp_date, (_, path) in latest_for_day.items():
            best[exp_date] = path
        if len(best) == len(target_expiries):
            break

    return {exp: path for exp, path in sorted(best.items())}


@st.cache_data(ttl=30)
def find_all_snapshots_for_expiry(
    symbol: str,
    expiry: date,
    data_dir: Path = OPTIONS_DIR,
) -> list[tuple[datetime, Path]]:
    """Return all (fetch_datetime, path) pairs for a given expiry, sorted by time."""
    results: list[tuple[datetime, Path]] = []
    for _, snapshot_dir in _iter_snapshot_dirs(data_dir):
        for exp_date, fetch_dt, path in _iter_symbol_snapshots(snapshot_dir, symbol):
            if exp_date == expiry:
                results.append((fetch_dt, path))
    return sorted(results)


@st.cache_data(ttl=3600)
def load_options_snapshot(path: Path) -> pd.DataFrame:
    """Load a single options snapshot CSV with typed columns."""
    df = pd.read_csv(path, dtype=_OPTIONS_DTYPES)  # type: ignore[arg-type]
    df["expiration_date"] = pd.to_datetime(df["expiration_date"])
    return df
