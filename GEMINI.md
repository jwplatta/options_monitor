# Options Monitor: Project Instructions

This project is a Streamlit-based options-data and market-monitoring dashboard focused on visualizing Gamma Exposure (GEX), aggressive flow (Maker-Taker), and volatility metrics.

## Core Mandates

- **Skill Management**: Use `skillex` to pull, update, and manage shared skills as needed to enhance your capabilities within this workspace.
- **Architectural Pattern**: Follow the established separation of concerns:
    - `src/options_monitor/data/`: Data loading and schema definitions (Pandas).
    - `src/options_monitor/calc/`: Pure mathematical and data transformation logic.
    - `src/options_monitor/charts/`: Plotly figure generation (standardize on `plotly_dark` template).
    - `src/options_monitor/tabs/`: Streamlit UI components and layout assembly.
- **Timezone Convention**: All market data and charts must standardize on `America/Chicago` time. Use `zoneinfo.ZoneInfo("America/Chicago")` for conversions. Perform UTC to Chicago naive conversions (removing `tzinfo` after conversion) to maintain consistency with Plotly and Streamlit rendering.

## Engineering Standards

- **Environment**: Use `uv` for all command executions and dependency management (e.g., `uv run streamlit ...`, `uv run pytest`).
- **Quality Control**:
    - **Linting**: Run `ruff check . --fix` before completing any task.
    - **Typing**: Ensure all new code passes `mypy`.
    - **Testing**: Add unit tests in `tests/unit/` for all new calculation or chart logic. Use `pytest` for verification.
- **Data Handling**: Use typed Pandas operations. Prefer `pd.to_numeric(..., errors="coerce")` followed by `.dropna()` for robust data ingestion from CSV snapshots.
- **State Management**: Use Streamlit's `st.session_state` with unique keys (e.g., prefixing with `_` and tab-specific identifiers) to cache expensive calculations across fragment reruns.

## Workflow

1. **Research**: Empirical reproduction of any reported issues is mandatory.
2. **Strategy**: Propose changes and gain alignment for architectural shifts.
3. **Execution**: Perform surgical updates. Ensure all changes are verified with `uv run pytest`.
4. **Finalization**: Run linting and type-checking to ensure project integrity.
