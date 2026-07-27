# Options Monitor Project

## Motivation

We want to build Options Monitor as a Streamlit dashboard that answers the following questions:

- What regime am I in?
  - Is the current regime exhausting?
- Where should I position my options?
- Is premium right for short selling vol?

## Data

All the data should be read from `~/.tickrake/data` folder on the local machine. So create something like a `DATA_DIR` env var for the dashboard. The `~/.tickrake/data` folder has the following structure. Candles are stored in the `~/.tickrake/data/history` by provider where each provider has its own folder. For candles we want to rely on the `ibkr-api` provider. Options are stored in the `~/.tickrake/data/options` by provider. We want to rely on the `schwab` provider for options. Let's also configure these paths as env vars for the dashboard app.

The candle filenames look like the below and include the ticker and the frequency.
```sh
data/history/ibkr-paper/SPX_5min.csv
```

The option filenames look like the below and include the ticker/root_symbol, expiration date, and sample data time:
```sh
data/options/schwab/SPXW_exp2026-02-05_2026-02-04_11-02-41.csv
```

The candles files have these columns:
```
datetime,open,high,low,close,volume
```

The option files have these columns
```
contract_type,symbol,description,strike,expiration_date,mark,bid,bid_size,ask,ask_size,last,last_size,open_interest,total_volume,delta,gamma,theta,vega,rho,volatility,theoretical_volatility,theoretical_option_value,intrinsic_value,extrinsic_value,underlying_price
```

Some of these files are large. So we will need to be careful about loading them into memory when we only need a subset of the rows. For example the 1 min candle files have months of data and are large.

## Panels / Tabs

The Dashboard should have 3 panels or tabs that the user can click between

1. Summary Panel
2. Regime Panel
3. Vol Panel
4. Gamma Map Panel

## Key Calculations

## Chart Descriptions

### GEX Aggregate

For the dashboard version of this chart we want to combine the GEXStrike and GEXPrice examples in the docs folder. So this new chart should include the net GEX by strike (defined as gamma x open_interest x strike^2), spot as a vertical bar, the net gex line graph, with the zero gamma line. This should all be in one chart with net gex on the y-axis and strike price on the x-axis.

Parameters:
- toggle inclusion of 0DTE on and off
- Select how many days out of options chains - so basically if 10 days out, then we need to aggregate the latest sampled option chain for the next 10 days of expirations.


### Simple Moving Averages Price Line Graph

This chart should show a fast and a slow moving average of price for a given ticker.

Parameters
- Ticker
- Frequency: day, 1min, 5min, 30min
- Range: if day, then start and end date. if a min frequency, then start datetime and end datetime
- Slow rolling window size
- Fast rolling window size. Validate that it is less than the slow rolling window size

### Simple Moving Averages Volume Line Graph

Similar to the above, but shows the volume rather than price.

Parameters
- Ticker
- Frequency: day, 1min, 5min, 30min
- Range: if day, then start and end date. if a min frequency, then start datetime and end datetime
- Slow rolling window size
- Fast rolling window size. Validate that it is less than the slow rolling window size

### GEX Single expiry

This chart is based on the GrossGEX example and it's suppose to show teh GEX for a single expiration. Instead of showing the net GEX we want to break out puts and calls and show them separately so that we can see where the main put and call walls are.

Parameters:
- Ticker
- expiration date

### IV-RV Spread Chart for SPX

We want to show the spread and the IV and the RV all on the same chart. So 3 lines. See the docs/IV_RV_Comparison.ipynb notebook for a prototype.

Parameters:
- Dropdown to select 9-day or 30-day. When 9 day is selected we want to use the VIX9D and calculate the SPX realized vol using a 9 day rolling and if 30 day then we want to use the VIX and calculate the SPX realized vol using 30 day rolling.
- frequency - day, 1min, 5min, 30min. I think we can hard code these.
- range - if day, then select start and end dates. If one of hte min frequency, then the user should be able to select start and end datetimes. I think we want to find the min and max available date and datetime from candles in the files. This might be a little tricky, but doable

### VIX-SPX Correlation

Display the VIX-SPX correlation over a certain range for a specific frequency. This isn't a chart, just a metric that we need to calculate using something like scipy or scikit or maybe pandas is also fine here. I think we want to display this above or along side the IV-RV spread chart.

Parameters
- frequency - day, 1min, 5min, 30min
- range - if day, then start and end date. if a min frequency, then start datetime and end datetime

### VIX-VIX9D-VIX1D Line Graph

This is a simple line graph just showing whether VIX and VIX9D is contango or not. So we only have min frequency data for the VIX1D, so only display this line if the frequency is one of the minute frequencies. If the frequencyt is day, then only show VIX and VIX9D

Parameters:
- frequency - day, 1min, 5min, 30min
- range - if day, then start and end date. if a min frequency, then start datetime and end datetime

### Agent Chat

Include a toggle to expand and collapse chat channel on the right hand side of the dashboard. Eventually we will build an agent into this channel that we'll feed the same data being used to populate the charts to the agent in the chat so teh user can have a discussion about how to interpret the charts with the agent.
