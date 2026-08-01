"""ES futures candlestick chart with volume subplot."""

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


def build_es_candlestick_chart(
    candles: pd.DataFrame,
    title: str = "ES Futures",
    freq: str = "day",
) -> go.Figure:
    """ES futures candlestick chart with optional volume subplot."""
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

    has_volume = "volume" in candles.columns and candles["volume"].notna().any()

    if has_volume:
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            row_heights=[0.65, 0.35],
            vertical_spacing=0.02,
        )
    else:
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

    if has_volume:
        fig.add_trace(
            go.Bar(
                x=x,
                y=candles["volume"],
                marker_color="steelblue",
                opacity=0.7,
                showlegend=False,
                hoverinfo="skip",
            ),
            row=2,
            col=1,
        )

    fig.update_layout(
        title=title,
        yaxis_title="Price",
        template="plotly_dark",
        margin={"l": 40, "r": 20, "t": 40, "b": 40},
        xaxis_rangeslider_visible=False,
    )

    if has_volume:
        fig.update_yaxes(title_text="Volume", row=2, col=1)
        fig.update_xaxes(title_text="Date/Time", row=2, col=1)
    else:
        fig.update_xaxes(title_text="Date/Time", row=1, col=1)

    if intraday:
        fig.update_xaxes(tickvals=tick_vals, ticktext=tick_text, tickangle=-45)
    else:
        fig.update_xaxes(tickvals=tick_vals_daily, ticktext=tick_text_daily, tickangle=-45)

    return fig
