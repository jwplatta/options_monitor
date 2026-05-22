"""Streamlit application for the trading dashboard."""

from __future__ import annotations

import streamlit as st

from trade_dash.config import CANDLE_DIR, OPTIONS_DIR
from trade_dash.tabs.gamma_map import render_gamma_map_tab
from trade_dash.tabs.regime import render_regime_tab
from trade_dash.tabs.vol import render_vol_tab


def render_dashboard() -> None:
    """Render the main 3-tab Streamlit dashboard."""
    st.set_page_config(
        page_title="trade_dash",
        page_icon=":chart_with_upwards_trend:",
        layout="wide",
    )

    with st.sidebar:
        st.title("trade_dash")
        show_chat = st.toggle("Agent Chat", value=False)
        if show_chat:
            st.subheader("Agent Chat")
            st.info(
                "Agent integration coming soon. Chat will be fed the same data as the active panel."
            )
            st.chat_input("Ask about the charts...", disabled=True)

    tab0, tab1, tab2 = st.tabs(["Regime", "Vol", "Gamma Map"])

    with tab0:
        render_regime_tab(candle_dir=CANDLE_DIR)
    with tab1:
        render_vol_tab(candle_dir=CANDLE_DIR)
    with tab2:
        render_gamma_map_tab(options_dir=OPTIONS_DIR, candle_dir=CANDLE_DIR)


if __name__ == "__main__":
    render_dashboard()
