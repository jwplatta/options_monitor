"""Open interest matrix calculation."""

from __future__ import annotations

from datetime import date

import pandas as pd


def build_oi_matrix(
    snapshots: dict[date, pd.DataFrame],
    contract_type: str = "CALL",
    spot: float = 0.0,
) -> pd.DataFrame:
    """Pivot per-expiry snapshots into an (expiry × strike) open interest matrix.

    Args:
        snapshots: Mapping of expiry date → options snapshot DataFrame.
        contract_type: "CALL", "PUT", or "OTM" (case-insensitive).
            OTM uses calls for strikes >= spot and puts for strikes < spot.
        spot: Current underlying price, required when contract_type is "OTM".

    Returns:
        DataFrame with expiration dates as index (sorted ascending),
        strikes as columns (sorted ascending), and open interest as values.
    """
    ct = contract_type.upper()
    frames: list[pd.DataFrame] = []
    for expiry, df in snapshots.items():
        if ct == "OTM":
            df_up = df[df["contract_type"].str.upper() == "CALL"].copy()
            df_up = df_up[df_up["strike"] >= spot]
            df_dn = df[df["contract_type"].str.upper() == "PUT"].copy()
            df_dn = df_dn[df_dn["strike"] < spot]
            filtered = pd.concat([df_up, df_dn], ignore_index=True)
        else:
            filtered = df[df["contract_type"].str.upper() == ct].copy()
        filtered = filtered.dropna(subset=["open_interest", "strike"])
        filtered["expiration_date"] = expiry
        frames.append(filtered[["expiration_date", "strike", "open_interest"]])

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    matrix = combined.pivot_table(
        index="expiration_date",
        columns="strike",
        values="open_interest",
        aggfunc="sum",
    )
    matrix = matrix.sort_index().sort_index(axis=1)
    return matrix
