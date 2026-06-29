# Parquet + DuckDB Migration Specification

## Goal

Replace per-file CSV loading for historical options data with DuckDB queries against
daily compacted parquet files, while keeping the existing SQLite metadata index + CSV
loading path for intraday (today's) data unchanged.

---

## Data Routing Rule

```
sample_date == today  →  SQLite index + CSV files  (unchanged)
sample_date <  today  →  DuckDB + parquet files    (new)
```

Tickrake writes one parquet per ticker per day:
```
~/.tickrake/data/options/schwab/{YYYY}/{MM}/{DD}/{TICKER}_samples_{YYYY-MM-DD}.parquet
```

Parquet schema is identical to the CSV columns plus a `sampled_at` timestamp column
(UTC ISO-8601 string today; will be typed `timestamp[us, UTC]` after tickrake fix).

---

## Benchmark Results (2026-06-26)

| Scenario | Time |
|---|---|
| pandas full parquet load (2.9M rows) | ~350ms |
| DuckDB parquet filtered by expiry (144k rows) | ~300ms |
| DuckDB parquet filtered expiry + snapshot (496 rows) | **~19ms** |
| pandas concat all SPXW CSVs (5,759 files) | ~12.5s |
| pandas concat CSVs for one expiry (SQLite → file list) | ~550ms |
| DuckDB glob all CSVs | ~19s — do not use |
| DuckDB narrow glob CSVs one expiry | ~1.4s — slower than pandas |
| DuckDB blend parquet+today_df UNION ALL | ~1.4s |

**Key finding:** DuckDB predicate pushdown on parquet is the win for historical data.
For today's CSVs, SQLite index → pandas concat remains the fastest path.

---

## Which Charts Use Historical vs Today Data

Each view falls into one of three cases:

### Today only (CSV path — no parquet benefit)

These views always load the most recent snapshot(s) for the current date. The existing
SQLite + CSV path is already the right approach. No changes needed.

| Tab | View | Data needed |
|---|---|---|
| GEX | GEX view | Latest snapshot per expiry, `start_date=today` |
| GEX | Gamma Heatmap | Latest snapshot per expiry, `start_date=today` |
| GEX | Chains view | Latest snapshot for selected expiry, `start_date=today` |
| Underlying | GEX overlay | Latest snapshot per expiry, `start_date=today` |
| Flow | Flow Tape / Profile / Intraday | When `sample_date == today` |

### Historical only (parquet path)

These views are explicitly user-navigated to a past date. No today data involved.
The user picks a `sample_date < today` from a date picker; all data comes from parquet.

| Tab | View | Data needed |
|---|---|---|
| GEX | GEX History view | All snapshots for selected past date across expiry window |
| GEX | Chain GEX History view | All snapshots for selected past date + expiry, with replay slider |
| Flow | Flow Tape / Profile / Intraday | When `sample_date < today` |

### Mixed (today + historical — both backends needed)

These views always need historical data for baseline/context AND today's data for the
current state. The two loads are separate function calls with no interleaving.

| Tab | View | Historical portion | Today portion |
|---|---|---|---|
| Fixed Strike Vol | IV matrix + z-score overlay | `_load_historical_frames()` — N past days of downsampled snapshots for z-score bucket building | `find_latest_snapshots(start_date=today)` — current IV matrix |

The historical and today loads in Fixed Strike Vol are already separate calls.
The z-score history load is all past dates → pure parquet. The current IV matrix
is always today → pure CSV. No interleaving required.

---

## Changes Required

### 1. `config.py` — add parquet root path

```python
PARQUET_OPTIONS_DIR: Path = Path(
    os.getenv("TRADE_DASH_PARQUET_OPTIONS_DIR", str(_TICKRAKE / "options" / "schwab"))
)
```

The parquet files live in the same root as the CSVs with the same date-partitioned
subdirectory structure. No new default path needed unless tickrake changes the layout.

---

### 2. `data/options.py` — new functions, existing functions unchanged

**Do not modify any existing functions.** Add a new section for parquet/DuckDB access.

#### New: `parquet_path_for_date(symbol, sample_date) -> Path | None`

Resolves the parquet file path for a given ticker and date. Returns `None` if the file
does not exist (e.g. today, weekends, or dates before compaction ran).

```python
def parquet_path_for_date(symbol: str, sample_date: date) -> Path | None:
    p = PARQUET_OPTIONS_DIR / f"{sample_date.year:04d}" / f"{sample_date.month:02d}" \
        / f"{sample_date.day:02d}" / f"{symbol}_samples_{sample_date.isoformat()}.parquet"
    return p if p.exists() else None
```

#### New: `load_historical_snapshot(symbol, expiry, sampled_at, parquet_path) -> pd.DataFrame`

Single-snapshot load from parquet. Equivalent to `load_options_snapshot(path)` for
historical dates. Filters by `expiration_date` and `sampled_at`.

#### New: `load_historical_expiry(symbol, expiry, sample_date, parquet_path) -> pd.DataFrame`

All snapshots for one expiry on one historical date, returned as a single DataFrame
with all rows sorted by `sampled_at`. Used by flow tape and chain replay views to
load an entire day's worth of data for one expiry in a single DuckDB query rather
than N CSV loads.

#### New: `find_historical_snapshot_times(expiry, parquet_path) -> list[datetime]`

Returns the distinct `sampled_at` values for a given expiry from a parquet file.
Replaces `find_snapshots_for_expiry_on_date()` for historical dates — instead of
returning `(datetime, Path)` pairs it returns just datetimes (no per-file paths needed).

#### New: `load_historical_lookback(symbol, parquet_glob, expiry_range, sampled_at_interval_minutes) -> pd.DataFrame`

Bulk historical load via DuckDB across a date-range glob. Returns a downsampled
DataFrame covering multiple past dates and expiries. Replaces the
`find_downsampled_snapshots_for_lookback()` + N × `load_options_snapshot()` loop
for all-historical use cases.

```sql
SELECT * FROM read_parquet('{glob}')
WHERE expiration_date BETWEEN '{start}' AND '{end}'
  AND (
    CAST(strftime('%H', sampled_at) AS INTEGER) * 60
    + CAST(strftime('%M', sampled_at) AS INTEGER)
  ) % {interval_minutes} = 0
ORDER BY sampled_at, expiration_date
```

---

### 3. Tab impact by case

#### Today-only views — no changes

GEX (GEX view, Gamma Heatmap, Chains), Underlying GEX overlay: unchanged.
These already use `find_latest_snapshots(start_date=today)` + `load_options_snapshot()`.

#### Historical-only views — GEX History, Chain GEX History, Flow (past date)

**`tabs/gex.py` — `_render_gex_history_view()` and `_render_history_view()`**

Currently: `find_snapshots_for_window_on_date()` / `find_snapshots_for_expiry_on_date()`
return `(datetime, Path)` pairs → `load_options_snapshot(path)` per replay step.

New: when `selected_sample_date < today`:
- Discovery: `find_historical_snapshot_times(expiry, parquet_path)` → `list[datetime]`
- Load per replay step: `load_historical_snapshot(symbol, expiry, sampled_at, parquet_path)`

`list_snapshot_dates()` and `list_expirations_for_window_on_date()` used for the date
picker and expiry selector still go through SQLite (it indexes all dates including past
ones). These are fast metadata-only queries and do not need to change.

**`tabs/flow.py` — Flow Tape, Flow Profile, Intraday Flow when `sample_date < today`**

Currently: `find_all_snapshots_for_expiry()` returns all `(datetime, Path)` pairs for
an expiry across all dates, then `_load_tape()` filters to `sample_date` and loads
each CSV individually.

New: when `sample_date < today`:
- Load entire expiry block for that date in one call: `load_historical_expiry()`
- Split by `sampled_at` in memory for per-snapshot iteration
- Eliminates the N-file loop entirely

When `sample_date == today`: unchanged — `find_snapshots_for_expiry_on_date()` + CSV.

#### Mixed view — Fixed Strike Vol

**`tabs/vol/fixed_strike.py`**

Two separate loads, routed independently:

**Historical portion** (`_load_historical_frames()`):
- Currently: `find_downsampled_snapshots_for_lookback()` → loop of `load_options_snapshot(path)`
- New: single call to `load_historical_lookback()` via DuckDB glob across past parquet files
- Returns a DataFrame directly — no path loop needed
- This is the highest-value change: replaces potentially hundreds of CSV reads with one query

**Today portion** (`find_latest_snapshots(start_date=today)`):
- Unchanged — SQLite + CSV

---

### 4. `calc/` layer — no changes required

All calc functions accept `pd.DataFrame` inputs with no knowledge of the data source.
Column names and types are identical between CSV and parquet (after tickrake schema fix).

One thing to confirm: `contract_type` must be uppercase before passing to calcs.
The benchmark parquet showed `CALL` — looks correct, but verify `PUT` as well.

---

## Migration Priority

Ordered by impact:

1. **Fixed Strike Vol z-score history load** — always runs on tab render, currently
   the most expensive load in the app. Pure historical → pure parquet. Highest ROI.

2. **Flow tab historical date** — user-triggered but currently slow for past dates
   due to N-file CSV loop. Pure historical → pure parquet.

3. **GEX History / Chain GEX History** — user-triggered historical replay. Currently
   loads N CSVs per replay step. Pure historical → pure parquet.

4. **Discovery functions** (`list_snapshot_dates`, `list_expirations_for_window_on_date`)
   for historical dates — lower priority since SQLite is already fast for these.

---

## Migration Phases

### Phase 1 — Foundation (no tab changes)
1. `duckdb` dependency added (done)
2. Add `parquet_path_for_date()` to `data/options.py`
3. Add `load_historical_snapshot()`, `load_historical_expiry()`,
   `find_historical_snapshot_times()`, `load_historical_lookback()`
4. Write unit tests against `~/.tickrake/.../2026/06/25/SPXW_samples_2026-06-25.parquet`

### Phase 2 — Fixed Strike Vol (highest impact)
5. Replace `_load_historical_frames()` in `fixed_strike.py` with `load_historical_lookback()`
6. Today portion (`find_latest_snapshots`) unchanged

### Phase 3 — Flow tab historical path
7. In `_load_tape()` and related helpers, branch on `sample_date < today` to use
   `load_historical_expiry()` instead of the CSV loop

### Phase 4 — GEX history views
8. In `_render_gex_history_view()` and `_render_history_view()`, branch on
   `selected_sample_date < today` to use parquet-backed discovery + loading

### Phase 5 — Cleanup
9. Remove `find_eod_snapshots_for_lookback()` (already marked unused)
10. Remove SQLite-backed discovery calls for historical dates once parquet coverage confirmed

---

## What Does NOT Change

- All `calc/` modules — pure functions, DataFrame in/out
- `data/candles.py` — candles not yet in parquet
- `tabs/vol/overview.py`, `tabs/vol/spx_rv.py` — candles only, no options data
- `tabs/history.py` — delegates entirely to `gex.py`, no direct data calls
- GEX, Underlying, and today's Flow views — already use SQLite + CSV correctly
- Streamlit `@st.cache_data` caching — stays on all public loader functions
- `_OPTIONS_DTYPES` — same column names and types, used for CSV and parquet casts
