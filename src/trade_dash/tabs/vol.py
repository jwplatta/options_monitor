"""Vol tab: IV vs realized vol analysis."""

from __future__ import annotations

import contextlib
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from trade_dash.calc.fixed_strike_vol import build_iv_matrix
from trade_dash.calc.vol import iv_rv_spread, realized_vol, vix_spx_correlation
from trade_dash.charts.rv_acceleration import build_rv_acceleration_chart
from trade_dash.charts.vix_term import build_vix_term_chart
from trade_dash.charts.vol_of_vol import build_vol_of_vol_chart
from trade_dash.charts.vol_spread import build_iv_rv_chart
from trade_dash.config import OPTIONS_DIR
from trade_dash.data.candles import list_available_dates, load_candles
from trade_dash.data.options import find_latest_snapshots, load_options_snapshot


def render_vol_tab(candle_dir: Path, options_dir: Path = OPTIONS_DIR) -> None:
    st.subheader("Volatility")

    tab_overview, tab_spx_rv, tab_fsv = st.tabs(["Overview", "SPX RV", "Fixed Strike Vol"])

    # ── Fixed Strike Vol tab ──────────────────────────────────────────────────
    with tab_fsv:
        c1, c2, c3, _ = st.columns([1, 1, 1, 3])
        with c1:
            fsv_days_out = int(
                st.radio("Days Out", [7, 14, 21, 30], index=3, horizontal=True, key="fsv_days_out")
            )
        with c2:
            fsv_contract_type = str(
                st.radio("Contract", ["Call", "Put"], index=0, horizontal=True, key="fsv_ct")
            ).upper()
        with c3:
            fsv_otm_pct = float(
                st.selectbox("Strike Range (±% OTM)", [2, 5, 10, 15], index=1, key="fsv_otm_pct")
            )

        snapshot_paths = find_latest_snapshots(
            "SPXW",
            start_date=date.today(),
            days_out=fsv_days_out,
            include_0dte=True,
            data_dir=options_dir,
        )

        if not snapshot_paths:
            st.warning("No SPXW snapshots found.")
        else:
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

            iv_matrix = build_iv_matrix(loaded, contract_type=fsv_contract_type)

            if iv_matrix.empty:
                st.warning("No IV data available for the selected parameters.")
            else:
                _render_fsv_table(iv_matrix, spot=spot, otm_pct=fsv_otm_pct)

    # ── Overview tab ──────────────────────────────────────────────────────────
    with tab_overview:
        ov_c1, ov_c2, ov_c3, ov_c4 = st.columns([1, 1, 1, 1])
        with ov_c1:
            window_choice = st.radio("Window", ["9D", "30D"], horizontal=True, key="vol_window")
        with ov_c2:
            freq_ov = (
                st.selectbox("Frequency", ["day", "1min", "5min", "30min"], index=0, key="vol_freq")
                or "day"
            )

        try:
            start_avail, end_avail = list_available_dates("SPX", str(freq_ov), data_dir=candle_dir)
        except FileNotFoundError:
            st.error("SPX data not available.")
            return

        today = date.today()
        default_start = max(date(today.year, today.month, 1), start_avail.date())

        with ov_c3:
            start_sel = st.date_input("Start", value=default_start, key="vol_start")
        with ov_c4:
            end_sel = st.date_input("End", value=end_avail.date(), key="vol_end")

        st.divider()

        window_days = 9 if window_choice == "9D" else 30
        iv_symbol = "VIX9D" if window_choice == "9D" else "VIX"

        _bars_per_day = {"day": 1, "30min": 13, "5min": 78, "1min": 390}
        f_per_day = _bars_per_day.get(str(freq_ov), 1)
        window_bars = window_days * f_per_day
        ann_factor = 252 * f_per_day

        lookback_start = date.fromisoformat(str(start_sel)) - timedelta(days=window_days * 3)
        spx_ov = load_candles(
            "SPX", str(freq_ov), start=lookback_start, end=end_sel, data_dir=candle_dir
        )

        try:
            iv_candles = load_candles(
                iv_symbol, str(freq_ov), start=lookback_start, end=end_sel, data_dir=candle_dir
            )
        except FileNotFoundError:
            st.error(f"{iv_symbol} data not available for frequency {freq_ov}.")
            return

        rv_ov = realized_vol(spx_ov["close"], window=window_bars, periods_per_year=ann_factor)
        merged = pd.merge(
            spx_ov[["datetime"]].assign(rv=rv_ov.values),
            iv_candles[["datetime", "close"]].rename(columns={"close": "iv"}),
            on="datetime",
            how="inner",
        ).dropna()

        start_trim = pd.Timestamp(start_sel, tz="UTC")
        merged = merged[merged["datetime"] >= start_trim].reset_index(drop=True)

        if merged.empty:
            st.warning("No overlapping data for selected range.")
            return

        spread = iv_rv_spread(merged["iv"], merged["rv"])

        try:
            vix_full = load_candles(
                "VIX", str(freq_ov), start=start_sel, end=end_sel, data_dir=candle_dir
            )
            corr = vix_spx_correlation(spx_ov, vix_full)
            st.metric(f"VIX-SPX Correlation ({freq_ov})", f"{corr:.3f}")
        except FileNotFoundError:
            st.info(f"VIX data not available for frequency {freq_ov}.")

        fig = build_iv_rv_chart(
            iv=merged["iv"],
            rv=merged["rv"],
            spread=spread,
            datetimes=merged["datetime"],
            window_label=str(window_choice),
            freq=str(freq_ov),
        )
        st.plotly_chart(fig, use_container_width=True)

        try:
            vix = load_candles(
                "VIX", str(freq_ov), start=start_sel, end=end_sel, data_dir=candle_dir
            )
            vix9d = load_candles(
                "VIX9D", str(freq_ov), start=start_sel, end=end_sel, data_dir=candle_dir
            )
            vix1d: pd.DataFrame | None = None
            if str(freq_ov) != "day":
                with contextlib.suppress(FileNotFoundError):
                    vix1d = load_candles(
                        "VIX1D", str(freq_ov), start=start_sel, end=end_sel, data_dir=candle_dir
                    )
            st.plotly_chart(
                build_vix_term_chart(vix, vix9d, vix1d, freq=str(freq_ov)),
                use_container_width=True,
            )
        except FileNotFoundError as e:
            st.info(f"VIX term structure incomplete: {e}")

    # ── SPX RV tab ────────────────────────────────────────────────────────────
    with tab_spx_rv:
        rv_c1, rv_c2, rv_c3, rv_c4, rv_c5 = st.columns([1, 1, 1, 1, 1])
        with rv_c1:
            freq_rv = (
                st.selectbox(
                    "Frequency", ["day", "1min", "5min", "30min"], index=0, key="rv_freq"
                )
                or "day"
            )
        with rv_c2:
            rv_fast_days = int(
                st.number_input("RV Fast (days)", min_value=1, value=3, key="vol_rv_fast")
            )
        with rv_c3:
            rv_slow_days = int(
                st.number_input("RV Slow (days)", min_value=2, value=10, key="vol_rv_slow")
            )
        with rv_c4:
            vov_freq = (
                st.selectbox(
                    "VoV Frequency", ["1min", "5min", "30min", "day"], index=0, key="vol_vov_freq"
                )
                or "1min"
            )
        with rv_c5:
            vov_n = int(st.number_input("VoV N (bars)", min_value=2, value=30, key="vol_vov_n"))
            vov_m = int(st.number_input("VoV M (bars)", min_value=2, value=60, key="vol_vov_m"))

        if rv_fast_days >= rv_slow_days:
            st.error(f"RV fast ({rv_fast_days}) must be less than slow ({rv_slow_days}).")
            return

        st.divider()

        try:
            start_avail_rv, end_avail_rv = list_available_dates(
                "SPX", str(freq_rv), data_dir=candle_dir
            )
        except FileNotFoundError:
            st.error("SPX data not available.")
            return

        today_rv = date.today()
        default_start_rv = max(date(today_rv.year, today_rv.month, 1), start_avail_rv.date())

        rv_date_c1, rv_date_c2, _ = st.columns([1, 1, 2])
        with rv_date_c1:
            start_rv = st.date_input("Start", value=default_start_rv, key="rv_start")
        with rv_date_c2:
            end_rv = st.date_input("End", value=end_avail_rv.date(), key="rv_end")

        lookback_rv = max(rv_slow_days, 30) * 3
        lookback_start_rv = date.fromisoformat(str(start_rv)) - timedelta(days=lookback_rv)
        spx_rv = load_candles(
            "SPX", str(freq_rv), start=lookback_start_rv, end=end_rv, data_dir=candle_dir
        )

        rv_fig = build_rv_acceleration_chart(
            spx_rv,
            fast_days=rv_fast_days,
            slow_days=rv_slow_days,
            freq=str(freq_rv),
            title=f"SPX RV Acceleration — {rv_fast_days}d vs {rv_slow_days}d",
        )
        start_trim_rv = pd.Timestamp(start_rv, tz="UTC")
        if str(freq_rv) in {"1min", "5min", "30min"}:
            mask = spx_rv["datetime"] >= start_trim_rv
            display_start = int(mask.idxmax()) if mask.any() else 0
            rv_fig.update_xaxes(range=[display_start - 0.5, len(spx_rv) - 0.5])
        else:
            rv_fig.update_xaxes(
                range=[start_trim_rv, pd.Timestamp(end_rv, tz="UTC") + pd.Timedelta(days=1)]
            )
        st.plotly_chart(rv_fig, use_container_width=True)

        _vov_bars_per_day = {"1min": 390, "5min": 78, "30min": 13, "day": 1}
        vov_bars_per_day = _vov_bars_per_day.get(str(vov_freq), 1)
        vov_lookback_days = ((vov_n + vov_m) // vov_bars_per_day + 1) * 2
        vov_lookback_start = date.fromisoformat(str(start_rv)) - timedelta(days=vov_lookback_days)
        try:
            spx_vov = load_candles(
                "SPX", str(vov_freq), start=vov_lookback_start, end=end_rv, data_dir=candle_dir
            )
            if spx_vov.empty:
                st.warning(f"No {vov_freq} SPX data for selected range.")
            else:
                vov_fig = build_vol_of_vol_chart(
                    spx_vov,
                    n_window=vov_n,
                    m_window=vov_m,
                    freq=str(vov_freq),
                    display_start=date.fromisoformat(str(start_rv)),
                    title=f"SPX Vol-of-Vol ({vov_freq}) — σ(N={vov_n}) · VoV(M={vov_m})",
                )
                st.plotly_chart(vov_fig, use_container_width=True)
        except FileNotFoundError:
            st.info(f"{vov_freq} SPX data not available for vol-of-vol chart.")


def _render_fsv_table(iv_matrix: pd.DataFrame, spot: float, otm_pct: float) -> None:
    """Render the fixed-strike IV matrix as a scrollable styled dataframe."""
    strikes = np.array(iv_matrix.columns.tolist(), dtype=float)

    # Filter strikes to ±otm_pct% around spot
    lo = spot * (1 - otm_pct / 100)
    hi = spot * (1 + otm_pct / 100)
    mask = (strikes >= lo) & (strikes <= hi)
    iv_filtered = iv_matrix.loc[:, mask]

    if iv_filtered.empty:
        st.warning("No strikes in the selected OTM range.")
        return

    # Find nearest strike to spot after filtering
    filtered_strikes = np.array(iv_filtered.columns.tolist(), dtype=float)
    nearest_strike = filtered_strikes[int(np.argmin(np.abs(filtered_strikes - spot)))]

    # Format values as percentages
    formatted = iv_filtered.copy()
    for col in formatted.columns:
        formatted[col] = formatted[col].apply(lambda v: f"{v:.2f}%" if pd.notna(v) else "")

    formatted.index = [str(d) for d in iv_filtered.index]
    formatted.index.name = "Expiry \\ Strike"
    formatted.columns = [f"{int(c)}" for c in formatted.columns]

    nearest_col_name = f"{int(nearest_strike)}"

    def highlight_nearest(col: pd.Series) -> list[str]:
        if col.name == nearest_col_name:
            return ["background-color: #1a3a6a; color: #7dd3fc"] * len(col)
        return [""] * len(col)

    styled = formatted.style.apply(highlight_nearest, axis=0)

    n_rows = len(iv_filtered)
    table_height = 38 + n_rows * 28

    st.dataframe(
        styled,
        use_container_width=True,
        height=table_height,
    )
