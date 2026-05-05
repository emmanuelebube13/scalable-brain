#!/usr/bin/env python3
"""
================================================================================
OANDA to PostgreSQL Price Ingestion Script - Scalable Brain Swing Trading System
================================================================================

🚀 SWING TRADING SYSTEM | Data Ingestion Layer

Production-grade ETL for ingesting OANDA candle data into Fact_Market_Prices.
This module supplies the historical and real-time price data needed for swing
trading signal generation (Layer 2) and regime detection (Layer 1) across H1, H4,
and D1 timeframes.

BUSINESS REQUIREMENTS:
- Ingest OANDA candles for all assets in Dim_Asset
- Support D1, H4, H1, M30, M15 granularities in a single table (via Granularity column)
- Resume mode: continue from MAX(Timestamp) per Asset_ID + Granularity
- Idempotent: safe to re-run repeatedly without duplicates

TECHNICAL REQUIREMENTS:
- Python 3 with oandapyV20 and psycopg2
- Window-based pagination (not huge count calls)
- Bid and Ask candles (price=BA), complete candles only (complete=true)
- INSERT ... ON CONFLICT upsert for duplicate prevention
- Rate limiting with exponential backoff and jitter
- Gap detection and logging for missing timestamps
- Bulk loading via PostgreSQL COPY for ingestion velocity

OPERATIONAL NOTES:
- Expected runtime: ~30-60 minutes for initial backfill (2006-present)
    - M15: largest candle count, longest runtime
    - M30: high candle count, moderate runtime
  - H1: ~150K candles per asset, ~30-40 min per asset
  - H4: ~37K candles per asset, ~8-10 min per asset
  - D1: ~6K candles per asset, ~2-3 min per asset
- Incremental runs: typically seconds to minutes depending on gap
- Safe to rerun: script is fully idempotent via INSERT ... ON CONFLICT upsert
- Resume mechanism: queries MAX(Timestamp) from Fact_Market_Prices
- Failures are logged but don't stop processing; summary shows all issues

USAGE EXAMPLES:
    # Full run - all assets, all granularities
    python ingest_oanda_prices.py

    # Single symbol only
    python ingest_oanda_prices.py --symbol EUR_USD

    # Single granularity only
    python ingest_oanda_prices.py --granularity H1

    # Combined filter
    python ingest_oanda_prices.py --symbol EUR_USD --granularity H4

    # Dry run (validate connections, show what would be processed)
    python ingest_oanda_prices.py --dry-run

================================================================================
"""

import os
import sys
import time
import json
import logging
import argparse
import random
import io
import csv
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
import re
from pathlib import Path

import psycopg2
from oandapyV20 import API
from oandapyV20.endpoints.instruments import InstrumentsCandles
from oandapyV20.exceptions import V20Error

# ==============================================================================
# CONFIGURATION - TUNABLE VALUES
# ==============================================================================

@dataclass
class IngestConfig:
    """Tunable configuration parameters for the ingestion process."""

    # Chunk sizes per granularity (duration of each API request window)
    # These balance API efficiency against memory and retry granularity
    CHUNK_DAYS: Dict[str, int] = field(default_factory=lambda: {
        "M15": 2,     # 2 days of 15m candles = ~192 candles
        "M30": 3,     # 3 days of 30m candles = ~144 candles
        "H1": 7,      # 7 days of hourly candles = ~168 candles
        "H4": 30,     # 30 days of 4H candles = ~180 candles
        "D1": 365,    # 365 days of daily candles = ~365 candles
    })

    # Processing order for full runs (higher timeframe first)
    PROCESS_GRANULARITIES: List[str] = field(default_factory=lambda: [
        "D1", "H4", "H1", "M30", "M15"
    ])

    # Sleep between API requests (seconds) - be nice to OANDA
    REQUEST_SLEEP_SECONDS: float = 0.5

    # Batch size for SQL upsert operations
    SQL_BATCH_SIZE: int = 1000

    # Retry configuration
    MAX_RETRIES: int = 5
    RETRY_BASE_DELAY: float = 1.0
    RETRY_MAX_DELAY: float = 60.0
    RETRY_BACKOFF_FACTOR: float = 2.0

    # Jitter range (0.0 to 1.0) - adds randomness to retry delays
    JITTER_FACTOR: float = 0.3

    # Rate limit handling
    RATE_LIMIT_STATUS_CODE: int = 429
    RATE_LIMIT_RETRY_AFTER_DEFAULT: int = 10

    # Default start date for new assets (no existing data)
    DEFAULT_START_DATE: datetime = field(
        default_factory=lambda: datetime(2006, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    )

    # OANDA API settings
    OANDA_PRICE: str = "BA"  # Bid + Ask candles
    OANDA_DEFAULT_URL: str = "https://api-fxpractice.oanda.com"

    # Logging
    LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(message)s"
    LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
    LOG_FILE: str = "oanda_ingest.log"


# Global config instance
CONFIG = IngestConfig()

# ==============================================================================
# LOGGING SETUP
# ==============================================================================

def setup_logging(log_file: Optional[str] = None) -> logging.Logger:
    """Configure structured logging to console and file."""
    log_file = log_file or CONFIG.LOG_FILE

    logger = logging.getLogger("oanda_ingest")
    logger.setLevel(logging.DEBUG)

    # Prevent duplicate handlers if called multiple times
    if logger.handlers:
        logger.handlers.clear()

    # Console handler (INFO and above)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(CONFIG.LOG_FORMAT, CONFIG.LOG_DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (DEBUG and above)
    file_handler = logging.FileHandler(log_file, mode="a")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        f"%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
        CONFIG.LOG_DATE_FORMAT
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger


logger = setup_logging()

# ==============================================================================
# ENVIRONMENT READING
# ==============================================================================

def clean_env_value(value: Optional[str]) -> Optional[str]:
    """
    Clean environment variable value by trimming whitespace and removing
    surrounding quotes (single or double).
    """
    if value is None:
        return None
    value = value.strip()
    if len(value) >= 2:
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
    return value.strip()


def load_repo_env_file() -> None:
    """Load key/value pairs from repo-root .env into process environment."""
    script_path = Path(__file__).resolve()
    env_path = None

    for candidate_root in script_path.parents:
        candidate_env = candidate_root / ".env"
        if candidate_env.exists():
            env_path = candidate_env
            break

    if env_path is None:
        logger.debug("No .env file found in script parent directories; using existing environment")
        return

    with env_path.open("r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, raw_value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue

            cleaned_value = clean_env_value(raw_value)
            os.environ[key] = cleaned_value or ""


def read_env() -> Dict[str, str]:
    """
    Read and validate all required environment variables.
    Returns cleaned dictionary of environment values.
    """
    load_repo_env_file()

    required_db_vars = ["DB_SERVER", "DB_USER", "DB_PASS", "DB_NAME"]
    required_oanda_vars = ["OANDA_API_KEY"]

    env = {}
    missing = []

    # Database variables
    for var in required_db_vars:
        value = clean_env_value(os.getenv(var))
        if not value:
            missing.append(var)
        env[var] = value or ""

    # Optional DB_PORT with default (PostgreSQL default is 5432)
    env["DB_PORT"] = clean_env_value(os.getenv("DB_PORT")) or "5432"

    # OANDA variables
    for var in required_oanda_vars:
        value = clean_env_value(os.getenv(var))
        if not value:
            missing.append(var)
        env[var] = value or ""

    # OANDA account ID (try DEMO first, then regular)
    oanda_account = clean_env_value(os.getenv("OANDA_ACCOUNT_ID_DEMO"))
    if not oanda_account:
        oanda_account = clean_env_value(os.getenv("OANDA_ACCOUNT_ID"))
    if not oanda_account:
        missing.append("OANDA_ACCOUNT_ID_DEMO or OANDA_ACCOUNT_ID")
    env["OANDA_ACCOUNT_ID"] = oanda_account or ""

    # OANDA URL with default
    oanda_url = clean_env_value(os.getenv("OANDA_URL"))
    env["OANDA_URL"] = oanda_url or CONFIG.OANDA_DEFAULT_URL

    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    # Mask sensitive values in logs
    log_env = {k: "***" if "PASS" in k or "KEY" in k else v for k, v in env.items()}
    logger.debug(f"Environment loaded: {log_env}")

    return env


# ==============================================================================
# DATABASE CONNECTION
# ==============================================================================

def get_db_connection(env: Dict[str, str]) -> psycopg2.extensions.connection:
    """Create and return a PostgreSQL database connection."""
    try:
        conn = psycopg2.connect(
            host=env['DB_SERVER'],
            dbname=env['DB_NAME'],
            user=env['DB_USER'],
            password=env['DB_PASS'],
            port=env['DB_PORT'],
            connect_timeout=30,
        )
        logger.debug("Database connection established")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Failed to connect to database: {e}")
        raise


def ensure_schema(conn: psycopg2.extensions.connection) -> None:
    """
    Ensure Fact_Market_Prices has all required columns.
    Adds Bid/Ask columns if they are missing (idempotent).
    """
    cursor = conn.cursor()

    # Check if Bid_Open exists
    cursor.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE LOWER(table_name) = 'fact_market_prices'
        AND LOWER(column_name) = 'bid_open'
        LIMIT 1
    """)
    has_bid_ask = cursor.fetchone() is not None

    if not has_bid_ask:
        logger.info("Migrating Fact_Market_Prices: adding Bid/Ask columns")
        cursor.execute("""
            ALTER TABLE Fact_Market_Prices
            ADD COLUMN IF NOT EXISTS Bid_Open NUMERIC(19, 6),
            ADD COLUMN IF NOT EXISTS Bid_High NUMERIC(19, 6),
            ADD COLUMN IF NOT EXISTS Bid_Low NUMERIC(19, 6),
            ADD COLUMN IF NOT EXISTS Bid_Close NUMERIC(19, 6),
            ADD COLUMN IF NOT EXISTS Ask_Open NUMERIC(19, 6),
            ADD COLUMN IF NOT EXISTS Ask_High NUMERIC(19, 6),
            ADD COLUMN IF NOT EXISTS Ask_Low NUMERIC(19, 6),
            ADD COLUMN IF NOT EXISTS Ask_Close NUMERIC(19, 6);
        """)
        conn.commit()
        logger.info("Schema migration complete")
    else:
        logger.debug("Fact_Market_Prices schema is up to date")


# ==============================================================================
# ASSET RETRIEVAL
# ==============================================================================

def get_assets(conn: psycopg2.extensions.connection, symbol_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieve assets from Dim_Asset table.

    Args:
        conn: Database connection
        symbol_filter: Optional single symbol to filter (e.g., "EUR_USD")

    Returns:
        List of dicts with Asset_ID and Symbol
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT data_type
        FROM information_schema.columns
        WHERE LOWER(table_name) = 'dim_asset' AND LOWER(column_name) = 'is_active'
        LIMIT 1
        """
    )
    is_active_type_row = cursor.fetchone()
    has_is_active = is_active_type_row is not None
    is_active_data_type = is_active_type_row[0].lower() if has_is_active and is_active_type_row[0] else ""

    if is_active_data_type == "boolean":
        active_clause = "Is_Active IS TRUE"
    else:
        # Legacy compatibility for integer-ish schemas.
        active_clause = "Is_Active = 1"

    if symbol_filter:
        # Validate symbol format (basic OANDA instrument validation)
        if not re.match(r'^[A-Z0-9]+_[A-Z0-9]+$', symbol_filter):
            raise ValueError(f"Invalid symbol format: {symbol_filter}. Expected format: XXX_YYY")

        if has_is_active:
            query = f"SELECT Asset_ID, Symbol FROM Dim_Asset WHERE Symbol = %s AND {active_clause}"
        else:
            query = "SELECT Asset_ID, Symbol FROM Dim_Asset WHERE Symbol = %s"
        cursor.execute(query, (symbol_filter,))
    else:
        if has_is_active:
            query = f"SELECT Asset_ID, Symbol FROM Dim_Asset WHERE {active_clause} ORDER BY Asset_ID"
        else:
            query = "SELECT Asset_ID, Symbol FROM Dim_Asset ORDER BY Asset_ID"
        cursor.execute(query)

    assets = [{"Asset_ID": row[0], "Symbol": row[1]} for row in cursor.fetchall()]

    if symbol_filter and not assets:
        if has_is_active:
            raise ValueError(f"Symbol {symbol_filter} not found in Dim_Asset or not active")
        raise ValueError(f"Symbol {symbol_filter} not found in Dim_Asset")

    logger.info(f"Retrieved {len(assets)} assets from Dim_Asset" +
                (f" (filtered to {symbol_filter})" if symbol_filter else ""))

    return assets


# ==============================================================================
# RESUME TIMESTAMP QUERY
# ==============================================================================

def get_resume_timestamp(
    conn: psycopg2.extensions.connection,
    asset_id: int,
    granularity: str
) -> datetime:
    """
    Get the timestamp to resume from for a given asset and granularity.

    Args:
        conn: Database connection
        asset_id: The Asset_ID to query
        granularity: The granularity (D1, H4, H1, M30, M15)

    Returns:
        datetime to start from (next candle after MAX(Timestamp), or default start)
    """
    cursor = conn.cursor()

    query = """
        SELECT MAX(Timestamp)
        FROM Fact_Market_Prices
        WHERE Asset_ID = %s AND Granularity = %s
    """
    cursor.execute(query, (asset_id, granularity))
    result = cursor.fetchone()

    max_timestamp = result[0] if result and result[0] else None

    if max_timestamp:
        # Resume from next candle after the last one we have
        next_ts = max_timestamp + get_interval_delta(granularity)
        logger.debug(f"Resuming Asset_ID={asset_id}, {granularity} from {next_ts} (after {max_timestamp})")
        return next_ts
    else:
        # No existing data - start from default
        logger.debug(f"No existing data for Asset_ID={asset_id}, {granularity}. Starting from {CONFIG.DEFAULT_START_DATE}")
        return CONFIG.DEFAULT_START_DATE


def get_interval_delta(granularity: str) -> timedelta:
    """Get the timedelta for one candle interval based on granularity."""
    deltas = {
        "M15": timedelta(minutes=15),
        "M30": timedelta(minutes=30),
        "H1": timedelta(hours=1),
        "H4": timedelta(hours=4),
        "D1": timedelta(days=1),
    }
    if granularity not in deltas:
        raise ValueError(f"Unsupported granularity: {granularity}")
    return deltas[granularity]


def to_oanda_granularity(granularity: str) -> str:
    """Map internal granularity names to OANDA API-compatible names."""
    mapping = {
        "M15": "M15",
        "M30": "M30",
        "H1": "H1",
        "H4": "H4",
        "D1": "D",
    }
    if granularity not in mapping:
        raise ValueError(f"Unsupported granularity for OANDA API: {granularity}")
    return mapping[granularity]


def normalize_granularity(granularity: Optional[str]) -> Optional[str]:
    """Normalize user-provided granularity and validate supported values."""
    if granularity is None:
        return None

    normalized = granularity.strip().upper()
    if normalized not in CONFIG.PROCESS_GRANULARITIES:
        raise ValueError(
            f"Invalid granularity: {granularity}. Must be one of {CONFIG.PROCESS_GRANULARITIES}"
        )
    return normalized


def normalize_granularity_list(granularities: Optional[str]) -> Optional[List[str]]:
    """Normalize comma-separated granularity input preserving defined order."""
    if granularities is None:
        return None

    raw_items = [item.strip().upper() for item in granularities.split(',') if item.strip()]
    if not raw_items:
        raise ValueError("--granularities was provided but no values were found")

    invalid = [g for g in raw_items if g not in CONFIG.PROCESS_GRANULARITIES]
    if invalid:
        raise ValueError(
            f"Invalid granularities: {invalid}. Must be subset of {CONFIG.PROCESS_GRANULARITIES}"
        )

    selected = set(raw_items)
    return [g for g in CONFIG.PROCESS_GRANULARITIES if g in selected]


# ==============================================================================
# OANDA API INTERACTION
# ==============================================================================

def create_oanda_client(env: Dict[str, str]) -> API:
    """Create and return an OANDA API client."""
    return API(
        access_token=env["OANDA_API_KEY"],
        environment="practice" if "practice" in env["OANDA_URL"] else "live"
    )


def calculate_jitter(base_delay: float) -> float:
    """Add random jitter to delay to prevent thundering herd."""
    jitter = base_delay * CONFIG.JITTER_FACTOR * (2 * random.random() - 1)
    return base_delay + jitter


def exponential_backoff_with_jitter(attempt: int) -> float:
    """Calculate delay with exponential backoff and jitter."""
    delay = min(
        CONFIG.RETRY_BASE_DELAY * (CONFIG.RETRY_BACKOFF_FACTOR ** attempt),
        CONFIG.RETRY_MAX_DELAY
    )
    return calculate_jitter(delay)


def fetch_candles_window(
    client: API,
    instrument: str,
    granularity: str,
    from_ts: datetime,
    to_ts: datetime,
    attempt: int = 0
) -> Tuple[List[Dict], int]:
    """
    Fetch candles from OANDA for a specific time window.

    Args:
        client: OANDA API client
        instrument: OANDA instrument symbol (e.g., "EUR_USD")
        granularity: Candle granularity (D1, H4, H1, M30, M15)
        from_ts: Start timestamp (inclusive)
        to_ts: End timestamp (exclusive)
        attempt: Current retry attempt

    Returns:
        Tuple of (list of candle dicts, http status code)
    """
    params = {
        "price": CONFIG.OANDA_PRICE,
        "granularity": to_oanda_granularity(granularity),
        "from": from_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to": to_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "includeFirst": True,
    }

    request = InstrumentsCandles(instrument=instrument, params=params)

    try:
        response = client.request(request)
        candles = response.get("candles", [])
        return candles, 200

    except V20Error as e:
        status_code = getattr(e, 'code', 500)
        logger.warning(f"OANDA API error for {instrument} {granularity}: {e} (status={status_code})")
        return [], status_code

    except Exception as e:
        logger.warning(f"Unexpected error fetching candles for {instrument} {granularity}: {e}")
        return [], 0


def fetch_candles_with_retry(
    client: API,
    instrument: str,
    granularity: str,
    from_ts: datetime,
    to_ts: datetime
) -> Tuple[List[Dict], bool, int]:
    """
    Fetch candles with retry logic for transient failures.

    Returns:
        Tuple of (candles list, success boolean, total attempts made)
    """
    for attempt in range(CONFIG.MAX_RETRIES):
        candles, status_code = fetch_candles_window(
            client, instrument, granularity, from_ts, to_ts, attempt
        )

        # Success case
        if status_code == 200:
            return candles, True, attempt + 1

        # Rate limit - use Retry-After if available
        if status_code == CONFIG.RATE_LIMIT_STATUS_CODE:
            retry_after = CONFIG.RATE_LIMIT_RETRY_AFTER_DEFAULT
            logger.warning(f"Rate limited (429). Waiting {retry_after}s before retry {attempt + 1}/{CONFIG.MAX_RETRIES}")
            time.sleep(retry_after)
            continue

        # Server errors (5xx) - retry with backoff
        if 500 <= status_code < 600:
            delay = exponential_backoff_with_jitter(attempt)
            logger.warning(f"Server error ({status_code}). Waiting {delay:.2f}s before retry {attempt + 1}/{CONFIG.MAX_RETRIES}")
            time.sleep(delay)
            continue

        # Client errors (4xx except 429) - don't retry
        if 400 <= status_code < 500:
            logger.error(f"Client error ({status_code}). Not retrying.")
            return [], False, attempt + 1

        # Other errors - retry with backoff
        delay = exponential_backoff_with_jitter(attempt)
        logger.warning(f"Error (status={status_code}). Waiting {delay:.2f}s before retry {attempt + 1}/{CONFIG.MAX_RETRIES}")
        time.sleep(delay)

    # Max retries exceeded
    logger.error(f"Max retries ({CONFIG.MAX_RETRIES}) exceeded for {instrument} {granularity}")
    return [], False, CONFIG.MAX_RETRIES


# ==============================================================================
# CANDLE TRANSFORMATION
# ==============================================================================

def parse_rfc3339_to_datetime(time_str: str) -> Optional[datetime]:
    """
    Safely parse OANDA RFC3339 timestamp to timezone-aware UTC datetime.

    OANDA format: "2023-01-15T14:30:00.000000000Z" or "2023-01-15T14:30:00Z"
    """
    try:
        # Handle various RFC3339 formats
        time_str = time_str.replace('Z', '+00:00')

        # Python 3.7+ fromisoformat handles this
        dt = datetime.fromisoformat(time_str)

        # Ensure UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        # Return timezone-aware datetime for PostgreSQL TIMESTAMPTZ
        return dt

    except (ValueError, AttributeError) as e:
        logger.warning(f"Failed to parse timestamp '{time_str}': {e}")
        return None


def transform_candles(
    candles: List[Dict],
    asset_id: int,
    granularity: str
) -> Tuple[List[Tuple], int, int]:
    """
    Transform OANDA candle data to database row format.

    Extracts both Bid and Ask prices. Mid prices are computed as the arithmetic
    mean of Bid and Ask for backward compatibility with existing queries.

    Args:
        candles: List of OANDA candle dicts
        asset_id: The Asset_ID for these candles
        granularity: The granularity string

    Returns:
        Tuple of (list of DB row tuples, valid count, skipped incomplete count)
    """
    rows = []
    skipped = 0

    for candle in candles:
        # Skip incomplete candles
        if not candle.get("complete", False):
            skipped += 1
            continue

        # Parse timestamp
        timestamp = parse_rfc3339_to_datetime(candle.get("time", ""))
        if timestamp is None:
            skipped += 1
            continue

        # Extract bid and ask prices
        bid = candle.get("bid", {})
        ask = candle.get("ask", {})
        if not bid or not ask:
            logger.warning(f"Missing bid or ask prices for candle at {timestamp}")
            skipped += 1
            continue

        try:
            bid_open = Decimal(bid.get("o", "0"))
            bid_high = Decimal(bid.get("h", "0"))
            bid_low = Decimal(bid.get("l", "0"))
            bid_close = Decimal(bid.get("c", "0"))

            ask_open = Decimal(ask.get("o", "0"))
            ask_high = Decimal(ask.get("h", "0"))
            ask_low = Decimal(ask.get("l", "0"))
            ask_close = Decimal(ask.get("c", "0"))

            # Compute mid prices for backward compatibility
            open_price = ((bid_open + ask_open) / Decimal("2")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            high_price = ((bid_high + ask_high) / Decimal("2")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            low_price = ((bid_low + ask_low) / Decimal("2")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            close_price = ((bid_close + ask_close) / Decimal("2")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

            volume = int(candle.get("volume", 0))
        except (InvalidOperation, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse price values for candle at {timestamp}: {e}")
            skipped += 1
            continue

        # Validate price logic
        if bid_high < bid_low or ask_high < ask_low:
            logger.warning(f"Invalid high/low price for candle at {timestamp}")
            skipped += 1
            continue

        row = (
            asset_id,
            timestamp,
            open_price,
            high_price,
            low_price,
            close_price,
            bid_open,
            bid_high,
            bid_low,
            bid_close,
            ask_open,
            ask_high,
            ask_low,
            ask_close,
            volume,
            granularity
        )
        rows.append(row)

    return rows, len(rows), skipped


# ==============================================================================
# GAP DETECTION
# ==============================================================================

def is_forex_market_open(dt: datetime) -> bool:
    """
    Rough heuristic for whether the forex market is typically open.
    Used to suppress false-positive gap warnings during known market closures.
    """
    weekday = dt.weekday()
    if weekday == 5:  # Saturday
        return False
    if weekday == 6 and dt.hour < 21:  # Sunday before ~21:00 UTC
        return False
    if weekday == 4 and dt.hour >= 22:  # Friday after ~22:00 UTC
        return False
    return True


def detect_gaps(
    from_ts: datetime,
    to_ts: datetime,
    granularity: str,
    rows: List[Tuple],
    symbol: str
) -> List[datetime]:
    """
    Detect missing timestamps in the expected sequence.

    Generates a perfect array of expected timestamps and compares against
    what the API returned. Logs gaps for later reconciliation.
    """
    interval = get_interval_delta(granularity)
    expected_timestamps = []
    current = from_ts
    while current < to_ts:
        if is_forex_market_open(current):
            expected_timestamps.append(current)
        current += interval

    actual_timestamps = {row[1] for row in rows}
    gaps = [ts for ts in expected_timestamps if ts not in actual_timestamps]

    if gaps:
        logger.warning(
            f"Detected {len(gaps)} gap(s) for {symbol} {granularity} "
            f"between {from_ts} and {to_ts}"
        )
        for gap in gaps[:5]:
            logger.warning(f"  Missing timestamp: {gap}")
        if len(gaps) > 5:
            logger.warning(f"  ... and {len(gaps) - 5} more")

    return gaps


# ==============================================================================
# DATABASE UPSERT
# ==============================================================================

def upsert_batch(
    conn: psycopg2.extensions.connection,
    rows: List[Tuple]
) -> Tuple[int, int]:
    """
    Upsert a batch of rows using INSERT ... ON CONFLICT with PostgreSQL COPY.

    Uses COPY FROM STDIN for high-velocity bulk loading into a temp table,
    then upserts into the target table via ON CONFLICT.

    Args:
        conn: Database connection
        rows: List of row tuples (
            Asset_ID, Timestamp, Open, High, Low, Close,
            Bid_Open, Bid_High, Bid_Low, Bid_Close,
            Ask_Open, Ask_High, Ask_Low, Ask_Close,
            Volume, Granularity
        )

    Returns:
        Tuple of (inserted count, updated count)
    """
    if not rows:
        return 0, 0

    cursor = conn.cursor()

    # Create temp table with fixed-point numeric types for prices
    cursor.execute("""
        CREATE TEMP TABLE batch_candles (
            Asset_ID INT,
            Timestamp TIMESTAMPTZ,
            "Open" NUMERIC(19,6),
            High NUMERIC(19,6),
            Low NUMERIC(19,6),
            "Close" NUMERIC(19,6),
            Bid_Open NUMERIC(19,6),
            Bid_High NUMERIC(19,6),
            Bid_Low NUMERIC(19,6),
            Bid_Close NUMERIC(19,6),
            Ask_Open NUMERIC(19,6),
            Ask_High NUMERIC(19,6),
            Ask_Low NUMERIC(19,6),
            Ask_Close NUMERIC(19,6),
            Volume INT,
            Granularity VARCHAR(10)
        )
    """)

    # Bulk load via COPY (institutional standard for velocity)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    for row in rows:
        writer.writerow(row)
    buffer.seek(0)

    cursor.copy_expert("""
        COPY batch_candles (
            Asset_ID, Timestamp, "Open", High, Low, "Close",
            Bid_Open, Bid_High, Bid_Low, Bid_Close,
            Ask_Open, Ask_High, Ask_Low, Ask_Close,
            Volume, Granularity
        ) FROM STDIN WITH CSV
    """, buffer)

    # Upsert into target table
    upsert_sql = """
        INSERT INTO Fact_Market_Prices (
            Asset_ID, Timestamp, "Open", High, Low, "Close",
            Bid_Open, Bid_High, Bid_Low, Bid_Close,
            Ask_Open, Ask_High, Ask_Low, Ask_Close,
            Volume, Granularity
        )
        SELECT
            Asset_ID, Timestamp, "Open", High, Low, "Close",
            Bid_Open, Bid_High, Bid_Low, Bid_Close,
            Ask_Open, Ask_High, Ask_Low, Ask_Close,
            Volume, Granularity
        FROM batch_candles
        ON CONFLICT (Timestamp, Asset_ID, Granularity) DO UPDATE SET
            "Open" = EXCLUDED."Open",
            High = EXCLUDED.High,
            Low = EXCLUDED.Low,
            "Close" = EXCLUDED."Close",
            Bid_Open = EXCLUDED.Bid_Open,
            Bid_High = EXCLUDED.Bid_High,
            Bid_Low = EXCLUDED.Bid_Low,
            Bid_Close = EXCLUDED.Bid_Close,
            Ask_Open = EXCLUDED.Ask_Open,
            Ask_High = EXCLUDED.Ask_High,
            Ask_Low = EXCLUDED.Ask_Low,
            Ask_Close = EXCLUDED.Ask_Close,
            Volume = EXCLUDED.Volume;
    """

    cursor.execute(upsert_sql)

    # Get counts (approximate from rowcount)
    # Note: psycopg2 rowcount after INSERT ... ON CONFLICT may not give exact insert/update split
    total_affected = cursor.rowcount if cursor.rowcount >= 0 else len(rows)

    # Drop temp table
    cursor.execute("DROP TABLE IF EXISTS batch_candles")

    conn.commit()

    # Estimate split
    inserted = min(len(rows), total_affected)
    updated = max(0, total_affected - len(rows))

    return inserted, updated


# ==============================================================================
# MAIN PROCESSING LOGIC
# ==============================================================================

@dataclass
class ProcessingResult:
    """Result summary for a single asset+granularity processing run."""
    asset_id: int
    symbol: str
    granularity: str
    success: bool
    candles_fetched: int = 0
    rows_inserted: int = 0
    rows_updated: int = 0
    rows_skipped: int = 0
    api_requests: int = 0
    failed_windows: int = 0
    error_message: Optional[str] = None
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None

    @property
    def duration_seconds(self) -> float:
        end = self.end_time or datetime.now(timezone.utc)
        return (end - self.start_time).total_seconds()


def process_asset_granularity(
    db_conn: psycopg2.extensions.connection,
    oanda_client: API,
    asset: Dict[str, Any],
    granularity: str
) -> ProcessingResult:
    """
    Process all candles for a single asset and granularity.

    Args:
        db_conn: Database connection
        oanda_client: OANDA API client
        asset: Asset dict with Asset_ID and Symbol
        granularity: Granularity string (D1, H4, H1, M30, M15)

    Returns:
        ProcessingResult with summary statistics
    """
    result = ProcessingResult(
        asset_id=asset["Asset_ID"],
        symbol=asset["Symbol"],
        granularity=granularity,
        success=False
    )

    logger.info(f"Starting {asset['Symbol']} {granularity}")

    try:
        # Get resume point
        from_ts = get_resume_timestamp(db_conn, asset["Asset_ID"], granularity)
        now = datetime.now(timezone.utc)

        # Skip if already up to date (within one interval)
        if from_ts >= now - get_interval_delta(granularity):
            logger.info(f"{asset['Symbol']} {granularity} already up to date (last: {from_ts})")
            result.success = True
            result.end_time = datetime.now(timezone.utc)
            return result

        # Calculate chunk size
        chunk_days = CONFIG.CHUNK_DAYS.get(granularity, 7)
        interval_delta = get_interval_delta(granularity)

        batch_buffer = []

        while from_ts < now:
            # Calculate window end
            to_ts = min(from_ts + timedelta(days=chunk_days), now)

            logger.debug(f"Fetching {asset['Symbol']} {granularity}: {from_ts} to {to_ts}")

            # Fetch with retry
            candles, success, attempts = fetch_candles_with_retry(
                oanda_client, asset["Symbol"], granularity, from_ts, to_ts
            )

            result.api_requests += attempts

            if not success:
                logger.error(
                    f"CRITICAL: Failed to fetch {asset['Symbol']} {granularity} window {from_ts} to {to_ts}."
                )
                logger.error(
                    "Halting processing for this asset to prevent data gaps. Will resume from here on next run."
                )
                result.failed_windows += 1
                result.success = False

                # Flush any successfully fetched rows before stopping so the last committed
                # timestamp remains contiguous and the next run can resume from MAX(Timestamp).
                if batch_buffer:
                    inserted, updated = upsert_batch(db_conn, batch_buffer)
                    result.rows_inserted += inserted
                    result.rows_updated += updated
                    logger.debug(f"Flushed buffered rows before halt: {inserted} inserted, {updated} updated")
                    batch_buffer = []

                break  # Stop processing this asset entirely

            result.candles_fetched += len(candles)

            if candles:
                # Transform candles
                rows, valid_count, skipped_count = transform_candles(
                    candles, asset["Asset_ID"], granularity
                )
                result.rows_skipped += skipped_count

                # Detect gaps against expected timeline (skip on initial backfill)
                if rows and from_ts > CONFIG.DEFAULT_START_DATE:
                    detect_gaps(from_ts, to_ts, granularity, rows, asset['Symbol'])

                if rows:
                    batch_buffer.extend(rows)

                    # Flush batch if full
                    if len(batch_buffer) >= CONFIG.SQL_BATCH_SIZE:
                        inserted, updated = upsert_batch(db_conn, batch_buffer)
                        result.rows_inserted += inserted
                        result.rows_updated += updated
                        logger.debug(f"Flushed batch: {inserted} inserted, {updated} updated")
                        batch_buffer = []

                # Advance using last transformed row to avoid skipping valid candles
                if rows:
                    from_ts = rows[-1][1] + interval_delta
                else:
                    from_ts = to_ts
            else:
                # No candles in window - advance
                logger.debug(f"No candles returned for {asset['Symbol']} {granularity} {from_ts} to {to_ts}")
                from_ts = to_ts

            # Throttle
            time.sleep(CONFIG.REQUEST_SLEEP_SECONDS)

        # Flush remaining batch
        if batch_buffer:
            inserted, updated = upsert_batch(db_conn, batch_buffer)
            result.rows_inserted += inserted
            result.rows_updated += updated
            logger.debug(f"Flushed final batch: {inserted} inserted, {updated} updated")

        result.success = True
        logger.info(
            f"Completed {asset['Symbol']} {granularity}: "
            f"{result.candles_fetched} candles, {result.rows_inserted} inserted, "
            f"{result.rows_updated} updated, {result.rows_skipped} skipped, "
            f"{result.failed_windows} failed windows"
        )

    except Exception as e:
        result.success = False
        result.error_message = str(e)
        logger.error(f"Error processing {asset['Symbol']} {granularity}: {e}", exc_info=True)
        # Rollback to prevent transaction poisoning on subsequent iterations
        try:
            db_conn.rollback()
        except Exception as rollback_err:
            logger.warning(f"Rollback failed: {rollback_err}")

    result.end_time = datetime.now(timezone.utc)
    return result


# ==============================================================================
# VALIDATION QUERIES
# ==============================================================================

def run_validation_queries(conn: psycopg2.extensions.connection) -> Dict[str, Any]:
    """
    Run post-ingestion validation queries and return summaries.

    Returns:
        Dict with validation results
    """
    cursor = conn.cursor()
    results = {}

    # Row counts by asset and granularity
    logger.info("Running validation queries...")

    cursor.execute("""
        SELECT
            a.Symbol,
            fmp.Granularity,
            COUNT(*) as TotalRows,
            MIN(fmp.Timestamp) as MinTimestamp,
            MAX(fmp.Timestamp) as MaxTimestamp
        FROM Fact_Market_Prices fmp
        JOIN Dim_Asset a ON fmp.Asset_ID = a.Asset_ID
        GROUP BY a.Symbol, fmp.Granularity
        ORDER BY a.Symbol, fmp.Granularity
    """)

    by_asset_granularity = []
    for row in cursor.fetchall():
        by_asset_granularity.append({
            "symbol": row[0],
            "granularity": row[1],
            "row_count": row[2],
            "min_timestamp": row[3],
            "max_timestamp": row[4]
        })

    results["by_asset_granularity"] = by_asset_granularity

    # Overall totals
    cursor.execute("""
        SELECT
            Granularity,
            COUNT(*) as TotalRows,
            COUNT(DISTINCT Asset_ID) as AssetCount
        FROM Fact_Market_Prices
        GROUP BY Granularity
        ORDER BY CASE Granularity
            WHEN 'D1' THEN 1
            WHEN 'H4' THEN 2
            WHEN 'H1' THEN 3
            WHEN 'M30' THEN 4
            WHEN 'M15' THEN 5
            ELSE 99
        END
    """)

    totals_by_granularity = []
    for row in cursor.fetchall():
        totals_by_granularity.append({
            "granularity": row[0],
            "total_rows": row[1],
            "asset_count": row[2]
        })

    results["totals_by_granularity"] = totals_by_granularity

    # Grand total
    cursor.execute("SELECT COUNT(*) FROM Fact_Market_Prices")
    results["grand_total"] = cursor.fetchone()[0]

    return results


def print_validation_results(results: Dict[str, Any]) -> None:
    """Print validation results in a readable format."""
    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)

    print(f"\nGrand Total Rows: {results.get('grand_total', 0):,}")

    print("\n--- Totals by Granularity ---")
    for gran in results.get("totals_by_granularity", []):
        print(f"  {gran['granularity']}: {gran['total_rows']:,} rows across {gran['asset_count']} assets")

    print("\n--- Per Asset/Granularity Summary (first 20) ---")
    for item in results.get("by_asset_granularity", [])[:20]:
        print(f"  {item['symbol']} {item['granularity']}: {item['row_count']:,} rows "
              f"({item['min_timestamp']} to {item['max_timestamp']})")

    remaining = len(results.get("by_asset_granularity", [])) - 20
    if remaining > 0:
        print(f"  ... and {remaining} more")

    print("=" * 80)


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================

def run(
    symbol_filter: Optional[str] = None,
    granularity_filter: Optional[str] = None,
    granularities_filter: Optional[str] = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Main entry point for OANDA price ingestion.

    Args:
        symbol_filter: Optional single symbol to process
        granularity_filter: Optional single granularity to process
        dry_run: If True, only validate connections and show what would be processed

    Returns:
        Summary dict with processing statistics
    """
    start_time = datetime.now(timezone.utc)
    logger.info("=" * 80)
    logger.info("OANDA Price Ingestion Started")
    logger.info(f"Symbol filter: {symbol_filter or 'None (all assets)'}")
    logger.info(f"Granularity filter: {granularity_filter or 'None (D1, H4, H1, M30, M15)'}")
    logger.info(f"Granularities filter: {granularities_filter or 'None'}")
    logger.info(f"Dry run: {dry_run}")
    logger.info("=" * 80)

    # Read environment
    try:
        env = read_env()
        logger.info("Environment variables loaded successfully")
    except ValueError as e:
        logger.error(f"Environment configuration error: {e}")
        raise

    # Determine granularities to process
    all_granularities = CONFIG.PROCESS_GRANULARITIES
    normalized_filter = normalize_granularity(granularity_filter)
    normalized_filter_list = normalize_granularity_list(granularities_filter)

    if normalized_filter and normalized_filter_list:
        raise ValueError("Use either --granularity or --granularities, not both")

    if normalized_filter:
        granularities = [normalized_filter]
    elif normalized_filter_list:
        granularities = normalized_filter_list
    else:
        granularities = all_granularities

    # Dry run - just validate connections
    if dry_run:
        logger.info("DRY RUN MODE - Validating connections...")
        try:
            db_conn = get_db_connection(env)
            assets = get_assets(db_conn, symbol_filter)
            logger.info(f"Would process {len(assets)} assets x {len(granularities)} granularities = {len(assets) * len(granularities)} combinations")
            db_conn.close()

            # Test OANDA connection
            oanda_client = create_oanda_client(env)
            logger.info("OANDA API client created successfully")

            logger.info("Dry run completed successfully - all connections validated")
            return {"status": "dry_run_success", "assets": len(assets), "granularities": len(granularities)}
        except Exception as e:
            logger.error(f"Dry run failed: {e}")
            raise

    # Production run
    db_conn = get_db_connection(env)
    ensure_schema(db_conn)
    oanda_client = create_oanda_client(env)

    try:
        assets = get_assets(db_conn, symbol_filter)
    except ValueError as e:
        logger.error(f"Asset retrieval failed: {e}")
        db_conn.close()
        raise

    # Process all combinations
    all_results: List[ProcessingResult] = []
    total_combinations = len(assets) * len(granularities)
    processed = 0

    for asset in assets:
        for granularity in granularities:
            processed += 1
            logger.info(f"Processing combination {processed}/{total_combinations}: {asset['Symbol']} {granularity}")

            result = process_asset_granularity(db_conn, oanda_client, asset, granularity)
            all_results.append(result)

            # Log progress every 10 combinations
            if processed % 10 == 0:
                successful = sum(1 for r in all_results if r.success)
                logger.info(f"Progress: {processed}/{total_combinations} combinations, {successful} successful")

    # Close connections
    db_conn.close()

    # Compile summary
    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    successful_results = [r for r in all_results if r.success]
    failed_results = [r for r in all_results if not r.success]

    summary = {
        "status": "completed",
        "duration_seconds": duration,
        "total_assets": len(assets),
        "total_combinations": total_combinations,
        "successful_combinations": len(successful_results),
        "failed_combinations": len(failed_results),
        "total_api_requests": sum(r.api_requests for r in all_results),
        "total_candles_fetched": sum(r.candles_fetched for r in all_results),
        "total_rows_inserted": sum(r.rows_inserted for r in all_results),
        "total_rows_updated": sum(r.rows_updated for r in all_results),
        "total_rows_skipped": sum(r.rows_skipped for r in all_results),
        "total_failed_windows": sum(r.failed_windows for r in all_results),
        "failures": [
            {"symbol": r.symbol, "granularity": r.granularity, "error": r.error_message}
            for r in failed_results
        ]
    }

    # Print summary
    print("\n" + "=" * 80)
    print("INGESTION SUMMARY")
    print("=" * 80)
    print(f"Duration: {duration:.2f} seconds ({duration/60:.2f} minutes)")
    print(f"Assets processed: {summary['total_assets']}")
    print(f"Combinations: {summary['total_combinations']}")
    print(f"Successful: {summary['successful_combinations']}")
    print(f"Failed: {summary['failed_combinations']}")
    print(f"Total API requests: {summary['total_api_requests']}")
    print(f"Total candles fetched: {summary['total_candles_fetched']:,}")
    print(f"Total rows inserted: {summary['total_rows_inserted']:,}")
    print(f"Total rows updated: {summary['total_rows_updated']:,}")
    print(f"Total rows skipped (incomplete/invalid): {summary['total_rows_skipped']:,}")
    print(f"Total failed windows: {summary['total_failed_windows']}")

    if failed_results:
        print("\n--- FAILURES ---")
        for r in failed_results:
            print(f"  {r.symbol} {r.granularity}: {r.error_message}")

    print("=" * 80)

    # Run validation queries
    db_conn = get_db_connection(env)
    try:
        validation_results = run_validation_queries(db_conn)
        print_validation_results(validation_results)
        summary["validation"] = validation_results
    finally:
        db_conn.close()

    logger.info("OANDA Price Ingestion Completed")

    return summary


def main():
    """CLI entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="OANDA to PostgreSQL Price Ingestion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full run - all assets, all granularities
    python ingest_oanda_prices.py

  # Single symbol only
    python ingest_oanda_prices.py --symbol EUR_USD

  # Single granularity only
    python ingest_oanda_prices.py --granularity H1

  # Combined filter
    python ingest_oanda_prices.py --symbol EUR_USD --granularity H4

    # Intraday additions
    python ingest_oanda_prices.py --granularity M30
    python ingest_oanda_prices.py --granularity M15

    # Multiple granularities in one run
    python ingest_oanda_prices.py --granularities D1,H4,H1,M30,M15

  # Dry run (validate connections, show what would be processed)
    python ingest_oanda_prices.py --dry-run
        """
    )

    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="Process only this symbol (e.g., EUR_USD)"
    )

    parser.add_argument(
        "--granularity",
        type=str,
        default=None,
        help="Process only this granularity (D1, H4, H1, M30, M15)"
    )

    parser.add_argument(
        "--granularities",
        type=str,
        default=None,
        help="Process selected granularities as comma-separated values (e.g., D1,H4,H1,M30,M15)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate connections without ingesting data"
    )

    parser.add_argument(
        "--log-file",
        type=str,
        default="oanda_ingest.log",
        help="Log file path (default: oanda_ingest.log)"
    )

    args = parser.parse_args()

    # Reconfigure logging with custom log file if specified
    global logger
    if args.log_file != CONFIG.LOG_FILE:
        logger = setup_logging(args.log_file)

    try:
        summary = run(
            symbol_filter=args.symbol,
            granularity_filter=args.granularity,
            granularities_filter=args.granularities,
            dry_run=args.dry_run
        )

        # Exit with error code if any failures
        if summary.get("failed_combinations", 0) > 0:
            sys.exit(1)

        sys.exit(0)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
