"""CLI entrypoint for launching the Streamlit dashboard."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def streamlit_app_path() -> Path:
    """Return the absolute path to the Streamlit app module."""
    return Path(__file__).with_name("app.py")


def build_streamlit_command() -> list[str]:
    """Build the command used to launch the local Streamlit app."""
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(streamlit_app_path()),
    ]


def main() -> None:
    """Launch the Streamlit dashboard."""
    subprocess.run(build_streamlit_command(), check=True)
