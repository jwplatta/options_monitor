"""Fixed-strike implied volatility matrix calculation."""

from __future__ import annotations

from datetime import date

import pandas as pd


def build_iv_matrix(
    snapshots: dict[date, pd.DataFrame],
    contract_type: str = "CALL",
) -> pd.DataFrame:
    """Pivot per-expiry snapshots into an (expiry × strike) IV matrix.

    Args:
        snapshots: Mapping of expiry date → options snapshot DataFrame.
        contract_type: "CALL" or "PUT" (case-insensitive).

    Returns:
        DataFrame with expiration dates as index (sorted ascending),
        strikes as columns (sorted ascending), and volatility % as values.
    """
    ct = contract_type.upper()
    frames: list[pd.DataFrame] = []
    for expiry, df in snapshots.items():
        filtered = df[df["contract_type"].str.upper() == ct].copy()
        filtered = filtered.dropna(subset=["volatility", "strike"])
        filtered["expiration_date"] = expiry
        frames.append(filtered[["expiration_date", "strike", "volatility"]])

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    matrix = combined.pivot_table(
        index="expiration_date",
        columns="strike",
        values="volatility",
        aggfunc="mean",
    )
    matrix = matrix.sort_index().sort_index(axis=1)
    return matrix
