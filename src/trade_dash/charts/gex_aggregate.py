"""GEX aggregate chart: strike bars + price-grid line + spot + ZGL."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from trade_dash.calc.gex import find_zero_gamma_level


def _add_vertical_marker(
    fig: go.Figure,
    x: float,
    text: str,
    color: str,
    line_dash: str,
    y_paper: float,
    xanchor: str,
) -> None:
    fig.add_vline(x=x, line_dash=line_dash, line_color=color)
    fig.add_annotation(
        x=x,
        y=y_paper,
        xref="x",
        yref="paper",
        text=text,
        textangle=-90,
        showarrow=False,
        font={"color": color},
        xanchor=xanchor,
        yanchor="middle",
        bgcolor="rgba(0, 0, 0, 0.45)",
    )


def _add_zone_overlay(
    fig: go.Figure,
    low: float,
    high: float,
    label: str,
    color: str,
    y_paper: float,
    xanchor: str,
) -> None:
    center = (low + high) / 2.0
    fig.add_vrect(
        x0=low,
        x1=high,
        fillcolor=color,
        opacity=0.12,
        line_width=1,
        line_color=color,
    )
    fig.add_annotation(
        x=center,
        y=y_paper,
        xref="x",
        yref="paper",
        text=label,
        textangle=-90,
        showarrow=False,
        font={"color": color},
        xanchor=xanchor,
        yanchor="middle",
        bgcolor="rgba(0, 0, 0, 0.45)",
    )


def build_gex_aggregate_chart(
    strike_gex: pd.DataFrame,
    price_gex: pd.DataFrame,
    spot: float,
    call_wall_strike: float | None = None,
    put_wall_strike: float | None = None,
    top_call_strikes: list[float] | None = None,
    top_put_strikes: list[float] | None = None,
    resistance_zones: list[dict[str, float]] | None = None,
    support_zones: list[dict[str, float]] | None = None,
    title: str = "GEX Aggregate",
) -> go.Figure:
    """Mixed bar (net GEX by strike) + line (net GEX by price) + spot + ZGL markers.

    Args:
        strike_gex: DataFrame with columns [strike, net_gex]
        price_gex: DataFrame with columns [price, net_gex]
        spot: Current underlying price
        call_wall_strike: Dominant call wall strike for the aggregate window
        put_wall_strike: Dominant put wall strike for the aggregate window
        top_call_strikes: Additional high-call-GEX strikes to mark
        top_put_strikes: Additional high-put-GEX strikes to mark
        resistance_zones: Resistance zone overlays [{low, high, center, score}]
        support_zones: Support zone overlays [{low, high, center, score}]
        title: Chart title
    """
    zgl = find_zero_gamma_level(
        prices=price_gex["price"].to_numpy(dtype=float),
        gex=price_gex["net_gex"].to_numpy(dtype=float),
    )

    colors: list[str] = ["green" if g >= 0 else "red" for g in strike_gex["net_gex"]]

    # Scale the price-grid line to match the strike bar y-axis range
    max_bar = float(np.abs(strike_gex["net_gex"]).max()) or 1.0
    max_line = float(np.abs(price_gex["net_gex"]).max()) or 1.0
    scale = max_bar / max_line

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=strike_gex["strike"],
            y=strike_gex["net_gex"],
            name="Net GEX by Strike",
            marker_color=colors,
            opacity=0.7,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=price_gex["price"],
            y=price_gex["net_gex"] * scale,
            name="Net GEX by Price (scaled)",
            line={"color": "yellow", "width": 2},
        )
    )
    fig.add_hline(y=0, line_dash="solid", line_color="white", line_width=0.5)
    _add_vertical_marker(
        fig,
        x=spot,
        text=f"Spot {spot:.0f}",
        color="white",
        line_dash="dash",
        y_paper=0.9,
        xanchor="left",
    )
    if zgl is not None:
        _add_vertical_marker(
            fig,
            x=zgl,
            text=f"ZGL {zgl:.0f}",
            color="yellow",
            line_dash="dot",
            y_paper=0.82,
            xanchor="right",
        )
    for idx, zone in enumerate(resistance_zones or [], start=1):
        _add_zone_overlay(
            fig,
            low=float(zone["low"]),
            high=float(zone["high"]),
            label=f"R{idx} {zone['low']:.0f}-{zone['high']:.0f}",
            color="rgba(0, 220, 0, 0.9)",
            y_paper=0.18 + (idx - 1) * 0.1,
            xanchor="left",
        )
    for idx, zone in enumerate(support_zones or [], start=1):
        _add_zone_overlay(
            fig,
            low=float(zone["low"]),
            high=float(zone["high"]),
            label=f"S{idx} {zone['low']:.0f}-{zone['high']:.0f}",
            color="rgba(220, 0, 0, 0.9)",
            y_paper=0.1 + (idx - 1) * 0.1,
            xanchor="right",
        )
    if call_wall_strike is not None:
        _add_vertical_marker(
            fig,
            x=call_wall_strike,
            text=f"Call Wall {call_wall_strike:.0f}",
            color="green",
            line_dash="dot",
            y_paper=0.18,
            xanchor="left",
        )
    if put_wall_strike is not None:
        _add_vertical_marker(
            fig,
            x=put_wall_strike,
            text=f"Put Wall {put_wall_strike:.0f}",
            color="red",
            line_dash="dot",
            y_paper=0.1,
            xanchor="right",
        )
    for idx, strike in enumerate(top_call_strikes or [], start=1):
        if call_wall_strike is not None and float(strike) == float(call_wall_strike):
            continue
        _add_vertical_marker(
            fig,
            x=strike,
            text=f"C{idx} {strike:.0f}",
            color="rgba(0, 220, 0, 0.75)",
            line_dash="dash",
            y_paper=0.74,
            xanchor="right",
        )
    for idx, strike in enumerate(top_put_strikes or [], start=1):
        if put_wall_strike is not None and float(strike) == float(put_wall_strike):
            continue
        _add_vertical_marker(
            fig,
            x=strike,
            text=f"P{idx} {strike:.0f}",
            color="rgba(220, 0, 0, 0.75)",
            line_dash="dash",
            y_paper=0.26,
            xanchor="left",
        )
    fig.update_layout(
        title=title,
        xaxis_title="Strike / Price",
        xaxis={"dtick": 25},
        yaxis_title="Net GEX",
        template="plotly_dark",
        legend={"orientation": "h", "y": 1.02},
        margin={"l": 40, "r": 20, "t": 40, "b": 40},
        bargap=0.1,
    )
    return fig
