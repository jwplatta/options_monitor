# Fixed Strike Vol

## Overview

The Fixed Strike Vol table displays implied volatility (IV) for SPXW options across a matrix of expiration dates (rows) and strikes (columns). Each cell shows the current market IV for that specific contract as a percentage. Cells are colored by a z-score heatmap that indicates whether IV is elevated or depressed relative to historical norms for options with similar characteristics.

---

## Controls

| Control | Description |
|---|---|
| **Days Out** | Maximum DTE to include (7, 14, 21, 30 days). Filters which expiry rows appear. |
| **Contract** | Call, Put, or OTM. OTM shows calls at/above spot and puts below spot in a single table. |
| **Strike Range (±% OTM)** | Filters columns to strikes within ±N% of the current spot price. |
| **Lookback (days)** | How many calendar days of historical snapshots to use when building z-score bucket statistics (10, 20, 30, 60, 90). |
| **Interval (min)** | Downsampling interval for historical data (30 or 60 min). Controls how many snapshots per day feed the historical bucket stats. |
| **Include 0DTE** | Toggle to include or exclude the same-day expiry chain. |
| **Spot (SPXW)** | Current underlying price read from the latest snapshot. |

---

## IV Data

- **Source**: Schwab options snapshots stored locally under `~/.tickrake/data/options/schwab/SPXW/`.
- **Field**: `volatility` column in each snapshot CSV — this is the market-implied volatility reported by Schwab, not the theoretical/model volatility.
- **Current snapshot**: The latest available snapshot per expiry is loaded. For each expiry date in the selected Days Out window, the most recently fetched file is used.
- **Gaps**: Not every strike exists in every expiry chain. Weekly expirations tend to have sparser strike grids (10pt spacing) vs. daily expirations (5pt spacing), so some cells will be blank where no contract exists at that strike.

---

## Z-Score Calculation

The z-score answers: *is this option's IV high or low compared to historical options with similar DTE and moneyness?*

### Bucketing

Rather than comparing a fixed strike's IV over time (which conflates spot movement with vol changes), each option is mapped to a **DTE bucket** and a **moneyness bucket**, and compared to all historical options that fell in the same buckets.

**DTE buckets** (days to expiration):

| Bucket | Range |
|---|---|
| 0–3d | Same-week / 0DTE |
| 3–7d | Very short-dated |
| 7–14d | 1–2 weeks |
| 14–21d | 2–3 weeks |
| 21–30d | ~1 month |
| 30–45d | 1–1.5 months |
| 45–60d | ~2 months |
| 60–90d | 2–3 months |
| 90–180d | 3–6 months |

**Moneyness buckets** (signed log-moneyness = `log(strike / spot)`):

| Bucket | Description |
|---|---|
| < −0.05 | Deep ITM (calls) / deep OTM (puts) — >5% ITM |
| −0.05 to −0.03 | ITM 3–5% |
| −0.03 to −0.01 | ITM 1–3% |
| −0.01 to −0.005 | ITM 0.5–1% |
| −0.005 to +0.005 | ATM ±0.5% |
| +0.005 to +0.01 | OTM 0.5–1% |
| +0.01 to +0.03 | OTM 1–3% |
| +0.03 to +0.05 | OTM 3–5% |
| > +0.05 | Deep OTM >5% |

Signed log-moneyness is used so that the same bucket definitions apply consistently to both calls and puts regardless of which side of spot a strike sits on.

### Building bucket statistics

For each historical snapshot loaded (one per interval sample per expiry), every option row is:
1. Assigned a DTE relative to the **fetch date** (not today), so historical options are compared at the right point in their lifecycle.
2. Assigned a log-moneyness using the `underlying_price` recorded in that snapshot.
3. Placed into its (contract_type, DTE bucket, moneyness bucket) cell.

After all historical frames are processed, each bucket accumulates a distribution of IV values. The bucket statistics are:
- `iv_mean`: mean IV across all observations in that bucket
- `iv_std`: standard deviation of IV across observations
- `count`: number of observations

### Computing the z-score

For each option in the current snapshot:

```
z = (IV_current - iv_mean) / iv_std
```

where `iv_mean` and `iv_std` come from the matching (contract_type, DTE bucket, moneyness bucket).

A cell shows **NaN** (no color) when:
- The bucket has fewer than 3 historical observations (`count < 3`)
- The bucket standard deviation is zero (all historical IVs were identical)
- The current option falls outside all defined bucket edges (e.g., DTE > 180)

### Color scale

The heatmap uses a continuous gradient clamped at ±3σ:

| Color | Meaning |
|---|---|
| Deep green | z ≥ +3: IV significantly elevated vs history |
| Mid green | z ≈ +1 to +2 |
| Dark gray | z ≈ 0: IV near historical average |
| Mid red | z ≈ −1 to −2 |
| Deep red | z ≤ −3: IV significantly depressed vs history |

The nearest-to-spot strike column is highlighted in blue when no z-score color is applied.

---

## Limitations

### Historical data coverage
- Z-scores are only as meaningful as the lookback window. With 10 days of history, bucket counts will be low and z-scores noisy. 30–90 days provides more stable estimates.
- If the options data feed was interrupted during the lookback window, affected buckets will have fewer observations and may show NaN.

### Downsampling
- Historical snapshots are downsampled to one per N-minute interval (30 or 60 min). Intraday IV moves within an interval are not captured. The latest snapshot in each bucket wins.
- Using 60-min intervals reduces the observation count per bucket compared to 30-min. This can increase NaN cells in sparsely populated buckets (e.g., very short-dated or deep wing strikes).

### Bucket granularity
- The moneyness buckets are relatively coarse in the wings (>3% OTM). Two options at 4% OTM and 8% OTM will be compared against the same bucket. Wing skew comparisons should be interpreted with this in mind.
- DTE bucketing means an option moving from 8 DTE to 6 DTE crosses a bucket boundary — its z-score reference population changes at that point.

### Same symbol only
- Historical bucket statistics are built from SPXW snapshots only. The z-scores do not incorporate SPX options or cross-product comparisons.

### Regime changes
- A longer lookback (60–90 days) improves bucket sample sizes but may span different vol regimes (e.g., a low-vol summer vs. a high-vol shock period). Z-scores during regime transitions can be misleading — a z = +2 during a vol spike may simply reflect that the spike is unprecedented in the lookback window.

### Cache
- Historical frames are cached for 30 minutes (`ttl=1800s`). Intraday bucket stats do not update on every page interaction. The z-score heatmap reflects conditions as of the last cache fill.
