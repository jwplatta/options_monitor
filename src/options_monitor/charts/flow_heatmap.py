"""Intraday flow heatmap: strike × time matrix colored by normalized flow metric."""

from __future__ import annotations

from datetime import datetime

import plotly.graph_objects as go

_COLORSCALE = [
    [0.0, "rgb(220,0,0)"],
    [0.35, "rgb(100,0,0)"],
    [0.47, "rgb(30,10,10)"],
    [0.5, "rgb(10,10,10)"],
    [0.53, "rgb(10,30,10)"],
    [0.65, "rgb(0,100,0)"],
    [1.0, "rgb(0,220,0)"],
]


def build_flow_heatmap_chart(
    strikes: list[float],
    timestamps: list[datetime],
    matrix: list[list[float]],
    prices: list[float] | None = None,
    title: str = "Intraday Flow",
) -> go.Figure:
    """Build a discrete heatmap from the precomputed flow matrix.

    Each cell is a (strike, timestamp) pair colored by normalized flow:
        positive (green) = bullish flow acceleration
        negative (red)   = bearish flow acceleration

    prices: optional underlying_price per timestamp, overlaid as a line.
    """
    if not strikes or not timestamps:
        fig = go.Figure()
        fig.update_layout(title=title, template="plotly_dark")
        return fig

    fig = go.Figure(
        go.Heatmap(
            x=timestamps,
            y=strikes,
            z=matrix,
            zmid=0,
            colorscale=_COLORSCALE,
            zsmooth=False,
            colorbar={"title": "Flow"},
            hovertemplate="Time: %{x}<br>Strike: %{y}<br>Flow: %{z:.3f}<extra></extra>",
        )
    )

    if prices:
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=prices,
                mode="lines",
                line={"color": "white", "width": 1.5},
                name="SPX",
                hovertemplate="Time: %{x}<br>Price: %{y:.2f}<extra>SPX</extra>",
            )
        )

    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title="Strike",
        template="plotly_dark",
        margin={"l": 40, "r": 20, "t": 40, "b": 40},
        showlegend=False,
    )
    return fig
