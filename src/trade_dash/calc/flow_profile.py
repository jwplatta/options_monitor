"""Flow Profile calc: VWEMA trade direction × delta-weighted volume → per-strike aggregated flow."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from trade_dash.data.options import load_options_snapshot

_CHICAGO = ZoneInfo("America/Chicago")


def _to_chicago(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(_CHICAGO).replace(tzinfo=None)


def compute_flow_profile(
    snapshots: list[tuple[datetime, Path]],
    sample_date: date,
    lookback_window: int = 5,
    mode: str = "lookback",
    contract_filter: str = "BOTH",
    ema_span: int = 20,
    as_of: datetime | None = None,
) -> tuple[list[float], list[float], list[float]]:
    """Compute per-strike aggregated flow for a single trading session.

    Returns (strikes, call_flow_by_strike, put_flow_by_strike).
    strikes: sorted unique strike values present in the result.
    call/put_flow_by_strike: parallel arrays aligned to strikes.
    mode: "lookback" (volume delta over lookback_window) or "cumulative" (total volume).
    as_of: if provided, only snapshots with timestamp <= as_of are included.
    """
    if mode not in ("lookback", "cumulative"):
        raise ValueError(f"mode must be 'lookback' or 'cumulative', got {mode!r}")

    if not snapshots:
        return [], [], []

    # Filter to sample_date in Chicago time, sort ascending.
    session = sorted(
        ((ts, path) for ts, path in snapshots if _to_chicago(ts).date() == sample_date),
        key=lambda x: x[0],
    )
    if as_of is not None:
        session = [(ts, path) for ts, path in session if ts <= as_of]
    if not session:
        return [], [], []

    # Load all session snapshots, tag with UTC timestamp.
    frames: list[pd.DataFrame] = []
    for ts, path in session:
        df = load_options_snapshot(path).copy()
        df["_ts"] = ts
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)

    # Coerce required numeric columns, uppercase contract_type, drop bad rows.
    for col in ["bid", "ask", "last", "total_volume", "delta", "strike"]:
        combined[col] = pd.to_numeric(combined[col], errors="coerce")
    combined["contract_type"] = combined["contract_type"].str.upper()
    combined = combined.dropna(subset=["bid", "ask", "last", "total_volume", "delta", "strike"])
    combined = combined[combined["total_volume"] > 0]
    # Drop rows where last is outside the bid/ask — stale print, trade_position is meaningless.
    last_in_spread = (combined["last"] >= combined["bid"]) & (combined["last"] <= combined["ask"])
    combined = combined[last_in_spread]

    if combined.empty:
        return [], [], []

    # Apply contract_filter.
    if contract_filter == "CALL":
        combined = combined[combined["contract_type"] == "CALL"]
    elif contract_filter == "PUT":
        combined = combined[combined["contract_type"] == "PUT"]

    if combined.empty:
        return [], [], []

    # Per-contract flow calculation.
    contract_cols = ["strike", "expiration_date", "contract_type"]
    combined = combined.sort_values(contract_cols + ["_ts"])

    flow_rows: list[dict[str, object]] = []
    for _, grp in combined.groupby(contract_cols, sort=False):
        grp = grp.sort_values("_ts").copy()

        spread = (grp["ask"] - grp["bid"]).clip(lower=0.01)
        trade_position = ((grp["last"] - grp["bid"]) / spread).clip(0.0, 1.0)
        volume = grp["total_volume"]

        # Volume-weighted EMA of trade_position.
        weighted = trade_position * volume
        num_ema = weighted.ewm(span=ema_span, adjust=False).mean()
        den_ema = volume.ewm(span=ema_span, adjust=False).mean()
        den_safe = den_ema.replace(0.0, np.nan)
        vwema_tp = (num_ema / den_safe).fillna(0.5)
        trade_direction = (vwema_tp - 0.5) * 2

        if mode == "lookback":
            new_volume = (grp["total_volume"] - grp["total_volume"].shift(lookback_window)).clip(
                lower=0.0
            ).fillna(0.0)
        else:
            new_volume = grp["total_volume"]

        flow = new_volume * trade_direction * grp["delta"].abs() * 100

        # Only the last snapshot row per contract contributes to the profile.
        last_idx = grp.index[-1]
        flow_val = flow.loc[last_idx]
        if pd.isna(flow_val):
            continue
        strike_val = float(grp["strike"].iloc[-1])
        ct = str(grp["contract_type"].iloc[-1])
        flow_rows.append({"strike": strike_val, "flow": float(flow_val), "contract_type": ct})

    if not flow_rows:
        return [], [], []

    flow_df = pd.DataFrame(flow_rows)

    call_by_strike = (
        flow_df[flow_df["contract_type"] == "CALL"].groupby("strike")["flow"].sum()
    )
    put_by_strike = (
        flow_df[flow_df["contract_type"] == "PUT"].groupby("strike")["flow"].sum()
    )

    all_strikes = sorted(set(call_by_strike.index) | set(put_by_strike.index))
    strike_index = pd.Index(all_strikes, name="strike")

    call_aligned = call_by_strike.reindex(strike_index, fill_value=0.0).tolist()
    put_aligned = put_by_strike.reindex(strike_index, fill_value=0.0).tolist()

    return all_strikes, call_aligned, put_aligned
