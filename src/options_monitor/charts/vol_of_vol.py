"""Vol-of-Vol chart: VoV and vol change (Δσ)."""

from __future__ import annotations

import datetime as _dt
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

_INTRADAY_FREQS = {"1min", "5min", "30min"}


def _day_boundary_ticks(datetimes: pd.Series) -> tuple[list[int], list[str]]:
    dates = datetimes.dt.normalize()
    changed = pd.Series([True], index=[dates.index[0]]).reindex(dates.index, fill_value=False)
    changed |= dates != dates.shift(1)
    tick_vals = changed[changed].index.tolist()
    tick_text = dates[changed].dt.strftime("%-m/%-d").tolist()
    return tick_vals, tick_text


def _hour_boundary_ticks(datetimes: pd.Series) -> tuple[list[int], list[str]]:
    hours = datetimes.dt.floor("h")
    changed = pd.Series([True], index=[hours.index[0]]).reindex(hours.index, fill_value=False)
    changed |= hours != hours.shift(1)
    tick_vals = changed[changed].index.tolist()
    tick_text = datetimes[changed].dt.strftime("%-m/%-d %H:%M").tolist()
    return tick_vals, tick_text


def build_vol_of_vol_chart(
    candles: pd.DataFrame,
    n_window: int = 30,
    m_window: int = 60,
    freq: str = "1min",
    display_start: date | None = None,
    title: str = "SPX Vol-of-Vol",
) -> go.Figure:
    """Two-panel chart: VoV (top) and Δσ filled areas (bottom).

    Pass the full candle history (including warmup bars) via `candles`.
    Set `display_start` to trim what is plotted after rolling values are warmed up.
    """
    closes = candles["close"]
    log_returns: pd.Series = pd.Series(np.log(closes / closes.shift(1)), index=closes.index)
    sigma: pd.Series = pd.Series(
        np.sqrt(log_returns.pow(2).rolling(n_window).sum()), index=closes.index
    )
    delta_sigma: pd.Series = sigma.diff()
    vov: pd.Series = delta_sigma.rolling(m_window).std()

    # Trim to display range after rolling values are fully computed
    if display_start is not None:
        dt = candles["datetime"]
        tz = dt.dt.tz
        start_ts = pd.Timestamp(display_start, tz=tz) if tz is not None else pd.Timestamp(display_start)
        mask = dt >= start_ts
        candles = candles[mask].reset_index(drop=True)
        delta_sigma = delta_sigma[mask].reset_index(drop=True)
        vov = vov[mask].reset_index(drop=True)

    pos_delta = delta_sigma.where(delta_sigma >= 0, 0.0)
    neg_delta = delta_sigma.where(delta_sigma <= 0, 0.0)

    intraday = freq in _INTRADAY_FREQS
    if intraday:
        x = list(range(len(candles)))
        dt_local = candles["datetime"]
        if dt_local.dt.tz is not None:
            dt_local = dt_local.dt.tz_convert(_dt.datetime.now().astimezone().tzinfo)
        n_days = (dt_local.iloc[-1] - dt_local.iloc[0]).days if len(dt_local) > 1 else 0
        tick_vals, tick_text = (
            _hour_boundary_ticks(dt_local) if n_days <= 3 else _day_boundary_ticks(dt_local)
        )
        hover = dt_local.dt.strftime("%m/%d %H:%M").tolist()
        htpl = "%{text}<br>%{y:.5f}<extra></extra>"
    else:
        dt_local = candles["datetime"]
        if dt_local.dt.tz is not None:
            dt_local = dt_local.dt.tz_convert(_dt.datetime.now().astimezone().tzinfo)
        x = dt_local.tolist()
        hover = None
        htpl = "%{y:.5f}<extra></extra>"

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.50, 0.50],
        vertical_spacing=0.04,
    )

    # ── Row 1: VoV ────────────────────────────────────────────────────────────
    fig.add_trace(
        go.Scatter(x=x, y=vov, name=f"VoV (M={m_window})",
                   line={"color": "orange", "width": 1.5},
                   text=hover, hovertemplate=htpl),
        row=1, col=1,
    )

    # ── Row 2: Δσ filled areas ────────────────────────────────────────────────
    fig.add_trace(
        go.Scatter(x=x, y=pos_delta, name="Δσ ↑ (vol rising)",
                   fill="tozeroy", line={"width": 0},
                   fillcolor="rgba(220, 60, 60, 0.55)",
                   text=hover, hovertemplate=htpl),
        row=2, col=1,
    )
    fig.add_trace(
        go.Scatter(x=x, y=neg_delta, name="Δσ ↓ (vol falling)",
                   fill="tozeroy", line={"width": 0},
                   fillcolor="rgba(40, 180, 120, 0.55)",
                   text=hover, hovertemplate=htpl),
        row=2, col=1,
    )

    fig.update_layout(
        title=title,
        template="plotly_dark",
        legend={"orientation": "h", "y": 1.02},
        margin={"l": 40, "r": 40, "t": 40, "b": 40},
    )
    fig.update_yaxes(title_text="VoV", row=1, col=1)
    fig.update_yaxes(title_text="Δσ", row=2, col=1)
    fig.update_xaxes(title_text="Date/Time", row=2, col=1)

    if intraday:
        fig.update_xaxes(tickvals=tick_vals, ticktext=tick_text, tickangle=-45)

    return fig
