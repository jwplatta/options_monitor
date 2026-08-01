"""Volatility calculation functions."""

from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np
import pandas as pd
from scipy.stats import pearsonr


def realized_vol(prices: pd.Series, window: int, periods_per_year: int = 252) -> pd.Series:
    """Horizon-matched annualized realized volatility from log returns.

    Formula: 100 * sqrt((periods_per_year / window) * rolling_sum(log_return²))

    This matches the VIX construction: annualized variance is the sum of squared
    returns over the horizon scaled by (A / H_bars), where A is periods per year
    and H_bars is the window length. Use window=trading days in horizon and
    periods_per_year=252 for daily data; scale both proportionally for intraday.
    """
    log_returns: pd.Series = np.log(prices / prices.shift(1))
    rolling_sum: pd.Series = (log_returns ** 2).rolling(window=window).sum()
    return pd.Series(
        100.0 * np.sqrt((periods_per_year / window) * rolling_sum),
        index=prices.index,
    )


def iv_rv_spread(iv: pd.Series, rv: pd.Series) -> pd.Series:
    """Elementwise IV minus RV."""
    diff: pd.Series = iv - rv
    return diff


def vix_spx_correlation(spx: pd.DataFrame, vix: pd.DataFrame) -> float:
    """Pearson correlation between aligned SPX and VIX close series."""
    merged = pd.merge(
        spx[["datetime", "close"]].rename(columns={"close": "spx"}),
        vix[["datetime", "close"]].rename(columns={"close": "vix"}),
        on="datetime",
        how="inner",
    ).dropna()
    if len(merged) < 2:
        return float("nan")
    return float(pearsonr(merged["spx"].to_numpy(), merged["vix"].to_numpy()).statistic)


# NOTE: unused — kept for potential future use in the Vol tab
def expected_move(spot: float, vix9d_close: float) -> tuple[float, float]:
    """One-day expected move: ± spot * (VIX9D / 100) * sqrt(1/252).

    Returns (lower, upper).
    """
    move = spot * (vix9d_close / 100.0) * math.sqrt(1.0 / 252.0)
    return spot - move, spot + move


class RiskReversalResult(NamedTuple):
    """25-delta risk reversal components. All IV values are in percentage points."""

    rr: float  # IV_25d_call - IV_25d_put
    iv_25d_call: float  # theoretical_volatility at ~+0.25 delta call
    iv_25d_put: float  # theoretical_volatility at ~-0.25 delta put
    strike_25d_call: float  # strike of selected 25D call
    strike_25d_put: float  # strike of selected 25D put


def _interp_iv_at_delta(
    leg: pd.DataFrame,
    target_delta: float,
) -> tuple[float, float] | tuple[None, None]:
    """Linearly interpolate IV at `target_delta` from a sorted options leg.

    Sorts by delta ascending, finds the two rows that bracket the target, and
    interpolates IV (and strike) proportionally. Returns (None, None) if the
    target is out of range or only one row exists.
    """
    sorted_leg = leg.sort_values("delta")
    deltas = sorted_leg["delta"].to_numpy()
    ivs = sorted_leg["iv"].to_numpy()
    strikes = sorted_leg["K"].to_numpy()

    # Find index of first delta >= target
    idx = int(np.searchsorted(deltas, target_delta))

    if idx == 0 or idx >= len(deltas):
        # Target is outside the range of available deltas — fall back to nearest
        nearest = 0 if idx == 0 else len(deltas) - 1
        return float(ivs[nearest]), float(strikes[nearest])

    d_lo, d_hi = deltas[idx - 1], deltas[idx]
    iv_lo, iv_hi = ivs[idx - 1], ivs[idx]
    k_lo, k_hi = strikes[idx - 1], strikes[idx]

    span = d_hi - d_lo
    if span == 0.0:
        return float(iv_lo), float(k_lo)

    t = (target_delta - d_lo) / span
    return float(iv_lo + t * (iv_hi - iv_lo)), float(k_lo + t * (k_hi - k_lo))


def compute_risk_reversal(
    opts: pd.DataFrame,
    expiry: str | None = None,
) -> RiskReversalResult | None:
    """Compute 25-delta risk reversal for a single-expiry options snapshot.

    RR = IV_25d_call - IV_25d_put (percentage points).
    Positive → calls richer (upside bid). Negative → puts richer (fear/hedging).

    Args:
        opts: Options snapshot DataFrame for a single expiry.
        expiry: ISO date prefix to filter (e.g. "2026-05-07"). If None, all rows used.

    Returns:
        RiskReversalResult, or None if data is insufficient.
    """
    required = {"delta", "volatility", "contract_type", "strike"}
    if not required.issubset(opts.columns):
        return None

    df = opts.copy()
    if expiry is not None:
        df = df[df["expiration_date"].astype(str).str.startswith(expiry)]

    df["delta"] = pd.to_numeric(df["delta"], errors="coerce")
    df["iv"] = pd.to_numeric(df["volatility"], errors="coerce")
    df["K"] = pd.to_numeric(df["strike"], errors="coerce")
    df = df.dropna(subset=["delta", "iv", "K", "contract_type"])
    df = df[df["iv"] > 0]

    calls = df[df["contract_type"].str.upper() == "CALL"].copy()
    puts = df[df["contract_type"].str.upper() == "PUT"].copy()

    if calls.empty or puts.empty:
        return None

    iv_call, strike_call = _interp_iv_at_delta(calls, target_delta=0.25)
    iv_put, strike_put = _interp_iv_at_delta(puts, target_delta=-0.25)

    if iv_call is None or strike_call is None or iv_put is None or strike_put is None:
        return None

    return RiskReversalResult(
        rr=iv_call - iv_put,
        iv_25d_call=iv_call,
        iv_25d_put=iv_put,
        strike_25d_call=strike_call,
        strike_25d_put=strike_put,
    )
