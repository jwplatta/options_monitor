"""Underlying tab: candlestick price chart for ES Futures or SPX."""

from __future__ import annotations

from datetime import date, time, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from trade_dash.calc.gex import (
    find_aggregate_wall_strikes,
    find_raw_wall_strikes,
    find_zero_gamma_level,
    net_gex_by_price,
)
from trade_dash.charts.es_chart import build_es_candlestick_chart
from trade_dash.charts.spx_chart import build_spx_candlestick_chart
from trade_dash.config import OPTIONS_DIR, SCHWAB_CANDLE_DIR
from trade_dash.data.candles import list_available_dates, load_candles
from trade_dash.data.options import find_latest_snapshots, load_options_snapshot

_INTRADAY_FREQS = {"1min", "5min", "30min"}

_TICKER_OPTIONS = ["ES Futures", "SPX"]
_TICKER_SYMBOL = {"ES Futures": "^ES", "SPX": "SPX"}


def _x_range(
    df: pd.DataFrame,
    start_sel: date,
    end_sel: date,
    freq: str,
    time_range: tuple[time, time] | None = None,
) -> list[object]:
    """Return xaxis range to align with the selected display window."""
    if freq in _INTRADAY_FREQS:
        dts = df["datetime"]
        if dts.dt.tz is not None:
            times_ct = dts.dt.tz_convert("America/Chicago").dt.tz_localize(None).dt.time.tolist()
        else:
            times_ct = dts.dt.time.tolist()
        n = len(df)
        if time_range is not None:
            t_start, t_end = time_range
            in_window = [t_start <= t <= t_end for t in times_ct]
            start_pos = next((i for i, v in enumerate(in_window) if v), 0)
            end_pos = next((i for i in range(n - 1, -1, -1) if in_window[i]), n - 1)
        else:
            start_pos = 0
            end_pos = n - 1
        return [start_pos - 0.5, end_pos + 0.5]
    else:
        return [
            pd.Timestamp(start_sel, tz="UTC"),
            pd.Timestamp(end_sel, tz="UTC") + pd.Timedelta(days=1),
        ]


def _load_gex_levels(
    symbol: str,
    today: date,
    days_out: int,
    options_dir: Path,
    include_0dte: bool = True,
) -> dict[str, float | None]:
    """Load options snapshot and compute wall + ZGL levels. Returns empty dict on failure."""
    snapshots = find_latest_snapshots(
        symbol, start_date=today, days_out=days_out, include_0dte=include_0dte, data_dir=options_dir
    )
    if not snapshots:
        return {}

    all_opts = pd.concat(
        [load_options_snapshot(p) for p in snapshots.values()], ignore_index=True
    )
    spot_series = pd.to_numeric(all_opts["underlying_price"], errors="coerce").dropna()
    if spot_series.empty:
        return {}
    spot = float(spot_series.iloc[0])
    strike_range = round(spot * 0.05)

    anchor_ts = pd.Timestamp(today)
    raw_call, raw_put = find_raw_wall_strikes(all_opts, spot=spot, strike_range=strike_range)
    dw_call, dw_put = find_aggregate_wall_strikes(
        all_opts, spot=spot, strike_range=strike_range,
        method="distance_weighted_aggregate", anchor_date=anchor_ts,
    )
    cl_call, cl_put = find_aggregate_wall_strikes(
        all_opts, spot=spot, strike_range=strike_range,
        method="per_expiry_clustering", anchor_date=anchor_ts,
    )
    price_gex = net_gex_by_price(all_opts, spot=spot, price_range=strike_range)
    zgl = find_zero_gamma_level(
        price_gex["price"].to_numpy(), price_gex["net_gex"].to_numpy()
    )

    return {
        "raw_call_wall": raw_call,
        "raw_put_wall": raw_put,
        "dw_call_wall": dw_call,
        "dw_put_wall": dw_put,
        "cluster_call_wall": cl_call,
        "cluster_put_wall": cl_put,
        "zero_gamma": zgl,
    }


def render_underlying_tab(candle_dir: Path) -> None:
    st.subheader("Underlying")

    col_ctrl, col_chart = st.columns([1, 3])

    with col_ctrl:
        ticker_label = (
            st.selectbox("Ticker", _TICKER_OPTIONS, index=1, key="reg_ticker") or "SPX"
        )
        freq = (
            st.selectbox("Frequency", ["1min", "5min", "30min", "day"], index=1, key="reg_freq")
            or "5min"
        )

        symbol = _TICKER_SYMBOL[ticker_label]
        data_dir = SCHWAB_CANDLE_DIR if ticker_label == "ES Futures" else candle_dir

        # Aggregate window, 0DTE toggle, and GEX toggle — only relevant for SPX
        days_out: int | None = None
        include_0dte: bool = True
        show_gex: bool = False
        if ticker_label == "SPX":
            days_out = int(
                st.radio(
                    "Aggregate window",
                    options=[5, 10, 20, 30],
                    horizontal=True,
                    key="reg_agg_window",
                )
            )
            include_0dte = st.toggle("Include 0DTE", value=True, key="reg_0dte")
            show_gex = st.toggle("Show GEX levels", value=False, key="reg_show_gex")

        try:
            start_avail, end_avail = list_available_dates(symbol, str(freq), data_dir=data_dir)
        except FileNotFoundError:
            st.error(f"No {ticker_label} data for frequency: {freq}")
            return

        if freq in _INTRADAY_FREQS:
            sel_date = st.date_input("Date", value=end_avail.date(), key="reg_date")
            start_sel = sel_date
            end_sel = sel_date + timedelta(days=1)
            if "reg_time_range" not in st.session_state:
                st.session_state["reg_time_range"] = (time(8, 30), time(15, 0))
            st.slider(
                "Time range (CT)",
                min_value=time(0, 0),
                max_value=time(23, 30),
                value=st.session_state["reg_time_range"],
                step=timedelta(minutes=30),
                key="reg_time_range",
            )
        else:
            today = date.today()
            default_start = max(date(today.year, today.month, 1), start_avail.date())
            start_sel = st.date_input("Start", value=default_start, key="reg_start")
            end_sel = st.date_input("End", value=end_avail.date(), key="reg_end")

    df = load_candles(symbol, str(freq), start=start_sel, end=end_sel, data_dir=data_dir)

    if df.empty:
        with col_chart:
            st.warning("No data for selected range.")
        return

    intraday = freq in _INTRADAY_FREQS
    intraday_time_range: tuple[time, time] | None = None
    if intraday:
        tr = st.session_state.get("reg_time_range", (time(8, 30), time(16, 0)))
        intraday_time_range = (tr[0], tr[1])

    with col_chart:
        if ticker_label == "SPX":
            gex_levels: dict[str, float | None] = {}
            if show_gex and days_out is not None:
                with st.spinner("Loading GEX levels..."):
                    gex_levels = _load_gex_levels(
                        "SPXW", date.today(), days_out, OPTIONS_DIR, include_0dte
                    )
            fig = build_spx_candlestick_chart(
                df,
                title=f"{ticker_label} ({freq})",
                freq=str(freq),
                **gex_levels,
            )
        else:
            fig = build_es_candlestick_chart(
                df,
                title=f"{ticker_label} ({freq})",
                freq=str(freq),
            )

        fig.update_xaxes(range=_x_range(df, start_sel, end_sel, str(freq), intraday_time_range))
        st.plotly_chart(fig, use_container_width=True)
