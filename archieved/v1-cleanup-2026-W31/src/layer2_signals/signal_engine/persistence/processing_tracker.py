"""
Processing Tracker - Tracks last processed timestamp per asset/granularity/strategy.

Prevents duplicate signal generation by tracking what data has already been processed.
Ensures incremental processing - only new data since last run is processed.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from signal_engine.config.database import DatabaseConnection
from signal_engine.config.settings import Settings

logger = logging.getLogger(__name__)


class ProcessingTracker:
    """
    Tracks processing state to enable incremental signal generation.
    
    Uses the Fact_Signal_Processing_Log table to track the last processed
    timestamp for each asset/granularity/strategy combination.
    
    This ensures:
    - Incremental processing: Only new data is processed on each run
    - Deduplication: Prevents re-processing of already-processed bars
    - Recovery: Can resume from last successful processing point
    """
    
    def __init__(self, db: DatabaseConnection, settings: Settings):
        """
        Initialize processing tracker.
        
        Args:
            db: Database connection manager
            settings: Application settings
        """
        self.db = db
        self.settings = settings
        logger.debug("Initialized ProcessingTracker")
    
    def get_last_processed_timestamp(
        self,
        asset_id: int,
        granularity: str,
        strategy_id: int
    ) -> Optional[datetime]:
        """
        Get the last processed timestamp for a specific combination.
        
        Args:
            asset_id: Asset identifier
            granularity: Time granularity (H1, H4, etc.)
            strategy_id: Strategy identifier
            
        Returns:
            Last processed timestamp or None if never processed
        """
        query = """
            SELECT MAX(Last_Processed_Timestamp) as Last_Timestamp
            FROM Fact_Signal_Processing_Log
            WHERE Asset_ID = %s
                AND Granularity = %s
                AND Strategy_ID = %s
        """
        
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (asset_id, granularity, strategy_id))
            row = cursor.fetchone()
            
            if row and row[0]:
                return row[0]
        
        return None
    
    def get_last_processed_for_batch(
        self,
        asset_ids: list,
        granularities: list,
        strategy_ids: list
    ) -> Dict[tuple, datetime]:
        """
        Get last processed timestamps for a batch of combinations.
        
        Args:
            asset_ids: List of asset IDs
            granularities: List of granularities
            strategy_ids: List of strategy IDs
            
        Returns:
            Dictionary mapping (asset_id, granularity, strategy_id) to last timestamp
        """
        if not asset_ids or not granularities or not strategy_ids:
            return {}
        
        query = """
            SELECT Asset_ID, Granularity, Strategy_ID, MAX(Last_Processed_Timestamp) as Last_Timestamp
            FROM Fact_Signal_Processing_Log
            WHERE Asset_ID IN ({0})
                AND Granularity IN ({1})
                AND Strategy_ID IN ({2})
            GROUP BY Asset_ID, Granularity, Strategy_ID
        """.format(
            ','.join(['%s'] * len(asset_ids)),
            ','.join(['%s'] * len(granularities)),
            ','.join(['%s'] * len(strategy_ids))
        )
        
        params = asset_ids + granularities + strategy_ids
        
        result = {}
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            for row in cursor.fetchall():
                key = (row[0], row[1], row[2])
                result[key] = row[3]
        
        return result
    
    def update_last_processed(
        self,
        asset_id: int,
        granularity: str,
        strategy_id: int,
        timestamp: datetime,
        batch_id: Optional[str] = None,
        records_processed: int = 0
    ) -> bool:
        """
        Update the last processed timestamp for a combination.
        
        Args:
            asset_id: Asset identifier
            granularity: Time granularity
            strategy_id: Strategy identifier
            timestamp: Timestamp that was processed
            batch_id: Optional batch identifier
            records_processed: Number of records processed
            
        Returns:
            True if successful
        """
        query = """
            INSERT INTO Fact_Signal_Processing_Log (
                Asset_ID, Granularity, Strategy_ID, Last_Processed_Timestamp,
                Batch_ID, Records_Processed, Processed_At
            ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (Asset_ID, Granularity, Strategy_ID)
            DO UPDATE SET
                Last_Processed_Timestamp = EXCLUDED.Last_Processed_Timestamp,
                Batch_ID = EXCLUDED.Batch_ID,
                Records_Processed = EXCLUDED.Records_Processed,
                Processed_At = EXCLUDED.Processed_At
        """
        
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (
                asset_id, granularity, strategy_id, timestamp, 
                batch_id, records_processed
            ))
            conn.commit()
        
        logger.debug(
            f"Updated processing log: Asset={asset_id}, Granularity={granularity}, "
            f"Strategy={strategy_id}, Last_TS={timestamp}"
        )
        return True
    
    def update_batch(
        self,
        updates: list,
        batch_id: Optional[str] = None
    ) -> bool:
        """
        Update processing log for multiple combinations.
        
        Args:
            updates: List of dicts with keys: asset_id, granularity, strategy_id, 
                     timestamp, records_processed
            batch_id: Optional batch identifier
            
        Returns:
            True if successful
        """
        if not updates:
            return True
        
        query = """
            INSERT INTO Fact_Signal_Processing_Log (
                Asset_ID, Granularity, Strategy_ID, Last_Processed_Timestamp,
                Batch_ID, Records_Processed, Processed_At
            ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (Asset_ID, Granularity, Strategy_ID)
            DO UPDATE SET
                Last_Processed_Timestamp = EXCLUDED.Last_Processed_Timestamp,
                Batch_ID = EXCLUDED.Batch_ID,
                Records_Processed = EXCLUDED.Records_Processed,
                Processed_At = EXCLUDED.Processed_At
        """
        
        params = [
            (
                u['asset_id'], u['granularity'], u['strategy_id'],
                u['timestamp'], batch_id, u.get('records_processed', 0)
            )
            for u in updates
        ]
        
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params)
            conn.commit()
        
        logger.debug(f"Updated processing log for {len(updates)} combinations")
        return True
    
    def calculate_start_date(
        self,
        asset_id: int,
        granularity: str,
        strategy_id: int,
        lookback_bars: int = 5
    ) -> Optional[datetime]:
        """
        Calculate the start date for fetching new data.
        
        Returns the last processed timestamp minus a lookback period,
        or None if never processed (indicating full historical load).
        
        Args:
            asset_id: Asset identifier
            granularity: Time granularity
            strategy_id: Strategy identifier
            lookback_bars: Number of bars to lookback for indicator warmup
            
        Returns:
            Start date for data fetching or None for full load
        """
        last_ts = self.get_last_processed_timestamp(asset_id, granularity, strategy_id)
        
        if last_ts is None:
            logger.info(
                f"No previous processing found for Asset={asset_id}, "
                f"Granularity={granularity}, Strategy={strategy_id}. "
                f"Will perform full historical load."
            )
            return None
        
        # Calculate lookback based on granularity
        # Include some overlap to handle indicators that need warmup
        granularity_minutes = self._granularity_to_minutes(granularity)
        lookback_minutes = granularity_minutes * lookback_bars
        
        start_date = last_ts - timedelta(minutes=lookback_minutes)
        
        logger.debug(
            f"Calculated start date: Asset={asset_id}, Granularity={granularity}, "
            f"Strategy={strategy_id}, Last_TS={last_ts}, Start_Date={start_date}"
        )
        
        return start_date
    
    def _granularity_to_minutes(self, granularity: str) -> int:
        """
        Convert granularity string to minutes.
        
        Args:
            granularity: Granularity string (M1, M5, M15, M30, H1, H4, D1, etc.)
            
        Returns:
            Number of minutes
        """
        granularity = granularity.upper()
        
        if granularity.startswith('M'):
            return int(granularity[1:])
        elif granularity.startswith('H'):
            return int(granularity[1:]) * 60
        elif granularity.startswith('D'):
            return int(granularity[1:]) * 60 * 24
        elif granularity.startswith('W'):
            return int(granularity[1:]) * 60 * 24 * 7
        else:
            # Default to 1 hour
            return 60
