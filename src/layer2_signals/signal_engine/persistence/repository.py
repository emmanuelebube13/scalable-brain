"""
Signal Repository - Database persistence with bulk MERGE operations.

Provides idempotent upsert operations using temp table + MERGE pattern
for efficient and safe signal persistence.
"""

import logging
import uuid
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

import pandas as pd
import pyodbc

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
    
    Uses temp table + MERGE pattern for idempotent upserts:
    1. Bulk insert into temp staging table
    2. MERGE into target table with match on PK
    3. Handle conflicts by updating existing records
    
    This ensures:
    - Idempotency: Running twice produces same result
    - Performance: Bulk operations are efficient
    - Safety: Atomic transaction with rollback on error
    """
    
    # Temp staging table name
    TEMP_TABLE = "Temp_Signals_Staging"
    
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
        batch_id: Optional[str] = None
    ) -> int:
        """
        Save signals to database using MERGE pattern.
        
        Args:
            signals_df: DataFrame with signal data
            strategy_version: Strategy config version
            config_hash: Hash of config for traceability
            batch_id: Optional batch identifier
            
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
        
        logger.info(f"Persisting {len(records)} signals (batch: {batch_id})")
        
        # Use temp table + MERGE pattern
        return self._bulk_merge(records)
    
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
    
    def _bulk_merge(self, records: List[SignalRecord]) -> int:
        """
        Perform bulk MERGE operation using temp table.
        
        Args:
            records: List of signal records
            
        Returns:
            Number of rows affected
        """
        total_affected = 0
        
        with self.db.connection() as conn:
            cursor = conn.cursor()
            
            try:
                # Step 1: Clear temp table
                cursor.execute(f"DELETE FROM {self.TEMP_TABLE}")
                logger.debug(f"Cleared temp table: {self.TEMP_TABLE}")
                
                # Step 2: Bulk insert into temp table
                temp_insert_sql = f"""
                    INSERT INTO {self.TEMP_TABLE} (
                        Timestamp, Asset_ID, Granularity, Strategy_ID, Signal_Value,
                        Strategy_Version, Config_Hash, Signal_Reason, Rule_ID,
                        Indicator_Snapshot, Confidence_Score, Batch_ID
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                
                # Insert in batches
                data_tuples = [r.to_tuple() for r in records]
                
                for i in range(0, len(data_tuples), self.batch_size):
                    batch = data_tuples[i:i + self.batch_size]
                    cursor.fast_executemany = True
                    cursor.executemany(temp_insert_sql, batch)
                    logger.debug(f"Inserted batch of {len(batch)} rows to temp table")
                
                # Step 3: MERGE into target table
                merge_sql = f"""
                    MERGE {self.TARGET_TABLE} AS target
                    USING {self.TEMP_TABLE} AS source
                    ON target.Timestamp = source.Timestamp
                        AND target.Asset_ID = source.Asset_ID
                        AND target.Granularity = source.Granularity
                        AND target.Strategy_ID = source.Strategy_ID
                    
                    WHEN MATCHED THEN
                        UPDATE SET
                            Signal_Value = source.Signal_Value,
                            Strategy_Version = source.Strategy_Version,
                            Config_Hash = source.Config_Hash,
                            Signal_Reason = source.Signal_Reason,
                            Rule_ID = source.Rule_ID,
                            Indicator_Snapshot = source.Indicator_Snapshot,
                            Confidence_Score = source.Confidence_Score,
                            Batch_ID = source.Batch_ID,
                            Created_At = GETUTCDATE()
                    
                    WHEN NOT MATCHED BY TARGET THEN
                        INSERT (
                            Timestamp, Asset_ID, Granularity, Strategy_ID, Signal_Value,
                            Strategy_Version, Config_Hash, Signal_Reason, Rule_ID,
                            Indicator_Snapshot, Confidence_Score, Created_At, Batch_ID
                        )
                        VALUES (
                            source.Timestamp, source.Asset_ID, source.Granularity,
                            source.Strategy_ID, source.Signal_Value, source.Strategy_Version,
                            source.Config_Hash, source.Signal_Reason, source.Rule_ID,
                            source.Indicator_Snapshot, source.Confidence_Score,
                            GETUTCDATE(), source.Batch_ID
                        );
                """
                
                cursor.execute(merge_sql)
                total_affected = cursor.rowcount
                
                # Clear temp table
                cursor.execute(f"DELETE FROM {self.TEMP_TABLE}")
                
                conn.commit()
                
                logger.info(
                    f"MERGE complete: {total_affected} rows inserted/updated"
                )
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Bulk MERGE failed: {e}")
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
            query += " AND Asset_ID = ?"
            params.append(asset_id)
        
        if granularity is not None:
            query += " AND Granularity = ?"
            params.append(granularity)
        
        if strategy_id is not None:
            query += " AND Strategy_ID = ?"
            params.append(strategy_id)
        
        if start_date is not None:
            query += " AND Timestamp >= ?"
            params.append(start_date)
        
        if end_date is not None:
            query += " AND Timestamp <= ?"
            params.append(end_date)
        
        if batch_id is not None:
            query += " AND Batch_ID = ?"
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
            query += " AND Asset_ID = ?"
            params.append(asset_id)
        
        if granularity is not None:
            query += " AND Granularity = ?"
            params.append(granularity)
        
        if strategy_id is not None:
            query += " AND Strategy_ID = ?"
            params.append(strategy_id)
        
        if batch_id is not None:
            query += " AND Batch_ID = ?"
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
            limit: Maximum number of signals to return
            
        Returns:
            DataFrame with recent signals
        """
        query = f"""
            SELECT TOP {limit} *
            FROM {self.TARGET_TABLE}
            ORDER BY Timestamp DESC
        """
        
        with self.db.connection() as conn:
            df = pd.read_sql(query, conn)
        
        return df
