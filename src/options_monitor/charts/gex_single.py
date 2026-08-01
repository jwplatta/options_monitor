"""GEX single-expiry chart: separate call and put walls."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def build_gex_single_expiry_chart(
    opts: pd.DataFrame,
    spot: float,
    strike_range: float = 300.0,
    title: str = "GEX Single Expiry",
) -> go.Figure:
    """Grouped bar chart: call GEX (positive) and put GEX (negative) by strike.

    Applies the same sign convention as calc/gex.py: calls positive, puts negative.
    Both bars display on the same signed Y-axis so values are directly comparable
    with the aggregate GEX chart.
    """
    df = opts.copy()

    # Coerce all numeric columns upfront and drop unusable rows
    df["gamma"] = pd.to_numeric(df["gamma"], errors="coerce")
    df["open_interest"] = pd.to_numeric(df["open_interest"], errors="coerce")
    df["K"] = pd.to_numeric(df["strike"], errors="coerce")
    df = df.dropna(subset=["gamma", "open_interest", "K", "contract_type"])
    df = df[df["open_interest"] > 0]

    # Apply sign before groupby: calls +1, puts -1 (matches calc/gex.py convention)
    sign = df["contract_type"].str.upper().map({"CALL": 1.0, "PUT": -1.0})
    df["gex"] = df["gamma"] * df["open_interest"] * (spot**2) * sign
    df = df.dropna(subset=["gex"])

    mask = (df["K"] >= spot - strike_range) & (df["K"] <= spot + strike_range)
    df = df[mask]

    calls = df[df["contract_type"].str.upper() == "CALL"].groupby("K")["gex"].sum()
    puts = df[df["contract_type"].str.upper() == "PUT"].groupby("K")["gex"].sum()

    all_strikes = sorted(set(calls.index) | set(puts.index))
    call_vals = [float(calls.get(k, 0.0)) for k in all_strikes]
    put_vals = [float(puts.get(k, 0.0)) for k in all_strikes]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=all_strikes,
            y=call_vals,
            name="Call GEX",
            marker_color="green",
            opacity=0.7,
        )
    )
    fig.add_trace(
        go.Bar(
            x=all_strikes,
            y=put_vals,
            name="Put GEX",
            marker_color="red",
            opacity=0.7,
        )
    )
    fig.add_vline(x=spot, line_dash="dash", line_color="white", annotation_text=f"Spot {spot:.0f}")
    fig.add_hline(y=0, line_color="white", line_width=0.5)
    fig.update_layout(
        title=title,
        xaxis_title="Strike",
        xaxis={"dtick": 25},
        yaxis_title="GEX",
        barmode="overlay",
        template="plotly_dark",
        legend={"orientation": "h", "y": 1.02},
        margin={"l": 40, "r": 20, "t": 40, "b": 40},
    )
    return fig
