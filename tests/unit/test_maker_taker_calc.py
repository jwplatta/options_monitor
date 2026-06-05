"""Unit tests for calc/maker_taker.py."""

from __future__ import annotations

import csv
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from trade_dash.calc.maker_taker import compute_maker_taker_flow

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_COLS = [
    "contract_type",
    "symbol",
    "description",
    "strike",
    "expiration_date",
    "mark",
    "bid",
    "bid_size",
    "ask",
    "ask_size",
    "last",
    "last_size",
    "open_interest",
    "total_volume",
    "delta",
    "gamma",
    "theta",
    "vega",
    "rho",
    "volatility",
    "theoretical_volatility",
    "theoretical_option_value",
    "intrinsic_value",
    "extrinsic_value",
    "underlying_price",
]


def _write_snapshot(
    path: Path,
    rows: list[dict],
    underlying_price: float = 5000.0,
) -> None:
    """Write a minimal options snapshot CSV."""
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_BASE_COLS)
        writer.writeheader()
        for row in rows:
            full_row = {col: "" for col in _BASE_COLS}
            full_row["underlying_price"] = str(underlying_price)
            full_row["expiration_date"] = "2026-04-30"
            full_row["symbol"] = "SPXW"
            full_row["open_interest"] = "100"
            full_row["total_volume"] = row.get("total_volume", "500")
            full_row.update({k: str(v) for k, v in row.items()})
            writer.writerow(full_row)


def _make_snapshot(
    directory: Path,
    fetch_dt: datetime,
    rows: list[dict],
    underlying_price: float = 5000.0,
) -> tuple[datetime, Path]:
    ts_str = fetch_dt.strftime("%Y-%m-%d_%H-%M-%S")
    path = directory / f"SPXW_exp2026-04-30_{ts_str}.csv"
    _write_snapshot(path, rows, underlying_price=underlying_price)
    return fetch_dt, path


# ---------------------------------------------------------------------------
# Test: empty input
# ---------------------------------------------------------------------------


def test_returns_empty_on_no_snapshots() -> None:
    result = compute_maker_taker_flow([], spot=5000.0)
    assert result == ([], [], [], [], [])


# ---------------------------------------------------------------------------
# Test: target_date filtering
# ---------------------------------------------------------------------------


def test_returns_empty_when_no_snapshots_on_target_date(tmp_path: Path) -> None:
    ts = datetime(2026, 4, 27, 14, 0, 0)
    snap = _make_snapshot(
        tmp_path,
        ts,
        [{"contract_type": "CALL", "strike": "5000", "bid": "10", "ask": "12", "last": "11.5", "last_size": "5"}],
    )
    result = compute_maker_taker_flow([snap], spot=5000.0, target_date=date(2026, 4, 28))
    assert result == ([], [], [], [], [])


def test_target_date_filter_uses_chicago_local_date_for_utc_snapshots(tmp_path: Path) -> None:
    prior_local_evening = _make_snapshot(
        tmp_path,
        datetime(2026, 6, 5, 0, 30, 0, tzinfo=UTC),
        [{"contract_type": "CALL", "strike": "5000", "bid": "10", "ask": "12", "last": "11.5", "last_size": "5"}],
    )
    target_local_morning = _make_snapshot(
        tmp_path,
        datetime(2026, 6, 5, 14, 30, 0, tzinfo=UTC),
        [{"contract_type": "CALL", "strike": "5025", "bid": "10", "ask": "12", "last": "11.5", "last_size": "7"}],
    )

    timestamps, strikes, flows, bucket_times, bucket_prices = compute_maker_taker_flow(
        [prior_local_evening, target_local_morning],
        spot=5000.0,
        target_date=date(2026, 6, 5),
    )

    assert len(timestamps) == 1
    assert len(strikes) == 1
    assert len(flows) == 1
    assert strikes == [5025.0]
    assert bucket_times[0].date() == date(2026, 6, 5)
    assert bucket_prices == [5000.0]


def test_target_date_filter_treats_naive_snapshot_datetimes_as_utc(tmp_path: Path) -> None:
    prior_local_evening = _make_snapshot(
        tmp_path,
        datetime(2026, 6, 5, 0, 30, 0),
        [{"contract_type": "CALL", "strike": "5000", "bid": "10", "ask": "12", "last": "11.5", "last_size": "5"}],
    )
    target_local_morning = _make_snapshot(
        tmp_path,
        datetime(2026, 6, 5, 14, 30, 0),
        [{"contract_type": "CALL", "strike": "5025", "bid": "10", "ask": "12", "last": "11.5", "last_size": "7"}],
    )

    timestamps, strikes, flows, bucket_times, bucket_prices = compute_maker_taker_flow(
        [prior_local_evening, target_local_morning],
        spot=5000.0,
        target_date=date(2026, 6, 5),
    )

    assert len(timestamps) == 1
    assert len(strikes) == 1
    assert len(flows) == 1
    assert strikes == [5025.0]
    assert bucket_times[0].date() == date(2026, 6, 5)
    assert bucket_prices == [5000.0]


# ---------------------------------------------------------------------------
# Test: bucket selection — LAST snapshot wins
# ---------------------------------------------------------------------------


def test_last_snapshot_selected_per_bucket(tmp_path: Path) -> None:
    """Two snapshots in the same 5-minute bucket — the last one's price is used."""
    snap1 = _make_snapshot(
        tmp_path,
        datetime(2026, 4, 28, 14, 1, 0),
        [{"contract_type": "CALL", "strike": "5000", "bid": "10", "ask": "12", "last": "11.5", "last_size": "10"}],
        underlying_price=4990.0,
    )
    snap2 = _make_snapshot(
        tmp_path,
        datetime(2026, 4, 28, 14, 4, 0),
        [{"contract_type": "CALL", "strike": "5000", "bid": "10", "ask": "12", "last": "11.5", "last_size": "10"}],
        underlying_price=5010.0,
    )
    _, _, _, _, bucket_prices = compute_maker_taker_flow(
        [snap1, snap2],
        spot=5000.0,
        bucket_minutes=5,
        target_date=date(2026, 4, 28),
    )
    # Only one bucket; underlying_price should be from snap2 (last in bucket)
    assert len(bucket_prices) == 1
    assert bucket_prices[0] == pytest.approx(5010.0)


# ---------------------------------------------------------------------------
# Test: hybrid sign direction
# ---------------------------------------------------------------------------


def test_sentiment_positive_when_last_near_ask(tmp_path: Path) -> None:
    """Quote-side rule: last near ask should sign the flow positive."""
    snap = _make_snapshot(
        tmp_path,
        datetime(2026, 4, 28, 14, 0, 0),
        [{"contract_type": "CALL", "strike": "5000", "bid": "10", "ask": "12", "last": "11.95", "last_size": "5"}],
    )
    _, _, flows, _, _ = compute_maker_taker_flow(
        [snap], spot=5000.0, target_date=date(2026, 4, 28)
    )
    assert len(flows) == 1
    assert flows[0] > 0


def test_sentiment_negative_when_last_near_bid(tmp_path: Path) -> None:
    """Quote-side rule: last near bid should sign the flow negative."""
    snap = _make_snapshot(
        tmp_path,
        datetime(2026, 4, 28, 14, 0, 0),
        [{"contract_type": "CALL", "strike": "5000", "bid": "10", "ask": "12", "last": "10.05", "last_size": "5"}],
    )
    _, _, flows, _, _ = compute_maker_taker_flow(
        [snap], spot=5000.0, target_date=date(2026, 4, 28)
    )
    assert len(flows) == 1
    assert flows[0] < 0


def test_sentiment_falls_back_to_tick_rule_inside_spread(tmp_path: Path) -> None:
    """Inside the spread, sign should fall back to the prior sampled last price."""
    snap1 = _make_snapshot(
        tmp_path,
        datetime(2026, 4, 28, 14, 0, 0),
        [{"contract_type": "CALL", "strike": "5000", "bid": "10", "ask": "12", "last": "11.0", "last_size": "5"}],
    )
    snap2 = _make_snapshot(
        tmp_path,
        datetime(2026, 4, 28, 14, 5, 0),
        [{"contract_type": "CALL", "strike": "5000", "bid": "10", "ask": "12", "last": "11.4", "last_size": "5"}],
    )
    _, _, flows, _, _ = compute_maker_taker_flow(
        [snap1, snap2], spot=5000.0, target_date=date(2026, 4, 28)
    )
    assert flows == pytest.approx([0.0, 5.0])


def test_sentiment_zero_when_inside_spread_without_prior_tick(tmp_path: Path) -> None:
    """Inside the spread with no prior sample should remain neutral."""
    snap = _make_snapshot(
        tmp_path,
        datetime(2026, 4, 28, 14, 0, 0),
        [{"contract_type": "CALL", "strike": "5000", "bid": "10", "ask": "12", "last": "11.0", "last_size": "5"}],
    )
    _, _, flows, _, _ = compute_maker_taker_flow(
        [snap], spot=5000.0, target_date=date(2026, 4, 28)
    )
    assert len(flows) == 1
    assert flows[0] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Test: moneyness filter
# ---------------------------------------------------------------------------


def test_moneyness_filter_excludes_far_strikes(tmp_path: Path) -> None:
    """Strike 20% from spot should be excluded when moneyness_pct=0.10."""
    far_strike = 5000.0 * 1.25  # 25% OTM
    snap = _make_snapshot(
        tmp_path,
        datetime(2026, 4, 28, 14, 0, 0),
        [{"contract_type": "CALL", "strike": str(far_strike), "bid": "1", "ask": "2", "last": "1.8", "last_size": "5"}],
    )
    result = compute_maker_taker_flow(
        [snap], spot=5000.0, moneyness_pct=0.10, target_date=date(2026, 4, 28)
    )
    assert result == ([], [], [], [], [])


# ---------------------------------------------------------------------------
# Test: contract type filter
# ---------------------------------------------------------------------------


def test_contract_type_filter_excludes_wrong_type(tmp_path: Path) -> None:
    """Only CALL rows should appear when contract_filter='CALL'."""
    snap = _make_snapshot(
        tmp_path,
        datetime(2026, 4, 28, 14, 0, 0),
        [
            {"contract_type": "PUT", "strike": "5000", "bid": "10", "ask": "12", "last": "11.5", "last_size": "5"},
        ],
    )
    result = compute_maker_taker_flow(
        [snap], spot=5000.0, contract_filter="CALL", target_date=date(2026, 4, 28)
    )
    assert result == ([], [], [], [], [])


def test_contract_type_filter_case_insensitive(tmp_path: Path) -> None:
    """Passing lowercase 'call' should not raise and should match CALL rows."""
    snap = _make_snapshot(
        tmp_path,
        datetime(2026, 4, 28, 14, 0, 0),
        [{"contract_type": "CALL", "strike": "5000", "bid": "10", "ask": "12", "last": "11.5", "last_size": "5"}],
    )
    _, _, flows, _, _ = compute_maker_taker_flow(
        [snap], spot=5000.0, contract_filter="call", target_date=date(2026, 4, 28)
    )
    assert len(flows) == 1


# ---------------------------------------------------------------------------
# Test: top-N strikes filter
# ---------------------------------------------------------------------------


def test_top_n_strikes_limits_output(tmp_path: Path) -> None:
    """With 10 strikes and top_n_strikes=3, only 3 unique strikes appear."""
    rows = []
    for i in range(10):
        strike = 4900.0 + i * 25
        # Assign increasing last_size so we can predict which 3 are top
        rows.append({
            "contract_type": "CALL",
            "strike": str(strike),
            "bid": "10",
            "ask": "12",
            "last": "11.95",
            "last_size": str((i + 1) * 10),
        })
    snap = _make_snapshot(tmp_path, datetime(2026, 4, 28, 14, 0, 0), rows)
    _, strikes_out, _, _, _ = compute_maker_taker_flow(
        [snap], spot=5100.0, moneyness_pct=0.20, top_n_strikes=3, target_date=date(2026, 4, 28)
    )
    assert len(set(strikes_out)) == 3
    # The top 3 by abs flow should be the highest last_size strikes
    assert max(strikes_out) == pytest.approx(4900.0 + 9 * 25)  # strike with last_size=100


# ---------------------------------------------------------------------------
# Test: weight_by parameter
# ---------------------------------------------------------------------------


def test_weight_by_total_volume_uses_bucket_delta(tmp_path: Path) -> None:
    """weight_by='total_volume' should use bucket-over-bucket cumulative volume delta."""
    snap1 = _make_snapshot(
        tmp_path,
        datetime(2026, 4, 28, 14, 0, 0),
        [{"contract_type": "CALL", "strike": "5000", "bid": "10", "ask": "12", "last": "11.95",
          "last_size": "1", "total_volume": "200"}],
    )
    snap2 = _make_snapshot(
        tmp_path,
        datetime(2026, 4, 28, 14, 5, 0),
        [{"contract_type": "CALL", "strike": "5000", "bid": "10", "ask": "12", "last": "11.95",
          "last_size": "1", "total_volume": "260"}],
    )
    _, _, flows_ls, _, _ = compute_maker_taker_flow(
        [snap1, snap2], spot=5000.0, weight_by="last_size", target_date=date(2026, 4, 28)
    )
    _, _, flows_tv, _, _ = compute_maker_taker_flow(
        [snap1, snap2], spot=5000.0, weight_by="total_volume", target_date=date(2026, 4, 28)
    )
    assert flows_ls == pytest.approx([1.0, 1.0])
    assert flows_tv == pytest.approx([0.0, 60.0])


def test_total_volume_uses_last_snapshot_in_bucket_for_delta(tmp_path: Path) -> None:
    """The volume delta should use the last chain sample from each time bucket."""
    snap1 = _make_snapshot(
        tmp_path,
        datetime(2026, 4, 28, 14, 1, 0),
        [{"contract_type": "CALL", "strike": "5000", "bid": "10", "ask": "12", "last": "11.95",
          "last_size": "1", "total_volume": "100"}],
    )
    snap2 = _make_snapshot(
        tmp_path,
        datetime(2026, 4, 28, 14, 4, 0),
        [{"contract_type": "CALL", "strike": "5000", "bid": "10", "ask": "12", "last": "11.95",
          "last_size": "1", "total_volume": "120"}],
    )
    snap3 = _make_snapshot(
        tmp_path,
        datetime(2026, 4, 28, 14, 6, 0),
        [{"contract_type": "CALL", "strike": "5000", "bid": "10", "ask": "12", "last": "11.95",
          "last_size": "1", "total_volume": "150"}],
    )
    _, _, flows, _, _ = compute_maker_taker_flow(
        [snap1, snap2, snap3],
        spot=5000.0,
        weight_by="total_volume",
        bucket_minutes=5,
        target_date=date(2026, 4, 28),
    )
    assert flows == pytest.approx([0.0, 30.0])


# ---------------------------------------------------------------------------
# Test: missing last column
# ---------------------------------------------------------------------------


def test_missing_last_column_returns_empty(tmp_path: Path) -> None:
    """CSV without 'last' column → all NaN after coerce → empty result."""
    path = tmp_path / "SPXW_exp2026-04-30_2026-04-28_14-00-00.csv"
    cols_no_last = [c for c in _BASE_COLS if c != "last"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols_no_last)
        writer.writeheader()
        writer.writerow({
            "contract_type": "CALL", "strike": "5000", "bid": "10", "ask": "12",
            "last_size": "5", "total_volume": "500", "underlying_price": "5000",
            "expiration_date": "2026-04-30", "symbol": "SPXW", "open_interest": "100",
            **{c: "" for c in cols_no_last if c not in ("contract_type", "strike", "bid", "ask", "last_size", "total_volume", "underlying_price", "expiration_date", "symbol", "open_interest")},
        })
    snap = (datetime(2026, 4, 28, 14, 0, 0), path)
    result = compute_maker_taker_flow([snap], spot=5000.0, target_date=date(2026, 4, 28))
    assert result == ([], [], [], [], [])


# ---------------------------------------------------------------------------
# Test: return array length consistency
# ---------------------------------------------------------------------------


def test_return_array_lengths_consistent(tmp_path: Path) -> None:
    """timestamps, strikes, weighted_flows must all have the same length."""
    rows = [
        {"contract_type": "CALL", "strike": "4950", "bid": "10", "ask": "12", "last": "11.5", "last_size": "5"},
        {"contract_type": "CALL", "strike": "5000", "bid": "10", "ask": "12", "last": "10.5", "last_size": "3"},
        {"contract_type": "CALL", "strike": "5050", "bid": "10", "ask": "12", "last": "11.0", "last_size": "7"},
    ]
    snap = _make_snapshot(tmp_path, datetime(2026, 4, 28, 14, 0, 0), rows)
    timestamps, strikes, flows, bucket_times, bucket_prices = compute_maker_taker_flow(
        [snap], spot=5000.0, target_date=date(2026, 4, 28)
    )
    assert len(timestamps) == len(strikes) == len(flows)
    assert len(bucket_times) == len(bucket_prices)
