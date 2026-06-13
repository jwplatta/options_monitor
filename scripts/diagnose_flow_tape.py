"""Diagnostic: inspect top contributors to call-flow movement in a time window.

Usage:
    uv run python scripts/diagnose_flow_tape.py \
        --date 2026-06-11 \
        --expiry 2026-06-11 \
        --start-ct 12:00 \
        --end-ct 13:30 \
        --lookback 5 \
        --top 15
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

# Make sure trade_dash is importable from the repo root.
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from trade_dash.config import OPTIONS_DIR
from trade_dash.data.options import find_snapshots_for_expiry_on_date, load_options_snapshot

_CHICAGO = ZoneInfo("America/Chicago")


def _to_chicago(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(_CHICAGO).replace(tzinfo=None)


def _ct(h: int, m: int) -> time:
    return time(h, m)


def run(
    sample_date: date,
    expiry: date,
    window_start_ct: time,
    window_end_ct: time,
    lookback_window: int,
    top_n: int,
    ema_span: int,
) -> None:
    snapshots = find_snapshots_for_expiry_on_date(
        "SPXW", expiry=expiry, sample_date=sample_date, data_dir=OPTIONS_DIR
    )
    print(f"Loaded {len(snapshots)} snapshots for {sample_date} expiry={expiry}")
    if not snapshots:
        print("No snapshots — aborting.")
        return

    # Load all session snapshots.
    frames: list[pd.DataFrame] = []
    for ts, path in snapshots:
        df = load_options_snapshot(path).copy()
        df["_ts_utc"] = ts
        df["_ts_ct"] = _to_chicago(ts)
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)

    for col in ["bid", "ask", "last", "total_volume", "delta", "strike"]:
        combined[col] = pd.to_numeric(combined[col], errors="coerce")
    combined["contract_type"] = combined["contract_type"].str.upper()
    combined = combined.dropna(subset=["bid", "ask", "last", "total_volume", "delta", "strike"])
    combined = combined[combined["total_volume"] > 0]

    # Restrict to the inspection window.
    ct_times = combined["_ts_ct"].dt.time
    in_window = (ct_times >= window_start_ct) & (ct_times <= window_end_ct)
    window_df = combined[in_window].copy()
    print(f"\nRows in window [{window_start_ct}–{window_end_ct} CT]: {len(window_df)}")

    # Recompute per-contract flow for every row in the full session
    # (so EMA state is correct), but only report rows in the window.
    contract_cols = ["strike", "expiration_date", "contract_type"]
    combined = combined.sort_values(contract_cols + ["_ts_utc"])

    rows: list[dict] = []
    for key, grp in combined.groupby(contract_cols, sort=False):
        grp = grp.sort_values("_ts_utc").copy()

        spread = (grp["ask"] - grp["bid"]).clip(lower=0.01)
        trade_position = ((grp["last"] - grp["bid"]) / spread).clip(0.0, 1.0)
        ema_tp = trade_position.ewm(span=ema_span, adjust=False).mean()
        trade_direction = (ema_tp - 0.5) * 2

        new_volume = (
            grp["total_volume"] - grp["total_volume"].shift(lookback_window)
        ).clip(lower=0.0).fillna(0.0)

        flow = new_volume * trade_direction * grp["delta"].abs()

        for i in range(len(grp)):
            ts_ct = grp["_ts_ct"].iloc[i].time() if hasattr(grp["_ts_ct"].iloc[i], "time") else grp["_ts_ct"].iloc[i]
            if ts_ct < window_start_ct or ts_ct > window_end_ct:
                continue
            rows.append({
                "time_ct": grp["_ts_ct"].iloc[i],
                "strike": float(grp["strike"].iloc[i]),
                "contract_type": str(grp["contract_type"].iloc[i]),
                "bid": float(grp["bid"].iloc[i]),
                "ask": float(grp["ask"].iloc[i]),
                "last": float(grp["last"].iloc[i]),
                "spread": float(spread.iloc[i]),
                "trade_position": float(trade_position.iloc[i]),
                "ema_tp": float(ema_tp.iloc[i]),
                "trade_direction": float(trade_direction.iloc[i]),
                "total_volume": float(grp["total_volume"].iloc[i]),
                "new_volume": float(new_volume.iloc[i]),
                "delta": float(grp["delta"].iloc[i]),
                "flow": float(flow.iloc[i]),
            })

    if not rows:
        print("No flow rows in window.")
        return

    df = pd.DataFrame(rows)

    # --- Summary: aggregate call flow per timestamp ---
    print("\n=== Call Flow Per Timestamp (window) ===")
    call_ts = (
        df[df["contract_type"] == "CALL"]
        .groupby("time_ct")["flow"]
        .sum()
        .sort_index()
    )
    pd.set_option("display.float_format", "{:,.1f}".format)
    print(call_ts.to_string())

    # --- Top negative call-flow contributors ---
    calls = df[df["contract_type"] == "CALL"].copy()
    print(f"\n=== Top {top_n} NEGATIVE call-flow rows (largest drag) ===")
    worst = calls.nsmallest(top_n, "flow")[
        ["time_ct", "strike", "bid", "ask", "last", "spread",
         "trade_position", "ema_tp", "trade_direction",
         "total_volume", "new_volume", "delta", "flow"]
    ]
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    print(worst.to_string(index=False))

    # --- Top positive call-flow contributors ---
    print(f"\n=== Top {top_n} POSITIVE call-flow rows ===")
    best = calls.nlargest(top_n, "flow")[
        ["time_ct", "strike", "bid", "ask", "last", "spread",
         "trade_position", "ema_tp", "trade_direction",
         "total_volume", "new_volume", "delta", "flow"]
    ]
    print(best.to_string(index=False))

    # --- Distribution of trade_position for calls in window ---
    print("\n=== trade_position distribution (calls in window) ===")
    print(calls["trade_position"].describe())
    print(f"\n  pct near ask (>0.65): {(calls['trade_position'] > 0.65).mean():.1%}")
    print(f"  pct neutral (0.35–0.65): {calls['trade_position'].between(0.35, 0.65).mean():.1%}")
    print(f"  pct near bid (<0.35):  {(calls['trade_position'] < 0.35).mean():.1%}")

    # --- Zero/tiny spread check ---
    tiny_spread = calls[calls["spread"] <= 0.05]
    print(f"\n=== Calls with spread <= 0.05 (unreliable trade_position): {len(tiny_spread)} rows ===")
    if not tiny_spread.empty:
        print(tiny_spread[["time_ct", "strike", "bid", "ask", "last", "spread", "flow"]]
              .nlargest(10, "flow").to_string(index=False))

    # --- Check: last outside bid/ask ---
    calls_raw = calls.copy()
    calls_raw["last_outside"] = (calls_raw["last"] < calls_raw["bid"]) | (calls_raw["last"] > calls_raw["ask"])
    pct_outside = calls_raw["last_outside"].mean()
    print(f"\n=== 'last' outside bid/ask for calls: {pct_outside:.1%} of rows ===")
    if pct_outside > 0:
        print(calls_raw[calls_raw["last_outside"]][
            ["time_ct", "strike", "bid", "ask", "last", "trade_position"]
        ].head(10).to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-06-11")
    parser.add_argument("--expiry", default="2026-06-11")
    parser.add_argument("--start-ct", default="12:00")
    parser.add_argument("--end-ct", default="13:30")
    parser.add_argument("--lookback", type=int, default=5)
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--ema-span", type=int, default=20)
    args = parser.parse_args()

    sample_date = date.fromisoformat(args.date)
    expiry = date.fromisoformat(args.expiry)
    start_h, start_m = map(int, args.start_ct.split(":"))
    end_h, end_m = map(int, args.end_ct.split(":"))

    run(
        sample_date=sample_date,
        expiry=expiry,
        window_start_ct=_ct(start_h, start_m),
        window_end_ct=_ct(end_h, end_m),
        lookback_window=args.lookback,
        top_n=args.top,
        ema_span=args.ema_span,
    )


if __name__ == "__main__":
    main()
