"""Tests for GEX calculation functions."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from trade_dash.calc.gex import (
    find_zero_gamma_level,
    net_gex_by_price,
    net_gex_by_strike,
)
from trade_dash.data.options import find_latest_snapshots, load_options_snapshot


@pytest.fixture()
def spxw_opts() -> pd.DataFrame:
    snapshots = find_latest_snapshots("SPXW", start_date=date(2026, 4, 14), days_out=5)
    if not snapshots:
        pytest.skip("No SPXW snapshots available")
    dfs = [load_options_snapshot(path) for path in snapshots.values()]
    return pd.concat(dfs, ignore_index=True)


def test_net_gex_by_strike_columns(spxw_opts: pd.DataFrame) -> None:
    spot = float(spxw_opts["underlying_price"].iloc[0])
    result = net_gex_by_strike(spxw_opts, spot=spot)
    assert "strike" in result.columns
    assert "net_gex" in result.columns
    assert len(result) > 0


def test_net_gex_by_strike_has_nonzero_values(spxw_opts: pd.DataFrame) -> None:
    spot = float(spxw_opts["underlying_price"].iloc[0])
    result = net_gex_by_strike(spxw_opts, spot=spot)
    assert result["net_gex"].max() > 0
    assert result["net_gex"].abs().sum() > 0


def test_find_zero_gamma_level_finds_crossing() -> None:
    prices = np.array([5000.0, 5100.0, 5200.0, 5300.0])
    gex = np.array([-100.0, -50.0, 50.0, 100.0])
    zgl = find_zero_gamma_level(prices, gex)
    assert zgl is not None
    assert 5100.0 < zgl < 5200.0


def test_find_zero_gamma_level_returns_none_when_no_crossing() -> None:
    prices = np.array([5000.0, 5100.0, 5200.0])
    gex = np.array([10.0, 20.0, 30.0])
    assert find_zero_gamma_level(prices, gex) is None


def test_net_gex_by_price_returns_price_gex_columns(spxw_opts: pd.DataFrame) -> None:
    spot = float(spxw_opts["underlying_price"].iloc[0])
    snap = pd.Timestamp("2026-04-14 14:00:00")
    result = net_gex_by_price(spxw_opts, spot=spot, snap_time=snap)
    assert "price" in result.columns
    assert "net_gex" in result.columns
    assert len(result) > 0


def test_net_gex_by_price_grid_is_integer_spaced(spxw_opts: pd.DataFrame) -> None:
    spot = float(spxw_opts["underlying_price"].iloc[0])
    snap = pd.Timestamp("2026-04-14 14:00:00")
    result = net_gex_by_price(spxw_opts, spot=spot, snap_time=snap, price_range=10.0)
    diffs = np.diff(result["price"].to_numpy())
    assert np.allclose(diffs, 1.0), "Price grid should be integer-spaced (step=1)"


def test_net_gex_by_price_deterministic_with_snap_time(spxw_opts: pd.DataFrame) -> None:
    spot = float(spxw_opts["underlying_price"].iloc[0])
    snap = pd.Timestamp("2026-04-14 14:00:00")
    r1 = net_gex_by_price(spxw_opts, spot=spot, snap_time=snap)
    r2 = net_gex_by_price(spxw_opts, spot=spot, snap_time=snap)
    pd.testing.assert_frame_equal(r1, r2)
