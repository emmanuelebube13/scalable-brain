"""Shared database client for Layer 5 services.

Reuses the same mssql+pyodbc connection pattern already proven in Layer 4
and the legacy Dash app to avoid connection mismatches.
"""

import urllib.parse
from typing import Any, List, Dict
import pandas as pd
import sqlalchemy as sa


__ENGINES: Dict[str, sa.engine.Engine] = {}


def get_engine(server: str, user: str, password: str, database: str) -> sa.engine.Engine:
    """Return a cached SQLAlchemy engine for the given credentials."""
    key = f"{server}:{user}:{database}"
    if key not in __ENGINES:
        params = urllib.parse.quote_plus(
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={user};"
            f"PWD={password}"
        )
        __ENGINES[key] = sa.create_engine(f"mssql+pyodbc:///?odbc_connect={params}")
    return __ENGINES[key]


def execute_query(engine: sa.engine.Engine, query: sa.TextClause, params: Dict[str, Any] | None = None) -> pd.DataFrame:
    """Execute a parameterized query and return a DataFrame."""
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params=params)


def execute_to_records(engine: sa.engine.Engine, query: sa.TextClause, params: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """Execute a query and return a list of dict records (JSON-friendly)."""
    df = execute_query(engine, query, params)
    if df.empty:
        return []
    # Convert timestamps to ISO strings for JSON serialization
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime("%Y-%m-%dT%H:%M:%S")
    return df.to_dict(orient="records")
