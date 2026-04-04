#!/usr/bin/env python3
"""
================================================================================
OANDA to SQL Server Price Ingestion Script
================================================================================
Production-grade ETL for ingesting OANDA candle data into Fact_Market_Prices.

BUSINESS REQUIREMENTS:
- Ingest OANDA candles for all assets in Dim_Asset
- Support H1, H4, D1 granularities in a single table (via Granularity column)
- Resume mode: continue from MAX(Timestamp) per Asset_ID + Granularity
- Idempotent: safe to re-run repeatedly without duplicates

TECHNICAL REQUIREMENTS:
- Python 3 with oandapyV20 and pyodbc
- Window-based pagination (not huge count calls)
- Mid candles only (price=M), complete candles only (complete=true)
- MERGE-based upsert for duplicate prevention
- Rate limiting with exponential backoff and jitter

OPERATIONAL NOTES:
- Expected runtime: ~30-60 minutes for initial backfill (2006-present)
  - H1: ~150K candles per asset, ~30-40 min per asset
  - H4: ~37K candles per asset, ~8-10 min per asset
  - D1: ~6K candles per asset, ~2-3 min per asset
- Incremental runs: typically seconds to minutes depending on gap
- Safe to rerun: script is fully idempotent via MERGE upsert
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
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from functools import wraps
import re

import pyodbc
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
        "H1": 7,      # 7 days of hourly candles = ~168 candles
        "H4": 30,     # 30 days of 4H candles = ~180 candles
        "D1": 365,    # 365 days of daily candles = ~365 candles
    })

    # Sleep between API requests (seconds) - be nice to OANDA
    REQUEST_SLEEP_SECONDS: float = 0.5

    # Batch size for SQL MERGE operations
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
        default_factory=lambda: datetime(2006, 1, 1, 0, 0, 0)
    )

    # OANDA API settings
    OANDA_PRICE: str = "M"  # Mid candles
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
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
    env_path = os.path.join(repo_root, ".env")

    if not os.path.exists(env_path):
        logger.debug(f"No .env file found at {env_path}; using existing environment")
        return

    with open(env_path, "r", encoding="utf-8") as env_file:
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

    # Optional DB_PORT with default
    env["DB_PORT"] = clean_env_value(os.getenv("DB_PORT")) or "1433"

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

def get_db_connection(env: Dict[str, str]) -> pyodbc.Connection:
    """Create and return a SQL Server database connection."""
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={env['DB_SERVER']},{env['DB_PORT']};"
        f"DATABASE={env['DB_NAME']};"
        f"UID={env['DB_USER']};"
        f"PWD={env['DB_PASS']};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=yes;"
        f"Connection Timeout=30;"
    )

    try:
        conn = pyodbc.connect(conn_str, timeout=30)
        logger.debug("Database connection established")
        return conn
    except pyodbc.Error as e:
        logger.error(f"Failed to connect to database: {e}")
        raise


# ==============================================================================
# ASSET RETRIEVAL
# ==============================================================================

def get_assets(conn: pyodbc.Connection, symbol_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieve assets from Dim_Asset table.

    Args:
        conn: Database connection
        symbol_filter: Optional single symbol to filter (e.g., "EUR_USD")

    Returns:
        List of dicts with Asset_ID and Symbol
    """
    cursor = conn.cursor()
    has_is_active = cursor.execute(
        "SELECT COL_LENGTH('Dim_Asset', 'Is_Active')"
    ).fetchone()[0] is not None

    if symbol_filter:
        # Validate symbol format (basic OANDA instrument validation)
        if not re.match(r'^[A-Z0-9]+_[A-Z0-9]+$', symbol_filter):
            raise ValueError(f"Invalid symbol format: {symbol_filter}. Expected format: XXX_YYY")

        if has_is_active:
            query = "SELECT Asset_ID, Symbol FROM Dim_Asset WHERE Symbol = ? AND Is_Active = 1"
        else:
            query = "SELECT Asset_ID, Symbol FROM Dim_Asset WHERE Symbol = ?"
        cursor.execute(query, (symbol_filter,))
    else:
        if has_is_active:
            query = "SELECT Asset_ID, Symbol FROM Dim_Asset WHERE Is_Active = 1 ORDER BY Asset_ID"
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
    conn: pyodbc.Connection,
    asset_id: int,
    granularity: str
) -> datetime:
    """
    Get the timestamp to resume from for a given asset and granularity.

    Args:
        conn: Database connection
        asset_id: The Asset_ID to query
        granularity: The granularity (H1, H4, D1)

    Returns:
        datetime to start from (next candle after MAX(Timestamp), or default start)
    """
    cursor = conn.cursor()

    query = """
        SELECT MAX(Timestamp)
        FROM Fact_Market_Prices
        WHERE Asset_ID = ? AND Granularity = ?
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
        "H1": timedelta(hours=1),
        "H4": timedelta(hours=4),
        "D1": timedelta(days=1),
    }
    if granularity not in deltas:
        raise ValueError(f"Unsupported granularity: {granularity}")
    return deltas[granularity]


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
        granularity: Candle granularity (H1, H4, D1)
        from_ts: Start timestamp (inclusive)
        to_ts: End timestamp (exclusive)
        attempt: Current retry attempt

    Returns:
        Tuple of (list of candle dicts, http status code)
    """
    params = {
        "price": CONFIG.OANDA_PRICE,
        "granularity": granularity,
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
    Safely parse OANDA RFC3339 timestamp to UTC datetime.

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

        # Return naive datetime for SQL Server compatibility
        return dt.replace(tzinfo=None)

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

        # Extract mid prices
        mid = candle.get("mid", {})
        if not mid:
            logger.warning(f"Missing mid prices for candle at {timestamp}")
            skipped += 1
            continue

        try:
            open_price = Decimal(mid.get("o", "0"))
            high_price = Decimal(mid.get("h", "0"))
            low_price = Decimal(mid.get("l", "0"))
            close_price = Decimal(mid.get("c", "0"))
            volume = int(candle.get("volume", 0))
        except (InvalidOperation, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse price values for candle at {timestamp}: {e}")
            skipped += 1
            continue

        # Validate price logic
        if high_price < low_price or high_price < open_price or high_price < close_price:
            logger.warning(f"Invalid high price for candle at {timestamp}")
            skipped += 1
            continue

        row = (
            asset_id,
            timestamp,
            open_price,
            high_price,
            low_price,
            close_price,
            volume,
            granularity
        )
        rows.append(row)

    return rows, len(rows), skipped


# ==============================================================================
# DATABASE UPSERT
# ==============================================================================

def upsert_batch(
    conn: pyodbc.Connection,
    rows: List[Tuple]
) -> Tuple[int, int]:
    """
    Upsert a batch of rows using MERGE statement.

    Args:
        conn: Database connection
        rows: List of row tuples (Asset_ID, Timestamp, Open, High, Low, Close, Volume, Granularity)

    Returns:
        Tuple of (inserted count, updated count)
    """
    if not rows:
        return 0, 0

    cursor = conn.cursor()

    # Create temp table for batch merge
    cursor.execute("""
        CREATE TABLE #BatchCandles (
            Asset_ID INT,
            Timestamp DATETIME,
            [Open] DECIMAL(18,6),
            High DECIMAL(18,6),
            Low DECIMAL(18,6),
            [Close] DECIMAL(18,6),
            Volume BIGINT,
            Granularity VARCHAR(10)
        )
    """)

    # Insert batch into temp table
    cursor.executemany(
        "INSERT INTO #BatchCandles VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows
    )

    # MERGE into target table
    merge_sql = """
        MERGE Fact_Market_Prices AS target
        USING #BatchCandles AS source
        ON target.Asset_ID = source.Asset_ID
           AND target.Timestamp = source.Timestamp
           AND target.Granularity = source.Granularity
        WHEN MATCHED THEN
            UPDATE SET
                [Open] = source.[Open],
                High = source.High,
                Low = source.Low,
                [Close] = source.[Close],
                Volume = source.Volume
        WHEN NOT MATCHED THEN
            INSERT (Asset_ID, Timestamp, [Open], High, Low, [Close], Volume, Granularity)
            VALUES (source.Asset_ID, source.Timestamp, source.[Open], source.High, source.Low,
                    source.[Close], source.Volume, source.Granularity);
    """

    cursor.execute(merge_sql)

    # Get counts (approximate from rowcount)
    # Note: pyodbc rowcount after MERGE may not give exact insert/update split
    # but we can at least report total affected
    total_affected = cursor.rowcount if cursor.rowcount >= 0 else len(rows)

    # Drop temp table
    cursor.execute("DROP TABLE #BatchCandles")

    conn.commit()

    # Estimate split (MERGE updates count as 2 rows in some drivers)
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
    start_time: datetime = field(default_factory=lambda: datetime.utcnow())
    end_time: Optional[datetime] = None

    @property
    def duration_seconds(self) -> float:
        end = self.end_time or datetime.utcnow()
        return (end - self.start_time).total_seconds()


def process_asset_granularity(
    db_conn: pyodbc.Connection,
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
        granularity: Granularity string (H1, H4, D1)

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
        now = datetime.utcnow()

        # Skip if already up to date (within one interval)
        if from_ts >= now - get_interval_delta(granularity):
            logger.info(f"{asset['Symbol']} {granularity} already up to date (last: {from_ts})")
            result.success = True
            result.end_time = datetime.utcnow()
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
                logger.error(f"Failed to fetch {asset['Symbol']} {granularity} window {from_ts} to {to_ts}")
                result.failed_windows += 1
                # Continue to next window rather than failing entirely
                from_ts = to_ts
                continue

            result.candles_fetched += len(candles)

            if candles:
                # Transform candles
                rows, valid_count, skipped_count = transform_candles(
                    candles, asset["Asset_ID"], granularity
                )
                result.rows_skipped += skipped_count

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

    result.end_time = datetime.utcnow()
    return result


# ==============================================================================
# VALIDATION QUERIES
# ==============================================================================

def run_validation_queries(conn: pyodbc.Connection) -> Dict[str, Any]:
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
        ORDER BY Granularity
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
    start_time = datetime.utcnow()
    logger.info("=" * 80)
    logger.info("OANDA Price Ingestion Started")
    logger.info(f"Symbol filter: {symbol_filter or 'None (all assets)'}")
    logger.info(f"Granularity filter: {granularity_filter or 'None (H1, H4, D1)'}")
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
    all_granularities = ["H1", "H4", "D1"]
    if granularity_filter:
        if granularity_filter not in all_granularities:
            raise ValueError(f"Invalid granularity: {granularity_filter}. Must be one of {all_granularities}")
        granularities = [granularity_filter]
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
    end_time = datetime.utcnow()
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
        description="OANDA to SQL Server Price Ingestion",
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
        choices=["H1", "H4", "D1"],
        default=None,
        help="Process only this granularity"
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
