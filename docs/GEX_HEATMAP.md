# GEX Heatmap

### User Story: Options Gamma Term Structure Heatmap

**As a** professional options trader managing multi-contract repairs,
**I want to** visualize the distribution of Gamma Exposure (GEX) across strike prices and expiration dates in a single interactive heatmap,
**So that** I can identify the migration of structural "walls," locate "air pockets" in the market structure, and determine the optimal duration and strikes for my hedges.

---

### Technical Acceptance Criteria (For the Developer)

#### 1. Data
* **X-Axis:** Expiration Dates (sorted chronologically from left to right).
* **Y-Axis:** Strike Prices (sorted numerically; the dashboard should default to a range of +/- 5% from the current SPX Spot price).
* **Color Scale (Z-Axis):** Use a **diverging color scale** (e.g., `RdYlGn` or `Picnic`).
    * **Bright Green:** High Positive Gamma (Call Walls).
    * **Bright Red:** High Negative Gamma (Put Floors).
    * **Neutral/White:** Zero or low Gamma (The "Air Pockets").
* You will need to grab the latest sample for each option chain in the date range
* See the @gex.py file for how to calculate the GEX for each strike. If possible, try to reuse a function here.

#### 2. Visual Overlays (The "Pro" Features)
* **The Wall Lines:** Use Plotly `go.Scatter` to overlay two distinct trend lines connecting the "Maximums":
    * **Call Wall Line:** A line connecting the strike with the highest positive GEX for each expiration.
    * **Put Floor Line:** A line connecting the strike with the highest negative GEX for each expiration.
* **Spot Price Line:** A horizontal dashed white line representing the **Current SPX Spot Price** so I can see where the market is relative to future walls.

#### 3. Interactivity & Controls
* **Strike Range Slider:** A Streamlit slider (`st.select_slider`) to zoom the Y-axis strike range (e.g., from 6500 to 7500).
* **Date Filter:** A date range picker to filter out specific expiration chains (e.g., only show Friday Weeklies and Monthly OpEx).
  * Default to starting with today's date and going out 10 days
* **Interactive Hover (Plotly Tooltips):** When hovering over a cell, display:
    * `Expiration Date`
    * `Strike Price`
    * `Total GEX ($ value)`
    * `Distance from Spot (%)`
* **Normalization:** Provide a toggle to view "Absolute GEX" vs. "Relative GEX" (where each expiration's color is normalized to its own max/min) to help see walls in further-dated expirations where volume is lower.

#### 4. Dashboard Logic
* Add this as a new sub tab under the Gamma Map. Name it "Gamma Heatmap"

---

### Why this is "High Value" (Developer Context)
* **The "Wall Migration" Insight:** Most charts only show today. If the developer builds this across time, I can see if the **Call Wall** is sloping *upward* (bullish expansion) or *downward* (structural ceiling lowering).
* **The "Air Pocket" Discovery:** Large areas of white/neutral color between the Call and Put lines indicate a "Volatility Zone" where price movement will likely accelerate due to a lack of dealer hedging.

***

### Suggested Plotly Implementation Note for the Developer:
> *"Use `plotly.graph_objects.Heatmap` for the base layer. Overlay the Wall Lines using `go.Scatter(mode='lines+markers')`. Ensure `zsmooth='best'` is used for a cleaner visual, but keep the hover data tied to the raw, un-smoothed strike data for accuracy."*