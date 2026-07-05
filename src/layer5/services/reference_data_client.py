"""Reference data client for Dim_Asset and Dim_Strategy lookups.

Returns real database-backed records with empty defaults for fields
that do not yet exist in the reference tables.
"""

from datetime import datetime
from typing import List, Dict, Any
import sqlalchemy as sa

from layer5.services.db_client import execute_to_records


def _table_columns(engine: sa.engine.Engine, table_name: str) -> set[str]:
    query = sa.text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE lower(table_name) = lower(:table_name)
    """)
    rows = execute_to_records(engine, query, {"table_name": table_name})
    return {str(r["column_name"]).lower() for r in rows if r.get("column_name")}


def get_assets(engine: sa.engine.Engine) -> List[Dict[str, Any]]:
    """Return active assets enriched with the latest regime label and live trade stats."""
    dim_asset_cols = _table_columns(engine, "Dim_Asset")
    asset_active_filter = (
        "WHERE da.Is_Active = TRUE" if "is_active" in dim_asset_cols else ""
    )

    query = sa.text(f"""
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
        {asset_active_filter}
        ORDER BY da.Symbol
    """)
    rows = execute_to_records(engine, query)

    stats_query = sa.text("""
        SELECT
            da.Symbol AS symbol,
            COUNT(*) AS total_signals,
            AVG(CAST(CASE WHEN flt.Actual_Outcome = 1 THEN 1.0 ELSE 0.0 END AS FLOAT)) * 100.0 AS win_rate,
            SUM(CASE WHEN flt.Is_Approved = 1 AND flt.Close_Time IS NULL THEN 1 ELSE 0 END) AS open_positions
        FROM Dim_Asset da
        LEFT JOIN Fact_Live_Trades flt
            ON da.Asset_ID = flt.Asset_ID
            AND flt.Timestamp >= now() - INTERVAL '30 days'
        GROUP BY da.Symbol
    """)
    stats_rows = execute_to_records(engine, stats_query)
    stats = {s["symbol"]: s for s in stats_rows}

    price_query = sa.text("""
        SELECT
            da.Symbol AS symbol,
            COALESCE(flt.Created_At, flt.Timestamp) AS ts,
            flt.Entry_Price AS px
        FROM Fact_Live_Trades flt
        INNER JOIN Dim_Asset da ON flt.Asset_ID = da.Asset_ID
        WHERE flt.Entry_Price IS NOT NULL
          AND COALESCE(flt.Created_At, flt.Timestamp) >= NOW() - INTERVAL '7 days'
        ORDER BY da.Symbol, COALESCE(flt.Created_At, flt.Timestamp)
    """)
    price_rows = execute_to_records(engine, price_query)
    price_history: Dict[str, List[Dict[str, Any]]] = {}
    for p in price_rows:
        symbol = p.get("symbol")
        if not symbol:
            continue
        px = float(p.get("px") or 0.0)
        if px <= 0:
            continue
        history = price_history.setdefault(symbol, [])
        history.append(
            {
                "timestamp": p.get("ts"),
                "open": px,
                "high": px,
                "low": px,
                "close": px,
                "volume": 0,
            }
        )

    for symbol, values in list(price_history.items()):
        if len(values) > 60:
            price_history[symbol] = values[-60:]

    latest_price_query = sa.text("""
        SELECT symbol, [close] AS last_close
        FROM (
            SELECT
                da.Symbol AS symbol,
                fmp.[Close] AS [close],
                ROW_NUMBER() OVER (PARTITION BY da.Symbol ORDER BY fmp.[Timestamp] DESC) AS rn
            FROM Fact_Market_Prices fmp
            INNER JOIN Dim_Asset da ON da.Asset_ID = fmp.Asset_ID
            WHERE fmp.[Close] IS NOT NULL
        ) t
        WHERE rn = 1
    """)
    latest_price_rows = execute_to_records(engine, latest_price_query)
    latest_prices = {
        str(r.get("symbol")): float(r.get("last_close") or 0.0)
        for r in latest_price_rows
        if r.get("symbol")
    }

    assets = []
    for r in rows:
        s = stats.get(r["symbol"], {})
        assets.append(
            {
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
            }
        )
    return assets


def get_strategies(engine: sa.engine.Engine) -> List[Dict[str, Any]]:
    """Return strategies from Dim_Strategy enriched with live signal stats."""
    # NOTE: dim_strategy has no strategy_key column in the live schema;
    # strategy_name is used as the display name (FND-004 Phase 3 drift).
    query = sa.text("""
        SELECT
            ds.Strategy_ID AS strategy_id,
            ds.Strategy_Name AS name,
            ds.Strategy_Type AS description,
            ds.Is_Active AS "Is_Active"
        FROM Dim_Strategy ds
        ORDER BY ds.Strategy_Name
    """)
    rows = execute_to_records(engine, query)

    stats_query = sa.text("""
        SELECT
            ds.Strategy_Name AS name,
            COUNT(*) AS total_signals,
            SUM(CASE WHEN flt.Is_Approved = 1 THEN 1 ELSE 0 END) AS approved_count,
            AVG(CAST(CASE WHEN flt.Actual_Outcome = 1 THEN 1.0 ELSE 0.0 END AS FLOAT)) * 100.0 AS win_rate
        FROM Dim_Strategy ds
        LEFT JOIN Fact_Live_Trades flt
            ON ds.Strategy_ID = flt.Strategy_ID
            AND flt.Timestamp >= now() - INTERVAL '30 days'
        GROUP BY ds.Strategy_Name
    """)
    stats_rows = execute_to_records(engine, stats_query)
    stats = {s["name"]: s for s in stats_rows}

    strategies = []
    for r in rows:
        s = stats.get(r["name"], {})
        total = s.get("total_signals", 0) or 0
        approved = s.get("approved_count", 0) or 0
        wr = s.get("win_rate") or 0.0
        strategies.append(
            {
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
            }
        )
    return strategies
