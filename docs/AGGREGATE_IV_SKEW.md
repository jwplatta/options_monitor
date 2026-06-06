# Technical Brief: SPX Aggregate Skew Visualization

## **Objective**
Create a "Master Skew" visualization that smooths out intraday noise and event-driven "warps" (like the current Fed/Earnings distortions) by aggregating Implied Volatility (IV) across multiple expirations into a single, representative curve.

## **1. Data Pre-processing & Filtering**
To ensure the aggregate isn't skewed by "junk" data, the developer should:
* **Filter by Liquidity:** Exclude strikes with zero Volume or Open Interest.
* **Moneyness Range:** Focus on strikes within a $\pm 10\%$ range of the current Spot price ($S$).
* **Outlier Removal:** Use a z-score filter on IV to remove "ghost quotes" (extremely wide bid-ask spreads that show artificial IV spikes).

## **2. Recommended Aggregation Approaches**

### **A. The Constant Maturity (VIX-Style) Weighting**
* **Logic:** Interpolate between the two expirations (e.g., April 30 and May 8) that bracket a target maturity (usually 30 days).
* **Math:** Use a time-weighted average based on the square root of time: $\sigma_{agg} = \sqrt{w_1 \sigma_1^2 + w_2 \sigma_2^2}$.
* **Developer Goal:** This removes the "event hump" from the short-dated chain while retaining the market’s long-term risk view.

### **B. Vega-Weighted Average**
* **Logic:** Give more "weight" to options that are more sensitive to volatility changes.
* **Math:** $\text{IV}_{strike} = \frac{\sum (\text{IV}_i \cdot \text{Vega}_i)}{\sum \text{Vega}_i}$ for each strike across all active expiries.
* **Developer Goal:** This naturally prioritizes At-the-Money (ATM) strikes, as they have the highest Vega, providing a cleaner "anchor" for the skew.

### **C. SVI (Stochastic Volatility Inspired) Curve Fitting**
* **Logic:** Instead of averaging points, fit a parametric "Smile" curve to the raw data points.
* **Tooling:** Use `scipy.optimize` to fit a "least squares" curve to the IV/Delta points.
* **Developer Goal:** This creates a smooth, continuous line that makes it easy to spot "Relative Value" opportunities (strikes sitting significantly above or below the fitted line).

## **3. UI/UX Implementation (Streamlit + Plotly)**

* **The Main Plot:** A Plotly `go.Scatter` chart showing the **Fitted Aggregate Skew** as a solid bold line, with the raw data points from individual expiries shown as semi-transparent "ghost" points in the background.
* **Interactive Toggles:** Streamlit `st.sidebar.multiselect` to allow the user to toggle specific expirations on/off to see how they are influencing the aggregate.
* **The "Warp" Indicator:** A metric card calculating the **Skew Slope** ($\text{IV}_{Put} - \text{IV}_{Call}$ at $0.25$ Delta). If this number is negative, trigger a "Bullish Inversion" alert in the UI.

## **4. Python Snippet for Developer Guidance**
```python
import pandas as pd
import numpy as np

# Example: Simple Vega-weighted aggregation by Strike
def aggregate_iv(df):
    # Ensure we only use liquid options
    df = df[df['volume'] > 0]

    # Group by strike and calculate weighted average
    agg_skew = df.groupby('strike').apply(
        lambda x: np.average(x['iv'], weights=x['vega'])
    ).reset_index(name='weighted_iv')

    return agg_skew
```

**Developer Note:** Ensure the `X-axis` can toggle between **Strike Price** and **Delta**, as Delta-based skew allows for better comparison across different market regimes.