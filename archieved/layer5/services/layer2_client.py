"""Layer 2 service client — signal data access.

Reads exclusively from Fact_Signals, Dim_Asset, and Dim_Strategy.
No signal generation logic is duplicated here.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import sqlalchemy as sa

from layer5.services.db_client import execute_to_records


def _table_columns(engine: sa.engine.Engine, table_name: str) -> set[str]:
    query = sa.text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE lower(table_name) = lower(:table_name)
    """)
    rows = execute_to_records(engine, query, {"table_name": table_name})
    # PostgreSQL column names are lowercase; compare lower-cased throughout.
    return {str(r["column_name"]).lower() for r in rows if r.get("column_name")}


def get_pending_signals(
    engine: sa.engine.Engine, limit: int = 5
) -> List[Dict[str, Any]]:
    """Return the most recent signals that have not yet been executed."""
    signal_cols = _table_columns(engine, "fact_signals")
    where_clause = "fs.Timestamp >= now() - INTERVAL '1 day'"
    if "is_active" in signal_cols:
        where_clause = "fs.Is_Active = TRUE AND " + where_clause

    # NOTE: dim_strategy has no strategy_key column in the live schema;
    # strategy_name is used as the display value (FND-004 Phase 3 drift).
    query = sa.text(f"""
        SELECT
            fs.Timestamp AS timestamp,
            da.Symbol AS asset,
            ds.Strategy_Name AS strategy,
            fs.Signal_Value AS signalValue,
            fs.Confidence_Score AS confidence,
            COALESCE(fmr.Regime_Label, 'Trending_LowVol') AS regime,
            'pending' AS status
        FROM Fact_Signals fs
        INNER JOIN Dim_Asset da ON fs.Asset_ID = da.Asset_ID
        INNER JOIN Dim_Strategy ds ON fs.Strategy_ID = ds.Strategy_ID
        LEFT JOIN Fact_Market_Regime_V2 fmr
            ON fs.Asset_ID = fmr.Asset_ID
            AND fs.Timestamp = fmr.Timestamp
            AND fs.Granularity = fmr.Granularity
        WHERE {where_clause}
          AND NOT EXISTS (
              SELECT 1 FROM Fact_Live_Trades flt
              WHERE flt.Asset_ID = fs.Asset_ID
                AND flt.Strategy_ID = fs.Strategy_ID
                AND flt.Timestamp = fs.Timestamp
          )
        ORDER BY fs.Timestamp DESC
        LIMIT {int(limit)}
    """)
    rows = execute_to_records(engine, query)
    for i, r in enumerate(rows):
        r["id"] = f"SIG-{int(datetime.now().timestamp() * 1000)}-{i}"
    return rows


def get_recent_signals(
    engine: sa.engine.Engine,
    granularity: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Return recent signals with their current disposition."""
    signal_cols = _table_columns(engine, "fact_signals")
    where_clause = "fs.Timestamp >= now() - INTERVAL '7 days'"
    if "is_active" in signal_cols:
        where_clause = "fs.Is_Active = TRUE AND " + where_clause
    if granularity:
        where_clause += f" AND fs.Granularity = '{granularity}'"
    query = sa.text(f"""
        SELECT
            fs.Timestamp AS timestamp,
            da.Symbol AS asset,
            ds.Strategy_Name AS strategy,
            fs.Signal_Value AS signalValue,
            fs.Confidence_Score AS confidence,
            COALESCE(fmr.Regime_Label, 'Trending_LowVol') AS regime,
            CASE
                WHEN flt.Is_Approved = 1 THEN 'approved'
                WHEN flt.Is_Approved = 0 THEN 'vetoed'
                ELSE 'pending'
            END AS status
        FROM Fact_Signals fs
        INNER JOIN Dim_Asset da ON fs.Asset_ID = da.Asset_ID
        INNER JOIN Dim_Strategy ds ON fs.Strategy_ID = ds.Strategy_ID
        LEFT JOIN Fact_Market_Regime_V2 fmr
            ON fs.Asset_ID = fmr.Asset_ID
            AND fs.Timestamp = fmr.Timestamp
            AND fs.Granularity = fmr.Granularity
        LEFT JOIN Fact_Live_Trades flt
            ON fs.Asset_ID = flt.Asset_ID
            AND fs.Strategy_ID = flt.Strategy_ID
            AND fs.Timestamp = flt.Timestamp
        WHERE {where_clause}
        ORDER BY fs.Timestamp DESC
        LIMIT {int(limit)}
    """)
    rows = execute_to_records(engine, query)
    for i, r in enumerate(rows):
        r["id"] = f"SIG-{int(datetime.now().timestamp() * 1000)}-{i}"
    return rows
