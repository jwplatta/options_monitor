"""Flow Profile chart: grouped bar chart of call/put flow aggregated by strike."""

from __future__ import annotations

import plotly.graph_objects as go


def build_flow_profile_chart(
    strikes: list[float],
    call_flow: list[float],
    put_flow: list[float],
    title: str = "Flow Profile",
) -> go.Figure:
    """Build a grouped bar chart showing call and put flow at each strike.

    Positive bars = buying activity. Negative bars = selling activity.
    """
    fig = go.Figure()

    if not strikes:
        fig.update_layout(title=title, template="plotly_dark")
        return fig

    fig.add_trace(
        go.Bar(
            x=strikes,
            y=call_flow,
            name="Call Flow",
            marker_color="rgb(0, 200, 80)",
            opacity=0.8,
            hovertemplate="Strike: %{x}<br>Call Flow: %{y:.1f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=strikes,
            y=put_flow,
            name="Put Flow",
            marker_color="rgb(220, 60, 60)",
            opacity=0.8,
            hovertemplate="Strike: %{x}<br>Put Flow: %{y:.1f}<extra></extra>",
        )
    )
    fig.add_hline(y=0, line={"color": "gray", "width": 1, "dash": "dot"})

    fig.update_layout(
        title=title,
        xaxis_title="Strike",
        yaxis_title="Flow (delta-equiv shares)",
        barmode="group",
        template="plotly_dark",
        legend={"orientation": "h", "y": 1.02, "x": 0},
        margin={"l": 40, "r": 20, "t": 40, "b": 40},
    )
    return fig
