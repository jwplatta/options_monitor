"""Flow tab: Flow Tape and Flow Profile charts for SPXW option activity."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from trade_dash.calc.flow_profile import compute_flow_profile
from trade_dash.calc.flow_tape import compute_flow_tape
from trade_dash.charts.flow_profile import build_flow_profile_chart
from trade_dash.charts.flow_tape import build_flow_tape_chart
from trade_dash.data.options import (
    find_snapshots_for_expiry_on_date,
    list_expirations,
    list_snapshot_dates,
    load_options_snapshot,
)

_SYMBOL = "SPXW"
_CONTRACT_MAP = {"Both": "BOTH", "Calls": "CALL", "Puts": "PUT"}
_MODE_MAP = {"New Flow": "lookback", "Cumulative Flow": "cumulative"}


def _get_spot(snapshots: list[tuple[datetime, Path]]) -> float | None:
    if not snapshots:
        return None
    latest_df = load_options_snapshot(snapshots[-1][1])
    spot_series = pd.to_numeric(latest_df["underlying_price"], errors="coerce").dropna()
    return float(spot_series.iloc[0]) if not spot_series.empty else None


def _render_flow_tape_view(
    snapshots: list[tuple[datetime, Path]],
    spot: float,
    sample_date: date,
    lookback_window: int,
    mode: str,
    contract_filter: str,
    selected_exp: date,
) -> None:
    tape_key = (
        _SYMBOL,
        selected_exp.isoformat(),
        sample_date.isoformat(),
        lookback_window,
        mode,
        contract_filter,
        len(snapshots),
    )
    if st.session_state.get("_fl_tape_key") != tape_key:
        with st.spinner("Computing flow tape..."):
            timestamps, call_flow, put_flow = compute_flow_tape(
                snapshots,
                spot=spot,
                sample_date=sample_date,
                lookback_window=lookback_window,
                mode=mode,
                contract_filter=contract_filter,
            )
        st.session_state["_fl_tape_key"] = tape_key
        st.session_state["_fl_tape_timestamps"] = timestamps
        st.session_state["_fl_tape_call"] = call_flow
        st.session_state["_fl_tape_put"] = put_flow
    else:
        timestamps = st.session_state["_fl_tape_timestamps"]
        call_flow = st.session_state["_fl_tape_call"]
        put_flow = st.session_state["_fl_tape_put"]

    if not timestamps:
        st.warning("No flow data for selected date/expiry.")
        return

    fig = build_flow_tape_chart(
        timestamps,
        call_flow,
        put_flow,
        title=f"Flow Tape — {_SYMBOL} {selected_exp.isoformat()} ({sample_date.isoformat()})",
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_flow_profile_view(
    snapshots: list[tuple[datetime, Path]],
    sample_date: date,
    lookback_window: int,
    mode: str,
    contract_filter: str,
    selected_exp: date,
    spot: float,
    range_pct: float,
) -> None:
    profile_key = (
        _SYMBOL,
        selected_exp.isoformat(),
        sample_date.isoformat(),
        lookback_window,
        mode,
        contract_filter,
        len(snapshots),
        range_pct,
    )
    if st.session_state.get("_fl_profile_key") != profile_key:
        with st.spinner("Computing flow profile..."):
            strikes, call_flow, put_flow = compute_flow_profile(
                snapshots,
                sample_date=sample_date,
                lookback_window=lookback_window,
                mode=mode,
                contract_filter=contract_filter,
            )
        st.session_state["_fl_profile_key"] = profile_key
        st.session_state["_fl_profile_strikes"] = strikes
        st.session_state["_fl_profile_call"] = call_flow
        st.session_state["_fl_profile_put"] = put_flow
    else:
        strikes = st.session_state["_fl_profile_strikes"]
        call_flow = st.session_state["_fl_profile_call"]
        put_flow = st.session_state["_fl_profile_put"]

    if not strikes:
        st.warning("No flow data for selected date/expiry.")
        return

    # Filter to strikes within range_pct of spot before charting.
    half_range = spot * range_pct / 100
    filtered = [
        (s, c, p)
        for s, c, p in zip(strikes, call_flow, put_flow, strict=True)
        if abs(s - spot) <= half_range
    ]
    if filtered:
        f_strikes, f_call, f_put = zip(*filtered, strict=False)
        strikes_plot = list(f_strikes)
        call_plot = list(f_call)
        put_plot = list(f_put)
    else:
        strikes_plot, call_plot, put_plot = strikes, call_flow, put_flow

    mode_label = "Lookback" if mode == "lookback" else "Cumulative"
    fig = build_flow_profile_chart(
        strikes_plot,
        call_plot,
        put_plot,
        title=(
            f"Flow Profile — {_SYMBOL} {selected_exp.isoformat()} "
            f"({sample_date.isoformat()}, {mode_label})"
        ),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_flow_tab(options_dir: Path) -> None:
    """Render the Flow tab with Flow Tape and Flow Profile charts."""
    st.subheader("Flow")

    col_ctrl, col_chart = st.columns([1, 3])

    with col_ctrl:
        # Sample date selection.
        sample_dates = list_snapshot_dates(_SYMBOL, data_dir=options_dir)
        if not sample_dates:
            st.error("No SPXW snapshots found.")
            return

        sample_date = st.date_input(
            "Sample date",
            value=sample_dates[-1],
            min_value=sample_dates[0],
            max_value=sample_dates[-1],
            key="fl_sample_date",
        )

        # Expiration selection — default to 0DTE if available.
        all_expiries = list_expirations(_SYMBOL, data_dir=options_dir)
        # Filter to expirations that have snapshots on the chosen sample date.
        available_expiries = [e for e in all_expiries if e >= sample_date]
        if not available_expiries:
            st.error("No expirations available for selected date.")
            return

        default_exp_idx = next(
            (i for i, e in enumerate(available_expiries) if e == sample_date), 0
        )
        selected_exp_str = st.selectbox(
            "Expiration",
            options=[e.isoformat() for e in available_expiries],
            index=default_exp_idx,
            key="fl_expiry",
        )
        selected_exp = date.fromisoformat(str(selected_exp_str))

        st.divider()

        lookback_window = int(
            st.select_slider(
                "Lookback window (min)",
                options=[1, 5, 15, 30],
                value=5,
                key="fl_lookback",
            )
        )
        mode_label = str(
            st.radio(
                "Mode",
                options=["New Flow", "Cumulative Flow"],
                horizontal=True,
                key="fl_mode",
            )
        )
        contract_label = str(
            st.radio(
                "Contracts",
                options=["Both", "Calls", "Puts"],
                horizontal=True,
                key="fl_contracts",
            )
        )
        range_pct = float(
            st.slider(
                "Strike range (% of spot)",
                min_value=1,
                max_value=25,
                value=3,
                step=1,
                key="fl_range_pct",
            )
        )

    contract_filter = _CONTRACT_MAP[contract_label]
    mode = _MODE_MAP[mode_label]

    # Load snapshots for the selected expiry on the selected date.
    snapshots = find_snapshots_for_expiry_on_date(
        _SYMBOL,
        expiry=selected_exp,
        sample_date=sample_date,
        data_dir=options_dir,
    )

    if not snapshots:
        with col_chart:
            st.warning(f"No snapshots found for {_SYMBOL} expiry {selected_exp} on {sample_date}.")
        return

    spot = _get_spot(snapshots)
    if spot is None:
        with col_chart:
            st.warning("Could not determine spot price from snapshots.")
        return

    with col_chart:
        active_view = str(
            st.segmented_control(
                "Flow View",
                options=["Flow Tape", "Flow Profile"],
                default="Flow Tape",
                selection_mode="single",
                key="fl_view",
                label_visibility="collapsed",
            )
        )

        if active_view == "Flow Tape":
            _render_flow_tape_view(
                snapshots,
                spot=spot,
                sample_date=sample_date,
                lookback_window=lookback_window,
                mode=mode,
                contract_filter=contract_filter,
                selected_exp=selected_exp,
            )
        else:
            _render_flow_profile_view(
                snapshots,
                sample_date=sample_date,
                lookback_window=lookback_window,
                mode=mode,
                contract_filter=contract_filter,
                selected_exp=selected_exp,
                spot=spot,
                range_pct=range_pct,
            )
