"""GEX term structure heatmap: strikes × expirations colored by net gamma exposure."""

from __future__ import annotations

from datetime import date

import numpy as np
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


def build_gex_term_structure_chart(
    strikes: list[float],
    expirations: list[date],
    matrix: list[list[float]],
    spot: float,
    normalize: bool = False,
    y_range: tuple[float, float] | None = None,
    title: str = "GEX Term Structure",
) -> go.Figure:
    """Build a heatmap showing net GEX across all expirations.

    X-axis: expiration dates (chronological, equally spaced as categories).
    Y-axis: strike prices.
    Color: net GEX (calls positive/green, puts negative/red).

    Overlays:
        - Call Wall: strike with highest positive GEX per expiry (green line)
        - Put Floor: strike with most negative GEX per expiry (red line)
        - Spot price: dashed white horizontal line

    Args:
        strikes: sorted list of strike prices (Y-axis).
        expirations: sorted list of expiration dates (X-axis).
        matrix: matrix[i][j] = net_gex for strikes[i] at expirations[j].
        spot: current underlying price for spot line and hover distance calc.
        normalize: if True, normalize each expiry column to [-1, 1] for color
            (makes far-dated walls visible); hover still shows raw GEX values.
        y_range: optional (min_strike, max_strike) to restrict visible y-axis window.
        title: chart title.
    """
    if not strikes or not expirations:
        fig = go.Figure()
        fig.update_layout(title=title, template="plotly_dark")
        return fig

    raw = np.array(matrix, dtype=float)  # shape: (n_strikes, n_expirations)

    if normalize:
        col_max = np.abs(raw).max(axis=0)
        col_max[col_max == 0] = 1.0
        z_display = raw / col_max
    else:
        z_display = raw

    # customdata: [raw_gex, dist_from_spot_%] per cell
    dist_pct = np.array(
        [[(s - spot) / spot * 100 for _ in expirations] for s in strikes], dtype=float
    )
    customdata = np.stack([raw, dist_pct], axis=-1)

    # Use human-readable labels; categorical axis makes all expirations equally spaced
    # so weekend gaps don't cause visual disconnects between adjacent trading days.
    exp_labels = [f"{e.strftime('%b')} {e.day}" for e in expirations]

    fig = go.Figure(
        go.Heatmap(
            x=exp_labels,
            y=strikes,
            z=z_display.tolist(),
            zmid=0,
            colorscale=_COLORSCALE,
            zsmooth="best",
            customdata=customdata.tolist(),
            colorbar={"title": "Norm GEX" if normalize else "Net GEX"},
            hovertemplate=(
                "Expiry: %{x}<br>"
                "Strike: %{y}<br>"
                "GEX: %{customdata[0]:.2e}<br>"
                "Dist: %{customdata[1]:.1f}%"
                "<extra></extra>"
            ),
        )
    )

    # Call Wall: strike with max positive GEX per expiry
    call_wall_y = []
    put_floor_y = []
    for j in range(len(expirations)):
        col = raw[:, j]
        pos_mask = col > 0
        neg_mask = col < 0
        call_wall_y.append(float(strikes[int(np.argmax(col))]) if pos_mask.any() else None)
        put_floor_y.append(float(strikes[int(np.argmin(col))]) if neg_mask.any() else None)

    fig.add_trace(
        go.Scatter(
            x=exp_labels,
            y=call_wall_y,
            mode="lines+markers",
            line={"color": "rgb(0,220,0)", "width": 2, "dash": "dot"},
            marker={"size": 5},
            name="Call Wall",
            hovertemplate="Call Wall<br>Expiry: %{x}<br>Strike: %{y}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=exp_labels,
            y=put_floor_y,
            mode="lines+markers",
            line={"color": "rgb(220,0,0)", "width": 2, "dash": "dot"},
            marker={"size": 5},
            name="Put Floor",
            hovertemplate="Put Floor<br>Expiry: %{x}<br>Strike: %{y}<extra></extra>",
        )
    )

    fig.add_hline(
        y=spot,
        line_dash="dash",
        line_color="white",
        annotation_text=f"Spot {spot:.0f}",
        annotation_position="right",
    )

    yaxis_kwargs: dict[str, object] = {"title": "Strike"}
    if y_range is not None:
        yaxis_kwargs["range"] = list(y_range)

    fig.update_layout(
        title=title,
        xaxis={"title": "Expiration", "type": "category", "tickangle": -30},
        yaxis=yaxis_kwargs,
        template="plotly_dark",
        margin={"l": 40, "r": 80, "t": 40, "b": 60},
        legend={"x": 0.01, "y": 0.99},
    )
    return fig
