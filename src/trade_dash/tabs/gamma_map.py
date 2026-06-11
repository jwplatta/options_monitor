"""Gamma Map tab: options positioning and key levels."""

from __future__ import annotations

from datetime import UTC, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from trade_dash.calc.flow import compute_intraday_flow
from trade_dash.calc.gex import (
    find_decision_zones,
    find_aggregate_wall_strikes,
    find_top_aggregate_gamma_strikes,
    net_gex_by_price,
    net_gex_by_strike,
)
from trade_dash.calc.gex_term_structure import compute_gex_term_structure
from trade_dash.calc.maker_taker import compute_maker_taker_flow
from trade_dash.calc.spread import compute_intraday_spread
from trade_dash.calc.vol import compute_risk_reversal
from trade_dash.charts.flow_heatmap import build_flow_heatmap_chart
from trade_dash.charts.gex_aggregate import build_gex_aggregate_chart
from trade_dash.charts.gex_single import build_gex_single_expiry_chart
from trade_dash.charts.gex_term_structure import build_gex_term_structure_chart
from trade_dash.charts.maker_taker_bubble import build_maker_taker_bubble_chart
from trade_dash.charts.skew_indicators import build_skew_indicators
from trade_dash.charts.spread_heatmap import build_spread_heatmap_chart
from trade_dash.charts.vol_skew import build_vol_skew_chart
from trade_dash.data.options import (
    find_all_snapshots_for_expiry,
    find_latest_snapshots,
    find_snapshots_for_expiry_on_date,
    find_snapshots_for_window_on_date,
    list_expirations,
    list_expirations_for_window_on_date,
    list_snapshot_dates,
    list_snapshot_dates_for_expiry,
    load_options_snapshot,
    select_window_snapshots_at_or_before,
)

_CHICAGO = ZoneInfo("America/Chicago")
_GAMMA_MAP_VIEWS = [
    "GEX",
    "Chains",
    "Intraday",
    "Gamma Heatmap",
    "Maker-Taker",
]
_SINGLE_EXPIRY_VIEWS = {
    "Chains",
    "Intraday",
    "Maker-Taker",
}


def _to_chicago_time(ts: pd.Timestamp | date | object) -> object:
    if isinstance(ts, pd.Timestamp):
        py_ts = ts.to_pydatetime()
        return py_ts.replace(tzinfo=UTC).astimezone(_CHICAGO).replace(tzinfo=None)
    if hasattr(ts, "replace"):
        return ts.replace(tzinfo=UTC).astimezone(_CHICAGO).replace(tzinfo=None)  # type: ignore[union-attr]
    return ts


def _compute_spot_and_strike_range(options_df: pd.DataFrame, range_pct: float) -> tuple[float, int]:
    spot_series = pd.to_numeric(options_df["underlying_price"], errors="coerce").dropna()
    if spot_series.empty:
        raise ValueError("No valid underlying_price in options data.")
    spot = float(spot_series.iloc[0])
    strike_range = round(spot * range_pct / 100)
    return spot, strike_range


def _load_window_snapshot_data(
    symbol: str,
    start_date: date,
    days_out: int,
    include_0dte: bool,
    range_pct: float,
    options_dir: Path,
) -> tuple[dict[date, Path], pd.DataFrame, float, int] | None:
    snapshots = find_latest_snapshots(
        symbol,
        start_date=start_date,
        days_out=days_out,
        include_0dte=include_0dte,
        data_dir=options_dir,
    )
    if not snapshots:
        return None
    all_opts = pd.concat(
        [load_options_snapshot(path) for path in snapshots.values()],
        ignore_index=True,
    )
    spot, strike_range = _compute_spot_and_strike_range(all_opts, range_pct)
    return snapshots, all_opts, spot, strike_range


def _load_single_expiry_snapshot_data(
    symbol: str,
    selected_exp: date,
    range_pct: float,
    options_dir: Path,
) -> tuple[pd.DataFrame, float, int] | None:
    single_snapshots = find_latest_snapshots(
        symbol,
        start_date=selected_exp,
        days_out=0,
        include_0dte=True,
        data_dir=options_dir,
    )
    if not single_snapshots:
        return None
    single_opts = load_options_snapshot(next(iter(single_snapshots.values())))
    spot, strike_range = _compute_spot_and_strike_range(single_opts, range_pct)
    return single_opts, spot, strike_range


def _select_single_expiry(symbol: str, today: date, options_dir: Path) -> str | None:
    available_exps_desc = sorted(list_expirations(symbol, data_dir=options_dir), reverse=True)
    if not available_exps_desc:
        return None

    exp_options = [expiry.isoformat() for expiry in available_exps_desc]
    today_iso = today.isoformat()
    default_idx = next((i for i, exp in enumerate(exp_options) if exp == today_iso), 0)
    return str(
        st.selectbox(
            "Single expiry",
            options=exp_options,
            index=default_idx,
            key="gm_expiry",
        )
    )


def _render_gex_view(
    symbol: str,
    today: date,
    include_0dte: bool,
    range_pct: float,
    options_dir: Path,
) -> None:
    days_out = int(
        st.radio(
            "Aggregate window",
            options=[5, 10, 20, 30],
            horizontal=True,
            key="gm_gex_days",
        )
    )
    wall_mode_label = st.radio(
        "Level model",
        options=["Distance-weighted aggregate", "Per-expiry clustering"],
        horizontal=True,
        key="gm_gex_wall_mode",
    )
    overlay_mode = st.radio(
        "Overlay",
        options=["Decision zones", "Walls"],
        horizontal=True,
        key="gm_gex_overlay_mode",
    )
    show_top_gamma_strikes = False
    if overlay_mode == "Walls":
        show_top_gamma_strikes = st.toggle(
            "Show top gamma strikes",
            value=False,
            key="gm_gex_show_top_gamma_strikes",
            help="Mark the largest aggregate call and put gamma strikes within the visible range.",
        )
    loaded = _load_window_snapshot_data(
        symbol=symbol,
        start_date=today,
        days_out=days_out,
        include_0dte=include_0dte,
        range_pct=range_pct,
        options_dir=options_dir,
    )
    if loaded is None:
        st.warning(f"No {symbol} options snapshots found for next {days_out} days.")
        return

    wall_mode = (
        "distance_weighted_aggregate"
        if wall_mode_label == "Distance-weighted aggregate"
        else "per_expiry_clustering"
    )
    _, all_opts, spot, strike_range = loaded
    strike_gex = net_gex_by_strike(all_opts, spot=spot, strike_range=strike_range)
    call_wall_strike: float | None = None
    put_wall_strike: float | None = None
    top_call_strikes: list[float] = []
    top_put_strikes: list[float] = []
    resistance_zones: list[dict[str, float]] = []
    support_zones: list[dict[str, float]] = []
    anchor_ts = pd.Timestamp(today)
    if overlay_mode == "Decision zones":
        resistance_zones, support_zones = find_decision_zones(
            all_opts,
            spot=spot,
            strike_range=strike_range,
            method=wall_mode,
            anchor_date=anchor_ts,
            top_n=2,
        )
    else:
        call_wall_strike, put_wall_strike = find_aggregate_wall_strikes(
            all_opts,
            spot=spot,
            strike_range=strike_range,
            method=wall_mode,
            anchor_date=anchor_ts,
        )
        if show_top_gamma_strikes:
            top_call_strikes, top_put_strikes = find_top_aggregate_gamma_strikes(
                all_opts,
                spot=spot,
                strike_range=strike_range,
                top_n=3,
                method=wall_mode,
                anchor_date=anchor_ts,
            )
    with st.spinner("Computing GEX by price grid..."):
        price_gex = net_gex_by_price(all_opts, spot=spot, price_range=strike_range)

    fig_agg = build_gex_aggregate_chart(
        strike_gex,
        price_gex,
        spot,
        call_wall_strike=call_wall_strike,
        put_wall_strike=put_wall_strike,
        top_call_strikes=top_call_strikes,
        top_put_strikes=top_put_strikes,
        resistance_zones=resistance_zones,
        support_zones=support_zones,
        title=f"{symbol} GEX Aggregate ({days_out}d)",
    )
    st.plotly_chart(fig_agg, use_container_width=True)


def _render_gex_history_view(
    symbol: str,
    include_0dte: bool,
    range_pct: float,
    options_dir: Path,
) -> None:
    sample_dates = list_snapshot_dates(symbol, data_dir=options_dir)
    if not sample_dates:
        st.warning(f"No historical {symbol} options snapshots found.")
        return

    col_date, col_window = st.columns([2, 2])
    with col_date:
        selected_sample_date = st.date_input(
            "Sample date",
            value=sample_dates[-1],
            min_value=sample_dates[0],
            max_value=sample_dates[-1],
            key="gm_gex_history_sample_date",
        )
    with col_window:
        days_out = int(
            st.radio(
                "Aggregate window",
                options=[5, 10, 20, 30],
                horizontal=True,
                key="gm_gex_history_days",
            )
        )

    if selected_sample_date not in set(sample_dates):
        st.warning(f"No historical {symbol} snapshots found on {selected_sample_date.isoformat()}.")
        return

    expiries = list_expirations_for_window_on_date(
        symbol,
        sample_date=selected_sample_date,
        days_out=days_out,
        include_0dte=include_0dte,
        data_dir=options_dir,
    )
    if not expiries:
        st.warning(
            f"No {symbol} expirations found in the {days_out}d window on "
            f"{selected_sample_date.isoformat()}."
        )
        return

    history_key = (
        symbol,
        selected_sample_date.isoformat(),
        days_out,
        include_0dte,
    )
    with st.spinner("Loading historical aggregate snapshots..."):
        if st.session_state.get("_gex_agg_history_key") != history_key:
            grouped_snapshots = find_snapshots_for_window_on_date(
                symbol,
                sample_date=selected_sample_date,
                expiries=tuple(expiries),
                data_dir=options_dir,
            )
            st.session_state["_gex_agg_history_key"] = history_key
            st.session_state["_gex_agg_history_grouped_snapshots"] = grouped_snapshots
        else:
            grouped_snapshots = st.session_state["_gex_agg_history_grouped_snapshots"]

    replay_times = sorted({ts for snapshots in grouped_snapshots.values() for ts, _ in snapshots})
    if not replay_times:
        st.warning(
            f"No historical {symbol} snapshots found for the selected aggregate window on "
            f"{selected_sample_date.isoformat()}."
        )
        return

    local_replay_times = [_to_chicago_time(ts) for ts in replay_times]
    slider_key = (
        symbol,
        selected_sample_date.isoformat(),
        days_out,
        include_0dte,
        len(local_replay_times),
    )
    if st.session_state.get("_gex_agg_history_slider_key") != slider_key:
        st.session_state["_gex_agg_history_slider_key"] = slider_key
        st.session_state["gm_gex_history_snapshot_time"] = local_replay_times[-1]

    if st.session_state.get("gm_gex_history_snapshot_time") not in local_replay_times:
        st.session_state["gm_gex_history_snapshot_time"] = local_replay_times[-1]

    selected_ts_local = st.select_slider(
        "Point in time (CT)",
        options=local_replay_times,
        key="gm_gex_history_snapshot_time",
        format_func=lambda ts: ts.strftime("%Y-%m-%d %H:%M:%S CT"),
    )
    replay_idx = local_replay_times.index(selected_ts_local)
    replay_time = replay_times[replay_idx]

    selected_paths = select_window_snapshots_at_or_before(grouped_snapshots, replay_time)
    if not selected_paths:
        st.warning(
            f"No {symbol} expiry snapshots were available at or before "
            f"{selected_ts_local.strftime('%Y-%m-%d %H:%M:%S CT')}."
        )
        return

    all_opts = pd.concat(
        [load_options_snapshot(path) for _, path in sorted(selected_paths.items())],
        ignore_index=True,
    )
    spot, strike_range = _compute_spot_and_strike_range(all_opts, range_pct)
    strike_gex = net_gex_by_strike(all_opts, spot=spot, strike_range=strike_range)
    snap_time = pd.Timestamp(replay_time)
    if snap_time.tzinfo is not None:
        snap_time = snap_time.tz_convert("UTC").tz_localize(None)
    with st.spinner("Computing historical GEX by price grid..."):
        price_gex = net_gex_by_price(
            all_opts,
            spot=spot,
            snap_time=snap_time,
            price_range=strike_range,
        )

    st.caption(
        f"Snapshot time: {selected_ts_local.strftime('%Y-%m-%d %H:%M:%S CT')} | "
        f"Expiries: {len(selected_paths)}"
    )
    fig_agg = build_gex_aggregate_chart(
        strike_gex,
        price_gex,
        spot,
        title=(
            f"{symbol} GEX History ({days_out}d) "
            f"({selected_sample_date.isoformat()} {selected_ts_local.strftime('%H:%M:%S')} CT)"
        ),
    )
    st.plotly_chart(fig_agg, use_container_width=True)


def _render_chains_view(
    symbol: str,
    selected_exp: date,
    range_pct: float,
    options_dir: Path,
) -> None:
    loaded = _load_single_expiry_snapshot_data(symbol, selected_exp, range_pct, options_dir)
    if loaded is None:
        st.warning(f"No {symbol} options snapshots found for {selected_exp.isoformat()}.")
        return

    single_opts, spot, strike_range = loaded
    rr_result = compute_risk_reversal(single_opts)
    if rr_result is not None:
        fig_rr = build_skew_indicators(rr_result, spot=spot)
        st.plotly_chart(fig_rr, use_container_width=True)

    fig_single = build_gex_single_expiry_chart(
        single_opts,
        spot=spot,
        strike_range=strike_range,
        title=f"{symbol} GEX {selected_exp}",
    )
    st.subheader("GEX Single Expiry")
    st.plotly_chart(fig_single, use_container_width=True)

    fig_skew = build_vol_skew_chart(
        single_opts,
        spot=spot,
        strike_range=strike_range,
        title=f"{symbol} Vol Skew {selected_exp}",
    )
    st.subheader("Volatility Skew")
    st.plotly_chart(fig_skew, use_container_width=True)

    price_series = st.radio(
        "Price series",
        options=["mark", "bid", "ask"],
        horizontal=True,
        key="gm_chain_price_series",
    )
    fig_price = build_vol_skew_chart(
        single_opts,
        spot=spot,
        strike_range=strike_range,
        title=f"{symbol} Option Price {selected_exp}",
        value_col=price_series,
        value_label="Price",
    )
    st.subheader("Option Price by Strike")
    st.plotly_chart(fig_price, use_container_width=True)

    fig_delta = build_vol_skew_chart(
        single_opts,
        spot=spot,
        strike_range=strike_range,
        title=f"{symbol} Delta by Strike {selected_exp}",
        value_col="delta",
        value_label="Delta",
        allow_negative=True,
        abs_puts=True,
    )
    st.subheader("Delta by Strike")
    st.plotly_chart(fig_delta, use_container_width=True)


def _render_history_view(
    symbol: str,
    selected_exp: date,
    range_pct: float,
    options_dir: Path,
) -> None:
    sample_dates = list_snapshot_dates_for_expiry(symbol, selected_exp, data_dir=options_dir)
    if not sample_dates:
        st.warning(f"No {symbol} options snapshots found for {selected_exp.isoformat()}.")
        return

    selected_sample_date = st.date_input(
        "Sample date",
        value=sample_dates[-1],
        min_value=sample_dates[0],
        max_value=sample_dates[-1],
        key="gm_history_sample_date",
    )

    if selected_sample_date not in set(sample_dates):
        st.warning(
            f"No {symbol} snapshots found on {selected_sample_date.isoformat()} for "
            f"{selected_exp.isoformat()}."
        )
        return

    history_key = (
        symbol,
        selected_exp.isoformat(),
        selected_sample_date.isoformat(),
        range_pct,
    )
    with st.spinner("Loading historical chain snapshots..."):
        if st.session_state.get("_gex_history_key") != history_key:
            snapshots = find_snapshots_for_expiry_on_date(
                symbol,
                expiry=selected_exp,
                sample_date=selected_sample_date,
                data_dir=options_dir,
            )
            st.session_state["_gex_history_key"] = history_key
            st.session_state["_gex_history_snapshots"] = snapshots
        else:
            snapshots = st.session_state["_gex_history_snapshots"]

    if not snapshots:
        st.warning(
            f"No {symbol} snapshots found on {selected_sample_date.isoformat()} for "
            f"{selected_exp.isoformat()}."
        )
        return

    local_timestamps = [_to_chicago_time(ts) for ts, _ in snapshots]
    if st.session_state.get("_gex_history_slider_key") != history_key:
        st.session_state["_gex_history_slider_key"] = history_key
        st.session_state["gm_history_snapshot_time"] = local_timestamps[-1]

    snapshot_idx = len(snapshots) - 1
    if len(snapshots) > 1:
        if st.session_state.get("gm_history_snapshot_time") not in local_timestamps:
            st.session_state["gm_history_snapshot_time"] = local_timestamps[-1]
        selected_ts_local = st.select_slider(
            "Point in time (CT)",
            options=local_timestamps,
            key="gm_history_snapshot_time",
            format_func=lambda ts: ts.strftime("%Y-%m-%d %H:%M:%S CT"),
        )
        snapshot_idx = local_timestamps.index(selected_ts_local)

    selected_ts, selected_path = snapshots[snapshot_idx]
    selected_ts_local = local_timestamps[snapshot_idx]
    st.caption(f"Snapshot time: {selected_ts_local.strftime('%Y-%m-%d %H:%M:%S CT')}")

    single_opts = load_options_snapshot(selected_path)
    spot, strike_range = _compute_spot_and_strike_range(single_opts, range_pct)
    fig_single = build_gex_single_expiry_chart(
        single_opts,
        spot=spot,
        strike_range=strike_range,
        title=(
            f"{symbol} Chain GEX History {selected_exp} "
            f"({selected_sample_date.isoformat()} {selected_ts_local.strftime('%H:%M:%S')} CT)"
        ),
    )
    st.plotly_chart(fig_single, use_container_width=True)


def _render_intraday_view(
    symbol: str,
    selected_exp: date,
    range_pct: float,
    options_dir: Path,
) -> None:
    loaded = _load_single_expiry_snapshot_data(symbol, selected_exp, range_pct, options_dir)
    if loaded is None:
        st.warning(f"No {symbol} options snapshots found for {selected_exp.isoformat()}.")
        return

    _, spot, strike_range = loaded
    col_ct, col_date, col_wt = st.columns([3, 2, 1])
    with col_ct:
        ct_filter = str(
            st.radio(
                "Contract type",
                options=["ALL", "CALL", "PUT"],
                horizontal=True,
                key="gm_intraday_ct",
            )
        )
    with col_date:
        intraday_date = st.date_input(
            "Sample date",
            value=date.today(),
            key="gm_intraday_date",
        )
    with col_wt:
        weight_by_delta = st.toggle("Weight by delta", value=True, key="gm_intraday_weight_delta")
    bucket_minutes = int(
        st.select_slider(
            "Sample interval (minutes)",
            options=[1, 5, 10, 15, 20, 25, 30],
            value=5,
            key="gm_intraday_bucket",
        )
    )

    all_expiry_snapshots = find_all_snapshots_for_expiry(
        symbol,
        expiry=selected_exp,
        data_dir=options_dir,
    )
    flow_key = (
        symbol,
        selected_exp.isoformat(),
        round(spot),
        strike_range,
        ct_filter,
        bucket_minutes,
        weight_by_delta,
        intraday_date,
        len(all_expiry_snapshots),
    )
    with st.spinner("Computing intraday flow..."):
        if st.session_state.get("_flow_key") != flow_key:
            flow_strikes, flow_timestamps, flow_matrix, flow_prices = compute_intraday_flow(
                all_expiry_snapshots,
                spot=spot,
                moneyness_pct=range_pct / 100,
                contract_filter=ct_filter,
                bucket_minutes=bucket_minutes,
                weight_by_delta=weight_by_delta,
                target_date=intraday_date,
            )
            st.session_state["_flow_key"] = flow_key
            st.session_state["_flow_strikes"] = flow_strikes
            st.session_state["_flow_timestamps"] = flow_timestamps
            st.session_state["_flow_matrix"] = flow_matrix
            st.session_state["_flow_prices"] = flow_prices
        else:
            flow_strikes = st.session_state["_flow_strikes"]
            flow_timestamps = st.session_state["_flow_timestamps"]
            flow_matrix = st.session_state["_flow_matrix"]
            flow_prices = st.session_state["_flow_prices"]

        fig_flow = build_flow_heatmap_chart(
            flow_strikes,
            flow_timestamps,
            flow_matrix,
            prices=flow_prices,
            title=f"{symbol} Intraday Flow {selected_exp}",
        )
    st.plotly_chart(fig_flow, use_container_width=True)

    st.divider()
    col_sct, col_sdate, _ = st.columns([2, 2, 2])
    with col_sct:
        spread_ct = str(
            st.radio(
                "Contract type",
                options=["CALL", "PUT"],
                horizontal=True,
                key="gm_spread_ct",
            )
        )
    with col_sdate:
        spread_date = st.date_input(
            "Sample Date",
            value=date.today(),
            key="gm_spread_date",
        )
    spread_bucket_minutes = int(
        st.select_slider(
            "Sample interval (minutes)",
            options=[1, 5, 10, 15, 20, 25, 30],
            value=5,
            key="gm_spread_bucket",
        )
    )

    spread_key = (
        symbol,
        selected_exp.isoformat(),
        round(spot),
        strike_range,
        spread_ct,
        spread_bucket_minutes,
        spread_date,
        len(all_expiry_snapshots),
    )
    with st.spinner("Computing spread heatmap..."):
        if st.session_state.get("_spread_key") != spread_key:
            spread_strikes, spread_ts, spread_matrix, spread_prices = compute_intraday_spread(
                all_expiry_snapshots,
                spot=spot,
                moneyness_pct=range_pct / 100,
                contract_filter=spread_ct,
                bucket_minutes=spread_bucket_minutes,
                target_date=spread_date,
            )
            st.session_state["_spread_key"] = spread_key
            st.session_state["_spread_strikes"] = spread_strikes
            st.session_state["_spread_ts"] = spread_ts
            st.session_state["_spread_matrix"] = spread_matrix
            st.session_state["_spread_prices"] = spread_prices
        else:
            spread_strikes = st.session_state["_spread_strikes"]
            spread_ts = st.session_state["_spread_ts"]
            spread_matrix = st.session_state["_spread_matrix"]
            spread_prices = st.session_state["_spread_prices"]

        fig_spread = build_spread_heatmap_chart(
            spread_strikes,
            spread_ts,
            spread_matrix,
            prices=spread_prices,
            title=f"{symbol} Bid-Ask Spread Z {selected_exp} ({spread_ct})",
        )
    st.plotly_chart(fig_spread, use_container_width=True)


def _render_gamma_heatmap_view(
    symbol: str,
    today: date,
    include_0dte: bool,
    range_pct: float,
    options_dir: Path,
) -> None:
    gh_date_range = st.date_input(
        "Expiration date range",
        value=(today, today + timedelta(days=10)),
        key="gm_gh_dates",
    )
    gh_normalize = st.toggle(
        "Relative GEX (per-expiry normalized)",
        value=False,
        key="gm_gh_normalize",
    )

    if isinstance(gh_date_range, tuple) and len(gh_date_range) == 2:
        gh_start, gh_end = gh_date_range[0], gh_date_range[1]
    else:
        gh_start, gh_end = today, today + timedelta(days=10)

    loaded = _load_window_snapshot_data(
        symbol=symbol,
        start_date=gh_start,
        days_out=(gh_end - gh_start).days,
        include_0dte=include_0dte,
        range_pct=range_pct,
        options_dir=options_dir,
    )
    if loaded is None:
        st.warning(f"No {symbol} snapshots found for selected date range.")
        return

    gh_snapshots, _, spot, strike_range = loaded
    gh_key = (symbol, round(spot), strike_range, gh_start, gh_end, len(gh_snapshots))
    with st.spinner("Computing GEX term structure..."):
        if st.session_state.get("_gh_key") != gh_key:
            gh_strikes, gh_expirations, gh_matrix = compute_gex_term_structure(
                gh_snapshots, spot=spot, strike_range=strike_range
            )
            st.session_state["_gh_key"] = gh_key
            st.session_state["_gh_strikes"] = gh_strikes
            st.session_state["_gh_expirations"] = gh_expirations
            st.session_state["_gh_matrix"] = gh_matrix
        else:
            gh_strikes = st.session_state["_gh_strikes"]
            gh_expirations = st.session_state["_gh_expirations"]
            gh_matrix = st.session_state["_gh_matrix"]

    gh_y_range: tuple[float, float] | None = None
    if gh_strikes and len(gh_strikes) >= 2:
        gh_strike_range = st.select_slider(
            "Strike range",
            options=gh_strikes,
            value=(gh_strikes[0], gh_strikes[-1]),
            key="gm_gh_strike_range",
        )
        gh_y_range = (float(gh_strike_range[0]), float(gh_strike_range[1]))

    fig_gh = build_gex_term_structure_chart(
        gh_strikes,
        gh_expirations,
        gh_matrix,
        spot=spot,
        normalize=gh_normalize,
        y_range=gh_y_range,
        title=f"{symbol} GEX Term Structure",
    )
    st.plotly_chart(fig_gh, use_container_width=True)


def _render_maker_taker_view(
    symbol: str,
    selected_exp: date,
    range_pct: float,
    options_dir: Path,
) -> None:
    loaded = _load_single_expiry_snapshot_data(symbol, selected_exp, range_pct, options_dir)
    if loaded is None:
        st.warning(f"No {symbol} options snapshots found for {selected_exp.isoformat()}.")
        return

    _, spot, strike_range = loaded
    col_mt_bucket, col_mt_top_n, col_mt_date = st.columns([1, 1, 1])
    with col_mt_bucket:
        mt_bucket = int(
            st.select_slider(
                "Sample interval (minutes)",
                options=[1, 5, 10, 15, 30, 60],
                value=5,
                key="gm_mt_bucket",
            )
        )
    with col_mt_top_n:
        mt_top_n = int(
            st.slider(
                "Top N strikes",
                min_value=5,
                max_value=20,
                value=10,
                key="gm_mt_top_n",
            )
        )
    with col_mt_date:
        mt_date = st.date_input("Sample date", value=date.today(), key="gm_mt_date")
    mt_weight = "total_volume"

    all_expiry_snapshots = find_all_snapshots_for_expiry(
        symbol,
        expiry=selected_exp,
        data_dir=options_dir,
    )
    for mt_ct in ["CALL", "PUT"]:
        mt_key = (
            symbol,
            selected_exp.isoformat(),
            round(spot),
            strike_range,
            mt_ct,
            mt_bucket,
            mt_date,
            mt_top_n,
            len(all_expiry_snapshots),
        )
        state_prefix = f"_mt_{mt_ct}"

        with st.spinner(f"Computing maker-taker flow ({mt_ct})..."):
            if st.session_state.get(f"{state_prefix}_key") != mt_key:
                mt_timestamps, mt_strikes, mt_flows, mt_bucket_times, mt_bucket_prices = (
                    compute_maker_taker_flow(
                        all_expiry_snapshots,
                        spot=spot,
                        moneyness_pct=range_pct / 100,
                        contract_filter=mt_ct,
                        bucket_minutes=mt_bucket,
                        weight_by=mt_weight,
                        target_date=mt_date,
                        top_n_strikes=mt_top_n,
                    )
                )
                st.session_state[f"{state_prefix}_key"] = mt_key
                st.session_state[f"{state_prefix}_timestamps"] = mt_timestamps
                st.session_state[f"{state_prefix}_strikes"] = mt_strikes
                st.session_state[f"{state_prefix}_flows"] = mt_flows
                st.session_state[f"{state_prefix}_bucket_times"] = mt_bucket_times
                st.session_state[f"{state_prefix}_bucket_prices"] = mt_bucket_prices
            else:
                mt_timestamps = st.session_state[f"{state_prefix}_timestamps"]
                mt_strikes = st.session_state[f"{state_prefix}_strikes"]
                mt_flows = st.session_state[f"{state_prefix}_flows"]
                mt_bucket_times = st.session_state[f"{state_prefix}_bucket_times"]
                mt_bucket_prices = st.session_state[f"{state_prefix}_bucket_prices"]

            fig_mt = build_maker_taker_bubble_chart(
                mt_timestamps,
                mt_strikes,
                mt_flows,
                mt_bucket_times,
                mt_bucket_prices,
                spot=spot,
                title=f"{symbol} Maker-Taker {selected_exp} ({mt_ct})",
            )
        st.plotly_chart(fig_mt, use_container_width=True)


def _render_active_gamma_view(
    active_view: str,
    symbol: str,
    today: date,
    include_0dte: bool,
    range_pct: float,
    selected_exp_str: str | None,
    options_dir: Path,
) -> None:
    if active_view == "GEX":
        _render_gex_view(symbol, today, include_0dte, range_pct, options_dir)
        return
    if active_view == "Gamma Heatmap":
        _render_gamma_heatmap_view(symbol, today, include_0dte, range_pct, options_dir)
        return
    if active_view not in _SINGLE_EXPIRY_VIEWS:
        raise ValueError(f"Unknown Gamma Map view: {active_view}")

    if selected_exp_str is None:
        st.warning(f"No expirations available for {symbol}.")
        return

    selected_exp = date.fromisoformat(selected_exp_str)
    if active_view == "Chains":
        _render_chains_view(symbol, selected_exp, range_pct, options_dir)
        return
    if active_view == "Intraday":
        _render_intraday_view(symbol, selected_exp, range_pct, options_dir)
        return
    if active_view == "Maker-Taker":
        _render_maker_taker_view(symbol, selected_exp, range_pct, options_dir)
        return
    raise ValueError(f"Unknown Gamma Map view: {active_view}")


def render_gamma_map_tab(options_dir: Path, candle_dir: Path) -> None:
    del candle_dir
    st.subheader("Gamma Map")

    @st.fragment(run_every="5m")
    def _render() -> None:
        col_ctrl, col_chart = st.columns([1, 3])

        with col_ctrl:
            include_0dte = st.toggle("Include 0DTE", value=True, key="gm_0dte")
            symbol = str(st.selectbox("Symbol", ["SPXW", "SPX"], index=0, key="gm_symbol"))
            range_pct = float(
                st.slider(
                    "Strike range (% of spot)",
                    min_value=1,
                    max_value=25,
                    value=5,
                    step=1,
                    key="gm_range_pct",
                )
            )

        today = date.today()

        with col_chart:
            active_view = str(
                st.segmented_control(
                    "Gamma Map View",
                    options=_GAMMA_MAP_VIEWS,
                    default="GEX",
                    selection_mode="single",
                    key="gm_view",
                    label_visibility="collapsed",
                )
            )

        selected_exp_str: str | None = None
        if active_view in _SINGLE_EXPIRY_VIEWS:
            with col_ctrl:
                st.divider()
                selected_exp_str = _select_single_expiry(symbol, today, options_dir)

        with col_chart:
            _render_active_gamma_view(
                active_view=active_view,
                symbol=symbol,
                today=today,
                include_0dte=include_0dte,
                range_pct=range_pct,
                selected_exp_str=selected_exp_str,
                options_dir=options_dir,
            )

    _render()
