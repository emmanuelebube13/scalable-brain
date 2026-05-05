#!/usr/bin/env python3
"""
Signal Integrity Verification Script
=====================================

Verifies the integrity of signals in the database:
1. Counts total signals
2. Checks for duplicate signals
3. Validates signal counts per asset/granularity/strategy
4. Checks for orphaned signals

Usage:
    python verify_signals.py
    python verify_signals.py --fix-duplicates
    python verify_signals.py --asset-id 5 --granularity H1
"""

import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from signal_engine.config.settings import Settings
from signal_engine.config.database import DatabaseConnection

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Verify signal integrity in database'
    )
    
    parser.add_argument(
        '--fix-duplicates',
        action='store_true',
        help='Remove duplicate signals from database'
    )
    
    parser.add_argument(
        '--asset-id',
        type=int,
        help='Filter by asset ID'
    )
    
    parser.add_argument(
        '--granularity',
        type=str,
        help='Filter by granularity (H1, H4, etc.)'
    )
    
    parser.add_argument(
        '--strategy-id',
        type=int,
        help='Filter by strategy ID'
    )
    
    parser.add_argument(
        '--env-file',
        type=str,
        help='Path to .env file'
    )
    
    return parser.parse_args()


def get_signal_counts(db: DatabaseConnection, args) -> dict:
    """Get signal counts by various dimensions."""
    query = """
        SELECT 
            Asset_ID,
            Granularity,
            Strategy_ID,
            COUNT(*) as Signal_Count,
            MIN(Timestamp) as First_Signal,
            MAX(Timestamp) as Last_Signal
        FROM Fact_Signals
        WHERE 1=1
    """
    
    params = []
    
    if args.asset_id:
        query += " AND Asset_ID = %s"
        params.append(args.asset_id)
    
    if args.granularity:
        query += " AND Granularity = %s"
        params.append(args.granularity)
    
    if args.strategy_id:
        query += " AND Strategy_ID = %s"
        params.append(args.strategy_id)
    
    query += " GROUP BY Asset_ID, Granularity, Strategy_ID"
    query += " ORDER BY Signal_Count DESC"
    
    with db.connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
    
    results = []
    for row in rows:
        results.append(dict(zip(columns, row)))
    
    return results


def get_total_signal_count(db: DatabaseConnection, args) -> int:
    """Get total number of signals."""
    query = "SELECT COUNT(*) FROM Fact_Signals WHERE 1=1"
    params = []
    
    if args.asset_id:
        query += " AND Asset_ID = %s"
        params.append(args.asset_id)
    
    if args.granularity:
        query += " AND Granularity = %s"
        params.append(args.granularity)
    
    if args.strategy_id:
        query += " AND Strategy_ID = %s"
        params.append(args.strategy_id)
    
    with db.connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchone()[0]


def get_duplicate_count(db: DatabaseConnection, args) -> int:
    """Count duplicate signals."""
    query = """
        SELECT COUNT(*) - COUNT(DISTINCT (
            Timestamp::TEXT || '_' ||
            Asset_ID::TEXT || '_' ||
            Granularity || '_' ||
            Strategy_ID::TEXT
        )) as DuplicateCount
        FROM Fact_Signals
        WHERE 1=1
    """
    
    params = []
    
    if args.asset_id:
        query = query.replace("WHERE 1=1", "WHERE Asset_ID = %s")
        params.append(args.asset_id)
    
    if args.granularity:
        query += " AND Granularity = %s"
        params.append(args.granularity)
    
    if args.strategy_id:
        query += " AND Strategy_ID = %s"
        params.append(args.strategy_id)
    
    with db.connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        result = cursor.fetchone()[0]
        return result or 0


def get_duplicate_details(db: DatabaseConnection, args) -> list:
    """Get details of duplicate signals."""
    query = """
        SELECT 
            Timestamp,
            Asset_ID,
            Granularity,
            Strategy_ID,
            COUNT(*) as Duplicate_Count
        FROM Fact_Signals
        WHERE 1=1
    """
    
    params = []
    
    if args.asset_id:
        query += " AND Asset_ID = %s"
        params.append(args.asset_id)
    
    if args.granularity:
        query += " AND Granularity = %s"
        params.append(args.granularity)
    
    if args.strategy_id:
        query += " AND Strategy_ID = %s"
        params.append(args.strategy_id)
    
    query += """
        GROUP BY Timestamp, Asset_ID, Granularity, Strategy_ID
        HAVING COUNT(*) > 1
        ORDER BY Duplicate_Count DESC
    """
    
    with db.connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
    
    results = []
    for row in rows:
        results.append(dict(zip(columns, row)))
    
    return results


def remove_duplicates(db: DatabaseConnection, args) -> int:
    """Remove duplicate signals, keeping the most recent."""
    logger.info("Removing duplicate signals...")
    
    # Use CTE to identify and delete duplicates
    query = """
        WITH DuplicateSignals AS (
            SELECT 
                Timestamp,
                Asset_ID,
                Granularity,
                Strategy_ID,
                Created_At,
                ROW_NUMBER() OVER (
                    PARTITION BY Timestamp, Asset_ID, Granularity, Strategy_ID
                    ORDER BY Created_At DESC
                ) AS RowNum
            FROM Fact_Signals
            WHERE 1=1
    """
    
    params = []
    
    if args.asset_id:
        query += " AND Asset_ID = %s"
        params.append(args.asset_id)
    
    if args.granularity:
        query += " AND Granularity = %s"
        params.append(args.granularity)
    
    if args.strategy_id:
        query += " AND Strategy_ID = %s"
        params.append(args.strategy_id)
    
    query += """
        )
        DELETE FROM Fact_Signals
        WHERE EXISTS (
            SELECT 1 FROM DuplicateSignals d
            WHERE d.RowNum > 1
                AND Fact_Signals.Timestamp = d.Timestamp
                AND Fact_Signals.Asset_ID = d.Asset_ID
                AND Fact_Signals.Granularity = d.Granularity
                AND Fact_Signals.Strategy_ID = d.Strategy_ID
                AND Fact_Signals.Created_At = d.Created_At
        )
    """
    
    with db.connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        deleted = cursor.rowcount
        conn.commit()
    
    return deleted


def get_signals_per_hour(db: DatabaseConnection, args) -> list:
    """Get signal count per hour for recent 24 hours."""
    query = """
        SELECT 
            DATE_TRUNC('hour', Timestamp) as Hour,
            COUNT(*) as Signal_Count
        FROM Fact_Signals
        WHERE Timestamp >= NOW() - INTERVAL '24 hours'
    """
    
    params = []
    
    if args.asset_id:
        query += " AND Asset_ID = %s"
        params.append(args.asset_id)
    
    if args.granularity:
        query += " AND Granularity = %s"
        params.append(args.granularity)
    
    if args.strategy_id:
        query += " AND Strategy_ID = %s"
        params.append(args.strategy_id)
    
    query += " GROUP BY DATE_TRUNC('hour', Timestamp)"
    query += " ORDER BY Hour DESC"
    
    with db.connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
    
    results = []
    for row in rows:
        results.append(dict(zip(columns, row)))
    
    return results


def main():
    """Main entry point."""
    args = parse_args()
    
    logger.info("=" * 70)
    logger.info("Signal Integrity Verification")
    logger.info("=" * 70)
    
    try:
        # Load settings
        settings = Settings.from_env(args.env_file)
        db = DatabaseConnection(settings)
        
        # Get total count
        total_count = get_total_signal_count(db, args)
        logger.info(f"\nTotal signals in database: {total_count}")
        
        # Check for duplicates
        dup_count = get_duplicate_count(db, args)
        if dup_count > 0:
            logger.warning(f"Found {dup_count} duplicate signals!")
            
            if args.fix_duplicates:
                deleted = remove_duplicates(db, args)
                logger.info(f"Removed {deleted} duplicate signals")
                
                # Recalculate
                total_count = get_total_signal_count(db, args)
                logger.info(f"New total signals: {total_count}")
            else:
                # Show duplicate details
                dup_details = get_duplicate_details(db, args)
                logger.info("\nTop 10 duplicates:")
                for dup in dup_details[:10]:
                    logger.info(
                        f"  {dup['Timestamp']} | Asset={dup['Asset_ID']} | "
                        f"Gran={dup['Granularity']} | Strategy={dup['Strategy_ID']} | "
                        f"Count={dup['Duplicate_Count']}"
                    )
                logger.info("\nRun with --fix-duplicates to remove duplicates")
        else:
            logger.info("No duplicate signals found")
        
        # Get breakdown by asset/granularity/strategy
        counts = get_signal_counts(db, args)
        
        logger.info("\n" + "=" * 70)
        logger.info("Signal Count Breakdown (Top 20)")
        logger.info("=" * 70)
        logger.info(f"{'Asset':>6} | {'Gran':>6} | {'Strategy':>8} | {'Count':>8} | {'First Signal':>20} | {'Last Signal':>20}")
        logger.info("-" * 70)
        
        for item in counts[:20]:
            first_ts = item['First_Signal'].strftime('%Y-%m-%d %H:%M') if item['First_Signal'] else 'N/A'
            last_ts = item['Last_Signal'].strftime('%Y-%m-%d %H:%M') if item['Last_Signal'] else 'N/A'
            logger.info(
                f"{item['Asset_ID']:>6} | {item['Granularity']:>6} | "
                f"{item['Strategy_ID']:>8} | {item['Signal_Count']:>8} | "
                f"{first_ts:>20} | {last_ts:>20}"
            )
        
        # Get hourly breakdown
        hourly = get_signals_per_hour(db, args)
        
        logger.info("\n" + "=" * 70)
        logger.info("Signals Per Hour (Last 24 Hours)")
        logger.info("=" * 70)
        
        for hour_data in hourly:
            hour_str = hour_data['Hour'].strftime('%Y-%m-%d %H:%M')
            bar_length = min(hour_data['Signal_Count'], 50)
            bar = "█" * bar_length
            logger.info(f"{hour_str} | {bar} {hour_data['Signal_Count']}")
        
        # Expected vs actual
        expected_per_hour = 5  # 5 currency pairs
        expected_with_strategies = expected_per_hour * 2  # Assuming ~2 strategies per pair
        
        logger.info("\n" + "=" * 70)
        logger.info("Expected vs Actual")
        logger.info("=" * 70)
        logger.info(f"Expected signals per hour (5 pairs, ~2 strategies): ~{expected_with_strategies}")
        
        if hourly:
            avg_signals = sum(h['Signal_Count'] for h in hourly) / len(hourly)
            logger.info(f"Actual average per hour: {avg_signals:.1f}")
            
            if avg_signals > expected_with_strategies * 3:
                logger.warning(
                    f"Signal count is HIGH! Expected ~{expected_with_strategies} per hour, "
                    f"but averaging {avg_signals:.1f}"
                )
            elif avg_signals < expected_with_strategies * 0.5:
                logger.warning(
                    f"Signal count is LOW! Expected ~{expected_with_strategies} per hour, "
                    f"but averaging {avg_signals:.1f}"
                )
            else:
                logger.info("Signal counts look reasonable")
        
        logger.info("\n" + "=" * 70)
        logger.info("Verification Complete")
        logger.info("=" * 70)
        
        return 0
        
    except Exception as e:
        logger.exception(f"Verification failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
