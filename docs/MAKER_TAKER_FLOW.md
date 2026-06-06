# Maker Taker Flow

### Technical Brief: "Maker-Taker" Option Flow Dashboard

#### **1. Objective**
Create a new interactive bubble chart sub-tab within the "Gamma Map" tab to visualize aggressive option flow (Maker-Taker dynamics). This chart will help identify whether customers are hitting the bid (selling) or lifting the ask (buying) at specific strikes over time.

#### **2. UI Placement & Controls**
* **Location:** A new Streamlit `st.tabs` element named **"Maker-Taker"** within the existing Gamma Map section.
* **Filters (Sidebar or Top of Tab):**
    * **Expiry Dropdown:** Reuse the existing single-expiry selection logic.
    * **Call/Put Radio:** `st.radio("View Side", options=["Calls", "Puts"])`.
    * **Weighting Radio:** `st.radio("Weight Bubbles By", options=["Last Size", "Total Volume"])`.
    * **Interval Slider:** `st.select_slider("Sample Interval (Minutes)", options=[1, 5, 10, 15, 30, 60], value=30)`.

#### **3. Data Processing Logic**
For the selected expiry and option type, implement the following transformations:

* **Midpoint Calculation:**
    `df['midpoint'] = (df['bid'] + df['ask']) / 2`
* **Trade Classification (Side Logic):**
    * `sentiment = +1` (Customer Buy / Dealer Short) if `last > midpoint`
    * `sentiment = -1` (Customer Sell / Dealer Long) if `last < midpoint`
    * `sentiment = 0` (Neutral) if `last == midpoint`
* **Weighted Sentiment:**
    * Calculate `weighted_flow = sentiment * weight_variable` (where `weight_variable` is the user-selected radio for `last_size` or `total_volume`).
* **Time-Series Resampling:**
    * Group data by the user-selected **Sample Interval**.
    * **Rule:** Within each time bucket, select the **last** available option chain sample to represent that interval (ensures we are seeing the most recent state of the tape for that period).

#### **4. Visualization Specifications (Plotly)**
* **Chart Type:** `px.scatter` (Bubble Chart).
* **X-Axis:** Sample Timestamp (Time).
* **Y-Axis:** Strike Price.
* **Size:** Absolute value of `weighted_flow`.
* **Color:** `weighted_flow` using a diverging color scale (e.g., `RdYlGn` or `Picnic`).
    * **Green:** Positive (Aggressive Buying).
    * **Red:** Negative (Aggressive Selling).
* **Reference Line:** Overlay a horizontal dashed line representing the current `underlying_price`.

#### **5. Developer Implementation Note**
> *"Ensure the Y-axis (Strikes) stays consistent with the Gamma Map view (roughly +/- 5-10% from spot) to allow for easy cross-referencing between structural walls and aggressive flow. Use Plotly's `size_max` parameter to ensure bubbles remain legible even during high-volume spikes (e.g., Fed announcements)."*