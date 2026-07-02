"""Environment-variable-backed path configuration for trade_dash."""

from __future__ import annotations

import os
from pathlib import Path

_HOME = Path.home()
_TICKRAKE = _HOME / ".tickrake" / "data"
_TICKRAKE_DB = _HOME / ".tickrake" / "tickrake.sqlite3"

DATA_DIR: Path = Path(os.getenv("TRADE_DASH_DATA_DIR", str(_TICKRAKE)))
# DASHBOARD.md specifies "ibkr-api" as the provider, but the actual data directory
# on disk is "ibkr-paper". Override via TRADE_DASH_CANDLE_DIR env var if needed.
CANDLE_DIR: Path = Path(
    os.getenv("TRADE_DASH_CANDLE_DIR", str(_TICKRAKE / "history" / "ibkr-paper"))
)
OPTIONS_DIR: Path = Path(os.getenv("TRADE_DASH_OPTIONS_DIR", str(_TICKRAKE / "options" / "schwab")))
TICKRAKE_DB_PATH: Path = Path(os.getenv("TRADE_DASH_TICKRAKE_DB_PATH", str(_TICKRAKE_DB)))
SCHWAB_CANDLE_DIR: Path = Path(
    os.getenv("TRADE_DASH_SCHWAB_CANDLE_DIR", str(_TICKRAKE / "history" / "schwab"))
)
PARQUET_OPTIONS_DIR: Path = Path(
    os.getenv("TRADE_DASH_PARQUET_OPTIONS_DIR", str(_TICKRAKE / "options" / "schwab"))
)
