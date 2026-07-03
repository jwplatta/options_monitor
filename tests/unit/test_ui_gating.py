from __future__ import annotations

from contextlib import nullcontext
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from trade_dash import app
from trade_dash.tabs import gex as gamma_map, history


def test_dashboard_router_only_invokes_selected_panel(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(app, "render_regime_tab", lambda candle_dir: calls.append("regime"))
    monkeypatch.setattr(app, "render_vol_tab", lambda candle_dir: calls.append("vol"))
    monkeypatch.setattr(
        app,
        "render_gamma_map_tab",
        lambda options_dir, candle_dir: calls.append("gamma"),
    )
    monkeypatch.setattr(
        app,
        "render_history_tab",
        lambda options_dir, candle_dir: calls.append("history"),
    )

    app._render_active_dashboard_tab("Vol")
    assert calls == ["vol"]


def test_dashboard_router_dispatches_history_panel(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        app,
        "render_history_tab",
        lambda options_dir, candle_dir: calls.append("history"),
    )

    app._render_active_dashboard_tab("History")
    assert calls == ["history"]


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


def test_gamma_router_rejects_chain_history_view(monkeypatch) -> None:
    with pytest.raises(ValueError, match="Unknown Gamma Map view"):
        gamma_map._render_active_gamma_view(
            active_view="Chain GEX History",
            symbol="SPXW",
            today=date(2026, 4, 15),
            include_0dte=True,
            range_pct=5.0,
            selected_exp_str="2026-04-18",
            options_dir=Path("/tmp/options"),
        )


def test_gamma_router_rejects_aggregate_history_view(monkeypatch) -> None:
    with pytest.raises(ValueError, match="Unknown Gamma Map view"):
        gamma_map._render_active_gamma_view(
            active_view="GEX History",
            symbol="SPXW",
            today=date(2026, 4, 15),
            include_0dte=True,
            range_pct=5.0,
            selected_exp_str=None,
            options_dir=Path("/tmp/options"),
        )


def test_history_router_dispatches_chain_history_view(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(history, "_render_history_view", lambda *args: calls.append("history"))

    history._render_active_history_view(
        active_view="Chain GEX History",
        symbol="SPXW",
        include_0dte=True,
        range_pct=5.0,
        selected_exp_str="2026-04-18",
        options_dir=Path("/tmp/options"),
    )
    assert calls == ["history"]


def test_history_router_dispatches_aggregate_history_view(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        history,
        "_render_gex_history_view",
        lambda *args: calls.append("gex_history"),
    )

    history._render_active_history_view(
        active_view="GEX History",
        symbol="SPXW",
        include_0dte=True,
        range_pct=5.0,
        selected_exp_str=None,
        options_dir=Path("/tmp/options"),
    )
    assert calls == ["gex_history"]


def test_render_history_tab_only_requests_single_expiry_for_chain_history(
    monkeypatch,
    tmp_path: Path,
) -> None:
    selectbox_calls: list[str] = []

    monkeypatch.setattr(history.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(history.st, "fragment", lambda **kwargs: lambda func: func)
    monkeypatch.setattr(history.st, "columns", lambda spec: (nullcontext(), nullcontext()))
    monkeypatch.setattr(history.st, "toggle", lambda *args, **kwargs: True)
    monkeypatch.setattr(history.st, "slider", lambda *args, **kwargs: 5.0)
    monkeypatch.setattr(history.st, "divider", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        history.st,
        "segmented_control",
        lambda *args, **kwargs: "Chain GEX History",
    )

    def _selectbox(label, options, index=0, key=None):
        selectbox_calls.append(label)
        return options[index]

    monkeypatch.setattr(history.st, "selectbox", _selectbox)
    monkeypatch.setattr(
        history,
        "_select_single_expiry",
        lambda symbol, today, options_dir: "2026-04-18",
    )
    monkeypatch.setattr(history, "_render_active_history_view", lambda **kwargs: None)

    history.render_history_tab(options_dir=tmp_path, candle_dir=tmp_path)

    assert selectbox_calls == ["Symbol"]


def test_render_history_tab_skips_single_expiry_for_aggregate_history(
    monkeypatch,
    tmp_path: Path,
) -> None:
    selected_exp_calls: list[str] = []

    monkeypatch.setattr(history.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(history.st, "fragment", lambda **kwargs: lambda func: func)
    monkeypatch.setattr(history.st, "columns", lambda spec: (nullcontext(), nullcontext()))
    monkeypatch.setattr(history.st, "toggle", lambda *args, **kwargs: True)
    monkeypatch.setattr(history.st, "slider", lambda *args, **kwargs: 5.0)
    monkeypatch.setattr(history.st, "segmented_control", lambda *args, **kwargs: "GEX History")
    monkeypatch.setattr(
        history.st, "selectbox", lambda label, options, index=0, key=None: options[index]
    )
    monkeypatch.setattr(
        history,
        "_select_single_expiry",
        lambda symbol, today, options_dir: selected_exp_calls.append(symbol) or "2026-04-18",
    )
    monkeypatch.setattr(history, "_render_active_history_view", lambda **kwargs: None)

    history.render_history_tab(options_dir=tmp_path, candle_dir=tmp_path)

    assert selected_exp_calls == []


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


def test_history_view_uses_selected_snapshot_and_reuses_single_expiry_chart(
    monkeypatch,
    tmp_path: Path,
) -> None:
    sample_df = pd.DataFrame(
        [{"underlying_price": 5000.0, "strike": 5000.0, "gamma": 0.01, "open_interest": 100.0}]
    )
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    chart_calls: list[tuple[float, float, str]] = []
    plotted: list[object] = []

    monkeypatch.setattr(
        gamma_map,
        "list_snapshot_dates_for_expiry",
        lambda symbol, expiry, data_dir: [date(2026, 4, 15)],
    )
    monkeypatch.setattr(
        gamma_map,
        "find_snapshots_for_expiry_on_date",
        lambda symbol, expiry, sample_date, data_dir: [
            (pd.Timestamp("2026-04-15T14:00:00").to_pydatetime(), first),
            (pd.Timestamp("2026-04-15T15:00:00").to_pydatetime(), second),
        ],
    )
    monkeypatch.setattr(gamma_map, "load_options_snapshot", lambda path: sample_df)
    monkeypatch.setattr(
        gamma_map,
        "build_gex_single_expiry_chart",
        lambda opts, spot, strike_range, title: (
            chart_calls.append((spot, strike_range, title)) or object()
        ),
    )
    monkeypatch.setattr(gamma_map.st, "date_input", lambda *args, **kwargs: date(2026, 4, 15))
    monkeypatch.setattr(
        gamma_map.st,
        "select_slider",
        lambda *args, **kwargs: kwargs["options"][1],
    )
    monkeypatch.setattr(gamma_map.st, "spinner", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(gamma_map.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(gamma_map.st, "plotly_chart", lambda fig, **kwargs: plotted.append(fig))
    monkeypatch.setattr(gamma_map.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(gamma_map.st, "session_state", {})

    gamma_map._render_history_view(
        symbol="SPXW",
        selected_exp=date(2026, 4, 18),
        range_pct=5.0,
        options_dir=tmp_path,
    )

    assert len(chart_calls) == 1
    assert chart_calls[0][0] == 5000.0
    assert "Chain GEX History" in chart_calls[0][2]
    assert plotted


def test_history_view_warns_when_selected_date_has_no_snapshots(
    monkeypatch, tmp_path: Path
) -> None:
    warnings: list[str] = []

    monkeypatch.setattr(
        gamma_map,
        "list_snapshot_dates_for_expiry",
        lambda symbol, expiry, data_dir: [date(2026, 4, 15)],
    )
    monkeypatch.setattr(gamma_map.st, "date_input", lambda *args, **kwargs: date(2026, 4, 16))
    monkeypatch.setattr(gamma_map.st, "warning", lambda message: warnings.append(message))

    gamma_map._render_history_view(
        symbol="SPXW",
        selected_exp=date(2026, 4, 18),
        range_pct=5.0,
        options_dir=tmp_path,
    )

    assert warnings



def test_render_gamma_map_tab_limits_symbol_options(monkeypatch, tmp_path: Path) -> None:
    captured_options: list[str] = []

    monkeypatch.setattr(gamma_map.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(gamma_map.st, "fragment", lambda **kwargs: lambda func: func)
    monkeypatch.setattr(gamma_map.st, "columns", lambda spec: (nullcontext(), nullcontext()))
    monkeypatch.setattr(gamma_map.st, "toggle", lambda *args, **kwargs: True)

    def _selectbox(label, options, index=0, key=None):
        if label == "Symbol":
            captured_options.extend(options)
        return options[index]

    monkeypatch.setattr(gamma_map.st, "selectbox", _selectbox)
    monkeypatch.setattr(gamma_map.st, "slider", lambda *args, **kwargs: 5.0)
    monkeypatch.setattr(gamma_map.st, "segmented_control", lambda *args, **kwargs: "GEX")
    monkeypatch.setattr(gamma_map, "_render_active_gamma_view", lambda **kwargs: None)

    gamma_map.render_gamma_map_tab(options_dir=tmp_path, candle_dir=tmp_path)

    assert captured_options == ["SPXW", "SPX"]
