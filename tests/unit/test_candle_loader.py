"""Tests for the candle data loader."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest
from options_monitor.data.candles import list_available_dates, load_candles


def test_load_candles_returns_expected_columns() -> None:
    df = load_candles("SPX", "day")
    assert list(df.columns) == ["datetime", "open", "high", "low", "close", "volume"]


def test_load_candles_date_range_filter() -> None:
    start = date(2026, 1, 1)
    end = date(2026, 2, 1)
    df = load_candles("SPX", "day", start=start, end=end)
    tz = df["datetime"].dt.tz
    assert df["datetime"].min() >= pd.Timestamp("2026-01-01", tz=tz)
    assert df["datetime"].max() <= pd.Timestamp("2026-02-01", tz=tz)


def test_load_candles_raises_for_missing_symbol() -> None:
    with pytest.raises(FileNotFoundError):
        load_candles("NOTREAL", "day")


def test_list_available_dates_returns_range() -> None:
    start, end = list_available_dates("SPX", "day")
    assert isinstance(start, datetime)
    assert isinstance(end, datetime)
    assert end > start
