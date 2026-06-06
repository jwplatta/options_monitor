# Plan: Maker-Taker Bubble Chart Subtab

## Context

Adds a "Maker-Taker" subtab to the Gamma Map tab to visualize aggressive option flow. Using the `last` vs `(bid+ask)/2` midpoint to classify each trade as a customer buy (+1) or customer sell (−1), weighted by `last_size` or `total_volume`, and sampled at configurable intraday intervals. The result is a bubble chart where bubbles are green for aggressive buying, red for aggressive selling, sized by flow magnitude.

---

## Files to Create

### `src/trade_dash/calc/maker_taker.py`

```python
def compute_maker_taker_flow(
    snapshots: list[tuple[datetime, Path]],
    spot: float,
    moneyness_pct: float = 0.15,
    contract_filter: str = "CALL",
    bucket_minutes: int = 5,
    weight_by: str = "last_size",   # "last_size" | "total_volume"
    target_date: date | None = None,
    top_n_strikes: int = 10,
) -> tuple[list[datetime], list[float], list[float], list[datetime], list[float]]:
    # Returns: (timestamps, strikes, weighted_flows, bucket_times, bucket_prices)
    # timestamps/strikes/weighted_flows: parallel flat arrays, one entry per (bucket × strike) point
    # bucket_times/bucket_prices: one underlying_price per unique bucket (for price overlay)
```

**Algorithm:**
1. Filter snapshots to `target_date` (default today)
2. Bucket selection: iterate snapshots in time order, **overwrite** `dict[bucket_key] = (ts, path)` so the **last** snapshot wins per bucket (contrast to flow.py which takes first)
3. Load each selected snapshot, coerce `bid`, `ask`, `last`, and weight column to float; `dropna` on all four
4. Moneyness filter: `abs(strike - spot) / spot <= moneyness_pct`
5. Contract type filter: `contract_type.str.upper() == contract_filter.upper()`
6. Compute: `midpoint = (bid + ask) / 2`, `sentiment = np.sign(last - midpoint)`, `weighted_flow = sentiment × weight_col`
7. Aggregate `(bucket_ts, strike)` pairs by **sum** (net pressure at a strike within a bucket)
8. **Top-N filter:** sum `abs(weighted_flow)` across all buckets per strike → rank → keep top `top_n_strikes` strikes by total activity; discard the rest
9. Build parallel flat arrays sorted by `(bucket_ts, strike)`, convert UTC → Chicago naive
10. Return `(timestamps, strikes, weighted_flows, bucket_times, bucket_prices)`

Edge cases:
- Missing `last` column → `dropna` produces empty → return 5 empty lists
- Empty snapshots → return 5 empty lists immediately

### `src/trade_dash/charts/maker_taker_bubble.py`

```python
_COLORSCALE = [
    [0.0,  "rgb(220,0,0)"],
    [0.35, "rgb(160,60,0)"],
    [0.47, "rgb(200,180,0)"],
    [0.5,  "rgb(240,230,50)"],
    [0.53, "rgb(100,180,0)"],
    [0.65, "rgb(0,140,0)"],
    [1.0,  "rgb(0,220,0)"],
]

def build_maker_taker_bubble_chart(
    timestamps: list[datetime],
    strikes: list[float],
    weighted_flows: list[float],
    bucket_times: list[datetime],
    bucket_prices: list[float],
    spot: float,
    title: str = "Maker-Taker Flow",
) -> go.Figure:
```

- Guard on empty data: return empty `go.Figure` with dark template
- Normalize bubble sizes to `[3, 40]` pixels relative to `max(abs(weighted_flows))`
- `go.Scatter(mode="markers", marker=dict(size=..., color=weighted_flows, colorscale=_COLORSCALE, cmid=0, colorbar=dict(title="Flow")))`
- `fig.add_hline(y=spot, line_dash="dash", line_color="white", annotation_text=f"Spot {spot:.0f}")` for current price reference
- Second trace: `go.Scatter(x=bucket_times, y=bucket_prices, mode="lines", line=dict(color="rgba(255,255,255,0.4)", width=1))` for price path overlay
- `template="plotly_dark"`, `showlegend=False`

### `tests/unit/test_maker_taker_calc.py`

Key tests:
- `test_last_snapshot_selected_per_bucket` — two snapshots same bucket, verify last wins (check underlying_price)
- `test_sentiment_positive_when_last_above_midpoint`
- `test_sentiment_negative_when_last_below_midpoint`
- `test_sentiment_zero_when_last_equals_midpoint`
- `test_top_n_strikes_limits_output` — 20 strikes in, top_n_strikes=5, assert only 5 unique strikes in output (the 5 with highest total abs flow)
- `test_moneyness_filter_excludes_far_strikes`
- `test_contract_type_filter_uppercases` — pass "call", no error
- `test_returns_empty_on_no_snapshots`
- `test_missing_last_column_returns_empty`
- `test_weight_by_total_volume_uses_volume`
- `test_return_array_lengths_are_consistent`

### `tests/unit/test_maker_taker_chart.py`

Key tests:
- `test_build_maker_taker_bubble_chart_returns_figure` — `isinstance(fig, go.Figure)`, `len(fig.data) >= 1`
- `test_empty_data_returns_figure_with_no_traces`
- `test_hline_present_when_spot_nonzero` — `len(fig.layout.shapes) >= 1`
- `test_price_overlay_trace_added_when_bucket_data_present` — `len(fig.data) == 2`

---

## Files to Modify

### `src/trade_dash/data/options.py`

Add to `_OPTIONS_DTYPES` dict (lines 14–27):
```python
"last": "float64",
"last_size": "float64",
```
Safe: pandas silently skips dtype entries for columns not present in a CSV, so old files won't break.

### `src/trade_dash/tabs/gamma_map.py`

**Line 114** — extend `st.tabs` call:
```python
tab_gex, tab_chains, tab_history, tab_intraday, tab_gamma_heatmap, tab_maker_taker = st.tabs(
    ["GEX", "Chains", "Chain GEX History", "Intraday", "Gamma Heatmap", "Maker-Taker"]
)
```

**Add imports** (top of file):
```python
from trade_dash.calc.maker_taker import compute_maker_taker_flow
from trade_dash.charts.maker_taker_bubble import build_maker_taker_bubble_chart
```

**Add `with tab_maker_taker:` block** after the `with tab_gamma_heatmap:` block (before `_render()` call):
- Controls: `mt_ct` radio (CALL/PUT, key `gm_mt_ct`), `mt_weight` radio (last_size/total_volume, key `gm_mt_weight`), `mt_bucket` select_slider (options=[1,5,10,15,30,60], key `gm_mt_bucket`), `mt_date` date_input (key `gm_mt_date`), `mt_top_n` slider (min=5, max=20, value=10, key `gm_mt_top_n`)
- Cache key: `(symbol, selected_exp_str, round(spot), strike_range, mt_ct, mt_bucket, mt_weight, mt_date, mt_top_n, len(all_expiry_snapshots))`
- Session state keys: `_mt_key`, `_mt_timestamps`, `_mt_strikes`, `_mt_flows`, `_mt_bucket_times`, `_mt_bucket_prices`
- Call `compute_maker_taker_flow(...)` then `build_maker_taker_bubble_chart(...)`
- Reuses `gm_expiry` selectbox (already rendered in `col_ctrl`)
- Calls `find_all_snapshots_for_expiry(symbol, expiry=selected_exp, data_dir=options_dir)` independently (not shared with Intraday tab)

---

## Implementation Sequence

1. `data/options.py` — add `last`/`last_size` to dtypes (prerequisite for all downstream)
2. `calc/maker_taker.py` + `test_maker_taker_calc.py` — pure functions, test in isolation
3. `charts/maker_taker_bubble.py` + `test_maker_taker_chart.py` — pure functions, no Streamlit
4. `tabs/gamma_map.py` — assembly only

---

## Verification

```bash
# Run unit tests
uv run pytest tests/unit/

# Confirm no regressions in options loader (dtype change is additive)
uv run pytest tests/unit/test_options_loader.py -v

# Lint and type-check new modules
uv run ruff check src/trade_dash/calc/maker_taker.py src/trade_dash/charts/maker_taker_bubble.py
uv run mypy src/trade_dash/calc/maker_taker.py src/trade_dash/charts/maker_taker_bubble.py

# Run the app and navigate to Gamma Map → Maker-Taker tab
uv run streamlit run src/trade_dash/app.py
```

End-to-end validation:
- Select an expiry, set Call/Put, choose a sample interval, pick today's date
- Bubbles should appear at traded strikes — green above spot (buyers lifting ask), red below spot (sellers hitting bid)
- Spot reference line should be visible as dashed horizontal
- Price path overlay should trace underlying movement across buckets
- Changing Weight By radio should update bubble sizes
- Changing interval slider should change bucket granularity (fewer/more x-axis points)
