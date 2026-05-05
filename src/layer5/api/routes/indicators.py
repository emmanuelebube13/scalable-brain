"""Technical Indicators routes — indicator calculation endpoints with caching.

Provides 30+ institutional-grade technical indicators with:
- Redis caching (if available) with in-memory fallback
- Batch calculation for efficiency
- Indicator metadata and documentation
"""

import time
import hashlib
import json
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from functools import wraps
from fastapi import APIRouter, Depends, Query, Body, HTTPException
import sqlalchemy as sa

from layer5.api.dependencies import get_db
from layer5.services import indicators_client, chart_data_client
from layer5.services import indicators_library
from layer5.services.data_contracts import (
    IndicatorResult,
    IndicatorInfo,
    IndicatorBatchRequest,
    IndicatorMetadata,
    OHLCData
)

router = APIRouter()

# =============================================================================
# Caching Setup
# =============================================================================

# In-memory cache (fallback when Redis is not available)
_in_memory_cache: Dict[str, Dict[str, Any]] = {}

# Try to import Redis
try:
    import redis
    from layer5.api.config import REDIS_HOST, REDIS_PORT, REDIS_DB
    
    _redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2
    )
    # Test connection
    _redis_client.ping()
    _redis_available = True
    print("[Indicators API] Redis caching enabled")
except Exception:
    _redis_available = False
    _redis_client = None
    print("[Indicators API] Using in-memory caching (Redis not available)")


def _generate_cache_key(
    symbol: str,
    indicator: str,
    timeframe: str,
    params: Dict[str, Any],
    limit: int
) -> str:
    """Generate a cache key for indicator calculations."""
    # Normalize params for consistent hashing
    params_str = json.dumps(params, sort_keys=True, default=str)
    key_data = f"{symbol}:{indicator}:{timeframe}:{params_str}:{limit}"
    return f"indicator:{hashlib.md5(key_data.encode()).hexdigest()}"


def _get_cached_result(cache_key: str) -> Optional[Dict[str, Any]]:
    """Get cached result if available and not expired."""
    try:
        if _redis_available and _redis_client:
            data = _redis_client.get(cache_key)
            if data:
                return json.loads(data)
        else:
            # In-memory cache
            entry = _in_memory_cache.get(cache_key)
            if entry and entry["expires"] > time.time():
                return entry["data"]
            elif entry:
                # Expired, remove it
                del _in_memory_cache[cache_key]
    except Exception as e:
        print(f"[Indicators API] Cache get error: {e}")
    
    return None


def _set_cached_result(
    cache_key: str,
    data: Dict[str, Any],
    ttl_seconds: int = 300
) -> None:
    """Cache calculation result."""
    try:
        if _redis_available and _redis_client:
            _redis_client.setex(
                cache_key,
                ttl_seconds,
                json.dumps(data, default=str)
            )
        else:
            # In-memory cache with TTL
            _in_memory_cache[cache_key] = {
                "data": data,
                "expires": time.time() + ttl_seconds
            }
            
            # Cleanup old entries if cache gets too large
            if len(_in_memory_cache) > 1000:
                now = time.time()
                expired_keys = [
                    k for k, v in _in_memory_cache.items()
                    if v["expires"] <= now
                ]
                for k in expired_keys[:100]:
                    del _in_memory_cache[k]
    except Exception as e:
        print(f"[Indicators API] Cache set error: {e}")


def cache_indicator_result(ttl_seconds: int = 300):
    """Decorator to cache indicator calculation results."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract parameters from kwargs
            symbol = kwargs.get("symbol", "")
            indicator = kwargs.get("indicator", "")
            timeframe = kwargs.get("timeframe", "1h")
            params = kwargs.get("params", {})
            limit = kwargs.get("limit", 500)
            skip_cache = kwargs.get("skip_cache", False)
            
            if skip_cache:
                return func(*args, **kwargs)
            
            cache_key = _generate_cache_key(symbol, indicator, timeframe, params, limit)
            
            # Try to get from cache
            cached = _get_cached_result(cache_key)
            if cached:
                print(f"[Indicators API] Cache hit for {indicator} ({symbol})")
                return IndicatorResult(**cached)
            
            # Calculate and cache
            result = func(*args, **kwargs)
            
            if result and not result.error:
                _set_cached_result(cache_key, result.model_dump(), ttl_seconds)
            
            return result
        return wrapper
    return decorator


# =============================================================================
# Indicator Endpoints
# =============================================================================

@router.get("/list", response_model=List[IndicatorInfo])
def get_available_indicators(
    category: Optional[str] = Query(None, description="Filter by category (trend, momentum, volatility, volume, trend_strength)")
):
    """Get list of available technical indicators with default parameters.
    
    Returns all 30+ indicators including:
    - **Trend**: SMA, EMA, WMA, TEMA, DEMA, MACD, ADX, MA Ribbon
    - **Momentum**: RSI, Stochastic, ROC, CCI, Williams %R
    - **Volatility**: Bollinger Bands, ATR, Keltner Channel, NATR, Historical Volatility
    - **Volume**: OBV, VWAP, Volume ROC, A/D Line, MFI
    - **Trend Strength**: QStick, VHF, Mass Index
    """
    indicators = indicators_library.get_available_indicators_list()
    
    if category:
        indicators = [ind for ind in indicators if ind["category"] == category.lower()]
    
    return [IndicatorInfo(
        id=ind["id"],
        name=ind["name"],
        category=ind["category"],
        defaultParams=ind["default_params"]
    ) for ind in indicators]


@router.get("/metadata/{indicator_id}", response_model=IndicatorMetadata)
def get_indicator_metadata(
    indicator_id: str,
    include_description: bool = Query(True, description="Include detailed description")
):
    """Get detailed metadata for a specific indicator.
    
    Includes formula, interpretation guidelines, parameter ranges,
    and trading signals the indicator generates.
    """
    info = indicators_library.get_indicator_info(indicator_id)
    
    if not info:
        raise HTTPException(status_code=404, detail=f"Indicator '{indicator_id}' not found")
    
    # Build detailed metadata
    descriptions = {
        "rsi": {
            "description": "Relative Strength Index measures the magnitude of recent price changes to evaluate overbought or oversold conditions.",
            "formula": "RSI = 100 - (100 / (1 + RS)) where RS = Average Gain / Average Loss",
            "interpretation": "Values above 70 indicate overbought conditions. Values below 30 indicate oversold conditions.",
            "signals": ["overbought", "oversold", "divergence"]
        },
        "macd": {
            "description": "Moving Average Convergence Divergence shows the relationship between two EMAs of price.",
            "formula": "MACD = EMA(12) - EMA(26), Signal = EMA(9) of MACD",
            "interpretation": "Bullish when MACD crosses above signal. Bearish when MACD crosses below signal.",
            "signals": ["bullish_crossover", "bearish_crossover", "divergence"]
        },
        "bollinger_bands": {
            "description": "Bollinger Bands consist of a middle SMA band and upper/lower bands at standard deviations.",
            "formula": "Middle = SMA(20), Upper = Middle + 2*StdDev, Lower = Middle - 2*StdDev",
            "interpretation": "Price near upper band suggests overbought. Price near lower band suggests oversold.",
            "signals": ["squeeze", "breakout", "mean_reversion"]
        },
        "adx": {
            "description": "Average Directional Index measures trend strength regardless of direction.",
            "formula": "ADX = Smoothed DX over 14 periods",
            "interpretation": "ADX > 25 indicates strong trend. ADX < 20 indicates weak/no trend.",
            "signals": ["trend_strength", "trend_weakness"]
        },
        "atr": {
            "description": "Average True Range measures market volatility.",
            "formula": "ATR = Smoothed average of True Range over N periods",
            "interpretation": "Higher ATR indicates higher volatility. Used for stop-loss positioning.",
            "signals": ["volatility_expansion", "volatility_contraction"]
        },
        "stochastic": {
            "description": "Stochastic Oscillator compares closing price to price range over time.",
            "formula": "%K = 100 * (Close - Lowest Low) / (Highest High - Lowest Low)",
            "interpretation": "Values above 80 overbought. Values below 20 oversold.",
            "signals": ["overbought", "oversold", "crossover"]
        },
        "obv": {
            "description": "On-Balance Volume is a cumulative indicator using volume flow.",
            "formula": "OBV = Previous OBV + Volume if Close > Previous Close, else - Volume",
            "interpretation": "Rising OBV confirms uptrend. Falling OBV confirms downtrend.",
            "signals": ["volume_confirmation", "divergence"]
        },
        "vwap": {
            "description": "Volume Weighted Average Price shows average price weighted by volume.",
            "formula": "VWAP = Sum(Typical Price * Volume) / Sum(Volume)",
            "interpretation": "Price above VWAP suggests bullish. Price below suggests bearish.",
            "signals": ["support", "resistance", "trend_bias"]
        }
    }
    
    desc_data = descriptions.get(indicator_id.lower(), {
        "description": f"{info['name']} technical indicator.",
        "formula": None,
        "interpretation": "Refer to technical analysis literature.",
        "signals": []
    })
    
    # Parameter ranges
    param_ranges = {}
    for param_name, default_value in info["default_params"].items():
        if param_name in ("period", "fast", "slow", "signal"):
            param_ranges[param_name] = {
                "type": "integer",
                "min": 2,
                "max": 200,
                "default": default_value
            }
        elif param_name == "std_dev":
            param_ranges[param_name] = {
                "type": "float",
                "min": 0.5,
                "max": 4.0,
                "default": default_value
            }
        elif param_name == "annualize":
            param_ranges[param_name] = {
                "type": "boolean",
                "default": default_value
            }
        elif param_name == "periods":
            param_ranges[param_name] = {
                "type": "array",
                "items": "integer",
                "default": default_value
            }
    
    return IndicatorMetadata(
        id=info["id"],
        name=info["name"],
        category=info["category"],
        description=desc_data["description"],
        formula=desc_data.get("formula"),
        interpretation=desc_data.get("interpretation"),
        defaultParams=info["default_params"],
        paramRanges=param_ranges,
        returnType=info["return_type"],
        signals=desc_data.get("signals")
    )


@router.post("/calculate", response_model=IndicatorResult)
@cache_indicator_result(ttl_seconds=300)
def calculate_indicator(
    symbol: str = Query(..., description="Trading symbol"),
    indicator: str = Query(..., description="Indicator type (sma, ema, rsi, macd, bollinger_bands, etc.)"),
    timeframe: str = Query("1h", description="Timeframe for calculation"),
    params: Optional[Dict[str, Any]] = Body(None, description="Indicator parameters"),
    limit: int = Query(500, ge=100, le=2000, description="Number of data points"),
    skip_cache: bool = Query(False, description="Skip cache and force recalculation"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Calculate a technical indicator for the specified symbol.
    
    Results are cached for 5 minutes to improve performance.
    Use `skip_cache=true` to force recalculation.
    
    Available indicators:
    - **Trend**: sma, ema, wma, tema, dema, macd, adx, ma_ribbon
    - **Momentum**: rsi, stochastic, roc, cci, williams_r
    - **Volatility**: bollinger_bands, atr, keltner_channel, natr, historical_volatility
    - **Volume**: obv, vwap, volume_roc, accumulation_distribution, mfi
    - **Trend Strength**: qstick, vhf, mass_index
    
    Returns indicator values aligned with OHLC timestamps.
    """
    # Get OHLC data
    ohlc_data = chart_data_client.get_ohlc_data(
        conn.engine, symbol, timeframe, limit
    )
    
    if not ohlc_data:
        return IndicatorResult(
            indicator=indicator,
            error="No data available for symbol/timeframe",
            values=[]
        )
    
    # Calculate using the new indicators library
    params = params or {}
    result = indicators_library.calculate_indicator(
        ohlc_data, indicator, params
    )
    
    if result.get("error"):
        return IndicatorResult(
            indicator=indicator,
            error=result["error"],
            values=[]
        )
    
    # Build IndicatorResult from calculation result
    values = result.get("values", [])
    timestamps = [c["timestamp"] for c in ohlc_data]
    
    # Handle different return types
    indicator_result = IndicatorResult(
        indicator=indicator,
        name=result.get("display_name", indicator),
        timestamps=timestamps,
        params=params
    )
    
    if isinstance(values, dict):
        # Multi-output indicator (MACD, Bollinger, etc.)
        if "macd" in values:
            indicator_result.values = values.get("macd", [])
            indicator_result.signal = values.get("signal", [])
            indicator_result.histogram = values.get("histogram", [])
        elif "upper" in values:
            indicator_result.upper = values.get("upper", [])
            indicator_result.middle = values.get("middle", [])
            indicator_result.lower = values.get("lower", [])
        elif "k" in values:
            indicator_result.k = values.get("k", [])
            indicator_result.d = values.get("d", [])
        elif "plus_di" in values:
            indicator_result.plus_di = values.get("plus_di", [])
            indicator_result.minus_di = values.get("minus_di", [])
            indicator_result.values = values.get("adx", [])
        else:
            # Generic dict result - use first key as values
            first_key = list(values.keys())[0] if values else None
            if first_key:
                indicator_result.values = values.get(first_key, [])
    else:
        # Single value list
        indicator_result.values = values if values else []
    
    # Add overbought/oversold for RSI
    if indicator.lower() == "rsi":
        indicator_result.overbought = params.get("overbought", 70)
        indicator_result.oversold = params.get("oversold", 30)
    
    return indicator_result


@router.post("/calculate-batch", response_model=List[IndicatorResult])
def calculate_indicators_batch(
    symbol: str = Query(..., description="Trading symbol"),
    timeframe: str = Query("1h", description="Timeframe for calculation"),
    indicators: List[IndicatorBatchRequest] = Body(..., description="List of indicators to calculate"),
    limit: int = Query(500, ge=100, le=2000, description="Number of data points"),
    skip_cache: bool = Query(False, description="Skip cache and force recalculation"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Calculate multiple indicators at once for efficient batch processing.
    
    This endpoint is optimized for fetching multiple indicators in a single
    database query, significantly reducing latency.
    
    Example request body:
    ```json
    [
        {"indicator": "sma", "params": {"period": 20}},
        {"indicator": "rsi", "params": {"period": 14}},
        {"indicator": "macd", "params": {"fast": 12, "slow": 26}}
    ]
    ```
    """
    # Get OHLC data once
    ohlc_data = chart_data_client.get_ohlc_data(
        conn.engine, symbol, timeframe, limit
    )
    
    if not ohlc_data:
        return []
    
    results = []
    timestamps = [c["timestamp"] for c in ohlc_data]
    
    for ind_config in indicators:
        indicator_name = ind_config.indicator
        params = ind_config.params or {}
        
        # Check cache first
        cache_key = _generate_cache_key(symbol, indicator_name, timeframe, params, limit)
        cached = _get_cached_result(cache_key) if not skip_cache else None
        
        if cached:
            results.append(IndicatorResult(**cached))
            continue
        
        # Calculate indicator
        calc_result = indicators_library.calculate_indicator(
            ohlc_data, indicator_name, params
        )
        
        if calc_result.get("error"):
            results.append(IndicatorResult(
                indicator=indicator_name,
                error=calc_result["error"],
                values=[]
            ))
            continue
        
        # Build result
        values = calc_result.get("values", [])
        
        indicator_result = IndicatorResult(
            indicator=indicator_name,
            name=calc_result.get("display_name", indicator_name),
            timestamps=timestamps,
            params=params
        )
        
        if isinstance(values, dict):
            if "macd" in values:
                indicator_result.values = values.get("macd", [])
                indicator_result.signal = values.get("signal", [])
                indicator_result.histogram = values.get("histogram", [])
            elif "upper" in values:
                indicator_result.upper = values.get("upper", [])
                indicator_result.middle = values.get("middle", [])
                indicator_result.lower = values.get("lower", [])
            elif "k" in values:
                indicator_result.k = values.get("k", [])
                indicator_result.d = values.get("d", [])
            elif "plus_di" in values:
                indicator_result.plus_di = values.get("plus_di", [])
                indicator_result.minus_di = values.get("minus_di", [])
                indicator_result.values = values.get("adx", [])
            else:
                first_key = list(values.keys())[0] if values else None
                if first_key:
                    indicator_result.values = values.get(first_key, [])
        else:
            indicator_result.values = values if values else []
        
        # Add RSI levels
        if indicator_name.lower() == "rsi":
            indicator_result.overbought = params.get("overbought", 70)
            indicator_result.oversold = params.get("oversold", 30)
        
        # Cache the result
        if not skip_cache:
            _set_cached_result(cache_key, indicator_result.model_dump(), 300)
        
        results.append(indicator_result)
    
    return results


@router.get("/{indicator}/default-params", response_model=Dict[str, Any])
def get_indicator_default_params(
    indicator: str,
):
    """Get default parameters for a specific indicator."""
    info = indicators_library.get_indicator_info(indicator)
    
    if info:
        return info.get("default_params", {})
    
    # Fallback to old method
    indicators = indicators_client.get_available_indicators()
    for ind in indicators:
        if ind["id"] == indicator:
            return ind.get("defaultParams", {})
    
    return {}


@router.post("/validate-params")
def validate_indicator_parameters(
    indicator: str = Query(..., description="Indicator name"),
    params: Dict[str, Any] = Body(..., description="Parameters to validate")
):
    """Validate indicator parameters before calculation.
    
    Returns validation result with normalized parameters if valid,
    or error messages if invalid.
    """
    validation = indicators_library.validate_indicator_params(indicator, params)
    
    return {
        "valid": validation["valid"],
        "error": validation.get("error"),
        "normalized_params": validation.get("normalized_params", {}),
        "indicator": indicator
    }


@router.get("/categories/list")
def get_indicator_categories():
    """Get list of indicator categories with counts."""
    indicators = indicators_library.get_available_indicators_list()
    
    categories = {}
    for ind in indicators:
        cat = ind["category"]
        if cat not in categories:
            categories[cat] = {"count": 0, "indicators": []}
        categories[cat]["count"] += 1
        categories[cat]["indicators"].append(ind["id"])
    
    category_info = {
        "trend": {
            "name": "Trend Indicators",
            "description": "Identify direction and strength of price trends"
        },
        "momentum": {
            "name": "Momentum Indicators",
            "description": "Measure speed and magnitude of price movements"
        },
        "volatility": {
            "name": "Volatility Indicators",
            "description": "Measure price variability and range expansion"
        },
        "volume": {
            "name": "Volume Indicators",
            "description": "Analyze trading volume and money flow"
        },
        "trend_strength": {
            "name": "Trend Strength Indicators",
            "description": "Determine if prices are trending or ranging"
        }
    }
    
    result = []
    for cat_id, data in categories.items():
        info = category_info.get(cat_id, {})
        result.append({
            "id": cat_id,
            "name": info.get("name", cat_id.title()),
            "description": info.get("description", ""),
            "indicator_count": data["count"],
            "indicators": data["indicators"]
        })
    
    return sorted(result, key=lambda x: x["name"])


@router.delete("/cache/clear")
def clear_indicator_cache(
    symbol: Optional[str] = Query(None, description="Clear cache for specific symbol only")
):
    """Clear the indicator calculation cache.
    
    Use this after data updates or when you want to force fresh calculations.
    """
    try:
        if _redis_available and _redis_client:
            if symbol:
                # Clear only keys matching symbol pattern
                pattern = f"indicator:*{symbol}*"
                keys = _redis_client.scan_iter(match=pattern)
                count = 0
                for key in keys:
                    _redis_client.delete(key)
                    count += 1
                return {"cleared": count, "scope": f"symbol:{symbol}", "backend": "redis"}
            else:
                # Clear all indicator cache
                keys = _redis_client.scan_iter(match="indicator:*")
                count = 0
                for key in keys:
                    _redis_client.delete(key)
                    count += 1
                return {"cleared": count, "scope": "all", "backend": "redis"}
        else:
            # Clear in-memory cache
            global _in_memory_cache
            if symbol:
                keys_to_remove = [
                    k for k in _in_memory_cache.keys()
                    if symbol in k
                ]
                for k in keys_to_remove:
                    del _in_memory_cache[k]
                return {"cleared": len(keys_to_remove), "scope": f"symbol:{symbol}", "backend": "memory"}
            else:
                count = len(_in_memory_cache)
                _in_memory_cache.clear()
                return {"cleared": count, "scope": "all", "backend": "memory"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {e}")


@router.get("/cache/stats")
def get_cache_stats():
    """Get cache statistics."""
    try:
        if _redis_available and _redis_client:
            keys = list(_redis_client.scan_iter(match="indicator:*"))
            return {
                "backend": "redis",
                "cached_indicators": len(keys),
                "redis_connected": True,
                "ttl_seconds": 300
            }
        else:
            # Clean expired entries before counting
            now = time.time()
            expired = [k for k, v in _in_memory_cache.items() if v["expires"] <= now]
            for k in expired:
                del _in_memory_cache[k]
            
            return {
                "backend": "memory",
                "cached_indicators": len(_in_memory_cache),
                "memory_limit": 1000,
                "ttl_seconds": 300
            }
    except Exception as e:
        return {
            "backend": "unknown",
            "error": str(e),
            "cached_indicators": 0
        }
