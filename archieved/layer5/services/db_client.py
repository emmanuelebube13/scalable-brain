"""Shared database client for Layer 5 services.

Routes through the canonical PostgreSQL + TimescaleDB connection module
(:mod:`src.common.db`) — FND-004 Phase 3 (was ``mssql+pyodbc`` with ODBC
auto-detection).
"""

import sys
from pathlib import Path
from typing import Any, List, Dict
import pandas as pd
import sqlalchemy as sa

# Ensure the repo root is importable so ``src.common`` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from src.common.db import get_engine as _get_canonical_engine  # noqa: E402


def get_engine(
    server: str = "",
    user: str = "",
    password: str = "",
    database: str = "",
) -> sa.engine.Engine:
    """Return the canonical cached PostgreSQL engine.

    The credential arguments are retained for backwards compatibility with
    existing callers (e.g. ``dependencies.py``) but are ignored — the canonical
    engine is built from ``.env`` by :mod:`src.common.db`.
    """
    return _get_canonical_engine()


def execute_query(
    engine: sa.engine.Engine, query: sa.TextClause, params: Dict[str, Any] | None = None
) -> pd.DataFrame:
    """Execute a parameterized query and return a DataFrame."""
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params=params)


def execute_to_records(
    engine: sa.engine.Engine, query: sa.TextClause, params: Dict[str, Any] | None = None
) -> List[Dict[str, Any]]:
    """Execute a query and return a list of dict records (JSON-friendly)."""
    df = execute_query(engine, query, params)
    if df.empty:
        return []
    # Convert timestamps to ISO strings for JSON serialization
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime("%Y-%m-%dT%H:%M:%S")
    return df.to_dict(orient="records")
