"""
Shared PostgreSQL database client for Scalable Brain.

Provides a unified interface for psycopg2 raw connections and SQLAlchemy engines,
replacing the previous pyodbc + SQL Server stack.
"""

import os
import logging
import urllib.parse
from contextlib import contextmanager
from typing import Optional, Generator, Dict, Any, List

import pandas as pd
import sqlalchemy as sa

logger = logging.getLogger(__name__)


def get_postgres_connection_string(
    server: Optional[str] = None,
    database: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    port: Optional[int] = None,
) -> str:
    """Build a PostgreSQL connection string from environment or explicit args."""
    server = server or os.getenv("DB_SERVER", "localhost")
    database = database or os.getenv("DB_NAME", "ForexBrainDB")
    user = user or os.getenv("DB_USER", "sa")
    password = password or os.getenv("DB_PASS", "password")
    port = port or int(os.getenv("DB_PORT", "5432"))
    return f"postgresql://{user}:{urllib.parse.quote(password)}@{server}:{port}/{database}"


def get_sqlalchemy_engine(
    server: Optional[str] = None,
    database: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    port: Optional[int] = None,
) -> sa.engine.Engine:
    """Return a SQLAlchemy engine for PostgreSQL."""
    conn_str = get_postgres_connection_string(server, database, user, password, port)
    return sa.create_engine(conn_str)


class PostgresClient:
    """
    Manages PostgreSQL database connections with proper resource handling.
    Drop-in replacement for the SQL Server DatabaseConnection class.
    """

    def __init__(self, connection_string: Optional[str] = None):
        self.connection_string = connection_string or get_postgres_connection_string()
        self._engine: Optional[sa.engine.Engine] = None

    @property
    def engine(self) -> sa.engine.Engine:
        if self._engine is None:
            self._engine = sa.create_engine(self.connection_string)
        return self._engine

    def connect(self):
        """Return a raw psycopg2 connection via SQLAlchemy."""
        return self.engine.raw_connection()

    @contextmanager
    def cursor(self) -> Generator[Any, None, None]:
        """Get a database cursor with automatic cleanup."""
        conn = None
        cur = None
        try:
            conn = self.connect()
            cur = conn.cursor()
            yield cur
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database operation failed: {e}")
            raise
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()
                logger.debug("Database connection closed")

    @contextmanager
    def connection(self) -> Generator[Any, None, None]:
        """Get a raw database connection with automatic cleanup."""
        conn = None
        try:
            conn = self.connect()
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

    def test_connection(self) -> bool:
        try:
            with self.cursor() as cur:
                cur.execute("SELECT 1")
                return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[tuple]:
        with self.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()

    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.executemany(query, params_list)
            rowcount = cur.rowcount
            cur.close()
            return rowcount

    def read_sql(self, query: str, params: Optional[tuple] = None) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql(sa.text(query), conn, params=params)


def execute_query_to_df(engine: sa.engine.Engine, query: str, params: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    """Execute a query via SQLAlchemy and return a DataFrame."""
    with engine.connect() as conn:
        return pd.read_sql(sa.text(query), conn, params=params or {})


def execute_query_to_records(engine: sa.engine.Engine, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Execute a query and return JSON-friendly records."""
    df = execute_query_to_df(engine, query, params)
    if df.empty:
        return []
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime("%Y-%m-%dT%H:%M:%S")
    return df.to_dict(orient="records")
