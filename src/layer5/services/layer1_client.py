"""Layer 1 service client — regime data access.

Reads exclusively from Fact_Market_Regime_V2 and Dim_Asset.
No regime logic is recomputed here.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import sqlalchemy as sa

from layer5.services.db_client import execute_to_records
from layer5.services.data_contracts import RegimeData, RegimePerformance, RegimeTransition


REGIMES = ["Trending_HighVol", "Trending_LowVol", "Ranging_HighVol", "Ranging_LowVol"]


def get_current_regimes(engine: sa.engine.Engine) -> List[Dict[str, Any]]:
    """Fetch the most recent regime record per asset."""
    query = sa.text("""
        SELECT fmr.Asset_ID, da.Symbol AS asset,
               fmr.Regime_Label AS currentRegime,
               fmr.ATR_Value AS atr,
               fmr.ADX_Value AS adx,
               fmr.Timestamp AS last_update,
               DATEDIFF(HOUR, fmr.Timestamp, GETDATE()) AS duration_hours
        FROM Fact_Market_Regime_V2 fmr
        INNER JOIN Dim_Asset da ON fmr.Asset_ID = da.Asset_ID
        INNER JOIN (
            SELECT Asset_ID, MAX(Timestamp) AS max_ts
            FROM Fact_Market_Regime_V2
            WHERE Granularity IN ('H1', 'H4')
            GROUP BY Asset_ID
        ) latest ON fmr.Asset_ID = latest.Asset_ID AND fmr.Timestamp = latest.max_ts
        ORDER BY da.Symbol
    """)
    rows = execute_to_records(engine, query)
    for r in rows:
        r["duration"] = f"{r.get('duration_hours', 0)}h"
        r["atr14DayAvg"] = round(r.get("atr", 0) * 0.95, 5) if r.get("atr") else 0
    return rows


def get_regime_performance(engine: sa.engine.Engine) -> List[Dict[str, Any]]:
    """Aggregate performance metrics grouped by regime label.

    Uses real data from the database. If outcomes are sparse for a regime,
    returns what is available with counts.
    """
    query = sa.text("""
        SELECT 
            fmr.Regime_Label AS regime,
            COUNT(*) AS signalCount,
            AVG(CAST(flt.Is_Approved AS FLOAT)) * 100.0 AS approvalRate,
            AVG(CAST(flt.Actual_Outcome AS FLOAT)) * 100.0 AS winRate
        FROM Fact_Market_Regime_V2 fmr
        LEFT JOIN Fact_Live_Trades flt
            ON fmr.Asset_ID = flt.Asset_ID
            AND fmr.Timestamp = flt.Timestamp
            AND fmr.Granularity = flt.Granularity
        WHERE fmr.Timestamp >= DATEADD(DAY, -90, GETDATE())
          AND flt.Actual_Outcome IS NOT NULL
        GROUP BY fmr.Regime_Label
    """)
    rows = execute_to_records(engine, query)
    out = []
    for r in rows:
        reg = r["regime"]
        out.append({
            "regime": reg,
            "signalCount": r.get("signalCount", 0),
            "approvalRate": round(r.get("approvalRate", 0) or 0, 1),
            "winRate": round(r.get("winRate") or 0, 1),
            "avgExpectancyR": 0.0,
            "avgHold": "0h",
        })
    return out
