# GEX Key Levels: Calculation Reference

This document describes every line and zone drawn on the aggregate GEX chart.

---

## Spot (white dashed)

The current underlying price, read directly from the `underlying_price` field of the most recent options snapshot.

---

## ZGL — Zero Gamma Level (yellow dotted)

The price at which aggregate net dealer gamma crosses zero, computed on a 1-point price grid using Black-Scholes gamma.

For each price `p` on the grid, dealer gamma exposure is:

```
GEX(p) = Σ [ BS_gamma(S=p, K, T, σ) × OI × p² × sign ]
```

where `sign = +1` for calls, `-1` for puts. The ZGL is the first price where `GEX` changes sign, found by linear interpolation.

**Interpretation:** Above the ZGL, dealers are net long gamma — they buy dips and sell rips, dampening moves. Below it, dealers are net short gamma and amplify moves.

---

## CW / PW — Raw Call Wall / Put Wall (solid bright green / red)

SpotGamma-style walls. The single OTM strike with the largest raw gamma exposure on each side, summed flat across all expiries with no weighting.

```
call_gex(K) = Σ_expiries [ gamma × OI × spot² ]   for CALL, K >= spot
put_gex(K)  = Σ_expiries [ gamma × OI × spot² ]   for PUT,  K <= spot

CW = argmax_K  call_gex(K)
PW = argmin_K  put_gex(K)     # most negative
```

**Interpretation:** The strike where the largest total open interest × gamma is concentrated on each side. Dealer delta-hedging at this strike creates the most mechanical buying (put wall) or selling (call wall) pressure.

---

## CW-DW / PW-DW — Distance-Weighted Call Wall / Put Wall (dashed medium green / red)

Same structure as the raw walls, but GEX at each strike is weighted by inverse DTE before aggregating, so nearer expiries count more:

```
weighted_gex = gamma × OI × spot² / max(DTE, 1)
```

The wall is the OTM peak of the weighted sum across expiries.

**Interpretation:** Emphasizes strikes where near-term open interest is concentrated, which are more immediately relevant to dealer hedging behavior than far-dated strikes.

---

## CW-CL / PW-CL — Clustering Call Wall / Put Wall (dotted muted green / red)

A consensus-based approach. Rather than summing across expiries, the strongest OTM wall strike is identified independently per expiry, then strikes are scored by how many expiries agree on them.

Steps:
1. For each expiry, find the single highest call GEX strike above spot (or lowest put GEX below spot).
2. Count how many expiries select each strike (`count`), and sum absolute GEX across those expiries (`abs_gex`).
3. The wall = strike with the highest `(count, abs_gex)` score.

**Interpretation:** Identifies strikes that are structurally dominant across multiple expiration cycles, not just the heaviest single expiry. A strike that appears as the top wall in 5 consecutive expiries is treated as more significant than one with a single very large expiry.

---

## R1 / R2 — Resistance Zones (translucent green bands)
## S1 / S2 — Support Zones (translucent red bands)

Decision zones highlight where the most significant gamma concentration clusters in a region rather than at a single strike. Zones are scored and built using the distance-weighted aggregate GEX data.

### Candidate scoring

Each OTM strike is scored on two dimensions:

| Component | Weight | Definition |
|---|---|---|
| Magnitude | 70% | `abs(weighted_gex) / max_abs_gex` — how large is the gamma exposure here relative to the strongest strike in the window |
| Persistence | 30% | `expiry_count / total_expiries` — how many expiries have open interest at this strike |

### Zone construction

1. The top-scoring candidates are filtered (above the 75th percentile or the strongest `top_n × 4` strikes).
2. Local score peaks are identified — a strike qualifies as a peak if its score is ≥ both neighbors.
3. Around each peak, nearby strikes within `merge_gap = 25 pts` scoring ≥ 80% of the peak score are grouped together.
4. The zone center is the score-weighted average of grouped strikes. The zone width is capped at **20 points** so bands stay tactical.
5. Overlapping zones are dropped; the top 2 zones per side are shown.

**Interpretation:** A zone marks a region where multiple strikes share significant, persistent gamma concentration. Price entering a zone is likely to encounter meaningful dealer hedging activity across a range rather than at a single point.

---

## Summary table

| Label | Color | Line style | Method | What it answers |
|---|---|---|---|---|
| Spot | White | Dashed | — | Where is price now? |
| ZGL | Yellow | Dotted | BS gamma grid | Where does dealer gamma flip sign? |
| CW / PW | Bright green / red | Solid | Raw OI×gamma peak | Where is the single biggest gamma concentration? |
| CW-DW / PW-DW | Medium green / red | Dashed | DTE-weighted peak | Where does near-term positioning peak? |
| CW-CL / PW-CL | Muted green / red | Dotted | Per-expiry consensus | Which strike do the most expiries agree on? |
| R1–R2 / S1–S2 | Green / red band | Filled zone | Magnitude + persistence score | Where is gamma clustered across a region? |
