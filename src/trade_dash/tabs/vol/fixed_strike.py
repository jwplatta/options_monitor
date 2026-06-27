"""Fixed Strike Vol subtab: IV matrix with z-score heatmap overlay."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from trade_dash.calc.fixed_strike_vol import build_iv_matrix
from trade_dash.calc.iv_zscore import build_bucket_stats, compute_zscore_matrix
from trade_dash.config import OPTIONS_DIR
from trade_dash.data.options import (
    find_downsampled_snapshots_for_lookback,
    find_latest_snapshots,
    load_options_snapshot,
)


@st.cache_data(ttl=1800)
def _load_historical_frames(
    symbol: str,
    lookback_days: int,
    interval_minutes: int,
    options_dir: Path,
) -> tuple[list[pd.DataFrame], list[date]]:
    """Load interval-downsampled historical chain snapshots for z-score bucket building.

    Downsampling is performed in SQL. Returns (frames, sample_dates).
    """
    all_snaps = find_downsampled_snapshots_for_lookback(
        symbol, lookback_days, interval_minutes, days_out=90, include_0dte=True,
        data_dir=options_dir,
    )
    frames: list[pd.DataFrame] = []
    sample_dates: list[date] = []

    for sample_date, expiry_grouped in sorted(all_snaps.items()):
        for snaps in expiry_grouped.values():
            for _, path in snaps:
                try:
                    frames.append(load_options_snapshot(path))
                    sample_dates.append(sample_date)
                except FileNotFoundError:
                    continue

    return frames, sample_dates


def render_fixed_strike_tab(options_dir: Path = OPTIONS_DIR) -> None:
    """Render the Fixed Strike Vol subtab."""
    c1, c2, c3, c4, c5, c6 = st.columns([1, 1, 1, 1, 1, 1])
    with c1:
        fsv_days_out = int(
            st.radio("Days Out", [7, 14, 21, 30], index=3, horizontal=True, key="fsv_days_out")
        )
    with c2:
        fsv_contract_type = str(
            st.radio("Contract", ["Call", "Put", "OTM"], index=0, horizontal=True, key="fsv_ct")
        ).upper()
    with c3:
        fsv_otm_pct = float(
            st.selectbox("Strike Range (±% OTM)", [2, 5, 10, 15], index=1, key="fsv_otm_pct")
        )
    with c4:
        fsv_lookback = int(
            st.selectbox("Lookback (days)", [10, 20, 30, 60, 90], index=2, key="fsv_lookback")
        )
        fsv_interval = int(st.selectbox("Interval (min)", [30, 60], index=1, key="fsv_interval"))
    with c5:
        fsv_include_0dte = st.toggle("Include 0DTE", value=True, key="fsv_include_0dte")

    snapshot_paths = find_latest_snapshots(
        "SPXW",
        start_date=date.today(),
        days_out=fsv_days_out,
        include_0dte=fsv_include_0dte,
        data_dir=options_dir,
    )

    if not snapshot_paths:
        st.warning("No SPXW snapshots found.")
        return

    loaded: dict[date, pd.DataFrame] = {}
    spot: float = 0.0
    for expiry, path in snapshot_paths.items():
        try:
            snap = load_options_snapshot(path)
            loaded[expiry] = snap
            if spot == 0.0 and not snap["underlying_price"].empty:
                spot = float(snap["underlying_price"].iloc[0])
        except FileNotFoundError:
            continue

    with c6:
        if spot:
            st.metric("Spot (SPXW)", f"{spot:,.2f}")

    iv_matrix = build_iv_matrix(loaded, contract_type=fsv_contract_type, spot=spot)

    if iv_matrix.empty:
        st.warning("No IV data available for the selected parameters.")
        return

    zscore_matrix: pd.DataFrame | None = None
    with st.spinner("Loading historical data for z-scores…"):
        hist_frames, hist_dates = _load_historical_frames(
            "SPXW", fsv_lookback, fsv_interval, options_dir
        )
    if hist_frames:
        bucket_stats = build_bucket_stats(hist_frames, hist_dates)
        zscore_matrix = compute_zscore_matrix(
            loaded,
            bucket_stats,
            spot=spot,
            contract_type=fsv_contract_type,
            today=date.today(),
        )
    _render_fsv_table(iv_matrix, spot=spot, otm_pct=fsv_otm_pct, zscore_matrix=zscore_matrix)


def _render_fsv_table(
    iv_matrix: pd.DataFrame,
    spot: float,
    otm_pct: float,
    zscore_matrix: pd.DataFrame | None = None,
) -> None:
    """Render the fixed-strike IV matrix as a scrollable styled dataframe."""
    strikes = np.array(iv_matrix.columns.tolist(), dtype=float)

    lo = spot * (1 - otm_pct / 100)
    hi = spot * (1 + otm_pct / 100)
    mask = (strikes >= lo) & (strikes <= hi)
    iv_filtered = iv_matrix.loc[:, mask]

    if iv_filtered.empty:
        st.warning("No strikes in the selected OTM range.")
        return

    z_aligned: pd.DataFrame | None = None
    if zscore_matrix is not None and not zscore_matrix.empty:
        shared_rows = iv_filtered.index.intersection(zscore_matrix.index)
        shared_cols = iv_filtered.columns.intersection(zscore_matrix.columns)
        if len(shared_rows) and len(shared_cols):
            z_aligned = zscore_matrix.loc[shared_rows, shared_cols].reindex(
                index=iv_filtered.index, columns=iv_filtered.columns
            )

    filtered_strikes = np.array(iv_filtered.columns.tolist(), dtype=float)
    nearest_strike = filtered_strikes[int(np.argmin(np.abs(filtered_strikes - spot)))]

    formatted = iv_filtered.copy()
    for col in formatted.columns:
        formatted[col] = formatted[col].apply(lambda v: f"{v:.2f}%" if pd.notna(v) else "")

    str_index = [str(d) for d in iv_filtered.index]
    str_cols = [f"{int(c)}" for c in iv_filtered.columns]
    formatted.index = str_index
    formatted.index.name = "Expiry \\ Strike"
    formatted.columns = str_cols

    nearest_col_name = f"{int(nearest_strike)}"

    if z_aligned is not None:
        z_display = z_aligned.copy()
        z_display.index = str_index[: len(z_display)]
        z_display.columns = [f"{int(c)}" for c in z_aligned.columns]
    else:
        z_display = None

    if z_display is not None:
        _render_zscore_legend()

    def _zscore_color(z: float) -> tuple[str, str]:
        z_clamped = max(-3.0, min(3.0, z))
        t = abs(z_clamped) / 3.0
        if z_clamped >= 0:
            r = int(30 * (1 - t) + 5 * t)
            g = int(30 * (1 - t) + 83 * t)
            b = int(30 * (1 - t) + 45 * t)
            fg = "#4ade80" if t > 0.4 else "#e0e0e0"
        else:
            r = int(30 * (1 - t) + 127 * t)
            g = int(30 * (1 - t) + 10 * t)
            b = int(30 * (1 - t) + 10 * t)
            fg = "#f87171" if t > 0.4 else "#e0e0e0"
        return f"#{r:02x}{g:02x}{b:02x}", fg

    def _cell_style(col: pd.Series) -> list[str]:
        col_name = str(col.name)
        styles: list[str] = []
        for row_label in col.index:
            z = (
                float(z_display.loc[row_label, col_name])
                if z_display is not None
                and col_name in z_display.columns
                and row_label in z_display.index
                and pd.notna(z_display.loc[row_label, col_name])
                else None
            )
            if z is not None:
                bg, fg = _zscore_color(z)
                styles.append(f"background-color: {bg}; color: {fg}")
            elif col_name == nearest_col_name:
                styles.append("background-color: #1a3a6a; color: #7dd3fc")
            else:
                styles.append("")
        return styles

    styled = formatted.style.apply(_cell_style, axis=0)
    n_rows = len(iv_filtered)
    table_height = 38 + n_rows * 28
    st.dataframe(styled, use_container_width=True, height=table_height)


def _render_zscore_legend() -> None:
    """Render a compact red→neutral→green gradient legend for z-score coloring."""
    stops = [
        (-3, "#7f0a0a", "#f87171"),
        (-2, "#550a0a", "#f87171"),
        (-1, "#2a1010", "#e0e0e0"),
        (0, "#1e1e1e", "#e0e0e0"),
        (1, "#0a2a10", "#e0e0e0"),
        (2, "#055320", "#4ade80"),
        (3, "#05532d", "#4ade80"),
    ]
    cells = "".join(
        f'<td style="background:{bg};color:{fg};padding:2px 8px;font-size:11px;'
        f'text-align:center;border:1px solid #333">z={z}</td>'
        for z, bg, fg in stops
    )
    st.markdown(
        f'<table style="border-collapse:collapse;margin-bottom:6px"><tr>{cells}</tr></table>',
        unsafe_allow_html=True,
    )
