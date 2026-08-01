"""SPX candlestick chart with GEX wall overlays."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from options_monitor.charts._chart_utils import daily_ticks, intraday_ticks, to_ct
from plotly.subplots import make_subplots

_INTRADAY_FREQS = {"1min", "5min", "30min"}

_OHLC_HOVER_INTRADAY = (
    "%{text}<br>O: %{open:.2f}  H: %{high:.2f}  L: %{low:.2f}  C: %{close:.2f}<extra></extra>"
)
_OHLC_HOVER_DAILY = (
    "%{x|%Y-%m-%d}<br>O: %{open:.2f}  H: %{high:.2f}  L: %{low:.2f}  C: %{close:.2f}<extra></extra>"
)

_WALL_SPECS: list[tuple[str, str, str]] = [
    ("raw_call_wall", "limegreen", "solid"),
    ("raw_put_wall", "tomato", "solid"),
    ("dw_call_wall", "mediumseagreen", "dash"),
    ("dw_put_wall", "indianred", "dash"),
    ("cluster_call_wall", "darkseagreen", "dot"),
    ("cluster_put_wall", "lightcoral", "dot"),
    ("zero_gamma", "gold", "dot"),
]

_WALL_LABELS: dict[str, str] = {
    "raw_call_wall": "CW",
    "raw_put_wall": "PW",
    "dw_call_wall": "CW-DW",
    "dw_put_wall": "PW-DW",
    "cluster_call_wall": "CW-CL",
    "cluster_put_wall": "PW-CL",
    "zero_gamma": "ZGL",
}


def build_spx_candlestick_chart(
    candles: pd.DataFrame,
    title: str = "SPX",
    freq: str = "day",
    raw_call_wall: float | None = None,
    raw_put_wall: float | None = None,
    dw_call_wall: float | None = None,
    dw_put_wall: float | None = None,
    cluster_call_wall: float | None = None,
    cluster_put_wall: float | None = None,
    zero_gamma: float | None = None,
) -> go.Figure:
    """SPX candlestick chart. No volume subplot. Optionally overlays GEX wall lines."""
    intraday = freq in _INTRADAY_FREQS

    if intraday:
        x: list[int] | pd.Series = list(range(len(candles)))
        tick_vals, tick_text = intraday_ticks(candles["datetime"], freq)
        hover_labels: list[str] | None = (
            to_ct(candles["datetime"]).dt.strftime("%m/%d %H:%M CT").tolist()
        )
        hover_tmpl = _OHLC_HOVER_INTRADAY
    else:
        x = candles["datetime"]
        tick_vals_daily, tick_text_daily = daily_ticks(candles["datetime"])
        hover_labels = None
        hover_tmpl = _OHLC_HOVER_DAILY

    fig = make_subplots(rows=1, cols=1)

    fig.add_trace(
        go.Candlestick(
            x=x,
            open=candles["open"],
            high=candles["high"],
            low=candles["low"],
            close=candles["close"],
            text=hover_labels,
            hovertemplate=hover_tmpl,
            increasing_line_color="limegreen",
            decreasing_line_color="tomato",
        ),
        row=1,
        col=1,
    )

    levels: dict[str, float | None] = {
        "raw_call_wall": raw_call_wall,
        "raw_put_wall": raw_put_wall,
        "dw_call_wall": dw_call_wall,
        "dw_put_wall": dw_put_wall,
        "cluster_call_wall": cluster_call_wall,
        "cluster_put_wall": cluster_put_wall,
        "zero_gamma": zero_gamma,
    }
    for key, color, dash in _WALL_SPECS:
        level = levels[key]
        if level is not None:
            label = f"{_WALL_LABELS[key]} {level}"
            fig.add_hline(
                y=level,
                line={"color": color, "width": 1, "dash": dash},
                annotation_text=label,
                annotation_position="right",
                annotation_font_color=color,
                row=1,
            )

    fig.update_layout(
        title=title,
        yaxis_title="Price",
        template="plotly_dark",
        margin={"l": 40, "r": 20, "t": 40, "b": 40},
        xaxis_rangeslider_visible=False,
    )
    fig.update_xaxes(title_text="Date/Time", row=1, col=1)

    if intraday:
        fig.update_xaxes(tickvals=tick_vals, ticktext=tick_text, tickangle=-45)
    else:
        fig.update_xaxes(tickvals=tick_vals_daily, ticktext=tick_text_daily, tickangle=-45)

    return fig
