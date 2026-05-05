"""Shared database client for Layer 5 services.

Reuses the PostgreSQL connection pattern to avoid connection mismatches.
"""

from typing import Any, List, Dict
import pandas as pd
import sqlalchemy as sa


__ENGINES: Dict[str, sa.engine.Engine] = {}


def get_engine(server: str, user: str, password: str, database: str, port: int = 5432) -> sa.engine.Engine:
    """Return a cached SQLAlchemy engine for the given credentials."""
    key = f"{server}:{user}:{database}:{port}"
    if key not in __ENGINES:
        import urllib.parse
        conn_str = (
            f"postgresql+psycopg2://{urllib.parse.quote(user)}:{urllib.parse.quote(password)}"
            f"@{server}:{port}/{database}"
        )
        __ENGINES[key] = sa.create_engine(conn_str)
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
