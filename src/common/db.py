"""Canonical PostgreSQL + TimescaleDB connection module (FND-004 Phase 3).

This is the single source of truth for database connectivity across every layer
of Scalable Brain. The canonical operational store is the host-system
PostgreSQL 16 + TimescaleDB cluster on ``localhost:5432`` (database
``ForexBrainDB``, role ``sa``). SQL Server / ODBC / ``pyodbc`` are no longer
used anywhere in the runtime.

Usage
-----
SQLAlchemy 2.0 (pandas, parameterized ``text()`` queries, ORM-style access)::

    from src.common.db import get_engine
    import pandas as pd
    from sqlalchemy import text

    engine = get_engine()
    df = pd.read_sql(text("SELECT count(*) FROM fact_market_prices"), engine)

Raw psycopg2 (bulk ``COPY`` / ``execute_values`` upserts)::

    from src.common.db import get_psycopg2_connection
    with get_psycopg2_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")

Bulk idempotent upsert helper (replaces the SQL Server temp-table + ``MERGE``
pattern)::

    from src.common.db import bulk_upsert
    bulk_upsert(
        table="fact_market_regime_v2",
        rows=records,                       # list[dict]
        conflict_columns=["timestamp", "asset_id", "granularity"],
    )

Canonical DSN convention
------------------------
Built once from ``.env``:

    postgresql+psycopg2://{user}:{quote_plus(password)}@{host}:{port}/{name}

Environment variables (``.env``):
    ``DB_SERVER`` (alias ``DB_HOST``), ``DB_PORT``, ``DB_NAME``, ``DB_USER``,
    ``DB_PASS``.

Note: the legacy ``DB_DRIVER`` variable is intentionally ignored — there is no
ODBC driver in the PostgreSQL path. It is retained in ``.env`` only as a
documented no-op for backwards compatibility and may be removed.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote_plus

import psycopg2
import psycopg2.extensions
import sqlalchemy as sa
from dotenv import load_dotenv
from psycopg2.extras import execute_values
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# Load .env exactly once at import time. Subsequent calls are cheap no-ops.
load_dotenv()

# Canonical defaults mirror the live host cluster (see docs/database/README.md).
_DEFAULT_HOST = "localhost"
_DEFAULT_PORT = "5432"
_DEFAULT_NAME = "ForexBrainDB"
_DEFAULT_USER = "sa"


def _config() -> dict[str, str]:
    """Resolve canonical DB connection parameters from the environment.

    ``DB_SERVER`` is the historical variable name used throughout the repo and
    in ``.env``; ``DB_HOST`` is accepted as an alias for forward compatibility.
    """
    host = os.getenv("DB_SERVER") or os.getenv("DB_HOST") or _DEFAULT_HOST
    port = os.getenv("DB_PORT", _DEFAULT_PORT)
    name = os.getenv("DB_NAME", _DEFAULT_NAME)
    user = os.getenv("DB_USER", _DEFAULT_USER)
    password = os.getenv("DB_PASS", "")
    return {
        "host": host,
        "port": port,
        "name": name,
        "user": user,
        "password": password,
    }


def get_sqlalchemy_url() -> str:
    """Return the canonical ``postgresql+psycopg2`` SQLAlchemy URL.

    The password is percent-encoded so special characters (e.g. ``$``) are
    safe inside the URL.
    """
    cfg = _config()
    return (
        "postgresql+psycopg2://"
        f"{cfg['user']}:{quote_plus(cfg['password'])}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['name']}"
    )


def get_psycopg2_dsn() -> str:
    """Return a libpq keyword/value DSN for direct ``psycopg2.connect``."""
    cfg = _config()
    return (
        f"host={cfg['host']} port={cfg['port']} dbname={cfg['name']} "
        f"user={cfg['user']} password={cfg['password']}"
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return a process-wide cached SQLAlchemy 2.0 Engine for ``ForexBrainDB``.

    The engine uses a pre-ping pooled connection so stale connections are
    transparently recycled. Safe to call from any layer; the underlying engine
    is created only once per process.
    """
    url = get_sqlalchemy_url()
    engine = sa.create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,
        future=True,
        # Force every pooled connection's session timezone to UTC so the
        # timestamptz columns round-trip as true UTC instants regardless of the
        # server's default timezone.
        connect_args={"options": "-c timezone=utc"},
    )
    cfg = _config()
    logger.debug(
        "Created SQLAlchemy engine for postgresql://%s@%s:%s/%s",
        cfg["user"],
        cfg["host"],
        cfg["port"],
        cfg["name"],
    )
    return engine


def get_psycopg2_connection() -> psycopg2.extensions.connection:
    """Return a new raw ``psycopg2`` connection.

    Caller owns the connection lifecycle (commit/rollback/close). Intended for
    bulk paths (``COPY``, :func:`psycopg2.extras.execute_values`) where the
    SQLAlchemy layer adds no value. Usable as a context manager (``with`` opens
    a transaction; it does NOT close the connection on exit per psycopg2
    semantics — close explicitly or use :func:`bulk_upsert`).
    """
    cfg = _config()
    return psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        dbname=cfg["name"],
        user=cfg["user"],
        password=cfg["password"],
        # Force the session timezone to UTC (see get_engine) so naive-UTC
        # datetimes are stored/read as true UTC instants.
        options="-c timezone=utc",
    )


def test_connection() -> bool:
    """Return ``True`` if a trivial round-trip query succeeds, else ``False``."""
    try:
        with get_engine().connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 - diagnostic helper
        logger.error("Database connection test failed: %s", exc)
        return False


def _quote_ident(identifier: str) -> str:
    """Safely double-quote a SQL identifier (column/table name).

    Preserves mixed-case columns such as ``"Close"``/``"Open"`` and protects
    against reserved words. Embedded double quotes are escaped per the SQL
    standard.
    """
    return '"' + identifier.replace('"', '""') + '"'


def bulk_upsert(
    table: str,
    rows: Sequence[Mapping[str, Any]],
    conflict_columns: Sequence[str],
    update_columns: Iterable[str] | None = None,
    *,
    columns: Sequence[str] | None = None,
    do_nothing: bool = False,
    page_size: int = 1000,
    conn: psycopg2.extensions.connection | None = None,
) -> int:
    """Idempotent bulk upsert via ``INSERT ... ON CONFLICT`` + ``execute_values``.

    This is the PostgreSQL replacement for the SQL Server temp-table + ``MERGE``
    pattern. Re-running with the same rows must not create duplicates.

    Args:
        table: Target table name (unquoted unless it needs quoting).
        rows: Sequence of dict-like records. Keys are column names.
        conflict_columns: Columns forming the conflict target (the table's
            PRIMARY KEY or a UNIQUE constraint).
        update_columns: Columns to overwrite on conflict. Defaults to every
            inserted column not in ``conflict_columns``. Ignored when
            ``do_nothing`` is True.
        columns: Explicit column ordering. Defaults to the keys of the first
            row (all rows must share the same keys).
        do_nothing: If True, emit ``ON CONFLICT DO NOTHING`` instead of an
            update (insert-or-ignore semantics).
        page_size: ``execute_values`` batch size.
        conn: Optional existing connection. If provided, the caller owns the
            transaction (no commit/close here). If omitted, a connection is
            opened, committed, and closed internally.

    Returns:
        Number of rows submitted (``len(rows)``). Note PostgreSQL does not
        cheaply report affected-row breakdown for ``execute_values``.
    """
    rows = list(rows)
    if not rows:
        return 0

    if columns is None:
        columns = list(rows[0].keys())
    col_idents = ", ".join(_quote_ident(c) for c in columns)
    conflict_idents = ", ".join(_quote_ident(c) for c in conflict_columns)

    if do_nothing:
        conflict_clause = "DO NOTHING"
    else:
        if update_columns is None:
            update_columns = [c for c in columns if c not in set(conflict_columns)]
        update_columns = list(update_columns)
        if update_columns:
            assignments = ", ".join(
                f"{_quote_ident(c)} = EXCLUDED.{_quote_ident(c)}"
                for c in update_columns
            )
            conflict_clause = f"DO UPDATE SET {assignments}"
        else:
            conflict_clause = "DO NOTHING"

    sql = (
        f"INSERT INTO {table} ({col_idents}) VALUES %s "
        f"ON CONFLICT ({conflict_idents}) {conflict_clause}"
    )

    values = [tuple(row.get(col) for col in columns) for row in rows]

    own_conn = conn is None
    if conn is None:
        conn = get_psycopg2_connection()
    try:
        with conn.cursor() as cur:
            execute_values(cur, sql, values, page_size=page_size)
        if own_conn:
            conn.commit()
    except Exception:
        if own_conn:
            conn.rollback()
        raise
    finally:
        if own_conn:
            conn.close()

    return len(rows)
