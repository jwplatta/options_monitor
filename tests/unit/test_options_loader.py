"""Tests for the options snapshot loader."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest
from options_monitor.data.options import (
    _parse_filename,
    find_all_snapshots_for_expiry,
    find_historical_snapshot_times,
    find_latest_snapshots,
    find_snapshots_for_expiry_on_date,
    list_expirations,
    list_expirations_for_window_on_date,
    list_snapshot_dates,
    list_snapshot_dates_for_expiry,
    load_historical_expiry,
    load_historical_expiry_lookback,
    load_historical_lookback,
    load_historical_snapshot,
    load_options_snapshot,
    parquet_path_for_date,
)


@pytest.fixture(autouse=True)
def clear_streamlit_caches() -> None:
    list_expirations.clear()
    list_snapshot_dates.clear()
    list_snapshot_dates_for_expiry.clear()
    list_expirations_for_window_on_date.clear()
    find_latest_snapshots.clear()
    find_all_snapshots_for_expiry.clear()
    find_snapshots_for_expiry_on_date.clear()
    load_options_snapshot.clear()
    find_historical_snapshot_times.clear()
    load_historical_snapshot.clear()
    load_historical_expiry.clear()
    load_historical_lookback.clear()
    load_historical_expiry_lookback.clear()


def _create_metadata_db(path: Path, with_table: bool = True) -> Path:
    conn = sqlite3.connect(path)
    if with_table:
        conn.execute(
            """
            CREATE TABLE file_metadata_cache (
              path TEXT PRIMARY KEY,
              dataset_type TEXT NOT NULL,
              provider_name TEXT NOT NULL,
              ticker TEXT NOT NULL,
              frequency TEXT,
              row_count INTEGER NOT NULL,
              first_observed_at TEXT,
              last_observed_at TEXT,
              file_mtime INTEGER NOT NULL,
              file_size INTEGER NOT NULL,
              updated_at TEXT NOT NULL,
              expiration_date TEXT
            )
            """
        )
    conn.commit()
    conn.close()
    return path


def _insert_metadata_row(
    db_path: Path,
    *,
    csv_path: Path,
    ticker: str = "SPXW",
    expiration_date: str,
    last_observed_at: str,
    dataset_type: str = "options",
    provider_name: str = "schwab",
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO file_metadata_cache (
            path,
            dataset_type,
            provider_name,
            ticker,
            frequency,
            row_count,
            first_observed_at,
            last_observed_at,
            file_mtime,
            file_size,
            updated_at,
            expiration_date
        )
        VALUES (?, ?, ?, ?, NULL, 1, ?, ?, 0, 0, ?, ?)
        """,
        (
            str(csv_path),
            dataset_type,
            provider_name,
            ticker,
            last_observed_at,
            last_observed_at,
            last_observed_at,
            expiration_date,
        ),
    )
    conn.commit()
    conn.close()


def _write_snapshot_csv(path: Path, underlying_price: float = 5200.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        [
            {
                "contract_type": "CALL",
                "symbol": "SPXW",
                "strike": 5200.0,
                "expiration_date": "2026-04-18",
                "mark": 10.0,
                "bid": 9.5,
                "ask": 10.5,
                "last": 10.0,
                "last_size": 1.0,
                "open_interest": 100.0,
                "total_volume": 50.0,
                "delta": 0.5,
                "gamma": 0.01,
                "theta": -0.1,
                "vega": 0.2,
                "theoretical_volatility": 0.2,
                "underlying_price": underlying_price,
            }
        ]
    )
    df.to_csv(path, index=False)
    return path


def test_parse_filename_valid(tmp_path: Path) -> None:
    path = tmp_path / "SPXW_exp2026-04-15_2026-04-15_13-30-00.csv"
    path.touch()
    result = _parse_filename(path)
    assert result is not None
    exp_date, fetch_dt = result
    assert exp_date == date(2026, 4, 15)
    assert fetch_dt == datetime(2026, 4, 15, 13, 30, 0)


def test_parse_filename_too_few_parts(tmp_path: Path) -> None:
    path = tmp_path / "SPXW_exp2026-04-15.csv"
    path.touch()
    assert _parse_filename(path) is None


def test_parse_filename_bad_date(tmp_path: Path) -> None:
    path = tmp_path / "SPXW_exp9999-99-99_2026-04-15_13-30-00.csv"
    path.touch()
    assert _parse_filename(path) is None


def test_list_expirations_deduplicated_and_sorted(tmp_path: Path) -> None:
    db_path = _create_metadata_db(tmp_path / "tickrake.sqlite3")
    first = _write_snapshot_csv(tmp_path / "a.csv")
    second = _write_snapshot_csv(tmp_path / "b.csv")
    third = _write_snapshot_csv(tmp_path / "c.csv")

    _insert_metadata_row(
        db_path,
        csv_path=first,
        expiration_date="2026-04-17",
        last_observed_at="2026-04-15T09:00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=second,
        expiration_date="2026-04-15",
        last_observed_at="2026-04-15T10:00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=third,
        expiration_date="2026-04-17",
        last_observed_at="2026-04-15T12:00:00",
    )

    expirations = list_expirations("SPXW", metadata_db_path=db_path)
    assert expirations == [date(2026, 4, 15), date(2026, 4, 17)]


def test_find_latest_snapshots_picks_most_recent_and_tiebreaks_by_path(tmp_path: Path) -> None:
    db_path = _create_metadata_db(tmp_path / "tickrake.sqlite3")
    older = _write_snapshot_csv(tmp_path / "older.csv")
    tied_low = _write_snapshot_csv(tmp_path / "a.csv")
    tied_high = _write_snapshot_csv(tmp_path / "z.csv")

    _insert_metadata_row(
        db_path,
        csv_path=older,
        expiration_date="2026-04-18",
        last_observed_at="2026-04-15T09:00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=tied_low,
        expiration_date="2026-04-18",
        last_observed_at="2026-04-15T12:00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=tied_high,
        expiration_date="2026-04-18",
        last_observed_at="2026-04-15T12:00:00",
    )

    snapshots = find_latest_snapshots(
        "SPXW",
        start_date=date(2026, 4, 18),
        days_out=0,
        include_0dte=True,
        metadata_db_path=db_path,
    )
    assert snapshots == {date(2026, 4, 18): tied_high}


def test_find_latest_snapshots_returns_one_path_per_expiry_in_window(tmp_path: Path) -> None:
    db_path = _create_metadata_db(tmp_path / "tickrake.sqlite3")
    exp_15 = _write_snapshot_csv(tmp_path / "15.csv")
    exp_16_old = _write_snapshot_csv(tmp_path / "16_old.csv")
    exp_16_new = _write_snapshot_csv(tmp_path / "16_new.csv")
    outside = _write_snapshot_csv(tmp_path / "outside.csv")

    _insert_metadata_row(
        db_path,
        csv_path=exp_15,
        expiration_date="2026-04-15",
        last_observed_at="2026-04-15T10:00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=exp_16_old,
        expiration_date="2026-04-16",
        last_observed_at="2026-04-15T09:00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=exp_16_new,
        expiration_date="2026-04-16",
        last_observed_at="2026-04-15T11:00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=outside,
        expiration_date="2026-04-20",
        last_observed_at="2026-04-15T12:00:00",
    )

    snapshots = find_latest_snapshots(
        "SPXW",
        start_date=date(2026, 4, 15),
        days_out=1,
        include_0dte=True,
        metadata_db_path=db_path,
    )
    assert snapshots == {
        date(2026, 4, 15): exp_15,
        date(2026, 4, 16): exp_16_new,
    }


def test_find_latest_snapshots_respects_include_0dte(tmp_path: Path) -> None:
    db_path = _create_metadata_db(tmp_path / "tickrake.sqlite3")
    zero_dte = _write_snapshot_csv(tmp_path / "0dte.csv")
    future = _write_snapshot_csv(tmp_path / "future.csv")

    _insert_metadata_row(
        db_path,
        csv_path=zero_dte,
        expiration_date="2026-04-15",
        last_observed_at="2026-04-15T09:00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=future,
        expiration_date="2026-04-16",
        last_observed_at="2026-04-15T09:05:00",
    )

    without_0dte = find_latest_snapshots(
        "SPXW",
        start_date=date(2026, 4, 15),
        days_out=2,
        include_0dte=False,
        metadata_db_path=db_path,
    )
    with_0dte = find_latest_snapshots(
        "SPXW",
        start_date=date(2026, 4, 15),
        days_out=2,
        include_0dte=True,
        metadata_db_path=db_path,
    )

    assert date(2026, 4, 15) not in without_0dte
    assert with_0dte[date(2026, 4, 15)] == zero_dte
    assert with_0dte[date(2026, 4, 16)] == future


def test_find_all_snapshots_for_expiry_returns_all_rows_ordered_by_time(tmp_path: Path) -> None:
    db_path = _create_metadata_db(tmp_path / "tickrake.sqlite3")
    first = _write_snapshot_csv(tmp_path / "first.csv")
    second = _write_snapshot_csv(tmp_path / "second.csv")
    third = _write_snapshot_csv(tmp_path / "third.csv")
    other = _write_snapshot_csv(tmp_path / "other.csv")

    _insert_metadata_row(
        db_path,
        csv_path=first,
        expiration_date="2026-04-18",
        last_observed_at="2026-04-14T09:00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=second,
        expiration_date="2026-04-18",
        last_observed_at="2026-04-14T12:00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=third,
        expiration_date="2026-04-18",
        last_observed_at="2026-04-15T10:00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=other,
        ticker="QQQ",
        expiration_date="2026-04-18",
        last_observed_at="2026-04-15T11:00:00",
    )

    snapshots = find_all_snapshots_for_expiry(
        "SPXW",
        expiry=date(2026, 4, 18),
        metadata_db_path=db_path,
    )
    assert snapshots == [
        (datetime(2026, 4, 14, 9, 0, 0), first),
        (datetime(2026, 4, 14, 12, 0, 0), second),
        (datetime(2026, 4, 15, 10, 0, 0), third),
    ]


def test_list_snapshot_dates_for_expiry_returns_distinct_sorted_dates(tmp_path: Path) -> None:
    db_path = _create_metadata_db(tmp_path / "tickrake.sqlite3")
    first = _write_snapshot_csv(tmp_path / "first.csv")
    second = _write_snapshot_csv(tmp_path / "second.csv")
    other_exp = _write_snapshot_csv(tmp_path / "other_exp.csv")

    _insert_metadata_row(
        db_path,
        csv_path=first,
        expiration_date="2026-04-18",
        last_observed_at="2026-04-14T09:00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=second,
        expiration_date="2026-04-18",
        last_observed_at="2026-04-15T12:00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=other_exp,
        expiration_date="2026-04-19",
        last_observed_at="2026-04-16T12:00:00",
    )

    sample_dates = list_snapshot_dates_for_expiry(
        "SPXW",
        expiry=date(2026, 4, 18),
        metadata_db_path=db_path,
    )
    assert sample_dates == [date(2026, 4, 14), date(2026, 4, 15)]


def test_list_snapshot_dates_returns_symbol_wide_distinct_sorted_dates(tmp_path: Path) -> None:
    db_path = _create_metadata_db(tmp_path / "tickrake.sqlite3")
    first = _write_snapshot_csv(tmp_path / "SPXW_exp2026-04-18_2026-04-14_09-00-00.csv")
    second = _write_snapshot_csv(tmp_path / "SPXW_exp2026-04-19_2026-04-15_12-00-00.csv")

    _insert_metadata_row(
        db_path,
        csv_path=first,
        expiration_date="2026-04-18",
        last_observed_at="2026-04-14T09:00:00+00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=second,
        expiration_date="2026-04-19",
        last_observed_at="2026-04-15T12:00:00+00:00",
    )

    sample_dates = list_snapshot_dates("SPXW", metadata_db_path=db_path)
    assert sample_dates == [date(2026, 4, 14), date(2026, 4, 15)]


def test_list_snapshot_dates_for_expiry_uses_chicago_market_date(tmp_path: Path) -> None:
    db_path = _create_metadata_db(tmp_path / "tickrake.sqlite3")
    prev_evening = _write_snapshot_csv(tmp_path / "SPXW_exp2026-06-05_2026-06-03_01-00-43.csv")
    market_open = _write_snapshot_csv(tmp_path / "SPXW_exp2026-06-05_2026-06-03_13-30-00.csv")

    _insert_metadata_row(
        db_path,
        csv_path=prev_evening,
        expiration_date="2026-06-05",
        last_observed_at="2026-06-03T00:00:43+00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=market_open,
        expiration_date="2026-06-05",
        last_observed_at="2026-06-03T13:30:00+00:00",
    )

    sample_dates = list_snapshot_dates_for_expiry(
        "SPXW",
        expiry=date(2026, 6, 5),
        metadata_db_path=db_path,
    )
    assert sample_dates == [date(2026, 6, 2), date(2026, 6, 3)]


def test_find_snapshots_for_expiry_on_date_filters_and_orders_rows(tmp_path: Path) -> None:
    db_path = _create_metadata_db(tmp_path / "tickrake.sqlite3")
    first = _write_snapshot_csv(tmp_path / "first.csv")
    second = _write_snapshot_csv(tmp_path / "second.csv")
    next_day = _write_snapshot_csv(tmp_path / "next_day.csv")
    other_symbol = _write_snapshot_csv(tmp_path / "other_symbol.csv")

    _insert_metadata_row(
        db_path,
        csv_path=second,
        expiration_date="2026-04-18",
        last_observed_at="2026-04-15T12:00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=first,
        expiration_date="2026-04-18",
        last_observed_at="2026-04-15T09:00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=next_day,
        expiration_date="2026-04-18",
        last_observed_at="2026-04-16T10:00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=other_symbol,
        ticker="SPX",
        expiration_date="2026-04-18",
        last_observed_at="2026-04-15T11:00:00",
    )

    snapshots = find_snapshots_for_expiry_on_date(
        "SPXW",
        expiry=date(2026, 4, 18),
        sample_date=date(2026, 4, 15),
        metadata_db_path=db_path,
    )
    assert snapshots == [
        (datetime(2026, 4, 15, 9, 0, 0), first),
        (datetime(2026, 4, 15, 12, 0, 0), second),
    ]


def test_find_snapshots_for_expiry_on_date_uses_chicago_market_date(tmp_path: Path) -> None:
    db_path = _create_metadata_db(tmp_path / "tickrake.sqlite3")
    prev_evening = _write_snapshot_csv(tmp_path / "SPXW_exp2026-06-05_2026-06-03_01-00-43.csv")
    market_open = _write_snapshot_csv(tmp_path / "SPXW_exp2026-06-05_2026-06-03_13-30-00.csv")
    market_midday = _write_snapshot_csv(tmp_path / "SPXW_exp2026-06-05_2026-06-03_18-00-00.csv")

    _insert_metadata_row(
        db_path,
        csv_path=prev_evening,
        expiration_date="2026-06-05",
        last_observed_at="2026-06-03T00:00:43+00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=market_open,
        expiration_date="2026-06-05",
        last_observed_at="2026-06-03T13:30:00+00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=market_midday,
        expiration_date="2026-06-05",
        last_observed_at="2026-06-03T18:00:00+00:00",
    )

    snapshots = find_snapshots_for_expiry_on_date(
        "SPXW",
        expiry=date(2026, 6, 5),
        sample_date=date(2026, 6, 3),
        metadata_db_path=db_path,
    )
    assert snapshots == [
        (datetime.fromisoformat("2026-06-03T13:30:00+00:00"), market_open),
        (datetime.fromisoformat("2026-06-03T18:00:00+00:00"), market_midday),
    ]


def test_list_expirations_for_window_on_date_anchors_to_sample_date(tmp_path: Path) -> None:
    db_path = _create_metadata_db(tmp_path / "tickrake.sqlite3")
    zero = _write_snapshot_csv(tmp_path / "SPXW_exp2026-06-03_2026-06-03_13-30-00.csv")
    inside = _write_snapshot_csv(tmp_path / "SPXW_exp2026-06-05_2026-06-03_13-31-00.csv")
    outside = _write_snapshot_csv(tmp_path / "SPXW_exp2026-06-10_2026-06-03_13-32-00.csv")

    _insert_metadata_row(
        db_path,
        csv_path=zero,
        expiration_date="2026-06-03",
        last_observed_at="2026-06-03T13:30:00+00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=inside,
        expiration_date="2026-06-05",
        last_observed_at="2026-06-03T13:31:00+00:00",
    )
    _insert_metadata_row(
        db_path,
        csv_path=outside,
        expiration_date="2026-06-10",
        last_observed_at="2026-06-03T13:32:00+00:00",
    )

    expiries = list_expirations_for_window_on_date(
        "SPXW",
        sample_date=date(2026, 6, 3),
        days_out=2,
        include_0dte=True,
        metadata_db_path=db_path,
    )
    assert expiries == [date(2026, 6, 3), date(2026, 6, 5)]


def test_missing_metadata_db_raises_clear_error(tmp_path: Path) -> None:
    missing_db = tmp_path / "missing.sqlite3"
    with pytest.raises(FileNotFoundError, match="Tickrake metadata DB not found"):
        list_expirations("SPXW", metadata_db_path=missing_db)


def test_missing_file_metadata_cache_table_raises_clear_error(tmp_path: Path) -> None:
    db_path = _create_metadata_db(tmp_path / "tickrake.sqlite3", with_table=False)
    with pytest.raises(RuntimeError, match="missing required table 'file_metadata_cache'"):
        find_latest_snapshots(
            "SPXW",
            start_date=date(2026, 4, 15),
            days_out=5,
            metadata_db_path=db_path,
        )


def test_missing_snapshot_path_is_returned_and_fails_on_load(tmp_path: Path) -> None:
    db_path = _create_metadata_db(tmp_path / "tickrake.sqlite3")
    missing_csv = tmp_path / "missing.csv"
    _insert_metadata_row(
        db_path,
        csv_path=missing_csv,
        expiration_date="2026-04-18",
        last_observed_at="2026-04-15T10:00:00",
    )

    snapshots = find_latest_snapshots(
        "SPXW",
        start_date=date(2026, 4, 18),
        days_out=0,
        metadata_db_path=db_path,
    )
    assert snapshots == {date(2026, 4, 18): missing_csv}

    with pytest.raises(
        FileNotFoundError,
        match="Options snapshot path from metadata DB does not exist",
    ):
        load_options_snapshot(missing_csv)


def test_load_options_snapshot_columns(tmp_path: Path) -> None:
    csv_path = _write_snapshot_csv(tmp_path / "snapshot.csv", underlying_price=5300.0)
    df = load_options_snapshot(csv_path)
    required = ["contract_type", "strike", "open_interest", "gamma", "underlying_price"]
    for column in required:
        assert column in df.columns
    assert df["underlying_price"].iloc[0] == 5300.0


# ---------------------------------------------------------------------------
# Parquet / DuckDB integration tests
#
# These tests require a real parquet file on disk produced by tickrake.
# They are skipped automatically if the file is absent.
# ---------------------------------------------------------------------------

_INTEGRATION_PARQUET = (
    Path.home() / ".tickrake/data/options/schwab/2026/06/25/SPXW_samples_2026-06-25.parquet"
)
_INTEGRATION_DATE = date(2026, 6, 25)
_INTEGRATION_SYMBOL = "SPXW"

pytestmark_integration = pytest.mark.skipif(
    not _INTEGRATION_PARQUET.exists(),
    reason="Integration parquet file not present on this machine",
)


def test_parquet_path_for_date_known_good() -> None:
    p = parquet_path_for_date(_INTEGRATION_SYMBOL, _INTEGRATION_DATE)
    if not _INTEGRATION_PARQUET.exists():
        pytest.skip("Integration parquet file not present")
    assert p is not None
    assert p.exists()


def test_parquet_path_for_date_missing_returns_none() -> None:
    # A future date will not have a parquet file
    p = parquet_path_for_date(_INTEGRATION_SYMBOL, date(2099, 1, 1))
    assert p is None


def test_find_historical_snapshot_times_returns_sorted_datetimes() -> None:
    if not _INTEGRATION_PARQUET.exists():
        pytest.skip("Integration parquet file not present")
    import duckdb

    expiry_raw = duckdb.execute(
        "SELECT DISTINCT expiration_date FROM read_parquet(?) LIMIT 1",
        [str(_INTEGRATION_PARQUET)],
    ).fetchone()
    assert expiry_raw is not None
    expiry = date.fromisoformat(str(expiry_raw[0]))

    times = find_historical_snapshot_times(expiry, _INTEGRATION_PARQUET)
    assert len(times) > 0
    assert all(isinstance(t, datetime) for t in times)
    assert times == sorted(times)


def test_load_historical_snapshot_returns_correct_columns() -> None:
    if not _INTEGRATION_PARQUET.exists():
        pytest.skip("Integration parquet file not present")
    import duckdb

    row = duckdb.execute(
        "SELECT expiration_date, sampled_at FROM read_parquet(?) LIMIT 1",
        [str(_INTEGRATION_PARQUET)],
    ).fetchone()
    assert row is not None
    expiry = date.fromisoformat(str(row[0]))
    sampled_at = datetime.fromisoformat(str(row[1]))

    df = load_historical_snapshot(_INTEGRATION_SYMBOL, expiry, sampled_at, _INTEGRATION_PARQUET)
    assert not df.empty
    required = ["contract_type", "strike", "gamma", "underlying_price", "expiration_date"]
    for col in required:
        assert col in df.columns
    assert df["contract_type"].str.isupper().all()


def test_load_historical_expiry_all_rows_for_expiry() -> None:
    if not _INTEGRATION_PARQUET.exists():
        pytest.skip("Integration parquet file not present")
    import duckdb

    expiry_raw = duckdb.execute(
        "SELECT DISTINCT expiration_date FROM read_parquet(?) LIMIT 1",
        [str(_INTEGRATION_PARQUET)],
    ).fetchone()
    assert expiry_raw is not None
    expiry = date.fromisoformat(str(expiry_raw[0]))

    df = load_historical_expiry(
        _INTEGRATION_SYMBOL, expiry, _INTEGRATION_DATE, _INTEGRATION_PARQUET
    )
    assert not df.empty
    assert (df["expiration_date"] == pd.Timestamp(expiry)).all()
    # should be sorted by sampled_at
    assert df["sampled_at"].is_monotonic_increasing


def test_load_historical_lookback_interval_filtering() -> None:
    if not _INTEGRATION_PARQUET.exists():
        pytest.skip("Integration parquet file not present")
    import duckdb

    bounds = duckdb.execute(
        "SELECT MIN(expiration_date), MAX(expiration_date) FROM read_parquet(?)",
        [str(_INTEGRATION_PARQUET)],
    ).fetchone()
    assert bounds is not None
    start = date.fromisoformat(str(bounds[0]))
    end = date.fromisoformat(str(bounds[1]))
    glob = str(_INTEGRATION_PARQUET.parent / "*.parquet")

    df = load_historical_lookback(_INTEGRATION_SYMBOL, glob, (start, end), interval_minutes=30)
    assert not df.empty
    # Each 30-minute bucket should produce at most one sampled_at per
    # (expiration_date, strike, contract_type) group.
    ts_ms = pd.to_datetime(df["sampled_at"], utc=True).astype("int64") // 1_000
    bucket = (ts_ms // (30 * 60 * 1_000)).rename("bucket")
    df_check = df[["expiration_date", "strike", "contract_type"]].copy()
    df_check["bucket"] = bucket.values
    assert (
        df_check.groupby(["bucket", "expiration_date", "strike", "contract_type"]).size().max() == 1
    )


def test_load_historical_expiry_lookback_single_expiry_across_dates() -> None:
    if not _INTEGRATION_PARQUET.exists():
        pytest.skip("Integration parquet file not present")
    import duckdb

    expiry_raw = duckdb.execute(
        "SELECT DISTINCT expiration_date FROM read_parquet(?) ORDER BY expiration_date LIMIT 1",
        [str(_INTEGRATION_PARQUET)],
    ).fetchone()
    assert expiry_raw is not None
    expiry = date.fromisoformat(str(expiry_raw[0]))
    glob = str(_INTEGRATION_PARQUET.parent / "*.parquet")

    df = load_historical_expiry_lookback(_INTEGRATION_SYMBOL, expiry, glob, interval_minutes=30)
    assert not df.empty
    # All rows must be for the requested expiry
    assert (df["expiration_date"] == pd.Timestamp(expiry)).all()
    # Each 30-minute bucket should produce at most one sampled_at per (strike, contract_type).
    ts_ms = pd.to_datetime(df["sampled_at"], utc=True).astype("int64") // 1_000
    bucket = (ts_ms // (30 * 60 * 1_000)).rename("bucket")
    df_check = df[["strike", "contract_type"]].copy()
    df_check["bucket"] = bucket.values
    assert df_check.groupby(["bucket", "strike", "contract_type"]).size().max() == 1
    # Bucket boundaries are non-decreasing (individual sampled_at within a bucket
    # may vary slightly across strikes, so check bucket order not raw timestamps).
    buckets = ts_ms // (30 * 60 * 1_000)
    assert buckets.is_monotonic_increasing
