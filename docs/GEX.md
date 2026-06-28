# GEX Implementation

Summary of how `calc/gex.py`, `calc/gex_term_structure.py`, and `tabs/gex.py` work together.

---

## Multi-expiry aggregation: how data flows into the aggregate GEX chart

The GEX view and Gamma Heatmap both operate on a **concatenated multi-expiry DataFrame** — not per-expiry files. The pipeline is:

1. **`find_latest_snapshots`** (data/options.py) — queries the metadata SQLite DB and returns `{expiry_date: path}`, one CSV path per expiry within the selected window (e.g. the next 10 days). This is a single SQL window-function query (`ROW_NUMBER() OVER PARTITION BY expiration_date ORDER BY last_observed_at DESC`), so it always picks the freshest file per expiry.

2. **`load_options_snapshot`** per path — each CSV is a full option chain snapshot for one expiry at one point in time. Columns include `strike`, `contract_type`, `gamma`, `open_interest`, `theoretical_volatility`, `underlying_price`, `expiration_date`, etc.

3. **`pd.concat`** across all expiry DataFrames — produces a single wide DataFrame `all_opts` that contains every strike × expiry combination. The `expiration_date` column distinguishes expiries; `contract_type` distinguishes calls/puts. All downstream calc functions receive this concatenated frame and work across all expiries simultaneously.

   ```python
   all_opts = pd.concat(
       [load_options_snapshot(path) for path in snapshots.values()],
       ignore_index=True,
   )
   ```

4. **Calc functions** then receive `all_opts` and aggregate across the full expiry window:
   - `net_gex_by_strike` — sums GEX across all expiries at each strike (no per-expiry distinction in the bar chart).
   - `find_raw_wall_strikes` / `find_aggregate_wall_strikes` / `find_decision_zones` — all operate on `all_opts`, but use `expiration_date` internally for DTE weighting and persistence scoring (see below).
   - `net_gex_by_price` — recomputes BS gamma at each hypothetical price using `theoretical_volatility` and DTE per contract, so IV and time-to-expiry are contract-specific even in the aggregate.

**Why concat instead of per-expiry iteration?** Vectorised pandas operations on one large frame are faster than N separate groupby passes. It also lets `_side_gex_rows` filter, coerce, and sign-assign all contracts in one pass, with `expiration_date` retained as a column for the weighting steps that follow.

---

## calc/gex.py — Pure Computation

### Data preparation: `_side_gex_rows`

Entry point for most calculations. Coerces `gamma`, `open_interest`, `strike`, and `contract_type` to numeric/typed values, drops nulls, filters to strikes within `±strike_range` of spot, and computes per-contract GEX:

```
gex = gamma × open_interest × spot² × sign
```

**Open interest caveat:** The `open_interest` field reflects the *previous trading day's* OI — options exchanges only update OI once daily after settlement. Intraday snapshots always carry stale OI, so GEX figures based on OI lag actual positioning by up to one full trading day.

**Sign convention (heuristic):** Calls are assigned `+1` and puts `-1`. This follows the market-maker hedging assumption: MMs are assumed to be net short options (i.e. short the gamma), so they must buy the underlying as price rises (delta-hedge calls) and sell as price falls (delta-hedge puts). Positive net GEX at a strike implies a stabilising, mean-reverting dealer flow around that level; negative net GEX implies amplifying, trending flow. This is a heuristic — actual dealer positioning is unobservable and can differ materially.

Returns a flat DataFrame with columns `[K, gex, expiration_date, contract_type]`.

---

### Intermediate aggregation: `_aggregate_side_gex_by_strike`

Internal helper used by wall-strike and decision-zone functions (not by `net_gex_by_strike`). Splits `all_opts` into call and put frames, then groups by strike with optional **DTE weighting**:

```
weighted_gex = gex / max(DTE, 1)
```

where `DTE = (expiration_date − anchor_date).days`. Near-expiry contracts carry higher weight because their gamma is more concentrated and directly relevant to near-term price action. Returns separate `calls[K, gex]` and `puts[K, gex]` DataFrames, where `gex` is the DTE-weighted sum across all expiries at that strike.

When `weight_by_distance=False` (used by `find_raw_wall_strikes`), the plain unweighted GEX sum is used instead.

---

### GEX by strike: `net_gex_by_strike`

Vectorised over the full options DataFrame (no per-expiry grouping). Computes net GEX per contract, sums by strike, and clips to `±strike_range`. Used for the bar chart in the aggregate GEX view. Unlike `_aggregate_side_gex_by_strike`, this does **not** apply DTE weighting — it's a raw cross-expiry sum, so the bar chart reflects total gamma exposure regardless of time horizon.

---

### GEX by price grid: `net_gex_by_price`

Builds a ±`price_range` integer price grid around spot. For each grid price it recomputes Black-Scholes gamma from scratch (using `_bs_gamma`) against every contract's strike, IV, and DTE — so gamma scales correctly as the hypothetical spot moves. Returns a `[price, net_gex]` DataFrame used to draw the GEX-by-price curve and find the zero-gamma level.

**`_bs_gamma`** — vectorised Black-Scholes gamma:
```
d1 = (ln(S/K) + (r - q + σ²/2)·T) / (σ√T)
Γ = N'(d1) / (S·σ·√T)
```

---

### Zero-gamma level: `find_zero_gamma_level`

Takes the `[price, net_gex]` output from `net_gex_by_price`, forward-fills sign across zero values, finds the first sign change, and linearly interpolates the exact crossing price.

---

### Wall strikes

Two approaches, both returning `(call_wall, put_wall)`:

**`find_raw_wall_strikes`** — SpotGamma style. OTM call with the highest gross call GEX above spot; OTM put with the most negative gross put GEX below spot. No DTE weighting.

**`find_aggregate_wall_strikes`** — two methods selectable via `method=`:
- `distance_weighted_aggregate`: aggregates OTM side GEX by strike, weighted by `1/DTE` so near-expiry contracts dominate. Picks the peak.
- `per_expiry_clustering`: for each expiry independently picks the top OTM wall strike, then clusters repeated strikes across expiries (sorted by `count → abs_gex`).

---

### Decision zones: `find_decision_zones`

The most sophisticated level-finding approach.

1. **Candidates** (`_distance_weighted_zone_candidates`): runs both `_side_gex_rows` and `_aggregate_side_gex_by_strike` (DTE-weighted), then scores each OTM strike:
   ```
   score = 0.70 × (|gex| / max_|gex|) + 0.30 × (expiry_count / total_expiries)
   ```
   Magnitude accounts for 70%, persistence across expiries for 30%.

2. **Zone clustering** (`_cluster_candidates_into_zones`): 
   - Pre-filters to strong candidates (score ≥ 60% of max, or at least 75th percentile).
   - Detects local score peaks.
   - For each peak, groups strikes within `merge_gap` (default 25 pts) that are ≥ 80% of the peak score.
   - Computes a score-weighted centroid as the zone center.
   - Expands to `[center ± zone_pad]` but caps at `max_zone_width`.
   - Skips zones that overlap already-placed zones.
   - Returns up to `top_n` zones sorted by score.

Returns `(resistance_zones, support_zones)` — each a list of `{low, high, center, score}` dicts.

---

## tabs/gex.py — Streamlit UI

### Layout

The tab uses a two-column layout: `col_ctrl` (controls, 1/4 width) and `col_chart` (charts, 3/4 width). The entire tab runs inside a `@st.fragment(run_every="5m")` for auto-refresh.

**Controls:** symbol (`SPXW`/`SPX`), include 0DTE toggle, strike range % of spot.

**Views** (segmented control): `GEX`, `Chains`, `Gamma Heatmap`.

---

### GEX view (`_render_gex_view`)

Aggregate window selector (5 / 10 / 20 / 30 days out from today).

1. `find_latest_snapshots` → one CSV path per expiry within the window.
2. `pd.concat([load_options_snapshot(p) for p in snapshots.values()])` → `all_opts`, a single DataFrame covering all expiries. See [Multi-expiry aggregation](#multi-expiry-aggregation-how-data-flows-into-the-aggregate-gex-chart) above.
3. Computes from `all_opts`:
   - `net_gex_by_strike` → raw cross-expiry GEX sum per strike (bar chart)
   - `find_raw_wall_strikes` → SpotGamma-style unweighted walls
   - `find_aggregate_wall_strikes(..., method="distance_weighted_aggregate")` → DTE-weighted peak wall
   - `find_aggregate_wall_strikes(..., method="per_expiry_clustering")` → cross-expiry repeated-strike wall
   - `find_decision_zones` → scored, clustered resistance/support zones (DTE-weighted magnitude + persistence)
   - `net_gex_by_price` (with spinner) → BS-recomputed GEX curve across a price grid; zero-gamma level derived from this
4. Passes everything to `build_gex_aggregate_chart`.

---

### Chains view (`_render_chains_view`)

Single-expiry view. Loads the latest snapshot for the selected expiration.

- Renders a risk-reversal skew indicator (25Δ call IV − 25Δ put IV) via `build_skew_indicators`.
- Renders a per-expiry GEX bar chart via `build_gex_single_expiry_chart`.
- Segmented control switches between **Vol Skew**, **Option Price**, and **Delta** charts, all built by `build_vol_skew_chart` with different `value_col` arguments.

---

### Gamma Heatmap view (`_render_gamma_heatmap_view`)

Date-range picker selects a window of expirations. Unlike the GEX view, data is **not concatenated** — each expiry is loaded and processed independently to preserve the per-expiry dimension needed for the heatmap axes.

`compute_gex_term_structure` (calc/gex_term_structure.py):
1. For each expiry in the window, loads its snapshot and runs `net_gex_by_strike`.
2. Collects the union of all strikes across expiries.
3. Builds a `matrix[strike_idx][expiry_idx]` of net GEX values (0.0 where a strike doesn't appear for a given expiry).
4. Returns `(strikes, expirations, matrix)`.

Result is cached in session state by `(symbol, spot, strike_range, gh_start, gh_end, len(snapshots))`. Rendered as a heatmap by `build_gex_term_structure_chart` with optional per-expiry normalization (divides each column by its max absolute value, making relative concentration visible across expiries of very different absolute GEX magnitude).

---

### Session-state caching pattern

Every expensive computation uses the same pattern:

```python
cache_key = (symbol, date, days_out, ...)
if st.session_state.get("_cache_key") != cache_key:
    result = expensive_computation(...)
    st.session_state["_cache_key"] = cache_key
    st.session_state["_result"] = result
else:
    result = st.session_state["_result"]
```

Cache keys always include `len(snapshots)` so new files on disk invalidate the cache.

---

### Timezone handling

Snapshot timestamps are UTC on disk. `_to_chicago_time` converts them to naive Chicago-local datetimes for display in sliders and captions. `snap_time` passed to `net_gex_by_price` is stripped of tzinfo after converting to UTC-naive so DTE arithmetic is consistent.
