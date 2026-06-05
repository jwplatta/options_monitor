"""Playwright smoke tests for the trade_dash Streamlit UI."""

from __future__ import annotations

from playwright.sync_api import Page, expect


def test_dashboard_loads_title(page: Page, streamlit_server: str) -> None:
    """Dashboard loads without error and shows the current navigation control."""
    page.goto(streamlit_server)
    page.wait_for_selector("text=trade_dash", timeout=20000)
    page.wait_for_selector("button:has-text('Regime')", timeout=20000)
    assert page.title() is not None


def test_all_navigation_options_visible(page: Page, streamlit_server: str) -> None:
    """The top-level segmented navigation exposes all dashboard panels."""
    page.goto(streamlit_server)
    page.wait_for_selector("button:has-text('Regime')", timeout=20000)
    for panel_name in ["Regime", "Vol", "Gamma Map"]:
        assert page.locator(f"button:has-text('{panel_name}')").count() > 0


def test_regime_tab_renders_chart(page: Page, streamlit_server: str) -> None:
    """Regime panel is the default view and renders a plotly chart."""
    page.goto(streamlit_server)
    page.wait_for_selector("button:has-text('Regime')", timeout=20000)
    page.wait_for_selector("[data-testid='stPlotlyChart']", timeout=30000, state="attached")


def test_vol_tab_renders(page: Page, streamlit_server: str) -> None:
    """Vol tab loads and shows the 9D/30D radio labels."""
    page.goto(streamlit_server)
    page.wait_for_selector("button:has-text('Vol')", timeout=20000)
    page.locator("button:has-text('Vol')").click()
    page.wait_for_selector("label:has-text('9D')", timeout=10000, state="attached")
    assert page.locator("label:has-text('9D')").count() > 0
    assert page.locator("label:has-text('30D')").count() > 0


def test_gamma_map_tab_renders(page: Page, streamlit_server: str) -> None:
    """Gamma Map tab loads and shows aggregate GEX day presets."""
    page.goto(streamlit_server)
    page.wait_for_selector("button:has-text('Gamma Map')", timeout=20000)
    page.locator("button:has-text('Gamma Map')").click()
    page.wait_for_selector("text=Aggregate window", timeout=15000, state="attached")
    assert page.locator("label:has-text('5')").count() > 0
    assert page.locator("label:has-text('10')").count() > 0
    assert page.locator("label:has-text('20')").count() > 0
    assert page.locator("label:has-text('30')").count() > 0


def test_agent_chat_toggle_visible(page: Page, streamlit_server: str) -> None:
    """Agent chat toggle is present in the sidebar."""
    page.goto(streamlit_server)
    sidebar = page.locator("[data-testid='stSidebar']")
    expect(sidebar.get_by_text("Agent Chat")).to_be_visible(timeout=20000)
