"""Chart data service — OHLC and price history access for institutional-grade charting.

Reads from Fact_Market_Regime_V2, Fact_Live_Trades, Fact_Market_Prices and Dim_Asset.
Provides multi-timeframe OHLC data for professional charting.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional, Literal
import sqlalchemy as sa
import pandas as pd

from layer5.services.db_client import execute_to_records, execute_query

# Timeframe configurations
TIMEFRAMES = {
    "1m": {"minutes": 1, "sql_interval": "MINUTE"},
    "5m": {"minutes": 5, "sql_interval": "MINUTE"},
    "15m": {"minutes": 15, "sql_interval": "MINUTE"},
    "30m": {"minutes": 30, "sql_interval": "MINUTE"},
    "1h": {"minutes": 60, "sql_interval": "HOUR"},
    "2h": {"minutes": 120, "sql_interval": "HOUR"},
    "4h": {"minutes": 240, "sql_interval": "HOUR"},
    "6h": {"minutes": 360, "sql_interval": "HOUR"},
    "8h": {"minutes": 480, "sql_interval": "HOUR"},
    "12h": {"minutes": 720, "sql_interval": "HOUR"},
    "1d": {"minutes": 1440, "sql_interval": "DAY"},
    "1w": {"minutes": 10080, "sql_interval": "WEEK"},
    "1M": {"minutes": 43200, "sql_interval": "MONTH"},
}

TimeframeType = Literal[
    "1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "1w", "1M"
]


def _get_asset_id(engine: sa.engine.Engine, symbol: str) -> Optional[int]:
    """Get Asset_ID from symbol."""
    query = sa.text("""
        SELECT Asset_ID FROM Dim_Asset WHERE Symbol = :symbol
    """)
    rows = execute_to_records(engine, query, {"symbol": symbol})
    return rows[0]["Asset_ID"] if rows else None


def get_ohlc_data(
    engine: sa.engine.Engine,
    symbol: str,
    timeframe: TimeframeType = "1h",
    limit: int = 500,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Fetch OHLC data for charting from Fact_Market_Prices.
    
    Prioritizes Fact_Market_Prices data.
    Falls back to Fact_Live_Trades entry prices if needed.
    Returns only real persisted data. No synthetic fallback is allowed.
    """
    asset_id = _get_asset_id(engine, symbol)
    print(f"[ChartDataClient] get_ohlc_data: symbol={symbol}, asset_id={asset_id}, timeframe={timeframe}")
    if not asset_id:
        print(f"[ChartDataClient] Asset not found for symbol: {symbol}")
        return []
    
    # First try Fact_Market_Prices (primary data source)
    try:
        print(f"[ChartDataClient] Attempting to fetch from Fact_Market_Prices...")
        ohlc_from_prices = _get_ohlc_from_market_prices(engine, asset_id, timeframe, limit, start_date, end_date)
        print(f"[ChartDataClient] Fact_Market_Prices returned {len(ohlc_from_prices)} candles")
        if ohlc_from_prices:
            return ohlc_from_prices
    except Exception as e:
        print(f"[ChartDataClient] Warning: Failed to fetch from Fact_Market_Prices: {e}")
    
    # Fallback to Fact_Live_Trades
    print(f"[ChartDataClient] Falling back to Fact_Live_Trades...")
    result = _get_ohlc_from_live_trades(engine, asset_id, timeframe, limit, start_date, end_date)
    print(f"[ChartDataClient] Fact_Live_Trades returned {len(result)} candles")
    
    if result:
        return result
    
    print(f"[ChartDataClient] No data available for {symbol}")
    return result


def _get_ohlc_from_market_prices(
    engine: sa.engine.Engine,
    asset_id: int,
    timeframe: TimeframeType,
    limit: int,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
) -> List[Dict[str, Any]]:
    """Get OHLC data from Fact_Market_Prices table."""
    
    # Build date filter
    date_filter = ""
    params = {"asset_id": asset_id}
    
    if start_date:
        date_filter += " AND fmp.Timestamp >= :start_date"
        params["start_date"] = start_date
    if end_date:
        date_filter += " AND fmp.Timestamp <= :end_date"
        params["end_date"] = end_date
    else:
        # Default to last 30 days if no date range
        date_filter += " AND fmp.Timestamp >= NOW() - INTERVAL '30 days'"
    
    # Query market prices directly (PostgreSQL allows LIMIT as a parameter)
    query = sa.text(f"""
        SELECT
            fmp.Timestamp as timestamp,
            fmp.[Open] as [open],
            fmp.High as high,
            fmp.Low as low,
            fmp.[Close] as [close],
            fmp.Volume as volume
        FROM Fact_Market_Prices fmp
        WHERE fmp.Asset_ID = :asset_id
          {date_filter}
        ORDER BY fmp.Timestamp DESC
        LIMIT {limit}
    """)
    
    print(f"[ChartDataClient._get_ohlc_from_market_prices] Query params: {params}")
    rows = execute_to_records(engine, query, params)
    print(f"[ChartDataClient._get_ohlc_from_market_prices] Query returned {len(rows)} rows")
    
    # Format as OHLC
    ohlc_data = []
    for r in rows:
        ohlc_data.append({
            "timestamp": r["timestamp"],
            "open": round(float(r.get("open") or 0), 5),
            "high": round(float(r.get("high") or 0), 5),
            "low": round(float(r.get("low") or 0), 5),
            "close": round(float(r.get("close") or 0), 5),
            "volume": int(r.get("volume") or 0),
        })
    
    return list(reversed(ohlc_data))


def _get_ohlc_from_live_trades(
    engine: sa.engine.Engine,
    asset_id: int,
    timeframe: TimeframeType,
    limit: int,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
) -> List[Dict[str, Any]]:
    """Get OHLC data by aggregating Fact_Live_Trades entry prices."""
    
    tf_config = TIMEFRAMES.get(timeframe, TIMEFRAMES["1h"])
    interval_seconds = tf_config['minutes'] * 60
    
    # Build date filter
    date_filter = ""
    params = {"asset_id": asset_id}
    
    if start_date:
        date_filter += " AND flt.Timestamp >= :start_date"
        params["start_date"] = start_date
    if end_date:
        date_filter += " AND flt.Timestamp <= :end_date"
        params["end_date"] = end_date
    else:
        # Default to last 30 days if no date range
        date_filter += " AND flt.Timestamp >= NOW() - INTERVAL '30 days'"
    
    # Query to aggregate entry prices into OHLC candles
    query = sa.text(f"""
        WITH price_points AS (
            SELECT 
                flt.Timestamp as ts,
                flt.Entry_Price as price,
                COALESCE(flt.Confidence_Score, 0.5) as volume_proxy
            FROM Fact_Live_Trades flt
            WHERE flt.Asset_ID = :asset_id
              AND flt.Entry_Price IS NOT NULL
              {date_filter}
        ),
        bucketed AS (
            SELECT 
                TO_TIMESTAMP(FLOOR(EXTRACT(EPOCH FROM ts) / {interval_seconds}) * {interval_seconds}) as bucket_time,
                price,
                volume_proxy
            FROM price_points
        )
        SELECT
            bucket_time as timestamp,
            MIN(price) as low,
            MAX(price) as high,
            AVG(price) as close,
            (SELECT price FROM bucketed b2 WHERE b2.bucket_time = bucketed.bucket_time ORDER BY b2.price LIMIT 1) as open,
            COUNT(*) as volume
        FROM bucketed
        GROUP BY bucket_time
        ORDER BY bucket_time DESC
        LIMIT {limit}
    """)
    
    print(f"[ChartDataClient._get_ohlc_from_live_trades] Query params: {params}")
    rows = execute_to_records(engine, query, params)
    print(f"[ChartDataClient._get_ohlc_from_live_trades] Query returned {len(rows)} rows")
    
    # Format as OHLC
    ohlc_data = []
    for r in rows:
        ohlc_data.append({
            "timestamp": r["timestamp"],
            "open": round(float(r.get("open") or 0), 5),
            "high": round(float(r.get("high") or 0), 5),
            "low": round(float(r.get("low") or 0), 5),
            "close": round(float(r.get("close") or 0), 5),
            "volume": int(r.get("volume") or 0),
        })
    
    return list(reversed(ohlc_data))


def get_price_history(
    engine: sa.engine.Engine,
    symbol: str,
    lookback_days: int = 30,
) -> List[Dict[str, Any]]:
    """Get simplified price history for sparklines and mini charts."""
    asset_id = _get_asset_id(engine, symbol)
    if not asset_id:
        return []
    
    query = sa.text("""
        SELECT 
            COALESCE(flt.Created_At, flt.Timestamp) as timestamp,
            flt.Entry_Price as price
        FROM Fact_Live_Trades flt
        WHERE flt.Asset_ID = :asset_id
          AND flt.Entry_Price IS NOT NULL
          AND COALESCE(flt.Created_At, flt.Timestamp) >= NOW() - INTERVAL '1 day' * :lookback
        ORDER BY COALESCE(flt.Created_At, flt.Timestamp)
    """)
    
    rows = execute_to_records(engine, query, {"asset_id": asset_id, "lookback": lookback_days})
    
    return [
        {
            "timestamp": r["timestamp"],
            "price": round(float(r.get("price") or 0), 5),
        }
        for r in rows
    ]


def get_volume_profile(
    engine: sa.engine.Engine,
    symbol: str,
    rows: int = 24,
    lookback_days: int = 7,
) -> List[Dict[str, Any]]:
    """Calculate volume profile (volume at price) for the symbol."""
    asset_id = _get_asset_id(engine, symbol)
    if not asset_id:
        return []
    
    query = sa.text("""
        WITH price_volume AS (
            SELECT 
                flt.Entry_Price as price,
                COUNT(*) as volume
            FROM Fact_Live_Trades flt
            WHERE flt.Asset_ID = :asset_id
              AND flt.Entry_Price IS NOT NULL
              AND COALESCE(flt.Created_At, flt.Timestamp) >= NOW() - INTERVAL '1 day' * :lookback
            GROUP BY flt.Entry_Price
        ),
        price_buckets AS (
            SELECT 
                price,
                volume,
                NTILE(:rows) OVER (ORDER BY price) as bucket
            FROM price_volume
        )
        SELECT 
            AVG(price) as price_level,
            SUM(volume) as volume,
            MIN(price) as price_min,
            MAX(price) as price_max
        FROM price_buckets
        GROUP BY bucket
        ORDER BY price_level
    """)
    
    result = execute_to_records(engine, query, {
        "asset_id": asset_id, 
        "rows": rows,
        "lookback": lookback_days
    })
    
    return [
        {
            "price": round(float(r.get("price_level") or 0), 5),
            "volume": int(r.get("volume") or 0),
            "priceRange": {
                "min": round(float(r.get("price_min") or 0), 5),
                "max": round(float(r.get("price_max") or 0), 5),
            }
        }
        for r in result
    ]


def get_available_symbols(engine: sa.engine.Engine) -> List[Dict[str, Any]]:
    """Get list of available symbols with their latest price info."""
    query = sa.text("""
        SELECT 
            da.Symbol as symbol,
            da.Asset_ID as asset_id,
            COALESCE(fmr.Regime_Label, 'Trending_LowVol') as regime,
            COALESCE(fmr.ATR_Value, 0.001) as atr,
            COALESCE(fmr.ADX_Value, 20.0) as adx
        FROM Dim_Asset da
        LEFT JOIN (
            SELECT Asset_ID, Regime_Label, ATR_Value, ADX_Value,
                   ROW_NUMBER() OVER (PARTITION BY Asset_ID ORDER BY Timestamp DESC) as rn
            FROM Fact_Market_Regime_V2
            WHERE Granularity IN ('H1', 'H4')
        ) fmr ON da.Asset_ID = fmr.Asset_ID AND fmr.rn = 1
        ORDER BY da.Symbol
    """)
    
    rows = execute_to_records(engine, query)
    
    # Get latest prices
    symbols = [r["symbol"] for r in rows]
    latest_prices = {}
    
    for symbol in symbols:
        price_history = get_price_history(engine, symbol, lookback_days=1)
        if price_history:
            latest_prices[symbol] = price_history[-1]["price"]
    
    return [
        {
            "symbol": r["symbol"],
            "assetId": r["asset_id"],
            "regime": r["regime"],
            "atr": round(float(r.get("atr") or 0.001), 5),
            "adx": round(float(r.get("adx") or 20.0), 1),
            "lastPrice": latest_prices.get(r["symbol"], 0.0),
        }
        for r in rows
    ]


def get_multi_timeframe_data(
    engine: sa.engine.Engine,
    symbol: str,
    timeframes: List[TimeframeType],
    limit: int = 100,
) -> Dict[str, List[Dict[str, Any]]]:
    """Get OHLC data for multiple timeframes at once."""
    result = {}
    for tf in timeframes:
        result[tf] = get_ohlc_data(engine, symbol, tf, limit)
    return result
