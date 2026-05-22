"""Unit tests for charts/maker_taker_bubble.py."""

from __future__ import annotations

from datetime import datetime

import plotly.graph_objects as go
import pytest

from trade_dash.charts.maker_taker_bubble import build_maker_taker_bubble_chart


def _sample_data() -> tuple[
    list[datetime], list[float], list[float], list[datetime], list[float]
]:
    timestamps = [datetime(2026, 4, 28, 9, 30), datetime(2026, 4, 28, 9, 30)]
    strikes = [5000.0, 5050.0]
    flows = [25.0, -15.0]
    bucket_times = [datetime(2026, 4, 28, 9, 30)]
    bucket_prices = [5010.0]
    return timestamps, strikes, flows, bucket_times, bucket_prices


def test_returns_go_figure() -> None:
    ts, st, fl, bt, bp = _sample_data()
    fig = build_maker_taker_bubble_chart(ts, st, fl, bt, bp, spot=5010.0)
    assert isinstance(fig, go.Figure)


def test_has_bubble_trace() -> None:
    ts, st, fl, bt, bp = _sample_data()
    fig = build_maker_taker_bubble_chart(ts, st, fl, bt, bp, spot=5010.0)
    assert len(fig.data) >= 1
    assert fig.data[0].mode == "markers"


def test_price_overlay_trace_added_when_bucket_data_present() -> None:
    ts, st, fl, bt, bp = _sample_data()
    fig = build_maker_taker_bubble_chart(ts, st, fl, bt, bp, spot=5010.0)
    assert len(fig.data) == 2


def test_no_price_overlay_when_bucket_data_empty() -> None:
    ts, st, fl, _, _ = _sample_data()
    fig = build_maker_taker_bubble_chart(ts, st, fl, [], [], spot=5010.0)
    assert len(fig.data) == 1


def test_hline_present_when_spot_nonzero() -> None:
    ts, st, fl, bt, bp = _sample_data()
    fig = build_maker_taker_bubble_chart(ts, st, fl, bt, bp, spot=5010.0)
    assert len(fig.layout.shapes) >= 1


def test_no_hline_when_spot_zero() -> None:
    ts, st, fl, bt, bp = _sample_data()
    fig = build_maker_taker_bubble_chart(ts, st, fl, bt, bp, spot=0.0)
    assert len(fig.layout.shapes) == 0


def test_empty_data_returns_figure_with_no_traces() -> None:
    fig = build_maker_taker_bubble_chart([], [], [], [], [], spot=5000.0)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0


def test_title_is_applied() -> None:
    ts, st, fl, bt, bp = _sample_data()
    fig = build_maker_taker_bubble_chart(ts, st, fl, bt, bp, spot=5000.0, title="Test Title")
    assert fig.layout.title.text == "Test Title"


def test_bubble_marker_color_encodes_flow() -> None:
    ts, st, fl, bt, bp = _sample_data()
    fig = build_maker_taker_bubble_chart(ts, st, fl, bt, bp, spot=5000.0)
    colors = list(fig.data[0].marker.color)
    assert colors == pytest.approx(fl)


def test_bubble_sizes_scale_with_abs_flow() -> None:
    """Larger |flow| should produce larger bubble."""
    ts = [datetime(2026, 4, 28, 9, 30), datetime(2026, 4, 28, 9, 30)]
    st = [5000.0, 5050.0]
    fl = [100.0, 10.0]  # first is 10x bigger
    fig = build_maker_taker_bubble_chart(ts, st, fl, [], [], spot=5000.0)
    sizes = list(fig.data[0].marker.size)
    assert sizes[0] > sizes[1]
