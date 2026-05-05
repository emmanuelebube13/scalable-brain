"""
Layer 0 Data Loader
===================

Database-backed data loader for strategy qualification.

Reads asset metadata from Dim_Asset and price candles from Fact_Market_Prices.
Uses the same .env conventions as the rest of the Scalable Brain system.
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

import pandas as pd
import psycopg2
from dotenv import load_dotenv

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


def _get_connection_params() -> Dict[str, str]:
    """Build PostgreSQL connection params from environment."""
    required = ["DB_SERVER", "DB_USER", "DB_PASS"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    return {
        "host": os.getenv("DB_SERVER"),
        "dbname": os.getenv("DB_NAME", "ForexBrainDB"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASS"),
        "port": os.getenv("DB_PORT", "5432"),
    }


def get_db_connection(env_path: Optional[str] = None) -> psycopg2.extensions.connection:
    """
    Establish a database connection.
    
    Args:
        env_path: Optional path to .env file
        
    Returns:
        Active psycopg2 connection
    """
    _load_env(env_path)
    params = _get_connection_params()
    logger.debug("Connecting to PostgreSQL...")
    return psycopg2.connect(**params, connect_timeout=30)


def _has_table(conn: psycopg2.extensions.connection, table_name: str) -> bool:
    """Return True when the specified table exists in the current database."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = LOWER(%s))",
        (table_name,),
    )
    result = cursor.fetchone()
    return bool(result and result[0])


def _has_column(conn: psycopg2.extensions.connection, table_name: str, column_name: str) -> bool:
    """Return True when the specified column exists on the table."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = LOWER(%s) AND column_name = LOWER(%s)
        )
        """,
        (table_name, column_name),
    )
    result = cursor.fetchone()
    return bool(result and result[0])


def load_assets(conn: Optional[psycopg2.extensions.connection] = None,
                env_path: Optional[str] = None) -> pd.DataFrame:
    """
    Load active assets from Dim_Asset.
    
    Returns:
        DataFrame with columns: Asset_ID, Symbol, Market_Type
    """
    close_conn = False
    if conn is None:
        conn = get_db_connection(env_path)
        close_conn = True

    has_is_active = _has_column(conn, "Dim_Asset", "Is_Active")
    if has_is_active:
        query = """
            SELECT Asset_ID, Symbol, Market_Type
            FROM Dim_Asset
            WHERE Is_Active = TRUE
            ORDER BY Asset_ID
        """
    else:
        query = """
            SELECT Asset_ID, Symbol, Market_Type
            FROM Dim_Asset
            ORDER BY Asset_ID
        """
        logger.warning(
            "Dim_Asset.Is_Active not found; loading all assets without active filter"
        )
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        columns = [col[0] for col in cursor.description]
        df = pd.DataFrame.from_records(rows, columns=columns)
        if not df.empty and "Asset_ID" in df.columns:
            df["Asset_ID"] = pd.to_numeric(df["Asset_ID"], errors="coerce").astype("Int64")
        logger.info(f"Loaded {len(df)} active assets from Dim_Asset")
        return df
    finally:
        if close_conn:
            conn.close()


def load_market_prices(
    asset_id: int,
    granularity: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    conn: Optional[psycopg2.extensions.connection] = None,
    env_path: Optional[str] = None
) -> pd.DataFrame:
    """
    Load OHLCV price data from Fact_Market_Prices.
    
    Args:
        asset_id: Asset identifier
        granularity: Candle granularity (H1, H4, D1, etc.)
        start_date: Optional start filter
        end_date: Optional end filter
        conn: Optional existing connection
        env_path: Optional .env file path
        
    Returns:
        DataFrame with columns: Timestamp, Open, High, Low, Close, Volume
    """
    close_conn = False
    if conn is None:
        conn = get_db_connection(env_path)
        close_conn = True

    # Route to the correct granularity-specific table if it exists
    table_name = "Fact_Market_Prices"
    if granularity == "H4" and _has_table(conn, "Fact_Market_Prices_H4"):
        table_name = "Fact_Market_Prices_H4"
    elif granularity == "D1" and _has_table(conn, "Fact_Market_Prices_D1"):
        table_name = "Fact_Market_Prices_D1"

    if table_name in ("Fact_Market_Prices_H4", "Fact_Market_Prices_D1"):
        query = f"""
            SELECT Timestamp, "Open", High, Low, "Close", Volume
            FROM {table_name}
            WHERE Asset_ID = %s
        """
        params = [asset_id]
    else:
        query = """
            SELECT Timestamp, "Open", High, Low, "Close", Volume
            FROM Fact_Market_Prices
            WHERE Asset_ID = %s AND Granularity = %s
        """
        params = [asset_id, granularity]

    if start_date:
        query += " AND Timestamp >= %s"
        params.append(start_date)
    if end_date:
        query += " AND Timestamp <= %s"
        params.append(end_date)

    query += " ORDER BY Timestamp"

    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        columns = [col[0] for col in cursor.description]
        df = pd.DataFrame.from_records(rows, columns=columns)
        if not df.empty:
            numeric_cols = ["Open", "High", "Low", "Close", "Volume"]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            df["Timestamp"] = pd.to_datetime(df["Timestamp"])
        if not df.empty:
            df.set_index("Timestamp", inplace=True)
        logger.info(f"Loaded {len(df)} rows for Asset_ID={asset_id}, Granularity={granularity}")
        return df
    finally:
        if close_conn:
            conn.close()


def get_asset_symbol_map(conn: Optional[psycopg2.extensions.connection] = None,
                         env_path: Optional[str] = None) -> Dict[int, str]:
    """
    Get a mapping of Asset_ID -> Symbol for all active assets.
    
    Returns:
        Dictionary mapping asset IDs to symbols
    """
    df = load_assets(conn, env_path)
    return dict(zip(df["Asset_ID"], df["Symbol"]))
