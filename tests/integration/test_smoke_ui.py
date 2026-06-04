"""Playwright smoke tests for the trade_dash Streamlit UI."""

from __future__ import annotations

from playwright.sync_api import Page, expect


def test_dashboard_loads_title(page: Page, streamlit_server: str) -> None:
    """Dashboard loads without error and shows tab navigation."""
    page.goto(streamlit_server)
    page.wait_for_selector("text=Summary", timeout=20000)
    assert page.title() is not None


def test_all_tabs_visible(page: Page, streamlit_server: str) -> None:
    """All 4 tabs are visible in the navigation."""
    page.goto(streamlit_server)
    page.wait_for_selector("text=Summary", timeout=20000)
    for tab_name in ["Summary", "Regime", "Vol", "Gamma Map"]:
        assert page.locator(f"text={tab_name}").count() > 0, f"Tab '{tab_name}' not found"


def test_regime_tab_renders_chart(page: Page, streamlit_server: str) -> None:
    """Regime tab loads and renders a plotly chart."""
    page.goto(streamlit_server)
    page.wait_for_selector("text=Regime", timeout=20000)
    page.get_by_role("tab", name="Regime").click()
    # Use state="attached" since Streamlit may keep elements in DOM but not visible
    page.wait_for_selector("[data-testid='stPlotlyChart']", timeout=30000, state="attached")


def test_vol_tab_renders(page: Page, streamlit_server: str) -> None:
    """Vol tab loads and shows the 9D/30D radio labels."""
    page.goto(streamlit_server)
    page.wait_for_selector("text=Vol", timeout=20000)
    page.get_by_role("tab", name="Vol").click()
    # Radio options "9D" and "30D" are rendered as labels; use partial-text match
    page.wait_for_selector("label:has-text('9D')", timeout=10000, state="attached")
    assert page.locator("label:has-text('9D')").count() > 0
    assert page.locator("label:has-text('30D')").count() > 0


def test_gamma_map_tab_renders(page: Page, streamlit_server: str) -> None:
    """Gamma Map tab loads and shows aggregate GEX day presets."""
    page.goto(streamlit_server)
    page.wait_for_selector("text=Gamma Map", timeout=20000)
    page.get_by_role("tab", name="Gamma Map").click()
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
