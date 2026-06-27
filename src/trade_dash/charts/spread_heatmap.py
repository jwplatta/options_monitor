"""Intraday spread z-score heatmap: strike × time matrix colored by bid-ask spread anomaly."""

from __future__ import annotations

from datetime import datetime

import plotly.graph_objects as go

_COLORSCALE = [
    [0.0, "rgb(220,100,0)"],
    [0.35, "rgb(100,40,0)"],
    [0.47, "rgb(30,10,10)"],
    [0.5, "rgb(10,10,10)"],
    [0.53, "rgb(10,10,30)"],
    [0.65, "rgb(0,40,100)"],
    [1.0, "rgb(0,100,220)"],
]


# NOTE: unused — planned feature, not yet wired into any tab
def build_spread_heatmap_chart(
    strikes: list[float],
    timestamps: list[datetime],
    matrix: list[list[float]],
    prices: list[float] | None = None,
    title: str = "Intraday Spread Z-Score",
) -> go.Figure:
    """Build a discrete heatmap from the precomputed spread z-score matrix.

    Each cell is a (strike, timestamp) pair colored by the rolling z-score of
    the bid-ask spread:
        positive (orange) = spread widening relative to recent history
        negative (blue)   = spread narrowing relative to recent history

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
            colorbar={"title": "Spread Z"},
            hovertemplate="Time: %{x}<br>Strike: %{y}<br>Spread Z: %{z:.3f}<extra></extra>",
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
