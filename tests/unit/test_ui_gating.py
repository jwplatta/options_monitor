from __future__ import annotations

from contextlib import nullcontext
from datetime import date
from pathlib import Path

import pandas as pd

from trade_dash import app
from trade_dash.tabs import gamma_map


def test_dashboard_router_only_invokes_selected_panel(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(app, "render_regime_tab", lambda candle_dir: calls.append("regime"))
    monkeypatch.setattr(app, "render_vol_tab", lambda candle_dir: calls.append("vol"))
    monkeypatch.setattr(
        app,
        "render_gamma_map_tab",
        lambda options_dir, candle_dir: calls.append("gamma"),
    )

    app._render_active_dashboard_tab("Vol")
    assert calls == ["vol"]


def test_gamma_router_only_invokes_selected_view(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        gamma_map,
        "_render_gex_view",
        lambda symbol, today, include_0dte, range_pct, options_dir: calls.append("gex"),
    )
    monkeypatch.setattr(
        gamma_map,
        "_render_chains_view",
        lambda symbol, selected_exp, range_pct, options_dir: calls.append("chains"),
    )
    monkeypatch.setattr(
        gamma_map,
        "_render_history_view",
        lambda symbol, selected_exp, range_pct, options_dir: calls.append("history"),
    )
    monkeypatch.setattr(
        gamma_map,
        "_render_intraday_view",
        lambda symbol, selected_exp, range_pct, options_dir: calls.append("intraday"),
    )
    monkeypatch.setattr(
        gamma_map,
        "_render_gamma_heatmap_view",
        lambda symbol, today, include_0dte, range_pct, options_dir: calls.append("heatmap"),
    )
    monkeypatch.setattr(
        gamma_map,
        "_render_maker_taker_view",
        lambda symbol, selected_exp, range_pct, options_dir: calls.append("maker_taker"),
    )

    gamma_map._render_active_gamma_view(
        active_view="Intraday",
        symbol="SPXW",
        today=date(2026, 4, 15),
        include_0dte=True,
        range_pct=5.0,
        selected_exp_str="2026-04-18",
        options_dir=Path("/tmp/options"),
    )
    assert calls == ["intraday"]


def test_gex_view_does_not_touch_history_snapshot_loader(monkeypatch, tmp_path: Path) -> None:
    snapshot_path = tmp_path / "snapshot.csv"
    sample_df = pd.DataFrame(
        [{"underlying_price": 5000.0, "strike": 5000.0, "gamma": 0.01, "open_interest": 100.0}]
    )

    monkeypatch.setattr(
        gamma_map,
        "find_latest_snapshots",
        lambda symbol, start_date, days_out, include_0dte, data_dir: {
            date(2026, 4, 18): snapshot_path
        },
    )
    monkeypatch.setattr(
        gamma_map,
        "find_all_snapshots_for_expiry",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("hidden history loader should not run")
        ),
    )
    monkeypatch.setattr(gamma_map, "load_options_snapshot", lambda path: sample_df)
    monkeypatch.setattr(gamma_map, "net_gex_by_strike", lambda df, spot, strike_range: sample_df)
    monkeypatch.setattr(gamma_map, "net_gex_by_price", lambda df, spot, price_range: sample_df)
    monkeypatch.setattr(gamma_map, "build_gex_aggregate_chart", lambda *args, **kwargs: object())
    monkeypatch.setattr(gamma_map.st, "radio", lambda *args, **kwargs: 5)
    monkeypatch.setattr(gamma_map.st, "spinner", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(gamma_map.st, "plotly_chart", lambda *args, **kwargs: None)
    monkeypatch.setattr(gamma_map.st, "warning", lambda *args, **kwargs: None)

    gamma_map._render_gex_view(
        symbol="SPXW",
        today=date(2026, 4, 15),
        include_0dte=True,
        range_pct=5.0,
        options_dir=tmp_path,
    )
