"""Flow Tape chart: cumulative call/put flow lines over the trading session."""

from __future__ import annotations

from datetime import datetime

import plotly.graph_objects as go


def build_flow_tape_chart(
    timestamps: list[datetime],
    call_flow: list[float],
    put_flow: list[float],
    title: str = "Flow Tape",
) -> go.Figure:
    """Build a line chart showing cumulative call and put flow over time.

    Rising call line = increasing call buying. Falling = increasing call selling.
    Rising put line = increasing put buying. Falling = increasing put selling.
    """
    fig = go.Figure()

    if not timestamps:
        fig.update_layout(title=title, template="plotly_dark")
        return fig

    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=call_flow,
            mode="lines",
            name="Call Flow",
            line={"color": "rgb(0, 200, 80)", "width": 1.5},
            hovertemplate="Time: %{x|%H:%M}<br>Call Flow: %{y:.1f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=put_flow,
            mode="lines",
            name="Put Flow",
            line={"color": "rgb(220, 60, 60)", "width": 1.5},
            hovertemplate="Time: %{x|%H:%M}<br>Put Flow: %{y:.1f}<extra></extra>",
        )
    )
    fig.add_hline(y=0, line={"color": "gray", "width": 1, "dash": "dot"})

    fig.update_layout(
        title=title,
        xaxis_title="Time (CT)",
        yaxis_title="Cumulative Flow",
        template="plotly_dark",
        legend={"orientation": "h", "y": 1.02, "x": 0},
        margin={"l": 40, "r": 20, "t": 40, "b": 40},
    )
    return fig
