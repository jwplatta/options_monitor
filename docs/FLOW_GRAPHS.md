# Flow Graphs

## Overview

Graphs designed for SPXW to estimate buying and selling pressure from option trading activity.

Unlike GEX, which describes dealer positioning and market structure, Flow attempts to answer:
* Where are traders actively transacting?
* Is buying or selling pressure building?
* Which strikes and expirations are attracting activity?
* Is pressure increasing, fading, or reversing throughout the session?

Construct a transparent and interpretable measure of option flow using one-minute option chain snapshots.

## Data Requirements

SPXW Option Chain Snapshots are collected roughly every minute.

Required fields:
* timestamp
* strike
* expiration_date
* contract_type (CALL / PUT)
* bid
* ask
* last
* total_volume
* delta
* underlying_price


## Flow Calculation

For each contract and timestamp:

```
Flow = New Volume × Trade Direction × Delta × Proximity (to spot) Weight
```

```
New Volume = Current Total Volume − Previous Total Volume
```

Measures newly traded contracts during the sampling interval.

### Trade Direction

Estimated from the position of the last trade within the bid-ask spread.

Trade Position:
```
(last − bid) / (ask − bid)
```

Classification:
* 0.00 – 0.35 → Seller Initiated (-1)
* 0.36 – 0.64 → Neutral (0)
* 0.65 – 1.00 → Buyer Initiated (+1)

### Delta

Current option delta from the chain snapshot.

Calls naturally contribute positive directional exposure.

Puts naturally contribute negative directional exposure.

### Proximity Weight

Weight contracts based on distance from spot.

Purpose:
* Emphasize ATM and near-ATM contracts.
* De-emphasize far OTM contracts that are unlikely to influence intraday dealer hedging.

Initial implementation may use:

Weight = 1 / (1 + DistanceFromSpot%)

## User Controls


- Toggle for
  * New Flow - delta between volumen in current snapshot and the previous snapshot
  * Cumulative Flow - total for the sample date

Defaults
* 0DTE when available - today's option or the latest
* Otherwise nearest expiration

Select the latest point during the trading session.

Used for:
* Historical replay
* Intraday inspection


- Contract Filter

Options:
* Calls
* Puts
* Both

## Visualization 1: Flow Tape

## Flow Tape

The Flow Tape is a time-series visualization designed to estimate whether traders are increasingly buying calls or buying puts throughout the trading session.

The indicator focuses on:
- All OTM options
- The 25 ITM strikes closest to spot

This captures the portion of the chain most likely to reflect active speculative positioning and dealer hedging activity while excluding deep ITM and deep OTM contracts that tend to contribute noise.

## Parameters
- lookback_window (EMA(trade_position) and volume diff)
- option chain expiry
- sample date

### Trade Position

For each option contract and timestamp:

$$
\text{Trade Position} = \frac{\text{Last} - \text{Bid}} {\text{Ask} - \text{Bid}}
$$

Trade Position ranges from:
- 0.0 = traded at the bid
- 0.5 = traded at the midpoint
- 1.0 = traded at the ask

To reduce noise from individual prints, a rolling exponential moving average is calculated separately for each contract:

$$
\text{EMA}{lookback_window}(\text{Trade Position})
$$

where the EMA uses the previous 20 samples from the same sample date only. Since option chain snapshots are collected approximately once per minute, this corresponds to approximately 20 minutes of trading activity.

The EMA is then transformed into a continuous trade direction score:

$$
\text{Trade Direction}
=
(\text{EMA}{20}(\text{Trade Position}) - 0.5) \times 2
$$

This produces values in the range:

$$
[-1, 1]
$$

where:

- -1 = persistent seller-initiated activity
- 0 = neutral activity
- +1 = persistent buyer-initiated activity

### New Volume

For each contract:

$$
\text{New Volume} = \text{Volume}{t} - \text{Volume}{t-lookback_window}
$$

representing newly traded contracts during the current sampling interval.

### Call Buying Pressure

For call options:

$$
\text{Call Flow} = \text{New Volume} \times \text{Trade Direction} \times |\Delta|
$$

Call Flow is aggregated across all selected call contracts for each timestamp.

### Put Buying Pressure

For put options:

$$
\text{Put Flow} = \text{New Volume} \times \text{Trade Direction} \times |\Delta|
$$

Put Flow is aggregated across all selected put contracts for each timestamp.

### Visualization

The chart displays two cumulative lines throughout the trading session:

- Call Flow
- Put Flow

Interpretation:

- Rising Call Line = increasing call buying activity
- Falling Call Line = increasing call selling activity
- Rising Put Line = increasing put buying activity
- Falling Put Line = increasing put selling activity

The goal of the Flow Tape is to identify sustained shifts in option market activity before those flows are fully reflected in SPX price action.

## Visualization 2: **Flow** Profile

The Flow Profile is a strike-level bar chart designed to show where option traders are actively buying and selling throughout the option chain.

Unlike the Flow Tape, which measures how pressure evolves through time, the Flow Profile provides a snapshot of where that activity is currently concentrated.

### Chart Type

Bar Chart

### X-Axis

Strike Price

Each bar represents the aggregated flow at a specific strike for the selected expiration.

### Y-Axis

Flow

Flow represents estimated trader activity weighted by option delta and trade aggressiveness. Positive values indicate buying activity.

Negative values indicate selling activity. Calls and puts are displayed as separate bar series.

## Inputs

### Sample Date

The trading session to analyze.

All calculations and rolling statistics are restricted to data from the selected trading date.

### Expiration Date

Selected SPXW expiration.

All calculations are performed using contracts from the chosen expiration only.

### Volume Lookback Window

Number of minutes used to calculate new volume.

Examples:

- 1 minute
- 5 minutes
- 15 minutes
- 30 minutes

### Mode

#### Lookback Flow

Displays flow generated during the selected lookback window.

#### Cumulative Flow

Displays total flow accumulated since market open.

## Trade Position

For each contract:

$$
\text{Trade Position} = \frac{\text{Last} - \text{Bid}} {\text{Ask} - \text{Bid}}
$$

Trade Position ranges from:

- 0.0 = traded at bid
- 0.5 = traded at midpoint
- 1.0 = traded at ask

To reduce noise from individual prints, a volume-weighted exponential moving average is calculated separately for each contract:

$$
\text{VWEMA}{20}(\text{Trade Position})
$$

The calculation uses only observations from the selected sample date.

The resulting trade direction score is:

$$
\text{Trade Direction} = (\text{VWEMA}{20}(\text{Trade Position}) - 0.5) \times 2
$$

Trade Direction ranges from:

$$
[-1,1]
$$

where:

- -1 = persistent seller-initiated activity
- 0 = neutral activity
- +1 = persistent buyer-initiated activity

## New Volume

For Lookback Flow mode:

$$
\text{New Volume} = \text{Volume}{t} - \text{Volume}{t-L}
$$

where:

- (t) = current timestamp
- (L) = selected lookback window

For Cumulative Flow mode:

$$
\text{New Volume} = \text{Volume}{t}
$$

since option volume is already cumulative throughout the trading day.

## Call Flow

For call options:

$$
\text{Call Flow} = \text{New Volume} \times \text{Trade Direction} \times |\Delta| \times 100
$$

The multiplier of 100 converts contracts into delta-equivalent share exposure.

## Put Flow

For put options:

$$
\text{Put Flow} = \text{New Volume} \times \text{Trade Direction} \times |\Delta| \times 100
$$

The same calculation is used for puts to preserve intuitive interpretation.

## Strike Aggregation

Flow is aggregated by strike:

$$
\text{Strike Flow} = \sum \text{Flow}{contracts\ at\ strike}
$$

Separate values are maintained for calls and puts.

## Interpretation

### Calls

Positive Call Flow
- Call buying activity

Negative Call Flow
- Call selling activity

### Puts

Positive Put Flow
- Put buying activity

Negative Put Flow
- Put selling activity

### Examples

Large positive call flow at 6100
- Traders are actively buying calls at 6100

Large positive put flow at 6000
- Traders are actively buying puts at 6000

Large negative put flow at 5950
- Traders are actively selling puts at 5950

The Flow Profile is intended to answer:
> Where are option traders actively transacting right now?

and can be used alongside GEX to compare trader activity with dealer positioning.