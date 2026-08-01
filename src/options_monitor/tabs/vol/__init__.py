"""Vol tab package."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from options_monitor.config import OPTIONS_DIR
from options_monitor.tabs.vol.fixed_strike import render_fixed_strike_tab
from options_monitor.tabs.vol.overview import render_overview_tab
from options_monitor.tabs.vol.spx_rv import render_spx_rv_tab


def render_vol_tab(candle_dir: Path, options_dir: Path = OPTIONS_DIR) -> None:
    st.subheader("Volatility")

    tab_overview, tab_spx_rv, tab_fsv = st.tabs(["Overview", "SPX RV", "Fixed Strike Vol"])

    with tab_overview:
        render_overview_tab(candle_dir)

    with tab_spx_rv:
        render_spx_rv_tab(candle_dir)

    with tab_fsv:
        render_fixed_strike_tab(options_dir)
