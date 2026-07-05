"""
Layer 0 Data Loader
===================

Database-backed data loader for strategy qualification.

Reads asset metadata from ``dim_asset`` and price candles from
``fact_market_prices`` (PostgreSQL 16 + TimescaleDB). All connectivity routes
through :mod:`src.common.db` (FND-004 Phase 3 — migrated off SQL Server/pyodbc).

Column-case contract: the price tables expose genuinely mixed-case ``"Open"`` and
``"Close"`` columns (double-quoted); every other column is lowercase. Queries
alias lowercase columns back to the historical mixed-case names this module's
consumers expect (``Asset_ID``, ``Timestamp``, ``High``, ``Low``, ``Volume`` …).
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from dotenv import load_dotenv

# Ensure the repo root is importable so ``src.common`` resolves when this module
# is run as part of a script launched from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common.db import get_engine, get_psycopg2_connection  # noqa: E402

logger = logging.getLogger(__name__)
_ENV_LOADED = False


def _find_env_file() -> Optional[str]:
    """Search for .env file from current directory up to repo root."""
    current = Path.cwd()
    for _ in range(8):
        env_file = current / ".env"
        if env_file.exists():
            return str(env_file)
        if current.parent == current:
            break
        current = current.parent
    return None


def _load_env(env_path: Optional[str] = None) -> None:
    """Load environment variables from .env file."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    if env_path is None:
        env_path = _find_env_file()
    if env_path and Path(env_path).exists():
        load_dotenv(env_path, override=True)
        logger.info(f"Loaded environment from: {env_path}")
    else:
        logger.warning("No .env file found; relying on existing environment variables")

    _ENV_LOADED = True


def get_db_connection(env_path: Optional[str] = None):
    """
    Establish a raw PostgreSQL (psycopg2) database connection.

    Retained for backwards compatibility / callers that need a raw DBAPI
    connection. Read helpers in this module use the pooled SQLAlchemy engine
    from :mod:`src.common.db` and do not require a connection to be passed.

    Args:
        env_path: Optional path to .env file

    Returns:
        Active psycopg2 connection (caller owns its lifecycle)
    """
    _load_env(env_path)
    logger.debug("Opening PostgreSQL connection...")
    return get_psycopg2_connection()


def _get_engine(env_path: Optional[str] = None) -> Engine:
    """Return the cached SQLAlchemy engine (loading .env first if needed)."""
    _load_env(env_path)
    return get_engine()


def _has_table(engine: Engine, table_name: str) -> bool:
    """Return True when the specified table exists in the current database."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT to_regclass(:tname)"),
            {"tname": table_name},
        ).scalar()
    return result is not None


def _table_has_rows(engine: Engine, table_name: str) -> bool:
    """Return True when the table exists and contains at least one row.

    The dedicated ``fact_market_prices_h4``/``_d1`` tables exist but are
    currently empty in the live store — H4/D1 candles live in
    ``fact_market_prices`` partitioned by ``granularity``. Routing must only
    prefer a dedicated table when it actually holds data, otherwise fall back.
    """
    if not _has_table(engine, table_name):
        return False
    with engine.connect() as conn:
        result = conn.execute(
            text(f"SELECT EXISTS (SELECT 1 FROM {table_name} LIMIT 1)")
        ).scalar()
    return bool(result)


def _has_column(engine: Engine, table_name: str, column_name: str) -> bool:
    """Return True when the specified column exists on the table.

    Case-insensitive on the table name (PostgreSQL folds unquoted identifiers
    to lowercase); column comparison is exact to respect mixed-case columns.
    """
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND lower(table_name) = lower(:tname)
                  AND column_name = :cname
                """),
            {"tname": table_name, "cname": column_name},
        ).first()
    return result is not None


def load_assets(
    conn=None,
    env_path: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load active assets from ``dim_asset``.

    Args:
        conn: Ignored (retained for backwards compatibility). Connectivity uses
            the pooled engine from :mod:`src.common.db`.
        env_path: Optional path to .env file.

    Returns:
        DataFrame with columns: Asset_ID, Symbol, Market_Type
    """
    engine = _get_engine(env_path)

    has_is_active = _has_column(engine, "dim_asset", "is_active")
    if has_is_active:
        query = text("""
            SELECT asset_id AS "Asset_ID", symbol AS "Symbol",
                   market_type AS "Market_Type"
            FROM dim_asset
            WHERE is_active = TRUE
            ORDER BY asset_id
            """)
    else:
        query = text("""
            SELECT asset_id AS "Asset_ID", symbol AS "Symbol",
                   market_type AS "Market_Type"
            FROM dim_asset
            ORDER BY asset_id
            """)
        logger.warning(
            "dim_asset.is_active not found; loading all assets without active filter"
        )

    with engine.connect() as connection:
        df = pd.read_sql(query, connection)
    if not df.empty and "Asset_ID" in df.columns:
        df["Asset_ID"] = pd.to_numeric(df["Asset_ID"], errors="coerce").astype("Int64")
    logger.info(f"Loaded {len(df)} active assets from dim_asset")
    return df


def load_market_prices(
    asset_id: int,
    granularity: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    conn=None,
    env_path: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load OHLCV price data from ``fact_market_prices``.

    Args:
        asset_id: Asset identifier
        granularity: Candle granularity (H1, H4, D1, etc.)
        start_date: Optional start filter
        end_date: Optional end filter
        conn: Ignored (retained for backwards compatibility).
        env_path: Optional .env file path

    Returns:
        DataFrame indexed by Timestamp with columns: Open, High, Low, Close, Volume
    """
    engine = _get_engine(env_path)

    # Route to the correct granularity-specific table if it exists.
    table_name = "fact_market_prices"
    if granularity == "H4" and _table_has_rows(engine, "fact_market_prices_h4"):
        table_name = "fact_market_prices_h4"
    elif granularity == "D1" and _table_has_rows(engine, "fact_market_prices_d1"):
        table_name = "fact_market_prices_d1"

    params: Dict[str, object] = {"asset_id": asset_id}
    if table_name in ("fact_market_prices_h4", "fact_market_prices_d1"):
        sql = f"""
            SELECT "timestamp" AS "Timestamp", "Open", high AS "High",
                   low AS "Low", "Close", volume AS "Volume"
            FROM {table_name}
            WHERE asset_id = :asset_id
        """
    else:
        sql = """
            SELECT "timestamp" AS "Timestamp", "Open", high AS "High",
                   low AS "Low", "Close", volume AS "Volume"
            FROM fact_market_prices
            WHERE asset_id = :asset_id AND granularity = :granularity
        """
        params["granularity"] = granularity

    if start_date:
        sql += ' AND "timestamp" >= :start_date'
        params["start_date"] = start_date
    if end_date:
        sql += ' AND "timestamp" <= :end_date'
        params["end_date"] = end_date

    sql += ' ORDER BY "timestamp"'

    with engine.connect() as connection:
        df = pd.read_sql(text(sql), connection, params=params)
    if not df.empty:
        numeric_cols = ["Open", "High", "Low", "Close", "Volume"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        # PostgreSQL stores these as timestamptz; normalise to naive UTC so the
        # downstream backtest/indicator code keeps the tz-naive contract it had
        # under SQL Server's DATETIME2.
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], utc=True).dt.tz_localize(None)
        df.set_index("Timestamp", inplace=True)
    logger.info(
        f"Loaded {len(df)} rows for Asset_ID={asset_id}, Granularity={granularity}"
    )
    return df


def get_asset_symbol_map(
    conn=None,
    env_path: Optional[str] = None,
) -> Dict[int, str]:
    """
    Get a mapping of Asset_ID -> Symbol for all active assets.

    Returns:
        Dictionary mapping asset IDs to symbols
    """
    df = load_assets(conn, env_path)
    return dict(zip(df["Asset_ID"], df["Symbol"]))
