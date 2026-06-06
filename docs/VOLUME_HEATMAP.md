TLDR: Build a strike × time heatmap where each cell shows a normalized intraday flow metric: (Δvolume / rolling avg Δvolume) × signed_delta, filtered to active, near-the-money contracts and grouped by symbol/expiry/type.

Metric definition
	•	Input data is snapshots like your CSV (one row per contract per timestamp).
	•	For each contract (unique strike + contract_type + expiration_date):
	•	dV_t = total_volume_t − total_volume_{t-1} (per sample interval)
	•	baseline = rolling_mean(dV over last N samples) (or EWMA)
	•	signed_delta = delta for calls, -delta for puts
	•	Final metric:
	•	flow = (dV_t / baseline) * signed_delta
	•	Optional:
	•	Clip signed_delta (e.g., ±0.7) to reduce ITM dominance

Chart structure (Plotly heatmap)
	•	X-axis: timestamp (from filename or data)
	•	Y-axis: strike
	•	Z-value: flow metric
	•	Color:
	•	Positive → bullish flow
	•	Negative → bearish flow
	•	Filters:
	•	symbol (e.g., SPXW)
	•	expiration_date
	•	contract_type (CALL / PUT / ALL)

Data handling
	•	Files follow pattern:
/.../SPXW_expYYYY-MM-DD_YYYY-MM-DD_HH-MM-SS.csv
	•	First date = expiration
	•	Second datetime = snapshot timestamp
	•	Load all files where snapshot date = today
	•	Concatenate and sort by timestamp
	•	Group by contract to compute dV

Filtering
	•	Drop rows where total_volume == 0
	•	Moneyness filter (required):
	•	Use underlying_price to compute moneyness
	•	Keep strikes within a band around spot (e.g., ±10–20%)
	•	Explicitly exclude:
	•	Far ITM (delta ≈ 1 or deep intrinsic)
	•	Far OTM (very low delta, illiquid tails)
	•	This keeps the heatmap focused on relevant, tradable strikes