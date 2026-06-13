"""Flow Tape calc: EMA trade direction × delta-weighted volume → cumulative call/put flow."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from trade_dash.data.options import load_options_snapshot

_CHICAGO = ZoneInfo("America/Chicago")


def _to_chicago(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(_CHICAGO).replace(tzinfo=None)


def compute_flow_tape(
    snapshots: list[tuple[datetime, Path]],
    spot: float,
    sample_date: date,
    lookback_window: int = 5,
    mode: str = "lookback",
    contract_filter: str = "BOTH",
    itm_strike_limit: int = 25,
    ema_span: int = 20,
) -> tuple[list[datetime], list[float], list[float]]:
    """Compute cumulative call and put flow series for a single trading session.

    Returns (timestamps, cumulative_call_flow, cumulative_put_flow).
    timestamps are Chicago-naive datetimes, one per snapshot in the session.
    mode: "lookback" (volume delta over lookback_window) or "cumulative" (total volume since open).
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
    # Drop rows where last is outside the bid/ask — indicates a stale print from a prior
    # session or an untouched strike. Such rows produce a meaningless trade_position.
    last_in_spread = (combined["last"] >= combined["bid"]) & (combined["last"] <= combined["ask"])
    combined = combined[last_in_spread]

    if combined.empty:
        return [], [], []

    # Strike filter: all OTM + itm_strike_limit nearest ITM strikes per contract side.
    call_mask = combined["contract_type"] == "CALL"
    put_mask = combined["contract_type"] == "PUT"

    call_strikes = combined.loc[call_mask, "strike"]
    put_strikes = combined.loc[put_mask, "strike"]

    # Calls: OTM = strike > spot, ITM = strike <= spot (nearest = largest <= spot)
    call_otm_strikes = set(call_strikes[call_strikes > spot].unique())
    call_itm_candidates = sorted(call_strikes[call_strikes <= spot].unique(), reverse=True)
    call_itm_strikes = set(call_itm_candidates[:itm_strike_limit])
    allowed_call_strikes = call_otm_strikes | call_itm_strikes

    # Puts: OTM = strike < spot, ITM = strike >= spot (nearest = smallest >= spot)
    put_otm_strikes = set(put_strikes[put_strikes < spot].unique())
    put_itm_candidates = sorted(put_strikes[put_strikes >= spot].unique())
    put_itm_strikes = set(put_itm_candidates[:itm_strike_limit])
    allowed_put_strikes = put_otm_strikes | put_itm_strikes

    strike_filter = (call_mask & combined["strike"].isin(allowed_call_strikes)) | (
        put_mask & combined["strike"].isin(allowed_put_strikes)
    )
    combined = combined[strike_filter]

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
        ema_tp = trade_position.ewm(span=ema_span, adjust=False).mean()
        trade_direction = (ema_tp - 0.5) * 2

        if mode == "lookback":
            new_volume = (
                grp["total_volume"] - grp["total_volume"].shift(lookback_window)
            ).clip(lower=0.0).fillna(0.0)
        else:
            new_volume = grp["total_volume"]

        flow = new_volume * trade_direction * grp["delta"].abs()

        for ts_val, flow_val, ct in zip(
            grp["_ts"], flow, grp["contract_type"], strict=True
        ):
            if pd.isna(flow_val):
                continue
            flow_rows.append({"_ts": ts_val, "flow": float(flow_val), "contract_type": str(ct)})

    if not flow_rows:
        return [], [], []

    flow_df = pd.DataFrame(flow_rows)

    # Aggregate per (timestamp, contract_type).
    agg = flow_df.groupby(["_ts", "contract_type"])["flow"].sum().reset_index()

    all_ts = sorted(agg["_ts"].unique())
    ts_index = pd.Index(all_ts, name="_ts")

    call_agg = (
        agg[agg["contract_type"] == "CALL"]
        .set_index("_ts")["flow"]
        .reindex(ts_index, fill_value=0.0)
    )
    put_agg = (
        agg[agg["contract_type"] == "PUT"]
        .set_index("_ts")["flow"]
        .reindex(ts_index, fill_value=0.0)
    )

    timestamps_chicago = [_to_chicago(ts) for ts in all_ts]
    cumulative_call = call_agg.cumsum().tolist()
    cumulative_put = put_agg.cumsum().tolist()

    return timestamps_chicago, cumulative_call, cumulative_put
