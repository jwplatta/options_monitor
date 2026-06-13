"""Shared tick and timezone helpers for price charts."""

from __future__ import annotations

import pandas as pd

_INTRADAY_FREQS = {"1min", "5min", "30min"}


def to_ct(datetimes: pd.Series) -> pd.Series:
    """Convert a UTC-aware (or naive) datetime series to tz-naive CT datetimes."""
    if datetimes.dt.tz is not None:
        result: pd.Series = datetimes.dt.tz_convert("America/Chicago").dt.tz_localize(None)
        return result
    return datetimes


def intraday_ticks(datetimes: pd.Series, freq: str) -> tuple[list[int], list[str]]:
    """Time-based ticks for integer-index intraday charts (labels in CT).

    Shows one label per hour for 1min/5min data, one per 2 hours for 30min data.
    Day boundaries get a date label; within-day ticks get HH:MM CT.
    """
    ct = to_ct(datetimes)
    interval_minutes = {"1min": 60, "5min": 60, "30min": 120}.get(freq, 60)
    tick_vals: list[int] = []
    tick_text: list[str] = []
    prev_date: pd.Timestamp | None = None
    for idx, ts in enumerate(ct):
        minute = ts.hour * 60 + ts.minute
        on_boundary = minute % interval_minutes == 0
        is_day_start = prev_date is None or ts.normalize() != prev_date
        if is_day_start or on_boundary:
            tick_vals.append(idx)
            if is_day_start:
                tick_text.append(ts.strftime("%-m/%-d"))
            else:
                tick_text.append(ts.strftime("%H:%M"))
        if is_day_start:
            prev_date = ts.normalize()
    return tick_vals, tick_text


def daily_ticks(datetimes: pd.Series) -> tuple[list[pd.Timestamp], list[str]]:
    """Adaptive date ticks for daily charts based on date-range width."""
    n_days = len(datetimes)
    if n_days <= 30:
        step = 1
        fmt = "%-m/%-d"
    elif n_days <= 90:
        step = 5
        fmt = "%-m/%-d"
    elif n_days <= 365:
        step = 15
        fmt = "%-m/%-d"
    else:
        step = 30
        fmt = "%b '%y"
    indices = range(0, n_days, step)
    tick_vals = [datetimes.iloc[i] for i in indices]
    tick_text = [datetimes.iloc[i].strftime(fmt) for i in indices]
    return tick_vals, tick_text
