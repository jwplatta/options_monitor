"""Tests for the options snapshot loader."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from trade_dash.data.options import (
    _parse_filename,
    find_all_snapshots_for_expiry,
    find_latest_snapshots,
    list_expirations,
    load_options_snapshot,
)

# ---------------------------------------------------------------------------
# _parse_filename
# ---------------------------------------------------------------------------


def test_parse_filename_valid(tmp_path: Path) -> None:
    p = tmp_path / "SPXW_exp2026-04-15_2026-04-15_13-30-00.csv"
    p.touch()
    result = _parse_filename(p)
    assert result is not None
    exp_date, fetch_dt = result
    assert exp_date == date(2026, 4, 15)
    assert fetch_dt == datetime(2026, 4, 15, 13, 30, 0)


def test_parse_filename_too_few_parts(tmp_path: Path) -> None:
    p = tmp_path / "SPXW_exp2026-04-15.csv"
    p.touch()
    assert _parse_filename(p) is None


def test_parse_filename_bad_date(tmp_path: Path) -> None:
    p = tmp_path / "SPXW_exp9999-99-99_2026-04-15_13-30-00.csv"
    p.touch()
    assert _parse_filename(p) is None


# ---------------------------------------------------------------------------
# find_latest_snapshots — most-recent-snapshot deduplication
# ---------------------------------------------------------------------------


def _touch(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / name
    p.touch()
    return p


def _snapshot_dir(root: Path, folder_date: date) -> Path:
    return root / f"{folder_date:%Y}" / f"{folder_date:%m}" / f"{folder_date:%d}"


def test_find_latest_snapshots_picks_most_recent(tmp_path: Path) -> None:
    """When three snapshots exist for the same expiry, only the latest is returned."""
    folder = _snapshot_dir(tmp_path, date(2026, 4, 15))
    _touch(folder, "SPXW_exp2026-04-15_2026-04-15_09-00-00.csv")
    _touch(folder, "SPXW_exp2026-04-15_2026-04-15_12-00-00.csv")
    latest = _touch(folder, "SPXW_exp2026-04-15_2026-04-15_15-30-00.csv")

    result = find_latest_snapshots(
        "SPXW",
        start_date=date(2026, 4, 15),
        days_out=0,
        include_0dte=True,
        data_dir=tmp_path,
    )

    assert list(result.keys()) == [date(2026, 4, 15)]
    assert result[date(2026, 4, 15)] == latest


def test_find_latest_snapshots_returns_one_per_expiry(tmp_path: Path) -> None:
    """Multiple files per expiry → exactly one path per expiry date in output."""
    # Two expirations, two snapshots each
    folder = _snapshot_dir(tmp_path, date(2026, 4, 14))
    _touch(folder, "SPXW_exp2026-04-15_2026-04-14_10-00-00.csv")
    _touch(folder, "SPXW_exp2026-04-15_2026-04-14_14-00-00.csv")
    _touch(folder, "SPXW_exp2026-04-16_2026-04-14_10-00-00.csv")
    latest_16 = _touch(folder, "SPXW_exp2026-04-16_2026-04-14_16-00-00.csv")

    result = find_latest_snapshots(
        "SPXW",
        start_date=date(2026, 4, 15),
        days_out=2,
        include_0dte=True,
        data_dir=tmp_path,
    )

    assert len(result) == 2
    assert result[date(2026, 4, 16)] == latest_16


def test_find_latest_snapshots_all_expirations_in_window(tmp_path: Path) -> None:
    """All distinct expiry dates within [start, start+days_out] are included."""
    folder = _snapshot_dir(tmp_path, date(2026, 4, 14))
    for d in ["15", "16", "17"]:
        _touch(folder, f"SPXW_exp2026-04-{d}_2026-04-14_09-00-00.csv")
    # This one is outside the window
    _touch(folder, "SPXW_exp2026-04-25_2026-04-14_09-00-00.csv")

    result = find_latest_snapshots(
        "SPXW",
        start_date=date(2026, 4, 15),
        days_out=3,
        include_0dte=True,
        data_dir=tmp_path,
    )

    assert set(result.keys()) == {date(2026, 4, 15), date(2026, 4, 16), date(2026, 4, 17)}


def test_find_latest_snapshots_excludes_outside_window(tmp_path: Path) -> None:
    """Expirations before start_date or after start+days_out are excluded."""
    folder = _snapshot_dir(tmp_path, date(2026, 4, 14))
    _touch(folder, "SPXW_exp2026-04-14_2026-04-13_09-00-00.csv")  # before
    _touch(folder, "SPXW_exp2026-04-15_2026-04-14_09-00-00.csv")  # in window
    _touch(folder, "SPXW_exp2026-04-22_2026-04-14_09-00-00.csv")  # after

    result = find_latest_snapshots(
        "SPXW",
        start_date=date(2026, 4, 15),
        days_out=5,
        include_0dte=True,
        data_dir=tmp_path,
    )

    assert date(2026, 4, 14) not in result
    assert date(2026, 4, 22) not in result
    assert date(2026, 4, 15) in result


def test_find_latest_snapshots_0dte_excluded(tmp_path: Path) -> None:
    """include_0dte=False drops the expiry that matches start_date."""
    folder = _snapshot_dir(tmp_path, date(2026, 4, 15))
    _touch(folder, "SPXW_exp2026-04-15_2026-04-15_09-00-00.csv")  # 0DTE
    _touch(folder, "SPXW_exp2026-04-16_2026-04-15_09-00-00.csv")  # future

    without = find_latest_snapshots(
        "SPXW",
        start_date=date(2026, 4, 15),
        days_out=2,
        include_0dte=False,
        data_dir=tmp_path,
    )
    with_0dte = find_latest_snapshots(
        "SPXW",
        start_date=date(2026, 4, 15),
        days_out=2,
        include_0dte=True,
        data_dir=tmp_path,
    )

    assert date(2026, 4, 15) not in without
    assert date(2026, 4, 15) in with_0dte


def test_find_latest_snapshots_empty_dir(tmp_path: Path) -> None:
    result = find_latest_snapshots(
        "SPXW",
        start_date=date(2026, 4, 15),
        days_out=10,
        data_dir=tmp_path,
    )
    assert result == {}


def test_find_latest_snapshots_ignores_other_symbols(tmp_path: Path) -> None:
    folder = _snapshot_dir(tmp_path, date(2026, 4, 15))
    _touch(folder, "SPXW_exp2026-04-15_2026-04-15_09-00-00.csv")
    _touch(folder, "QQQ_exp2026-04-15_2026-04-15_09-00-00.csv")

    result = find_latest_snapshots(
        "SPXW",
        start_date=date(2026, 4, 15),
        days_out=0,
        include_0dte=True,
        data_dir=tmp_path,
    )
    assert list(result.keys()) == [date(2026, 4, 15)]


# ---------------------------------------------------------------------------
# list_expirations
# ---------------------------------------------------------------------------


def test_list_expirations_deduplicated_and_sorted(tmp_path: Path) -> None:
    """Multiple snapshots per expiry → each expiry appears exactly once, ascending."""
    folder = _snapshot_dir(tmp_path, date(2026, 4, 15))
    for ts in ["09-00-00", "12-00-00", "15-30-00"]:
        _touch(folder, f"SPXW_exp2026-04-17_2026-04-15_{ts}.csv")
    _touch(folder, "SPXW_exp2026-04-15_2026-04-15_09-00-00.csv")

    exps = list_expirations("SPXW", data_dir=tmp_path)

    assert exps == [date(2026, 4, 15), date(2026, 4, 17)]


def test_find_latest_snapshots_prefers_newest_folder_over_older_times(tmp_path: Path) -> None:
    older = _snapshot_dir(tmp_path, date(2026, 4, 14))
    newer = _snapshot_dir(tmp_path, date(2026, 4, 15))
    old_late = _touch(older, "SPXW_exp2026-04-18_2026-04-14_15-59-59.csv")
    new_early = _touch(newer, "SPXW_exp2026-04-18_2026-04-15_09-00-00.csv")

    result = find_latest_snapshots(
        "SPXW",
        start_date=date(2026, 4, 18),
        days_out=0,
        include_0dte=True,
        data_dir=tmp_path,
    )

    assert old_late.exists()
    assert result == {date(2026, 4, 18): new_early}


def test_find_latest_snapshots_falls_back_to_older_folder_for_missing_expiry(tmp_path: Path) -> None:
    older = _snapshot_dir(tmp_path, date(2026, 4, 14))
    newer = _snapshot_dir(tmp_path, date(2026, 4, 15))
    older_16 = _touch(older, "SPXW_exp2026-04-16_2026-04-14_15-00-00.csv")
    newer_15 = _touch(newer, "SPXW_exp2026-04-15_2026-04-15_10-00-00.csv")

    result = find_latest_snapshots(
        "SPXW",
        start_date=date(2026, 4, 15),
        days_out=1,
        include_0dte=True,
        data_dir=tmp_path,
    )

    assert result == {
        date(2026, 4, 15): newer_15,
        date(2026, 4, 16): older_16,
    }


def test_find_latest_snapshots_ignores_legacy_root_files(tmp_path: Path) -> None:
    _touch(tmp_path, "SPXW_exp2026-04-15_2026-04-15_16-00-00.csv")
    folder = _snapshot_dir(tmp_path, date(2026, 4, 15))
    nested = _touch(folder, "SPXW_exp2026-04-15_2026-04-15_09-00-00.csv")

    result = find_latest_snapshots(
        "SPXW",
        start_date=date(2026, 4, 15),
        days_out=0,
        include_0dte=True,
        data_dir=tmp_path,
    )

    assert result == {date(2026, 4, 15): nested}


def test_list_expirations_empty(tmp_path: Path) -> None:
    assert list_expirations("SPXW", data_dir=tmp_path) == []


def test_find_all_snapshots_for_expiry_across_multiple_sample_dates(tmp_path: Path) -> None:
    older = _snapshot_dir(tmp_path, date(2026, 4, 14))
    newer = _snapshot_dir(tmp_path, date(2026, 4, 15))
    first = _touch(older, "SPXW_exp2026-04-18_2026-04-14_09-00-00.csv")
    second = _touch(older, "SPXW_exp2026-04-18_2026-04-14_12-00-00.csv")
    third = _touch(newer, "SPXW_exp2026-04-18_2026-04-15_10-00-00.csv")
    _touch(newer, "SPXW_exp2026-04-19_2026-04-15_10-00-00.csv")
    _touch(newer, "QQQ_exp2026-04-18_2026-04-15_10-00-00.csv")

    result = find_all_snapshots_for_expiry("SPXW", expiry=date(2026, 4, 18), data_dir=tmp_path)

    assert result == [
        (datetime(2026, 4, 14, 9, 0, 0), first),
        (datetime(2026, 4, 14, 12, 0, 0), second),
        (datetime(2026, 4, 15, 10, 0, 0), third),
    ]


# ---------------------------------------------------------------------------
# Integration-style: live data smoke tests (skip when no data available)
# ---------------------------------------------------------------------------


def test_list_expirations_returns_dates() -> None:
    exps = list_expirations("SPXW")
    assert len(exps) > 0
    assert all(isinstance(d, date) for d in exps)


def test_find_latest_snapshots_returns_paths() -> None:
    today = date.today()
    snapshots = find_latest_snapshots("SPXW", start_date=today, days_out=10)
    assert isinstance(snapshots, dict)
    for _, path in snapshots.items():
        assert path.exists(), f"Snapshot file missing: {path}"


def test_find_latest_snapshots_one_path_per_expiry() -> None:
    """Verify live data: each expiry maps to exactly one path (no duplicates)."""
    today = date.today()
    snapshots = find_latest_snapshots("SPXW", start_date=today, days_out=10)
    # dict keys are inherently unique, but assert path uniqueness too
    paths = list(snapshots.values())
    assert len(paths) == len(set(paths)), "Duplicate snapshot paths returned"


def test_load_options_snapshot_columns() -> None:
    today = date.today()
    snapshots = find_latest_snapshots("SPXW", start_date=today, days_out=5)
    if not snapshots:
        pytest.skip("No SPXW snapshots available for today's window")
    path = next(iter(snapshots.values()))
    df = load_options_snapshot(path)
    required = ["contract_type", "strike", "open_interest", "gamma", "underlying_price"]
    for col in required:
        assert col in df.columns, f"Missing column: {col}"


def test_load_options_snapshot_underlying_price_populated() -> None:
    """underlying_price must be non-null for all rows (needed for spot)."""
    today = date.today()
    snapshots = find_latest_snapshots("SPXW", start_date=today, days_out=5)
    if not snapshots:
        pytest.skip("No SPXW snapshots available for today's window")
    path = next(iter(snapshots.values()))
    df = load_options_snapshot(path)
    assert df["underlying_price"].notna().any(), "underlying_price is all null"


def test_find_latest_snapshots_0dte_exclusion() -> None:
    today = date.today()
    with_0dte = find_latest_snapshots("SPXW", start_date=today, days_out=5, include_0dte=True)
    without_0dte = find_latest_snapshots("SPXW", start_date=today, days_out=5, include_0dte=False)
    assert len(without_0dte) <= len(with_0dte)
