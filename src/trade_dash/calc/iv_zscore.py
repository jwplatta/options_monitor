"""IV z-score computation: bucket-based historical comparison."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

_DTE_EDGES: list[int] = [0, 3, 7, 14, 21, 30, 45, 60, 90, 180]

# Signed log-moneyness edges: finer resolution near ATM, coarser in the wings.
# Negative = ITM for calls / OTM for puts; positive = OTM for calls / ITM for puts.
# Buckets (from deep ITM to deep OTM):
#   < -0.05  : ITM >5%
#   -0.05 – -0.03 : ITM 3–5%
#   -0.03 – -0.01 : ITM 1–3%
#   -0.01 – -0.005: ITM 0.5–1%
#   -0.005 – 0.005: ATM ±0.5%
#    0.005 –  0.01: OTM 0.5–1%
#    0.01  –  0.03: OTM 1–3%
#    0.03  –  0.05: OTM 3–5%
#   > 0.05        : OTM >5%
_MONEYNESS_EDGES: list[float] = [
    -float("inf"), -0.05, -0.03, -0.01, -0.005, 0.005, 0.01, 0.03, 0.05, float("inf")
]


def build_bucket_stats(
    frames: list[pd.DataFrame],
    sample_dates: list[date],
    dte_edges: list[int] = _DTE_EDGES,
    moneyness_edges: list[float] = _MONEYNESS_EDGES,
) -> pd.DataFrame:
    """Compute mean/std of IV per (contract_type, dte_bucket, moneyness_bucket).

    Args:
        frames: Historical chain snapshot DataFrames (one per interval sample).
        sample_dates: Chicago date corresponding to each frame (parallel list).
        dte_edges: Bin edges for days-to-expiration buckets.
        moneyness_edges: Bin edges for log-moneyness buckets.

    Returns:
        DataFrame indexed by (contract_type, dte_bucket, moneyness_bucket) with
        columns iv_mean, iv_std, count.
    """
    pieces: list[pd.DataFrame] = []
    for df, sample_date in zip(frames, sample_dates, strict=False):
        needed = {"strike", "volatility", "underlying_price", "expiration_date", "contract_type"}
        if not needed.issubset(df.columns):
            continue
        row = df[list(needed)].dropna().copy()
        if row.empty:
            continue

        exp_dates = pd.to_datetime(row["expiration_date"])
        row["dte"] = (exp_dates - pd.Timestamp(sample_date)).dt.days
        row = row[row["dte"] >= 0]
        if row.empty:
            continue

        spot_col = row["underlying_price"].replace(0, np.nan).dropna()
        if spot_col.empty:
            continue
        row = row.loc[spot_col.index]
        row["log_moneyness"] = np.log(row["strike"] / row["underlying_price"])

        row["dte_bucket"] = pd.cut(
            row["dte"],
            bins=dte_edges,
            labels=[f"{dte_edges[i]}-{dte_edges[i+1]}d" for i in range(len(dte_edges) - 1)],
            right=True,
            include_lowest=True,
        )
        row["moneyness_bucket"] = pd.cut(
            row["log_moneyness"],
            bins=moneyness_edges,
            labels=[
                f"{moneyness_edges[i]:.2f}/{moneyness_edges[i+1]:.2f}"
                for i in range(len(moneyness_edges) - 1)
            ],
            right=True,
            include_lowest=True,
        )
        row["contract_type"] = row["contract_type"].str.upper()
        pieces.append(row[["contract_type", "dte_bucket", "moneyness_bucket", "volatility"]])

    if not pieces:
        return pd.DataFrame(columns=["iv_mean", "iv_std", "count"])

    combined = pd.concat(pieces, ignore_index=True).dropna(
        subset=["dte_bucket", "moneyness_bucket"]
    )
    stats = (
        combined.groupby(["contract_type", "dte_bucket", "moneyness_bucket"], observed=True)[
            "volatility"
        ]
        .agg(iv_mean="mean", iv_std="std", count="count")
        .reset_index()
        .set_index(["contract_type", "dte_bucket", "moneyness_bucket"])
    )
    return stats


def compute_zscore_matrix(
    current_snapshots: dict[date, pd.DataFrame],
    bucket_stats: pd.DataFrame,
    spot: float,
    contract_type: str,
    today: date,
    dte_edges: list[int] = _DTE_EDGES,
    moneyness_edges: list[float] = _MONEYNESS_EDGES,
) -> pd.DataFrame:
    """Compute IV z-scores for each (expiry, strike) using bucket stats.

    Args:
        current_snapshots: Mapping of expiry → latest snapshot DataFrame.
        bucket_stats: Output of build_bucket_stats().
        spot: Current underlying price.
        contract_type: "CALL", "PUT", or "OTM".
        today: Current date (used to compute DTE).
        dte_edges: Must match those used in build_bucket_stats().
        moneyness_edges: Must match those used in build_bucket_stats().

    Returns:
        DataFrame with expiry dates as index, strikes as columns, z-scores as values.
        NaN where bucket has insufficient history (count < 3 or std == 0).
    """
    if bucket_stats.empty or spot == 0:
        return pd.DataFrame()

    ct = contract_type.upper()
    rows: list[dict[str, object]] = []

    for expiry, df in current_snapshots.items():
        if ct == "OTM":
            calls = df[df["contract_type"].str.upper() == "CALL"]
            calls = calls[calls["strike"] >= spot]
            puts = df[df["contract_type"].str.upper() == "PUT"]
            puts = puts[puts["strike"] < spot]
            options = pd.concat([calls, puts], ignore_index=True)
        else:
            options = df[df["contract_type"].str.upper() == ct]

        options = options.dropna(subset=["volatility", "strike"])
        dte = (expiry - today).days
        if dte < 0:
            continue

        for _, opt in options.iterrows():
            iv = float(opt["volatility"])
            strike = float(opt["strike"])
            opt_ct = str(opt["contract_type"]).upper()

            if spot <= 0:
                continue
            log_m = math.log(strike / spot)

            dte_bin = pd.cut(
                [dte], bins=dte_edges, right=True, include_lowest=True,
                labels=[f"{dte_edges[i]}-{dte_edges[i+1]}d" for i in range(len(dte_edges) - 1)],
            )[0]
            m_bin = pd.cut(
                [log_m], bins=moneyness_edges, right=True, include_lowest=True,
                labels=[
                    f"{moneyness_edges[i]:.2f}/{moneyness_edges[i+1]:.2f}"
                    for i in range(len(moneyness_edges) - 1)
                ],
            )[0]

            if pd.isna(dte_bin) or pd.isna(m_bin):
                continue

            key = (opt_ct, dte_bin, m_bin)
            if key not in bucket_stats.index:
                continue

            stat_row: pd.Series = bucket_stats.loc[key, :]  # type: ignore[assignment]
            cnt = int(stat_row["count"])
            std = float(stat_row["iv_std"])
            mean = float(stat_row["iv_mean"])

            z = float("nan") if cnt < 3 or std == 0 or math.isnan(std) else (iv - mean) / std

            rows.append({"expiration_date": expiry, "strike": strike, "z": z})

    if not rows:
        return pd.DataFrame()

    df_z = pd.DataFrame(rows)
    matrix = df_z.pivot_table(
        index="expiration_date", columns="strike", values="z", aggfunc="mean"
    )
    return matrix.sort_index().sort_index(axis=1)
