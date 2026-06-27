"""Maker-Taker bubble chart: aggressive option flow by strike over time."""

from __future__ import annotations

from datetime import datetime

import plotly.graph_objects as go

_COLORSCALE = [
    [0.0, "rgb(220,0,0)"],
    [0.35, "rgb(160,60,0)"],
    [0.47, "rgb(200,180,0)"],
    [0.5, "rgb(240,230,50)"],
    [0.53, "rgb(100,180,0)"],
    [0.65, "rgb(0,140,0)"],
    [1.0, "rgb(0,220,0)"],
]

_MIN_BUBBLE_PX = 3.0
_MAX_BUBBLE_PX = 40.0


# NOTE: unused — planned feature, not yet wired into any tab
def build_maker_taker_bubble_chart(
    timestamps: list[datetime],
    strikes: list[float],
    weighted_flows: list[float],
    bucket_times: list[datetime],
    bucket_prices: list[float],
    spot: float,
    title: str = "Maker-Taker Flow",
) -> go.Figure:
    """Return a bubble chart of maker-taker flow by strike over time.

    Each bubble sits at (time, strike). Size encodes absolute flow magnitude;
    color encodes direction — green for aggressive buying, red for selling.
    """
    fig = go.Figure()

    if not timestamps:
        fig.update_layout(title=title, template="plotly_dark")
        return fig

    abs_flows = [abs(f) for f in weighted_flows]
    max_flow = max(abs_flows) if abs_flows else 1.0
    marker_sizes = [
        _MIN_BUBBLE_PX + (a / max_flow) * (_MAX_BUBBLE_PX - _MIN_BUBBLE_PX)
        for a in abs_flows
    ]

    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=strikes,
            mode="markers",
            marker=dict(
                size=marker_sizes,
                color=weighted_flows,
                colorscale=_COLORSCALE,
                cmid=0,
                colorbar=dict(title="Flow"),
                line=dict(width=0),
            ),
            hovertemplate=(
                "Time: %{x}<br>"
                "Strike: %{y}<br>"
                "Flow: %{marker.color:.1f}<extra></extra>"
            ),
            name="Flow",
        )
    )

    if bucket_times and bucket_prices:
        fig.add_trace(
            go.Scatter(
                x=bucket_times,
                y=bucket_prices,
                mode="lines",
                line=dict(color="rgba(255,255,255,0.4)", width=1),
                name="Price",
                hovertemplate="Time: %{x}<br>Price: %{y:.2f}<extra>Price</extra>",
            )
        )

    if spot:
        fig.add_hline(
            y=spot,
            line_dash="dash",
            line_color="white",
            line_width=1,
            annotation_text=f"Spot {spot:.0f}",
            annotation_position="right",
        )

    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title="Strike",
        template="plotly_dark",
        showlegend=False,
        margin=dict(l=40, r=20, t=40, b=40),
    )
    return fig
