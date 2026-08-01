from pathlib import Path

from options_monitor.__main__ import build_streamlit_command, streamlit_app_path


def test_streamlit_app_path_points_to_app_module() -> None:
    assert streamlit_app_path().name == "app.py"
    assert isinstance(streamlit_app_path(), Path)


def test_build_streamlit_command() -> None:
    command = build_streamlit_command()
    assert command[1:4] == ["-m", "streamlit", "run"]
    assert command[4].endswith("src/options_monitor/app.py")
