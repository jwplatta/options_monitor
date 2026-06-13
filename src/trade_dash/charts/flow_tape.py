"""Flow Tape chart: three-panel — New Flow, Cumulative Flow, Oscillator Bars."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

_GREEN = "#00c850"
_GREEN_DARK = "#004d1a"
_RED = "#dc3c3c"
_RED_DARK = "#6b0000"


def build_flow_tape_chart(
    timestamps: list[datetime],
    new_call: list[float],
    new_put: list[float],
    cum_call: list[float],
    cum_put: list[float],
    raw_call: list[float],
    raw_put: list[float],
) -> go.Figure:
    """Build a three-panel flow tape chart.

    Row 1 — New Flow: cumsum of per-snapshot lookback flow (rate/trend).
    Row 2 — Cumulative Flow: volume-since-open × expanding mean direction (net positioning).
    Row 3 — Oscillator: raw per-snapshot bars from New Flow calculation.
    """
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.35, 0.35, 0.30],
        vertical_spacing=0.02,
    )

    if not timestamps:
        fig.update_layout(template="plotly_dark")
        return fig

    # --- Row 1: New Flow cumsum lines ---
    fig.add_trace(
        go.Scatter(
            x=timestamps, y=new_call, mode="lines", name="Call Flow",
            line={"color": _GREEN, "width": 1.5},
            hovertemplate="Time: %{x|%H:%M}<br>%{y:.1f}<extra>Call New Flow</extra>",
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=timestamps, y=new_put, mode="lines", name="Put Flow",
            line={"color": _RED, "width": 1.5},
            hovertemplate="Time: %{x|%H:%M}<br>%{y:.1f}<extra>Put New Flow</extra>",
        ),
        row=1, col=1,
    )
    fig.add_hline(y=0, line={"color": "gray", "width": 1, "dash": "dot"}, row=1, col=1)
    # --- Row 2: Cumulative Flow lines ---
    fig.add_trace(
        go.Scatter(
            x=timestamps, y=cum_call, mode="lines", name="Call Cum",
            line={"color": _GREEN, "width": 1.5},
            showlegend=False,
            hovertemplate="Time: %{x|%H:%M}<br>%{y:.1f}<extra>Call Cum Flow</extra>",
        ),
        row=2, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=timestamps, y=cum_put, mode="lines", name="Put Cum",
            line={"color": _RED, "width": 1.5},
            showlegend=False,
            hovertemplate="Time: %{x|%H:%M}<br>%{y:.1f}<extra>Put Cum Flow</extra>",
        ),
        row=2, col=1,
    )
    fig.add_hline(y=0, line={"color": "gray", "width": 1, "dash": "dot"}, row=2, col=1)
    # --- Row 3: Oscillator bars (raw per-snapshot New Flow) ---
    rc = pd.Series(raw_call, index=timestamps)
    rp = pd.Series(raw_put, index=timestamps)

    fig.add_trace(
        go.Bar(
            x=timestamps, y=rc.clip(lower=0).tolist(), name="Call Buy",
            marker_color=_GREEN,
            hovertemplate="Time: %{x|%H:%M}<br>%{y:.1f}<extra>Call Buy</extra>",
        ),
        row=3, col=1,
    )
    fig.add_trace(
        go.Bar(
            x=timestamps, y=rc.clip(upper=0).tolist(), name="Call Sell",
            marker_color=_GREEN_DARK,
            hovertemplate="Time: %{x|%H:%M}<br>%{y:.1f}<extra>Call Sell</extra>",
        ),
        row=3, col=1,
    )
    fig.add_trace(
        go.Bar(
            x=timestamps, y=rp.clip(lower=0).tolist(), name="Put Buy",
            marker_color=_RED,
            hovertemplate="Time: %{x|%H:%M}<br>%{y:.1f}<extra>Put Buy</extra>",
        ),
        row=3, col=1,
    )
    fig.add_trace(
        go.Bar(
            x=timestamps, y=rp.clip(upper=0).tolist(), name="Put Sell",
            marker_color=_RED_DARK,
            hovertemplate="Time: %{x|%H:%M}<br>%{y:.1f}<extra>Put Sell</extra>",
        ),
        row=3, col=1,
    )
    fig.add_hline(y=0, line={"color": "gray", "width": 1, "dash": "dot"}, row=3, col=1)
    fig.update_layout(
        template="plotly_dark",
        barmode="overlay",
        legend={"orientation": "h", "y": 1.0, "x": 0, "yanchor": "bottom"},
        margin={"l": 40, "r": 20, "t": 60, "b": 40},
        height=800,
    )
    fig.update_yaxes(title_text="", autorange=True)
    fig.update_xaxes(title_text="Time (CT)", row=3, col=1)

    # Row labels via annotations
    fig.update_yaxes(title_text="New Flow", row=1, col=1)
    fig.update_yaxes(title_text="Cum Flow", row=2, col=1)

    return fig
