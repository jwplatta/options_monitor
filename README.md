# Options Monitor

Options-data and market-monitoring dashboard built with Streamlit.

## Stack

- `uv` for environment and dependency management
- `streamlit` for the dashboard UI
- `ruff` for linting and formatting
- `mypy` for strict type checking
- `pytest` with coverage reporting
- `src/` layout for clean packaging

## Quick Start

```bash
uv sync
uv run options-monitor
```

The command above starts Streamlit and serves Options Monitor in your browser.

## Development

```bash
uv run ruff check .
uv run ruff format .
uv run mypy
uv run pytest
uv run streamlit run src/trade_dash/app.py
```

## Structure

```text
.
├── .vscode/
├── docs/
├── src/trade_dash/
└── tests/
```
