"""Candle (OHLCV) data loader with caching."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from options_monitor.config import CANDLE_DIR

_FREQ_TO_SUFFIX: dict[str, str] = {
    "day": "day",
    "1min": "1min",
    "5min": "5min",
    "30min": "30min",
}

_CANDLE_DTYPES: dict[str, str] = {
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume": "float64",
}


def _candle_path(symbol: str, freq: str, data_dir: Path = CANDLE_DIR) -> Path:
    suffix = _FREQ_TO_SUFFIX.get(freq, freq)
    return data_dir / f"{symbol}_{suffix}.csv"


@st.cache_data(ttl=300)
def _load_full_candles(symbol: str, freq: str, data_dir: Path = CANDLE_DIR) -> pd.DataFrame:
    """Load the complete candle CSV into memory (cached by symbol/freq/dir only)."""
    path = _candle_path(symbol, freq, data_dir)
    if not path.exists():
        raise FileNotFoundError(f"Candle file not found: {path}")

    df = pd.read_csv(path, parse_dates=["datetime"], dtype=_CANDLE_DTYPES)  # type: ignore[arg-type]
    return df[["datetime", "open", "high", "low", "close", "volume"]]


def load_candles(
    symbol: str,
    freq: str,
    start: date | None = None,
    end: date | None = None,
    data_dir: Path = CANDLE_DIR,
) -> pd.DataFrame:
    """Return candle data, optionally filtered to [start, end].

    The full file is cached by _load_full_candles; this wrapper slices from the
    cache so repeated calls with different date ranges don't re-read from disk.
    """
    df = _load_full_candles(symbol, freq, data_dir)

    tz = df["datetime"].dt.tz
    if start is not None:
        start_ts = pd.Timestamp(start, tz="UTC") if tz is not None else pd.Timestamp(start)
        df = df[df["datetime"] >= start_ts]
    if end is not None:
        end_ts = pd.Timestamp(end, tz="UTC") if tz is not None else pd.Timestamp(end)
        df = df[df["datetime"] <= end_ts]

    return df.reset_index(drop=True)


@st.cache_data(ttl=300)
def list_available_dates(
    symbol: str, freq: str, data_dir: Path = CANDLE_DIR
) -> tuple[datetime, datetime]:
    """Return (earliest, latest) datetime available for the given symbol and frequency."""
    df = _load_full_candles(symbol, freq, data_dir)
    start_dt: datetime = df["datetime"].iloc[0].to_pydatetime()
    end_dt: datetime = df["datetime"].iloc[-1].to_pydatetime()
    return start_dt, end_dt
