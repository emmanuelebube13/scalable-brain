"""
Signal Repository - Database persistence with bulk upsert operations.

Provides idempotent upsert operations using PostgreSQL ON CONFLICT
for efficient and safe signal persistence.

Features:
- Deduplication: Prevents duplicate signal insertion
- Incremental processing: Only processes new data since last run
- Validation: Ensures signal data integrity before insertion
"""

import logging
import uuid
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime
from dataclasses import dataclass

import pandas as pd

from signal_engine.config.database import DatabaseConnection
from signal_engine.config.settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class SignalRecord:
    """
    Single signal record for persistence.
    
    Attributes:
        timestamp: Signal timestamp
        asset_id: Asset identifier
        granularity: Time granularity (H1, H4, etc.)
        strategy_id: Strategy identifier
        signal_value: Signal value (-1, 0, 1)
        strategy_version: Config version used
        config_hash: Hash of configuration
        signal_reason: Human-readable reason
        rule_id: Rule that triggered
        indicator_snapshot: JSON of indicator values
        confidence_score: Optional confidence metric
        batch_id: Batch identifier for tracking
    """
    timestamp: datetime
    asset_id: int
    granularity: str
    strategy_id: int
    signal_value: int
    strategy_version: str
    config_hash: str
    signal_reason: Optional[str] = None
    rule_id: Optional[str] = None
    indicator_snapshot: Optional[str] = None
    confidence_score: Optional[float] = None
    batch_id: Optional[str] = None
    
    def to_tuple(self) -> Tuple:
        """Convert to tuple for database insertion."""
        return (
            self.timestamp,
            self.asset_id,
            self.granularity,
            self.strategy_id,
            self.signal_value,
            self.strategy_version,
            self.config_hash,
            self.signal_reason,
            self.rule_id,
            self.indicator_snapshot,
            self.confidence_score,
            self.batch_id
        )


class SignalRepository:
    """
    Repository for signal persistence operations.
    
    Uses PostgreSQL INSERT ... ON CONFLICT for idempotent upserts.
    This ensures:
    - Idempotency: Running twice produces same result
    - Performance: Bulk operations are efficient
    - Safety: Atomic transaction with rollback on error
    """
    
    # Target table name
    TARGET_TABLE = "Fact_Signals"
    
    def __init__(self, db: DatabaseConnection, settings: Settings):
        """
        Initialize repository.
        
        Args:
            db: Database connection manager
            settings: Application settings
        """
        self.db = db
        self.settings = settings
        self.batch_size = settings.batch_size
        logger.debug("Initialized SignalRepository")
    
    def save_signals(
        self,
        signals_df: pd.DataFrame,
        strategy_version: str,
        config_hash: str,
        batch_id: Optional[str] = None,
        asset_id: Optional[int] = None,
        granularity: Optional[str] = None,
        strategy_id: Optional[int] = None,
        validate_current_hour_only: bool = True
    ) -> int:
        """
        Save signals to database using ON CONFLICT upsert with deduplication.
        
        Args:
            signals_df: DataFrame with signal data
            strategy_version: Strategy config version
            config_hash: Hash of config for traceability
            batch_id: Optional batch identifier
            asset_id: Asset ID for deduplication check
            granularity: Granularity for deduplication check
            strategy_id: Strategy ID for deduplication check
            validate_current_hour_only: If True, only process signals from current hour
            
        Returns:
            Number of rows inserted/updated
        """
        if batch_id is None:
            batch_id = str(uuid.uuid4())[:8]
        
        # Convert DataFrame to records
        records = self._dataframe_to_records(
            signals_df, strategy_version, config_hash, batch_id
        )
        
        if not records:
            logger.info("No signals to persist")
            return 0
        
        # Deduplication: Remove signals that already exist in database
        if asset_id and granularity and strategy_id:
            records = self._filter_existing_signals(
                records, asset_id, granularity, strategy_id
            )
        
        if not records:
            logger.info("All signals already exist in database (duplicates filtered)")
            return 0
        
        # Validate: Only process signals for current hour if enabled
        if validate_current_hour_only:
            records = self._filter_to_current_hour(records)
        
        if not records:
            logger.info("No signals for current hour to persist")
            return 0
        
        logger.info(f"Persisting {len(records)} signals after deduplication (batch: {batch_id})")
        
        # Use PostgreSQL upsert
        return self._bulk_upsert(records)
    
    def _dataframe_to_records(
        self,
        df: pd.DataFrame,
        strategy_version: str,
        config_hash: str,
        batch_id: str
    ) -> List[SignalRecord]:
        """
        Convert DataFrame to list of SignalRecord objects.
        
        Args:
            df: DataFrame with signal columns
            strategy_version: Config version
            config_hash: Config hash
            batch_id: Batch ID
            
        Returns:
            List of SignalRecord objects
        """
        records = []
        
        required_cols = ['Timestamp', 'Asset_ID', 'Granularity', 'Strategy_ID', 'Signal_Value']
        
        # Validate required columns
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Required column '{col}' not found in DataFrame")
        
        for _, row in df.iterrows():
            # Skip zero signals (no signal generated)
            if row['Signal_Value'] == 0:
                continue
            
            record = SignalRecord(
                timestamp=row['Timestamp'],
                asset_id=int(row['Asset_ID']),
                granularity=row['Granularity'],
                strategy_id=int(row['Strategy_ID']),
                signal_value=int(row['Signal_Value']),
                strategy_version=strategy_version,
                config_hash=config_hash,
                signal_reason=row.get('Signal_Reason'),
                rule_id=row.get('Rule_ID'),
                indicator_snapshot=row.get('Indicator_Snapshot'),
                confidence_score=row.get('Confidence_Score'),
                batch_id=batch_id
            )
            records.append(record)
        
        return records
    
    def _filter_existing_signals(
        self,
        records: List[SignalRecord],
        asset_id: int,
        granularity: str,
        strategy_id: int
    ) -> List[SignalRecord]:
        """
        Filter out signals that already exist in database.
        
        Uses an efficient batch query to check for existing signals
        and removes duplicates from the records list.
        
        Args:
            records: List of signal records to filter
            asset_id: Asset ID
            granularity: Granularity
            strategy_id: Strategy ID
            
        Returns:
            Filtered list of records (non-duplicates only)
        """
        if not records:
            return []
        
        # Get unique timestamps from records
        timestamps = list(set([r.timestamp for r in records]))
        
        if not timestamps:
            return records
        
        # Query database for existing signals with these timestamps
        placeholders = ','.join(['%s' for _ in timestamps])
        query = f"""
            SELECT Timestamp
            FROM {self.TARGET_TABLE}
            WHERE Asset_ID = %s
                AND Granularity = %s
                AND Strategy_ID = %s
                AND Timestamp IN ({placeholders})
        """
        
        params = [asset_id, granularity, strategy_id] + timestamps
        
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                existing_timestamps = {row[0] for row in cursor.fetchall()}
            
            # Filter out existing signals
            filtered_records = [
                r for r in records 
                if r.timestamp not in existing_timestamps
            ]
            
            duplicates_removed = len(records) - len(filtered_records)
            if duplicates_removed > 0:
                logger.debug(
                    f"Filtered {duplicates_removed} duplicate signals for "
                    f"Asset={asset_id}, Granularity={granularity}, Strategy={strategy_id}"
                )
            
            return filtered_records
            
        except Exception as e:
            logger.error(f"Error checking for existing signals: {e}")
            # On error, return original records to be safe
            return records
    
    def _filter_to_current_hour(
        self,
        records: List[SignalRecord]
    ) -> List[SignalRecord]:
        """
        Filter records to only include signals for the current hour.
        
        This prevents accumulation of signals from historical data
        when the cron job runs.
        
        Args:
            records: List of signal records
            
        Returns:
            Filtered list of records for current hour only
        """
        if not records:
            return []
        
        now = datetime.utcnow()
        
        # Get the current hour boundaries
        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        
        # Filter to only current hour
        filtered = [
            r for r in records
            if r.timestamp >= current_hour_start
        ]
        
        skipped = len(records) - len(filtered)
        if skipped > 0:
            logger.debug(
                f"Skipped {skipped} signals from previous hours "
                f"(current hour only mode)"
            )
        
        return filtered
    
    def check_existing_signal(
        self,
        timestamp: datetime,
        asset_id: int,
        granularity: str,
        strategy_id: int
    ) -> bool:
        """
        Check if a signal already exists in the database.
        
        Args:
            timestamp: Signal timestamp
            asset_id: Asset ID
            granularity: Granularity
            strategy_id: Strategy ID
            
        Returns:
            True if signal exists, False otherwise
        """
        query = f"""
            SELECT 1 FROM {self.TARGET_TABLE}
            WHERE Timestamp = %s
                AND Asset_ID = %s
                AND Granularity = %s
                AND Strategy_ID = %s
        """
        
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (timestamp, asset_id, granularity, strategy_id))
            return cursor.fetchone() is not None
    
    def get_existing_timestamps(
        self,
        timestamps: List[datetime],
        asset_id: int,
        granularity: str,
        strategy_id: int
    ) -> Set[datetime]:
        """
        Get timestamps that already exist in database.
        
        Args:
            timestamps: List of timestamps to check
            asset_id: Asset ID
            granularity: Granularity
            strategy_id: Strategy ID
            
        Returns:
            Set of timestamps that already exist
        """
        if not timestamps:
            return set()
        
        placeholders = ','.join(['%s' for _ in timestamps])
        query = f"""
            SELECT Timestamp
            FROM {self.TARGET_TABLE}
            WHERE Asset_ID = %s
                AND Granularity = %s
                AND Strategy_ID = %s
                AND Timestamp IN ({placeholders})
        """
        
        params = [asset_id, granularity, strategy_id] + timestamps
        
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return {row[0] for row in cursor.fetchall()}
    
    def _bulk_upsert(self, records: List[SignalRecord]) -> int:
        """
        Perform bulk upsert using PostgreSQL ON CONFLICT.
        
        Args:
            records: List of signal records
            
        Returns:
            Number of rows affected
        """
        total_affected = 0
        
        upsert_sql = f"""
            INSERT INTO {self.TARGET_TABLE} (
                Timestamp, Asset_ID, Granularity, Strategy_ID, Signal_Value,
                Strategy_Version, Config_Hash, Signal_Reason, Rule_ID,
                Indicator_Snapshot, Confidence_Score, Created_At, Batch_ID
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s)
            ON CONFLICT (Timestamp, Asset_ID, Granularity, Strategy_ID)
            DO UPDATE SET
                Signal_Value = EXCLUDED.Signal_Value,
                Strategy_Version = EXCLUDED.Strategy_Version,
                Config_Hash = EXCLUDED.Config_Hash,
                Signal_Reason = EXCLUDED.Signal_Reason,
                Rule_ID = EXCLUDED.Rule_ID,
                Indicator_Snapshot = EXCLUDED.Indicator_Snapshot,
                Confidence_Score = EXCLUDED.Confidence_Score,
                Batch_ID = EXCLUDED.Batch_ID
            -- Note: Created_At is NOT updated to preserve original creation time
        """
        
        with self.db.connection() as conn:
            cursor = conn.cursor()
            
            try:
                data_tuples = [r.to_tuple() for r in records]
                
                for i in range(0, len(data_tuples), self.batch_size):
                    batch = data_tuples[i:i + self.batch_size]
                    cursor.executemany(upsert_sql, batch)
                    total_affected += cursor.rowcount
                    logger.debug(f"Upserted batch of {len(batch)} rows")
                
                logger.info(
                    f"Upsert complete: {total_affected} rows inserted/updated"
                )
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Bulk upsert failed: {e}")
                raise
            finally:
                cursor.close()
        
        return total_affected
    
    def get_signals(
        self,
        asset_id: Optional[int] = None,
        granularity: Optional[str] = None,
        strategy_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        batch_id: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Query signals from database.
        
        Args:
            asset_id: Filter by asset
            granularity: Filter by granularity
            strategy_id: Filter by strategy
            start_date: Filter by start date
            end_date: Filter by end date
            batch_id: Filter by batch
            
        Returns:
            DataFrame with signal data
        """
        query = f"SELECT * FROM {self.TARGET_TABLE} WHERE 1=1"
        params = []
        
        if asset_id is not None:
            query += " AND Asset_ID = %s"
            params.append(asset_id)
        
        if granularity is not None:
            query += " AND Granularity = %s"
            params.append(granularity)
        
        if strategy_id is not None:
            query += " AND Strategy_ID = %s"
            params.append(strategy_id)
        
        if start_date is not None:
            query += " AND Timestamp >= %s"
            params.append(start_date)
        
        if end_date is not None:
            query += " AND Timestamp <= %s"
            params.append(end_date)
        
        if batch_id is not None:
            query += " AND Batch_ID = %s"
            params.append(batch_id)
        
        query += " ORDER BY Timestamp"
        
        with self.db.connection() as conn:
            df = pd.read_sql(query, conn, params=params)
        
        logger.debug(f"Retrieved {len(df)} signals from database")
        return df
    
    def delete_signals(
        self,
        asset_id: Optional[int] = None,
        granularity: Optional[str] = None,
        strategy_id: Optional[int] = None,
        batch_id: Optional[str] = None
    ) -> int:
        """
        Delete signals from database.
        
        Args:
            asset_id: Filter by asset
            granularity: Filter by granularity
            strategy_id: Filter by strategy
            batch_id: Filter by batch
            
        Returns:
            Number of rows deleted
        """
        query = f"DELETE FROM {self.TARGET_TABLE} WHERE 1=1"
        params = []
        
        if asset_id is not None:
            query += " AND Asset_ID = %s"
            params.append(asset_id)
        
        if granularity is not None:
            query += " AND Granularity = %s"
            params.append(granularity)
        
        if strategy_id is not None:
            query += " AND Strategy_ID = %s"
            params.append(strategy_id)
        
        if batch_id is not None:
            query += " AND Batch_ID = %s"
            params.append(batch_id)
        
        with self.db.cursor() as cursor:
            cursor.execute(query, params)
            deleted = cursor.rowcount
        
        logger.info(f"Deleted {deleted} signals from database")
        return deleted
    
    def get_latest_signals(self, limit: int = 100) -> pd.DataFrame:
        """
        Get most recent signals.
        
        Args:
            limit: Maximum number of signals to retrieve
            
        Returns:
            DataFrame with recent signals
        """
        query = f"""
            SELECT *
            FROM {self.TARGET_TABLE}
            ORDER BY Timestamp DESC
            LIMIT {limit}
        """
        
        with self.db.connection() as conn:
            df = pd.read_sql(query, conn)
        
        return df
