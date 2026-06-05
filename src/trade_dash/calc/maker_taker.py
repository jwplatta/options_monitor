"""Maker-Taker flow metric: aggressor-signed option flow by strike."""

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


def compute_maker_taker_flow(
    snapshots: list[tuple[datetime, Path]],
    spot: float,
    moneyness_pct: float = 0.15,
    contract_filter: str = "CALL",
    bucket_minutes: int = 5,
    weight_by: str = "last_size",
    target_date: date | None = None,
    top_n_strikes: int = 10,
) -> tuple[list[datetime], list[float], list[float], list[datetime], list[float]]:
    """Compute maker-taker bubble chart data for a given expiry's intraday snapshots.

    Classifies each sampled contract as aggressive buying (+1) or selling (-1)
    with a hybrid rule: quote-side when the last trade is near the ask/bid,
    otherwise tick-rule fallback versus the prior sampled bucket's ``last``.
    When weighting by ``total_volume``, uses the bucket-over-bucket change in
    cumulative volume for each contract. Returns the top N strikes by total
    absolute flow.

    Returns:
        timestamps:    one datetime per (bucket, strike) data point
        strikes:       parallel to timestamps
        weighted_flows: parallel to timestamps (positive=buy, negative=sell)
        bucket_times:  one datetime per unique bucket (for price overlay x-axis)
        bucket_prices: underlying_price per bucket (for price overlay y-axis)
    """
    if not snapshots:
        return [], [], [], [], []

    local_target_date = target_date if target_date is not None else date.today()

    # Filter to the selected Chicago-local session date, then sort ascending.
    today_snapshots = sorted(
        ((ts, path) for ts, path in snapshots if _to_chicago(ts).date() == local_target_date),
        key=lambda x: x[0],
    )
    if not today_snapshots:
        return [], [], [], [], []

    # Select the LAST snapshot within each bucket (overwrite on each match)
    bucket_map: dict[datetime, tuple[datetime, Path]] = {}
    for ts, path in today_snapshots:
        floored = (ts.minute // bucket_minutes) * bucket_minutes
        bucket = ts.replace(minute=floored, second=0, microsecond=0)
        bucket_map[bucket] = (ts, path)  # last one wins

    # Load selected snapshots
    frames: list[pd.DataFrame] = []
    price_by_bucket: dict[datetime, float] = {}
    for bucket_key in sorted(bucket_map):
        ts, path = bucket_map[bucket_key]
        df = load_options_snapshot(path).copy()
        df["_ts"] = bucket_key
        frames.append(df)
        price_val = pd.to_numeric(df["underlying_price"], errors="coerce").dropna()
        if not price_val.empty:
            price_by_bucket[bucket_key] = float(price_val.iloc[0])

    if not frames:
        return [], [], [], [], []

    combined = pd.concat(frames, ignore_index=True)

    # Coerce required numeric columns; return empty if any required column is absent
    weight_col = weight_by if weight_by in ("last_size", "total_volume") else "last_size"
    required_cols = ["bid", "ask", "last", weight_col]
    for col in required_cols:
        if col not in combined.columns:
            return [], [], [], [], []
        combined[col] = pd.to_numeric(combined[col], errors="coerce")
    combined = combined.dropna(subset=required_cols)

    if combined.empty:
        return [], [], [], [], []

    # Moneyness filter
    combined["_strike"] = pd.to_numeric(combined["strike"], errors="coerce")
    combined = combined.dropna(subset=["_strike"])
    combined = combined[(combined["_strike"] - spot).abs() / spot <= moneyness_pct]

    if combined.empty:
        return [], [], [], [], []

    # Contract type filter
    combined = combined[combined["contract_type"].str.upper() == contract_filter.upper()]

    if combined.empty:
        return [], [], [], [], []

    combined = combined.copy()
    contract_cols = ["symbol", "expiration_date", "contract_type", "_strike"]
    combined = combined.sort_values(contract_cols + ["_ts"])

    prev_last = combined.groupby(contract_cols, sort=False)["last"].shift(1)
    spread = (combined["ask"] - combined["bid"]).clip(lower=0.0)
    quote_eps = spread.mul(0.1).clip(lower=0.01)

    near_ask = combined["last"] >= (combined["ask"] - quote_eps)
    near_bid = combined["last"] <= (combined["bid"] + quote_eps)
    tick_up = combined["last"] > prev_last
    tick_down = combined["last"] < prev_last

    combined["_sentiment"] = 0.0
    combined.loc[near_ask, "_sentiment"] = 1.0
    combined.loc[near_bid, "_sentiment"] = -1.0
    combined.loc[~near_ask & ~near_bid & tick_up, "_sentiment"] = 1.0
    combined.loc[~near_ask & ~near_bid & tick_down, "_sentiment"] = -1.0

    if weight_col == "total_volume":
        volume_delta = (
            combined.groupby(contract_cols, sort=False)["total_volume"]
            .diff()
            .fillna(0.0)
        )
        combined["_weight"] = volume_delta
    else:
        combined["_weight"] = combined[weight_col]
    combined["_weighted_flow"] = combined["_sentiment"] * combined["_weight"]

    # Aggregate (bucket_ts, strike) by sum — net pressure per strike per bucket
    flow_df = (
        combined.groupby(["_ts", "_strike"], as_index=False)["_weighted_flow"]
        .sum()
    )

    if flow_df.empty:
        return [], [], [], [], []

    # Top-N strike filter: rank by total absolute flow across all buckets
    strike_totals = flow_df.groupby("_strike")["_weighted_flow"].apply(
        lambda s: s.abs().sum()
    )
    top_strikes = set(
        strike_totals.nlargest(top_n_strikes).index.tolist()
    )
    flow_df = flow_df[flow_df["_strike"].isin(top_strikes)]

    if flow_df.empty:
        return [], [], [], [], []

    # Sort and build parallel flat arrays
    flow_df = flow_df.sort_values(["_ts", "_strike"])

    timestamps = [_to_chicago(ts) for ts in flow_df["_ts"].tolist()]
    strikes = [float(s) for s in flow_df["_strike"].tolist()]
    weighted_flows = [float(f) for f in flow_df["_weighted_flow"].tolist()]

    sorted_buckets = sorted(price_by_bucket)
    bucket_times = [_to_chicago(b) for b in sorted_buckets]
    bucket_prices = [price_by_bucket[b] for b in sorted_buckets]

    return timestamps, strikes, weighted_flows, bucket_times, bucket_prices
