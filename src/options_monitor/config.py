"""Environment-variable-backed path configuration for options_monitor."""

from __future__ import annotations

import os
from pathlib import Path

_HOME = Path.home()
_TICKRAKE = _HOME / ".tickrake" / "data"
_TICKRAKE_DB = _HOME / ".tickrake" / "tickrake.sqlite3"

DATA_DIR: Path = Path(os.getenv("options_monitor_DATA_DIR", str(_TICKRAKE)))
# DASHBOARD.md specifies "ibkr-api" as the provider, but the actual data directory
# on disk is "ibkr-paper". Override via options_monitor_CANDLE_DIR env var if needed.
CANDLE_DIR: Path = Path(
    os.getenv("options_monitor_CANDLE_DIR", str(_TICKRAKE / "history" / "ibkr-paper"))
)
OPTIONS_DIR: Path = Path(
    os.getenv("options_monitor_OPTIONS_DIR", str(_TICKRAKE / "options" / "schwab"))
)
TICKRAKE_DB_PATH: Path = Path(os.getenv("options_monitor_TICKRAKE_DB_PATH", str(_TICKRAKE_DB)))
SCHWAB_CANDLE_DIR: Path = Path(
    os.getenv("options_monitor_SCHWAB_CANDLE_DIR", str(_TICKRAKE / "history" / "schwab"))
)
PARQUET_OPTIONS_DIR: Path = Path(
    os.getenv("options_monitor_PARQUET_OPTIONS_DIR", str(_TICKRAKE / "options" / "schwab"))
)
