"""Fixed-strike implied volatility table chart."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go


def build_fixed_strike_vol_table(
    iv_matrix: pd.DataFrame,
    spot: float,
) -> go.Figure:
    """Render an IV matrix as a Plotly table.

    Args:
        iv_matrix: DataFrame with expiry dates as index, strikes as columns, IV% as values.
        spot: Current underlying price — column nearest spot is highlighted.

    Returns:
        Plotly Figure containing a go.Table.
    """
    if iv_matrix.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data", showarrow=False)
        return fig

    strikes = iv_matrix.columns.tolist()
    expiries = iv_matrix.index.tolist()

    # Find the strike column closest to spot
    strike_arr = np.array(strikes, dtype=float)
    nearest_idx = int(np.argmin(np.abs(strike_arr - spot)))

    # Build header: ["Expiry | Strike", strike1, strike2, ...]
    header_values = ["Expiry \\ Strike"] + [f"{int(s)}" for s in strikes]

    # Build cell values: first column = formatted expiry dates, rest = IV%
    expiry_col = [str(e) for e in expiries]
    cell_columns: list[list[str]] = [expiry_col]
    for strike in strikes:
        col_vals = iv_matrix[strike]
        cell_columns.append(
            [f"{v:.2f}%" if not pd.isna(v) else "" for v in col_vals]
        )

    # Per-column fill colors: highlight nearest-to-spot column
    n_data_cols = len(strikes)
    header_fills = ["#1e1e2e"] + [
        "#2a3a5c" if i == nearest_idx else "#1e1e2e" for i in range(n_data_cols)
    ]
    cell_fills = ["#16213e"] + [
        "#1a2a4a" if i == nearest_idx else "#16213e" for i in range(n_data_cols)
    ]

    fig = go.Figure(
        go.Table(
            columnwidth=[120] + [70] * n_data_cols,
            header=dict(
                values=header_values,
                fill_color=header_fills,
                font=dict(color="white", size=11),
                align="center",
                line_color="#2a2a3e",
            ),
            cells=dict(
                values=cell_columns,
                fill_color=cell_fills,
                font=dict(color="#e0e0e0", size=11),
                align="center",
                line_color="#2a2a3e",
            ),
        )
    )

    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
    )
    return fig
