"""Moving average and VWAP calculation functions."""

from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    """Simple moving average."""
    result: pd.Series = series.rolling(window=window).mean()
    return result


def _vwap_for_groups(
    candles: pd.DataFrame, groups: pd.Series
) -> tuple[pd.Series, pd.Series]:
    """VWAP and volume-weighted std dev for the given grouping key.

    Uses E[X²] − E[X]² identity; single groupby pass over three columns at once.
    Returns (vwap, std), both reset_index(drop=True), aligned to candles.index.
    """
    tp = (candles["high"] + candles["low"] + candles["close"]) / 3
    vol = candles["volume"]
    agg = pd.DataFrame(
        {"vol": vol, "tp_vol": tp * vol, "tp2_vol": tp**2 * vol}
    ).groupby(groups).cumsum()
    v = agg["tp_vol"] / agg["vol"]
    std = (agg["tp2_vol"] / agg["vol"] - v**2).clip(lower=0).pow(0.5)
    return v.reset_index(drop=True), std.reset_index(drop=True)


def vwap_session(candles: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Session VWAP + 1-σ width. Resets at each RTH open (calendar day)."""
    return _vwap_for_groups(candles, candles["datetime"].dt.date)


def vwap_weekly(candles: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Weekly anchored VWAP + 1-σ width. Resets each Monday (ISO week)."""
    iso = candles["datetime"].dt.isocalendar()
    # Numeric key avoids slow string operations: year*100 + week is unique per ISO week.
    week_key = iso["year"] * 100 + iso["week"]
    return _vwap_for_groups(candles, week_key)


def validate_windows(fast: int, slow: int) -> None:
    """Raise ValueError if fast >= slow or either is non-positive."""
    if fast <= 0 or slow <= 0:
        raise ValueError(f"Window sizes must be positive, got fast={fast}, slow={slow}")
    if fast >= slow:
        raise ValueError(f"fast window ({fast}) must be less than slow window ({slow})")
