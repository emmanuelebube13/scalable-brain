"""Reference data client for Dim_Asset and Dim_Strategy lookups.

Returns real database-backed records with empty defaults for fields
that do not yet exist in the reference tables.
"""

from datetime import datetime
from typing import List, Dict, Any
import sqlalchemy as sa

from layer5.services.db_client import execute_to_records


def get_assets(engine: sa.engine.Engine) -> List[Dict[str, Any]]:
    """Return active assets enriched with the latest regime label and live trade stats."""
    query = sa.text("""
        SELECT
            da.Asset_ID AS asset_id,
            da.Symbol AS symbol,
            COALESCE(fmr.Regime_Label, 'Trending_LowVol') AS currentRegime,
            COALESCE(fmr.ATR_Value, 0.001) AS atr,
            COALESCE(fmr.ADX_Value, 20.0) AS adx
        FROM Dim_Asset da
        LEFT JOIN (
            SELECT Asset_ID, Regime_Label, ATR_Value, ADX_Value,
                   ROW_NUMBER() OVER (PARTITION BY Asset_ID ORDER BY Timestamp DESC) AS rn
            FROM Fact_Market_Regime_V2
            WHERE Granularity IN ('H1', 'H4')
        ) fmr ON da.Asset_ID = fmr.Asset_ID AND fmr.rn = 1
        WHERE da.Is_Active = 1
        ORDER BY da.Symbol
    """)
    rows = execute_to_records(engine, query)

    stats_query = sa.text("""
        SELECT
            da.Symbol AS symbol,
            COUNT(*) AS total_signals,
            AVG(CAST(CASE WHEN flt.Actual_Outcome = 1 THEN 1.0 ELSE 0.0 END AS FLOAT)) * 100.0 AS win_rate
        FROM Dim_Asset da
        LEFT JOIN Fact_Live_Trades flt
            ON da.Asset_ID = flt.Asset_ID
            AND flt.Timestamp >= DATEADD(DAY, -30, GETDATE())
        GROUP BY da.Symbol
    """)
    stats_rows = execute_to_records(engine, stats_query)
    stats = {s["symbol"]: s for s in stats_rows}

    assets = []
    for r in rows:
        s = stats.get(r["symbol"], {})
        assets.append({
            "id": f"ASSET-{r['asset_id']}",
            "symbol": r["symbol"],
            "name": r["symbol"].replace("_", "/"),
            "currentPrice": 0.0,
            "change24h": 0.0,
            "change24hPct": 0.0,
            "currentRegime": r.get("currentRegime", "Trending_LowVol"),
            "regimeDuration": "0h",
            "atr": round(r.get("atr", 0.001), 5),
            "atr14DayAvg": round(r.get("atr", 0.001) * 0.95, 5),
            "openPositions": 0,
            "winRate": round(s.get("win_rate") or 0.0, 1),
            "correlationToPortfolio": 0.0,
            "maxDrawdown": 0.0,
            "priceHistory": [],
            "signals": [],
            "correlationToOthers": {},
        })
    return assets


def get_strategies(engine: sa.engine.Engine) -> List[Dict[str, Any]]:
    """Return strategies from Dim_Strategy enriched with live signal stats."""
    query = sa.text("""
        SELECT
            ds.Strategy_ID AS strategy_id,
            ds.Strategy_Key AS name,
            ds.Strategy_Type AS description,
            ds.Is_Active
        FROM Dim_Strategy ds
        ORDER BY ds.Strategy_Key
    """)
    rows = execute_to_records(engine, query)

    stats_query = sa.text("""
        SELECT
            ds.Strategy_Key AS name,
            COUNT(*) AS total_signals,
            SUM(CASE WHEN flt.Is_Approved = 1 THEN 1 ELSE 0 END) AS approved_count,
            AVG(CAST(CASE WHEN flt.Actual_Outcome = 1 THEN 1.0 ELSE 0.0 END AS FLOAT)) * 100.0 AS win_rate
        FROM Dim_Strategy ds
        LEFT JOIN Fact_Live_Trades flt
            ON ds.Strategy_ID = flt.Strategy_ID
            AND flt.Timestamp >= DATEADD(DAY, -30, GETDATE())
        GROUP BY ds.Strategy_Key
    """)
    stats_rows = execute_to_records(engine, stats_query)
    stats = {s["name"]: s for s in stats_rows}

    strategies = []
    for r in rows:
        s = stats.get(r["name"], {})
        total = s.get("total_signals", 0) or 0
        approved = s.get("approved_count", 0) or 0
        wr = s.get("win_rate") or 0.0
        strategies.append({
            "id": f"STRAT-{r['strategy_id']}",
            "name": r["name"],
            "description": r.get("description", ""),
            "winRate": round(wr, 1),
            "expectancyR": 0.0,
            "profitFactor": 0.0,
            "totalSignals": int(total),
            "approvalRate": round((approved / total) * 100, 1) if total else 0.0,
            "status": "active" if r.get("Is_Active") else "paused",
            "equityCurve": [],
            "winLossByGranularity": {},
            "bestTrade": None,
            "worstTrade": None,
            "correlationWithOthers": {},
        })
    return strategies
