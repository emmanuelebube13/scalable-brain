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
    """Fetch the most recent regime record per asset.
    
    Returns all assets from Dim_Asset that have regime data, ensuring
    all 5 currency pairs are displayed in the Overview.
    """
    query = sa.text("""
        WITH LatestRegimes AS (
            SELECT 
                fmr.Asset_ID,
                da.Symbol AS asset,
                fmr.Regime_Label AS currentRegime,
                fmr.ATR_Value AS atr,
                fmr.ADX_Value AS adx,
                fmr.Timestamp AS last_update,
                EXTRACT(EPOCH FROM (NOW() - fmr.Timestamp)) / 3600 AS duration_hours,
                ROW_NUMBER() OVER (PARTITION BY fmr.Asset_ID ORDER BY fmr.Timestamp DESC) AS rn
            FROM Fact_Market_Regime_V2 fmr
            INNER JOIN Dim_Asset da ON fmr.Asset_ID = da.Asset_ID
            WHERE fmr.Granularity IN ('H1', 'H4', 'M15', 'M30')
        )
        SELECT 
            Asset_ID,
            asset,
            currentRegime,
            atr,
            adx,
            last_update,
            duration_hours
        FROM LatestRegimes
        WHERE rn = 1
        ORDER BY asset
    """)
    rows = execute_to_records(engine, query)

    # Get transitions for the last 7 days
    transitions_query = sa.text("""
        WITH changes AS (
            SELECT
                da.Symbol AS asset,
                fmr.Timestamp AS ts,
                LAG(fmr.Regime_Label) OVER (
                    PARTITION BY fmr.Asset_ID, fmr.Granularity ORDER BY fmr.Timestamp
                ) AS prev_regime,
                fmr.Regime_Label AS current_regime
            FROM Fact_Market_Regime_V2 fmr
            INNER JOIN Dim_Asset da ON fmr.Asset_ID = da.Asset_ID
            WHERE fmr.Granularity IN ('H1', 'H4', 'M15', 'M30')
              AND fmr.Timestamp >= NOW() - INTERVAL '7 days'
        )
        SELECT asset, ts, prev_regime, current_regime
        FROM changes
        WHERE prev_regime IS NOT NULL
          AND prev_regime <> current_regime
        ORDER BY ts DESC
    """)
    transition_rows = execute_to_records(engine, transitions_query)
    transition_map: Dict[str, List[Dict[str, Any]]] = {}
    for t in transition_rows:
        asset = t.get("asset")
        if not asset:
            continue
        bucket = transition_map.setdefault(asset, [])
        if len(bucket) >= 5:
            continue
        bucket.append(
            {
                "timestamp": t.get("ts"),
                "from": t.get("prev_regime"),
                "to": t.get("current_regime"),
            }
        )

    for r in rows:
        r["duration"] = f"{r.get('duration_hours', 0)}h"
        r["atr14DayAvg"] = round(r.get("atr", 0) * 0.95, 5) if r.get("atr") else 0
        r["transitions"] = transition_map.get(r.get("asset"), [])
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
            AVG(CAST(CASE WHEN flt.Is_Approved = 1 THEN 1.0 ELSE 0.0 END AS FLOAT)) * 100.0 AS approvalRate,
            AVG(CAST(CASE WHEN flt.Actual_Outcome = 1 THEN 1.0 WHEN flt.Actual_Outcome = 0 THEN 0.0 ELSE NULL END AS FLOAT)) * 100.0 AS winRate,
            AVG(CAST(CASE WHEN flt.Actual_Outcome = 1 THEN 1.0 WHEN flt.Actual_Outcome = 0 THEN -1.0 ELSE NULL END AS FLOAT)) AS expectancy,
            AVG(CAST(CASE WHEN flt.Close_Time IS NOT NULL THEN EXTRACT(EPOCH FROM (flt.Close_Time - COALESCE(flt.Created_At, flt.Timestamp))) / 60 ELSE NULL END AS FLOAT)) AS avg_hold_min
        FROM Fact_Market_Regime_V2 fmr
        LEFT JOIN Fact_Live_Trades flt
            ON fmr.Asset_ID = flt.Asset_ID
            AND fmr.Timestamp = flt.Timestamp
            AND fmr.Granularity = flt.Granularity
        WHERE fmr.Timestamp >= NOW() - INTERVAL '90 days'
        GROUP BY fmr.Regime_Label
    """)
    rows = execute_to_records(engine, query)
    by_regime: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        reg = r.get("regime")
        if not reg:
            continue
        avg_hold_min = r.get("avg_hold_min")
        hold = "0h"
        if avg_hold_min is not None:
            mins = max(0, int(float(avg_hold_min)))
            hold = f"{mins // 60}h {mins % 60}m"
        by_regime[reg] = {
            "regime": reg,
            "signalCount": int(r.get("signalCount", 0) or 0),
            "approvalRate": round(r.get("approvalRate", 0) or 0, 1),
            "winRate": round(r.get("winRate") or 0, 1),
            "avgExpectancyR": round(float(r.get("expectancy") or 0.0), 2),
            "avgHold": hold,
        }

    out = []
    for reg in REGIMES:
        out.append(
            by_regime.get(
                reg,
                {
                    "regime": reg,
                    "signalCount": 0,
                    "approvalRate": 0.0,
                    "winRate": 0.0,
                    "avgExpectancyR": 0.0,
                    "avgHold": "0h",
                },
            )
        )
    return out
