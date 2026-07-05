"""
Signal Repository - Database persistence with bulk upsert operations.

Provides idempotent upsert operations using PostgreSQL
``INSERT ... ON CONFLICT`` (FND-004 Phase 3 — migrated off the SQL Server
temp-table + ``MERGE`` pattern) for efficient and safe signal persistence.
"""

import logging
import uuid
from typing import List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

import pandas as pd
from psycopg2.extras import execute_values

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
            self.batch_id,
        )


class SignalRepository:
    """
    Repository for signal persistence operations.

    Uses PostgreSQL ``INSERT ... ON CONFLICT`` for idempotent upserts:
    1. Bulk insert rows with ``execute_values``
    2. On PK conflict, update the existing record

    This ensures:
    - Idempotency: Running twice produces same result
    - Performance: Bulk operations are efficient
    - Safety: Atomic transaction with rollback on error
    """

    # Target table name
    TARGET_TABLE = "fact_signals"

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
        self, df: pd.DataFrame, strategy_version: str, config_hash: str, batch_id: str
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

        required_cols = [
            "Timestamp",
            "Asset_ID",
            "Granularity",
            "Strategy_ID",
            "Signal_Value",
        ]

        # Validate required columns
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Required column '{col}' not found in DataFrame")

        for _, row in df.iterrows():
            # Skip zero signals (no signal generated)
            if row["Signal_Value"] == 0:
                continue

            record = SignalRecord(
                timestamp=row["Timestamp"],
                asset_id=int(row["Asset_ID"]),
                granularity=row["Granularity"],
                strategy_id=int(row["Strategy_ID"]),
                signal_value=int(row["Signal_Value"]),
                strategy_version=strategy_version,
                config_hash=config_hash,
                signal_reason=row.get("Signal_Reason"),
                rule_id=row.get("Rule_ID"),
                indicator_snapshot=row.get("Indicator_Snapshot"),
                confidence_score=row.get("Confidence_Score"),
                batch_id=batch_id,
            )
            records.append(record)

        return records

    def _bulk_merge(self, records: List[SignalRecord]) -> int:
        """
        Perform a bulk idempotent upsert via ``INSERT ... ON CONFLICT``.

        The conflict target is the ``fact_signals`` primary key
        ``(timestamp, asset_id, granularity, strategy_id)``; ``created_at`` is
        set to ``now()`` on both insert and update (matching the former
        ``GETUTCDATE()`` behaviour). ``indicator_snapshot`` is cast to ``jsonb``.

        Args:
            records: List of signal records

        Returns:
            Number of rows affected
        """
        total_affected = 0

        upsert_sql = f"""
            INSERT INTO {self.TARGET_TABLE} (
                "timestamp", asset_id, granularity, strategy_id, signal_value,
                strategy_version, config_hash, signal_reason, rule_id,
                indicator_snapshot, confidence_score, batch_id, created_at
            ) VALUES %s
            ON CONFLICT ("timestamp", asset_id, granularity, strategy_id)
            DO UPDATE SET
                signal_value = EXCLUDED.signal_value,
                strategy_version = EXCLUDED.strategy_version,
                config_hash = EXCLUDED.config_hash,
                signal_reason = EXCLUDED.signal_reason,
                rule_id = EXCLUDED.rule_id,
                indicator_snapshot = EXCLUDED.indicator_snapshot,
                confidence_score = EXCLUDED.confidence_score,
                batch_id = EXCLUDED.batch_id,
                created_at = now()
        """
        # to_tuple() yields 12 values; created_at is supplied by now() in the
        # template. indicator_snapshot (position 10) is cast to jsonb.
        template = "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, now())"

        with self.db.connection() as conn:
            cursor = conn.cursor()

            try:
                data_tuples = [r.to_tuple() for r in records]

                for i in range(0, len(data_tuples), self.batch_size):
                    batch = data_tuples[i : i + self.batch_size]
                    execute_values(
                        cursor,
                        upsert_sql,
                        batch,
                        template=template,
                        page_size=self.batch_size,
                    )
                    total_affected += cursor.rowcount
                    logger.debug(f"Upserted batch of {len(batch)} rows")

                conn.commit()

                logger.info(f"Upsert complete: {total_affected} rows inserted/updated")

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
        batch_id: Optional[str] = None,
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
            query += " AND asset_id = %s"
            params.append(asset_id)

        if granularity is not None:
            query += " AND granularity = %s"
            params.append(granularity)

        if strategy_id is not None:
            query += " AND strategy_id = %s"
            params.append(strategy_id)

        if start_date is not None:
            query += ' AND "timestamp" >= %s'
            params.append(start_date)

        if end_date is not None:
            query += ' AND "timestamp" <= %s'
            params.append(end_date)

        if batch_id is not None:
            query += " AND batch_id = %s"
            params.append(batch_id)

        query += ' ORDER BY "timestamp"'

        with self.db.connection() as conn:
            df = pd.read_sql(query, conn, params=params)

        logger.debug(f"Retrieved {len(df)} signals from database")
        return df

    def delete_signals(
        self,
        asset_id: Optional[int] = None,
        granularity: Optional[str] = None,
        strategy_id: Optional[int] = None,
        batch_id: Optional[str] = None,
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
            query += " AND asset_id = %s"
            params.append(asset_id)

        if granularity is not None:
            query += " AND granularity = %s"
            params.append(granularity)

        if strategy_id is not None:
            query += " AND strategy_id = %s"
            params.append(strategy_id)

        if batch_id is not None:
            query += " AND batch_id = %s"
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
            SELECT *
            FROM {self.TARGET_TABLE}
            ORDER BY "timestamp" DESC
            LIMIT {int(limit)}
        """

        with self.db.connection() as conn:
            df = pd.read_sql(query, conn)

        return df
