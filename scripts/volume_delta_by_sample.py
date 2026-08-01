"""Inspect volume changes for a specific option contract across intraday snapshots.

Usage:
    uv run python scripts/volume_delta_by_sample.py \
        --symbol SPXW \
        --expiry 2026-06-29 \
        --sample-date 2026-06-26 \
        --strike 7400 \
        --contract-type CALL
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd
from options_monitor.data.options import find_snapshots_for_expiry_on_date, load_options_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Volume delta per snapshot for a single contract.")
    parser.add_argument("--symbol", default="SPXW")
    parser.add_argument("--expiry", default="2026-06-29")
    parser.add_argument("--sample-date", default="2026-06-26")
    parser.add_argument("--strike", type=float, default=7400.0)
    parser.add_argument("--contract-type", default="CALL")
    args = parser.parse_args()

    expiry = date.fromisoformat(args.expiry)
    sample_date = date.fromisoformat(args.sample_date)
    strike = args.strike
    contract_type = args.contract_type.upper()

    snapshots = find_snapshots_for_expiry_on_date(
        args.symbol,
        expiry=expiry,
        sample_date=sample_date,
    )
    if not snapshots:
        print(f"No snapshots found for {args.symbol} expiry={expiry} on {sample_date}.")
        return

    print(f"Found {len(snapshots)} snapshots. Loading...")

    rows = []
    for ts, path in snapshots:
        df = load_options_snapshot(path)
        df["contract_type"] = df["contract_type"].astype(str).str.upper()
        df["strike"] = pd.to_numeric(df["strike"], errors="coerce")

        mask = (df["strike"] == strike) & (df["contract_type"] == contract_type)
        match = df[mask]
        if match.empty:
            continue

        row = match.iloc[0]
        rows.append(
            {
                "datetime": ts,
                "total_volume": float(row.get("total_volume", float("nan"))),
                "mid": round(
                    (float(row.get("bid", float("nan"))) + float(row.get("ask", float("nan")))) / 2,
                    2,
                ),
                "bid": float(row.get("bid", float("nan"))),
                "ask": float(row.get("ask", float("nan"))),
            }
        )

    if not rows:
        print(f"No data found for {contract_type} strike={strike} expiry={expiry}.")
        return

    result = pd.DataFrame(rows).sort_values("datetime").reset_index(drop=True)
    result["volume_delta"] = result["total_volume"].diff().fillna(0).astype(int)

    result = result[["datetime", "volume_delta", "total_volume", "mid", "bid", "ask"]]

    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", 120)
    print(f"\n{contract_type} {strike} | expiry={expiry} | sampled on {sample_date}\n")
    print(result.to_string(index=False))

    tmp_dir = Path(__file__).parent.parent / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    fname = f"volume_delta_{args.symbol}_{contract_type}_{int(strike)}_{expiry}_{sample_date}.csv"
    out_path = tmp_dir / fname
    result.to_csv(out_path, index=False)
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
