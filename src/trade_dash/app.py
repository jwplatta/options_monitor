"""Streamlit application for the trading dashboard."""

from __future__ import annotations

import streamlit as st

from trade_dash.config import CANDLE_DIR, OPTIONS_DIR
from trade_dash.tabs.flow import render_flow_tab
from trade_dash.tabs.gamma_map import render_gamma_map_tab
from trade_dash.tabs.history import render_history_tab
from trade_dash.tabs.regime import render_regime_tab
from trade_dash.tabs.vol import render_vol_tab

_TOP_LEVEL_TABS = ["Regime", "Vol", "Gamma Map", "History", "Flow"]

_TAB_SPINNER_MSG: dict[str, str] = {
    "Regime":    "Loading Regime...",
    "Vol":       "Loading Vol...",
    "Gamma Map": "Loading Gamma Map...",
    "History":   "Loading History...",
    "Flow":      "Loading Flow...",
}


def _render_active_dashboard_tab(active_tab: str) -> None:
    """Render only the selected top-level dashboard panel."""
    if active_tab == "Regime":
        render_regime_tab(candle_dir=CANDLE_DIR)
        return
    if active_tab == "Vol":
        render_vol_tab(candle_dir=CANDLE_DIR)
        return
    if active_tab == "Gamma Map":
        render_gamma_map_tab(options_dir=OPTIONS_DIR, candle_dir=CANDLE_DIR)
        return
    if active_tab == "History":
        render_history_tab(options_dir=OPTIONS_DIR, candle_dir=CANDLE_DIR)
        return
    if active_tab == "Flow":
        render_flow_tab(options_dir=OPTIONS_DIR)
        return
    raise ValueError(f"Unknown dashboard tab: {active_tab}")


def render_dashboard() -> None:
    """Render the main 3-tab Streamlit dashboard."""
    st.set_page_config(
        page_title="trade_dash",
        page_icon=":chart_with_upwards_trend:",
        layout="wide",
    )

    with st.sidebar:
        st.title("trade_dash")
        active_tab = str(
            st.radio(
                "Navigation",
                options=_TOP_LEVEL_TABS,
                index=0,
                key="dashboard_tab",
                label_visibility="collapsed",
            )
        )
    with st.spinner(_TAB_SPINNER_MSG.get(active_tab, "Loading...")):
        _render_active_dashboard_tab(active_tab)


if __name__ == "__main__":
    render_dashboard()
