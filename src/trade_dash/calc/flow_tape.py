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


def _load_session(
    snapshots: list[tuple[datetime, Path]],
    sample_date: date,
    spot: float,
    contract_filter: str,
    itm_strike_limit: int,
) -> pd.DataFrame:
    """Load, clean, and filter all session snapshots into a single DataFrame.

    Returns an empty DataFrame if no usable data is found.
    """
    session = sorted(
        ((ts, path) for ts, path in snapshots if _to_chicago(ts).date() == sample_date),
        key=lambda x: x[0],
    )
    if not session:
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    for ts, path in session:
        df = load_options_snapshot(path).copy()
        df["_ts"] = ts
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)

    for col in ["bid", "ask", "last", "total_volume", "delta", "strike"]:
        combined[col] = pd.to_numeric(combined[col], errors="coerce")
    combined["contract_type"] = combined["contract_type"].str.upper()
    combined = combined.dropna(subset=["bid", "ask", "last", "total_volume", "delta", "strike"])
    combined = combined[combined["total_volume"] > 0]

    # Drop stale prints — last outside bid/ask produces a meaningless trade_position.
    last_in_spread = (combined["last"] >= combined["bid"]) & (combined["last"] <= combined["ask"])
    combined = combined[last_in_spread]

    if combined.empty:
        return pd.DataFrame()

    # Strike filter: all OTM + itm_strike_limit nearest ITM strikes per side.
    call_mask = combined["contract_type"] == "CALL"
    put_mask = combined["contract_type"] == "PUT"

    call_strikes = combined.loc[call_mask, "strike"]
    put_strikes = combined.loc[put_mask, "strike"]

    call_otm = set(call_strikes[call_strikes > spot].unique())
    call_itm_candidates = sorted(call_strikes[call_strikes <= spot].unique(), reverse=True)
    call_itm = set(call_itm_candidates[:itm_strike_limit])
    put_otm = set(put_strikes[put_strikes < spot].unique())
    put_itm = set(sorted(put_strikes[put_strikes >= spot].unique())[:itm_strike_limit])

    strike_filter = (call_mask & combined["strike"].isin(call_otm | call_itm)) | (
        put_mask & combined["strike"].isin(put_otm | put_itm)
    )
    combined = combined[strike_filter]

    if combined.empty:
        return pd.DataFrame()

    if contract_filter == "CALL":
        combined = combined[combined["contract_type"] == "CALL"]
    elif contract_filter == "PUT":
        combined = combined[combined["contract_type"] == "PUT"]

    return combined


def _aggregate_flow(
    flow_rows: list[dict[str, object]],
) -> tuple[pd.Series, pd.Series, list[datetime]]:
    """Aggregate per-contract flow rows into per-timestamp call/put series.

    Returns (call_agg, put_agg, timestamps_chicago).
    """
    flow_df = pd.DataFrame(flow_rows)
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
    return call_agg, put_agg, timestamps_chicago


def _compute_new_flow(
    combined: pd.DataFrame,
    lookback_window: int,
    ema_span: int,
) -> tuple[list[datetime], list[float], list[float], list[float], list[float]]:
    """New Flow mode: per-snapshot volume delta × EMA trade direction, then cumsum.

    cum_call/cum_put: running cumsum of per-snapshot flow — slope shows current activity,
    level shows who has been winning the session.
    raw_call/raw_put: per-snapshot flow before cumsum (oscillator bars).
    """
    contract_cols = ["strike", "expiration_date", "contract_type"]
    combined = combined.sort_values(contract_cols + ["_ts"])

    flow_rows: list[dict[str, object]] = []
    for _, grp in combined.groupby(contract_cols, sort=False):
        grp = grp.sort_values("_ts").copy()

        spread = (grp["ask"] - grp["bid"]).clip(lower=0.01)
        trade_position = ((grp["last"] - grp["bid"]) / spread).clip(0.0, 1.0)
        ema_tp = trade_position.ewm(span=ema_span, adjust=False).mean()
        trade_direction = (ema_tp - 0.5) * 2

        new_volume = (
            (grp["total_volume"] - grp["total_volume"].shift(lookback_window))
            .clip(lower=0.0)
            .fillna(0.0)
        )
        flow = new_volume * trade_direction * grp["delta"].abs()

        for ts_val, flow_val, ct in zip(grp["_ts"], flow, grp["contract_type"], strict=True):
            if pd.isna(flow_val):
                continue
            flow_rows.append({"_ts": ts_val, "flow": float(flow_val), "contract_type": str(ct)})

    if not flow_rows:
        return [], [], [], [], []

    call_agg, put_agg, timestamps = _aggregate_flow(flow_rows)
    raw_call = call_agg.tolist()
    raw_put = put_agg.tolist()
    cum_call = call_agg.cumsum().tolist()
    cum_put = put_agg.cumsum().tolist()
    return timestamps, cum_call, cum_put, raw_call, raw_put


def _compute_cumulative_flow(
    combined: pd.DataFrame,
    ema_span: int,
    smooth_window: int = 5,
) -> tuple[list[datetime], list[float], list[float], list[float], list[float]]:
    """Cumulative Flow mode: volume-since-open x expanding-mean trade direction.

    At each snapshot T the value represents total directed pressure since market open.
    A rolling mean (smooth_window) is applied to reduce late-day noise from volume spikes.
    raw_call/raw_put: unsmoothed per-snapshot values (oscillator bars).
    """
    contract_cols = ["strike", "expiration_date", "contract_type"]
    combined = combined.sort_values(contract_cols + ["_ts"])

    flow_rows: list[dict[str, object]] = []
    for _, grp in combined.groupby(contract_cols, sort=False):
        grp = grp.sort_values("_ts").copy()

        spread = (grp["ask"] - grp["bid"]).clip(lower=0.01)
        trade_position = ((grp["last"] - grp["bid"]) / spread).clip(0.0, 1.0)
        ema_tp = trade_position.ewm(span=ema_span, adjust=False).mean()
        trade_direction = (ema_tp.expanding().mean() - 0.5) * 2

        vol_t0 = grp["total_volume"].iloc[0]
        new_volume = (grp["total_volume"] - vol_t0).clip(lower=0.0)
        flow = new_volume * trade_direction * grp["delta"].abs()

        for ts_val, flow_val, ct in zip(grp["_ts"], flow, grp["contract_type"], strict=True):
            if pd.isna(flow_val):
                continue
            flow_rows.append({"_ts": ts_val, "flow": float(flow_val), "contract_type": str(ct)})

    if not flow_rows:
        return [], [], [], [], []

    call_agg, put_agg, timestamps = _aggregate_flow(flow_rows)
    raw_call = call_agg.tolist()
    raw_put = put_agg.tolist()
    cum_call = call_agg.rolling(window=smooth_window, min_periods=1).mean().tolist()
    cum_put = put_agg.rolling(window=smooth_window, min_periods=1).mean().tolist()
    return timestamps, cum_call, cum_put, raw_call, raw_put


def compute_flow_tape(
    snapshots: list[tuple[datetime, Path]],
    spot: float,
    sample_date: date,
    lookback_window: int = 5,
    mode: str = "lookback",
    contract_filter: str = "BOTH",
    itm_strike_limit: int = 25,
    ema_span: int = 20,
) -> tuple[list[datetime], list[float], list[float], list[float], list[float]]:
    """Compute call and put flow series for a single trading session.

    Returns (timestamps, cum_call, cum_put, raw_call, raw_put).
    timestamps: Chicago-naive datetimes, one per snapshot.
    cum_call/cum_put: smoothed/cumulative flow for the trend line.
    raw_call/raw_put: per-snapshot flow for the oscillator bars.
    mode: "lookback" (new flow) or "cumulative" (flow since open).
    """
    if mode not in ("lookback", "cumulative"):
        raise ValueError(f"mode must be 'lookback' or 'cumulative', got {mode!r}")
    if not snapshots:
        return [], [], [], [], []

    combined = _load_session(snapshots, sample_date, spot, contract_filter, itm_strike_limit)
    if combined.empty:
        return [], [], [], [], []

    if mode == "lookback":
        return _compute_new_flow(combined, lookback_window, ema_span)
    else:
        return _compute_cumulative_flow(combined, ema_span, smooth_window=lookback_window)
