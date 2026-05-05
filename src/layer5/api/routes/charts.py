"""Chart data routes — OHLC and price history endpoints with advanced charting features."""

from typing import List, Optional, Literal, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
import sqlalchemy as sa
import numpy as np

from layer5.api.dependencies import get_db
from layer5.services import chart_data_client
from layer5.services.data_contracts import (
    OHLCData,
    SimplePricePoint,
    VolumeProfilePoint,
    SymbolInfo,
    MultiTimeframeData,
    SupportResistanceLevel,
    AnalysisMetric,
    AnalysisMetricsResponse,
    StrategyOverlayData,
    StrategyEntryPoint,
    StrategyTradeResult,
    EnhancedVolumeProfile,
    VolumeProfileVPOC,
)

router = APIRouter()


# =============================================================================
# Basic Chart Data Endpoints
# =============================================================================

@router.get("/ohlc", response_model=List[OHLCData])
def get_ohlc(
    symbol: str = Query(..., description="Trading symbol (e.g., EUR_USD)"),
    timeframe: str = Query("1h", description="Timeframe (1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 1w, 1M)"),
    limit: int = Query(500, ge=1, le=5000, description="Number of candles to return"),
    start_date: Optional[datetime] = Query(None, description="Start date for data range"),
    end_date: Optional[datetime] = Query(None, description="End date for data range"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Get OHLC candlestick data for charting.
    
    Returns open, high, low, close prices and volume for the specified
    symbol and timeframe.
    """
    data = chart_data_client.get_ohlc_data(
        conn.engine, symbol, timeframe, limit, start_date, end_date
    )
    print(f"[Layer5 API] get_ohlc({symbol}, {timeframe}) returned {len(data)} candles")
    return [OHLCData(**d) for d in data]


@router.get("/price-history", response_model=List[SimplePricePoint])
def get_price_history(
    symbol: str = Query(..., description="Trading symbol"),
    lookback_days: int = Query(30, ge=1, le=365, description="Days of history to retrieve"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Get simplified price history for sparklines and mini charts."""
    data = chart_data_client.get_price_history(conn.engine, symbol, lookback_days)
    return [SimplePricePoint(**d) for d in data]


@router.get("/volume-profile", response_model=List[VolumeProfilePoint])
def get_volume_profile(
    symbol: str = Query(..., description="Trading symbol"),
    rows: int = Query(24, ge=10, le=100, description="Number of price levels"),
    lookback_days: int = Query(7, ge=1, le=30, description="Days to analyze"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Get volume profile (volume at price) analysis."""
    data = chart_data_client.get_volume_profile(conn.engine, symbol, rows, lookback_days)
    return [VolumeProfilePoint(**d) for d in data]


@router.get("/symbols", response_model=List[SymbolInfo])
def get_available_symbols(
    conn: sa.engine.Connection = Depends(get_db),
):
    """Get list of available trading symbols with metadata."""
    data = chart_data_client.get_available_symbols(conn.engine)
    return [SymbolInfo(**d) for d in data]


@router.get("/multi-timeframe", response_model=MultiTimeframeData)
def get_multi_timeframe(
    symbol: str = Query(..., description="Trading symbol"),
    timeframes: str = Query("1h,4h,1d", description="Comma-separated timeframes"),
    limit: int = Query(100, ge=1, le=1000, description="Candles per timeframe"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Get OHLC data for multiple timeframes at once.
    
    Useful for multi-timeframe analysis and chart synchronization.
    """
    tf_list = [t.strip() for t in timeframes.split(",")]
    data = chart_data_client.get_multi_timeframe_data(conn.engine, symbol, tf_list, limit)
    return MultiTimeframeData(symbol=symbol, data=data)


# =============================================================================
# Advanced Charting Endpoints
# =============================================================================

def _detect_pivot_points(
    highs: List[float],
    lows: List[float],
    timestamps: List[datetime],
    sensitivity: int
) -> tuple:
    """Detect pivot high and low points.
    
    Args:
        highs: List of high prices
        lows: List of low prices
        timestamps: List of timestamps
        sensitivity: Number of bars on each side to confirm pivot
        
    Returns:
        Tuple of (pivot_highs, pivot_lows) where each is a list of
        (index, price, timestamp) tuples
    """
    pivot_highs = []
    pivot_lows = []
    
    for i in range(sensitivity, len(highs) - sensitivity):
        # Check for pivot high
        is_pivot_high = all(
            highs[i] > highs[i - j] for j in range(1, sensitivity + 1)
        ) and all(
            highs[i] > highs[i + j] for j in range(1, sensitivity + 1)
        )
        
        if is_pivot_high:
            pivot_highs.append((i, highs[i], timestamps[i]))
        
        # Check for pivot low
        is_pivot_low = all(
            lows[i] < lows[i - j] for j in range(1, sensitivity + 1)
        ) and all(
            lows[i] < lows[i + j] for j in range(1, sensitivity + 1)
        )
        
        if is_pivot_low:
            pivot_lows.append((i, lows[i], timestamps[i]))
    
    return pivot_highs, pivot_lows


def _cluster_levels(
    pivot_points: List[tuple],
    tolerance_pct: float = 0.002
) -> List[Dict]:
    """Cluster pivot points into support/resistance levels.
    
    Args:
        pivot_points: List of (index, price, timestamp) tuples
        tolerance_pct: Price tolerance for clustering (as decimal)
        
    Returns:
        List of clustered level dictionaries
    """
    if not pivot_points:
        return []
    
    # Sort by price
    sorted_points = sorted(pivot_points, key=lambda x: x[1])
    
    clusters = []
    current_cluster = [sorted_points[0]]
    
    for point in sorted_points[1:]:
        current_price = point[1]
        cluster_avg = sum(p[1] for p in current_cluster) / len(current_cluster)
        
        if abs(current_price - cluster_avg) / cluster_avg <= tolerance_pct:
            current_cluster.append(point)
        else:
            clusters.append(current_cluster)
            current_cluster = [point]
    
    if current_cluster:
        clusters.append(current_cluster)
    
    # Convert clusters to level dictionaries
    levels = []
    for cluster in clusters:
        prices = [p[1] for p in cluster]
        timestamps = [p[2] for p in cluster]
        avg_price = sum(prices) / len(prices)
        
        levels.append({
            "price": round(avg_price, 5),
            "touches": len(cluster),
            "first_touch": min(timestamps),
            "last_touch": max(timestamps),
        })
    
    return levels


@router.get("/support-resistance", response_model=List[SupportResistanceLevel])
def get_support_resistance(
    symbol: str = Query(..., description="Trading symbol (e.g., EUR_USD)"),
    timeframe: str = Query("1h", description="Timeframe for analysis"),
    sensitivity: int = Query(5, ge=1, le=20, description="Pivot detection sensitivity (bars each side)"),
    lookback: int = Query(100, ge=50, le=500, description="Number of candles to analyze"),
    tolerance_pct: float = Query(0.002, ge=0.0005, le=0.01, description="Clustering tolerance as decimal"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Auto-detect support and resistance levels using pivot algorithm.
    
    Uses a two-step process:
    1. Detect pivot highs/lows using the specified sensitivity
    2. Cluster nearby pivots into support/resistance levels
    
    Returns levels sorted by strength (number of touches).
    """
    # Get OHLC data
    ohlc_data = chart_data_client.get_ohlc_data(
        conn.engine, symbol, timeframe, lookback
    )
    
    if not ohlc_data or len(ohlc_data) < sensitivity * 2 + 1:
        return []
    
    # Extract data
    highs = [c["high"] for c in ohlc_data]
    lows = [c["low"] for c in ohlc_data]
    closes = [c["close"] for c in ohlc_data]
    timestamps = [c["timestamp"] for c in ohlc_data]
    current_price = closes[-1]
    
    # Detect pivot points
    pivot_highs, pivot_lows = _detect_pivot_points(
        highs, lows, timestamps, sensitivity
    )
    
    # Cluster into levels
    resistance_levels = _cluster_levels(pivot_highs, tolerance_pct)
    support_levels = _cluster_levels(pivot_lows, tolerance_pct)
    
    # Build response
    levels = []
    
    for level_data in resistance_levels:
        # Calculate strength based on touches and recency
        age_hours = (datetime.now() - level_data["last_touch"]).total_seconds() / 3600
        recency_factor = max(0.3, 1 - (age_hours / (lookback * 24)))
        strength = min(1.0, (level_data["touches"] / 5) * recency_factor)
        
        distance_pct = abs(current_price - level_data["price"]) / current_price * 100
        
        levels.append(SupportResistanceLevel(
            price=level_data["price"],
            type="resistance",
            strength=round(strength, 2),
            touches=level_data["touches"],
            firstTouch=level_data["first_touch"],
            lastTouch=level_data["last_touch"],
            isActive=level_data["price"] >= current_price * 0.99,
            distancePct=round(distance_pct, 3)
        ))
    
    for level_data in support_levels:
        # Calculate strength based on touches and recency
        age_hours = (datetime.now() - level_data["last_touch"]).total_seconds() / 3600
        recency_factor = max(0.3, 1 - (age_hours / (lookback * 24)))
        strength = min(1.0, (level_data["touches"] / 5) * recency_factor)
        
        distance_pct = abs(current_price - level_data["price"]) / current_price * 100
        
        levels.append(SupportResistanceLevel(
            price=level_data["price"],
            type="support",
            strength=round(strength, 2),
            touches=level_data["touches"],
            firstTouch=level_data["first_touch"],
            lastTouch=level_data["last_touch"],
            isActive=level_data["price"] <= current_price * 1.01,
            distancePct=round(distance_pct, 3)
        ))
    
    # Sort by strength (descending)
    levels.sort(key=lambda x: x.strength, reverse=True)
    
    return levels


def _calculate_correlation(
    prices1: List[float],
    prices2: List[float]
) -> float:
    """Calculate Pearson correlation between two price series."""
    if len(prices1) != len(prices2) or len(prices1) < 2:
        return 0.0
    
    n = len(prices1)
    sum1 = sum(prices1)
    sum2 = sum(prices2)
    sum1_sq = sum(x ** 2 for x in prices1)
    sum2_sq = sum(x ** 2 for x in prices2)
    psum = sum(x * y for x, y in zip(prices1, prices2))
    
    numerator = psum - (sum1 * sum2 / n)
    denominator = ((sum1_sq - sum1 ** 2 / n) * (sum2_sq - sum2 ** 2 / n)) ** 0.5
    
    if denominator == 0:
        return 0.0
    
    return numerator / denominator


def _calculate_volatility(
    closes: List[float],
    window: int = 20
) -> float:
    """Calculate annualized volatility from price series."""
    if len(closes) < window + 1:
        return 0.0
    
    # Calculate returns
    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            returns.append((closes[i] - closes[i - 1]) / closes[i - 1])
    
    if len(returns) < window:
        return 0.0
    
    # Calculate standard deviation of recent returns
    recent_returns = returns[-window:]
    mean_return = sum(recent_returns) / len(recent_returns)
    variance = sum((r - mean_return) ** 2 for r in recent_returns) / len(recent_returns)
    std_dev = variance ** 0.5
    
    # Annualize (assuming daily data, multiply by sqrt(252))
    annualized = std_dev * (252 ** 0.5)
    
    return annualized * 100  # As percentage


def _calculate_trend_strength(
    closes: List[float],
    highs: List[float],
    lows: List[float]
) -> Dict[str, float]:
    """Calculate trend strength metrics."""
    if len(closes) < 20:
        return {"adx": 0.0, "direction": 0.0, "strength": 0.0}
    
    # Simple trend strength based on linear regression slope
    n = min(20, len(closes))
    recent_closes = closes[-n:]
    
    x_mean = (n - 1) / 2
    y_mean = sum(recent_closes) / n
    
    numerator = sum((i - x_mean) * (price - y_mean) for i, price in enumerate(recent_closes))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    
    slope = numerator / denominator if denominator != 0 else 0
    
    # Normalize slope as percentage of average price
    avg_price = y_mean
    normalized_slope = (slope / avg_price) * 100 if avg_price > 0 else 0
    
    # Calculate directional movement
    up_moves = sum(1 for i in range(1, n) if recent_closes[i] > recent_closes[i - 1])
    down_moves = sum(1 for i in range(1, n) if recent_closes[i] < recent_closes[i - 1])
    
    total_moves = up_moves + down_moves
    if total_moves > 0:
        direction = (up_moves - down_moves) / total_moves  # -1 to 1
    else:
        direction = 0
    
    # Strength is absolute value of direction
    strength = abs(direction)
    
    return {
        "adx": round(strength * 100, 2),  # Approximate ADX
        "direction": round(direction, 3),
        "strength": round(strength, 3),
        "slope": round(normalized_slope, 4)
    }


@router.get("/analysis-metrics", response_model=AnalysisMetricsResponse)
def get_analysis_metrics(
    symbol: str = Query(..., description="Trading symbol (e.g., EUR_USD)"),
    metric: Literal["correlation", "volatility", "strength", "all"] = Query("all", description="Metric type to return"),
    period: str = Query("1M", description="Analysis period (1W, 1M, 3M, 6M, 1Y)"),
    compare_symbols: Optional[str] = Query(None, description="Comma-separated symbols for correlation comparison"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Get analysis metrics: correlation, volatility, trend strength.
    
    Returns comprehensive analysis metrics for the specified symbol:
    - **Correlation**: Price correlation with other symbols
    - **Volatility**: Annualized volatility percentage
    - **Strength**: Trend strength and directional bias
    """
    # Map period to lookback
    period_days = {"1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 365}
    lookback = period_days.get(period, 30)
    
    # Get OHLC data
    ohlc_data = chart_data_client.get_ohlc_data(
        conn.engine, symbol, "1d", min(lookback, 500)
    )
    
    if not ohlc_data or len(ohlc_data) < 10:
        return AnalysisMetricsResponse(
            symbol=symbol,
            period=period,
            timestamp=datetime.now(),
            metrics=[]
        )
    
    closes = [c["close"] for c in ohlc_data]
    highs = [c["high"] for c in ohlc_data]
    lows = [c["low"] for c in ohlc_data]
    timestamps = [c["timestamp"] for c in ohlc_data]
    
    metrics = []
    
    # Volatility metric
    if metric in ("volatility", "all"):
        vol = _calculate_volatility(closes)
        vol_signal = "neutral"
        if vol > 30:
            vol_signal = "bearish"  # High volatility often precedes drops
        elif vol < 10:
            vol_signal = "bullish"  # Low volatility can indicate accumulation
        
        metrics.append(AnalysisMetric(
            name="volatility",
            value=round(vol, 2),
            unit="%",
            description="Annualized price volatility",
            timestamp=timestamps[-1] if timestamps else None,
            threshold=20.0,
            signal=vol_signal
        ))
    
    # Trend strength metric
    if metric in ("strength", "all"):
        trend_data = _calculate_trend_strength(closes, highs, lows)
        
        direction_signal = "neutral"
        if trend_data["direction"] > 0.3:
            direction_signal = "bullish"
        elif trend_data["direction"] < -0.3:
            direction_signal = "bearish"
        
        metrics.append(AnalysisMetric(
            name="trend_strength",
            value=round(trend_data["adx"], 2),
            unit="index",
            description="Trend strength (0-100, >25 indicates trend)",
            timestamp=timestamps[-1] if timestamps else None,
            threshold=25.0,
            signal=direction_signal
        ))
        
        metrics.append(AnalysisMetric(
            name="trend_slope",
            value=round(trend_data["slope"], 4),
            unit="%/day",
            description="Normalized price slope",
            timestamp=timestamps[-1] if timestamps else None
        ))
    
    # Correlation metrics
    if metric in ("correlation", "all") and compare_symbols:
        compare_list = [s.strip() for s in compare_symbols.split(",") if s.strip()]
        
        for compare_symbol in compare_list[:5]:  # Limit to 5 comparisons
            compare_data = chart_data_client.get_ohlc_data(
                conn.engine, compare_symbol, "1d", len(ohlc_data)
            )
            
            if compare_data and len(compare_data) == len(ohlc_data):
                compare_closes = [c["close"] for c in compare_data]
                corr = _calculate_correlation(closes, compare_closes)
                
                corr_signal = "neutral"
                if corr > 0.7:
                    corr_signal = "bullish"
                elif corr < -0.7:
                    corr_signal = "bearish"
                
                metrics.append(AnalysisMetric(
                    name=f"correlation_{compare_symbol}",
                    value=round(corr, 3),
                    unit="coefficient",
                    description=f"Price correlation with {compare_symbol}",
                    timestamp=timestamps[-1] if timestamps else None,
                    signal=corr_signal
                ))
    
    # Price momentum
    if metric == "all":
        if len(closes) >= 10:
            momentum_10 = ((closes[-1] - closes[-10]) / closes[-10]) * 100
            mom_signal = "bullish" if momentum_10 > 0 else "bearish" if momentum_10 < 0 else "neutral"
            
            metrics.append(AnalysisMetric(
                name="momentum_10d",
                value=round(momentum_10, 2),
                unit="%",
                description="10-day price momentum",
                timestamp=timestamps[-1] if timestamps else None,
                signal=mom_signal
            ))
    
    return AnalysisMetricsResponse(
        symbol=symbol,
        period=period,
        timestamp=datetime.now(),
        metrics=metrics
    )


@router.get("/correlation")
def get_correlation(
    symbol: str = Query(..., description="Base trading symbol"),
    period: str = Query("1M", description="Analysis period (1W, 1M, 3M)"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Return base-symbol correlations against other available symbols."""
    period_days = {"1W": 7, "1M": 30, "3M": 90}
    lookback = period_days.get(period, 30)

    symbols = chart_data_client.get_available_symbols(conn.engine)
    all_symbols = [s.get("symbol") for s in symbols if s.get("symbol") and s.get("symbol") != symbol]

    base = chart_data_client.get_ohlc_data(conn.engine, symbol, "1d", limit=min(lookback, 365))
    if not base:
        return {"baseAsset": symbol, "correlations": [], "period": period}

    base_closes = [c["close"] for c in base]
    correlations: List[Dict[str, Any]] = []

    for other in all_symbols[:12]:
        other_data = chart_data_client.get_ohlc_data(conn.engine, other, "1d", limit=min(lookback, 365))
        if not other_data:
            continue
        other_closes = [c["close"] for c in other_data]
        n = min(len(base_closes), len(other_closes))
        if n < 5:
            continue
        corr = _calculate_correlation(base_closes[-n:], other_closes[-n:])
        correlations.append(
            {
                "symbol": other,
                "correlation": round(corr, 3),
                "slope": "converging",
            }
        )

    correlations.sort(key=lambda x: abs(x["correlation"]), reverse=True)
    return {"baseAsset": symbol, "correlations": correlations, "period": period}


@router.get("/correlation-matrix")
def get_correlation_matrix(
    symbols: str = Query(..., description="Comma-separated symbols"),
    period: str = Query("1M", description="Analysis period (1W, 1M, 3M)"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Return a simple Pearson correlation matrix for requested symbols."""
    period_days = {"1W": 7, "1M": 30, "3M": 90}
    lookback = period_days.get(period, 30)
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()][:12]

    series: Dict[str, List[float]] = {}
    for sym in symbol_list:
        data = chart_data_client.get_ohlc_data(conn.engine, sym, "1d", limit=min(lookback, 365))
        series[sym] = [c["close"] for c in data] if data else []

    matrix: List[List[float]] = []
    for s1 in symbol_list:
        row: List[float] = []
        for s2 in symbol_list:
            if s1 == s2:
                row.append(1.0)
                continue
            n = min(len(series.get(s1, [])), len(series.get(s2, [])))
            if n < 5:
                row.append(0.0)
            else:
                row.append(round(_calculate_correlation(series[s1][-n:], series[s2][-n:]), 3))
        matrix.append(row)

    return {"symbols": symbol_list, "matrix": matrix, "period": period}


@router.get("/session-volume")
def get_session_volume(
    symbol: str = Query(..., description="Trading symbol"),
    session: Literal["asian", "london", "ny", "all"] = Query("all"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Return coarse session volume split from recent intraday candles."""
    data = chart_data_client.get_ohlc_data(conn.engine, symbol, "1h", limit=240)
    if not data:
        return {
            "session": session,
            "totalVolume": 0,
            "buyVolume": 0,
            "sellVolume": 0,
            "delta": 0,
        }

    def in_session(dt: datetime) -> bool:
        hour = dt.hour
        if session == "all":
            return True
        if session == "asian":
            return 0 <= hour < 8
        if session == "london":
            return 8 <= hour < 16
        return 13 <= hour < 21

    filtered = [c for c in data if isinstance(c.get("timestamp"), datetime) and in_session(c["timestamp"])]
    total_volume = int(sum(int(c.get("volume") or 0) for c in filtered))
    buy_volume = int(sum(int(c.get("volume") or 0) for c in filtered if (c.get("close") or 0) >= (c.get("open") or 0)))
    sell_volume = max(total_volume - buy_volume, 0)

    return {
        "session": session,
        "totalVolume": total_volume,
        "buyVolume": buy_volume,
        "sellVolume": sell_volume,
        "delta": buy_volume - sell_volume,
    }


@router.get("/strategy-overlay", response_model=StrategyOverlayData)
def get_strategy_overlay(
    symbol: str = Query(..., description="Trading symbol (e.g., EUR_USD)"),
    strategy: str = Query(..., description="Strategy name/ID"),
    timeframe: str = Query("1h", description="Timeframe for analysis"),
    lookback_days: int = Query(30, ge=1, le=365, description="Days to look back"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Get strategy entries and trade results for chart overlay.
    
    Returns entry points and completed trades for visualizing
    strategy performance directly on the price chart.
    """
    from layer5.services import layer4_client, layer2_client
    
    # Get trades for this symbol and strategy
    trades = layer4_client.get_live_trades(
        conn.engine,
        limit=100,
        asset=symbol,
        strategy=strategy
    )
    
    # Get pending signals
    signals = layer2_client.get_pending_signals(
        conn.engine,
        limit=20
    )
    
    # Filter signals for this symbol and strategy
    strategy_signals = [
        s for s in signals
        if s.get("asset") == symbol and s.get("strategy") == strategy
    ]
    
    entries = []
    completed_trades = []
    total_pnl = 0.0
    wins = 0
    
    # Process completed trades
    for trade in trades:
        entry_time = trade.get("timestamp")
        entry_price = trade.get("entry_price") or trade.get("Entry_Price")
        exit_price = trade.get("exit_price") or trade.get("Exit_Price")
        side = "long" if trade.get("signal_value") == 1 or trade.get("Signal_Value") == 1 else "short"
        pnl = trade.get("pnl") or trade.get("PnL") or 0
        confidence = trade.get("confidence") or trade.get("Confidence_Score") or 0.5
        regime = trade.get("regime") or trade.get("Regime_Label")
        
        if entry_time and entry_price:
            entries.append(StrategyEntryPoint(
                timestamp=entry_time if isinstance(entry_time, datetime) else datetime.fromisoformat(str(entry_time)),
                price=round(float(entry_price), 5),
                side=side,
                strategy=strategy,
                confidence=round(float(confidence), 3),
                regime=regime
            ))
        
        # Process completed trades
        if exit_price and entry_time:
            exit_time = trade.get("exit_time") or trade.get("closed_at") or datetime.now()
            outcome = trade.get("outcome") or trade.get("Outcome")
            
            if outcome:
                if outcome == "win":
                    wins += 1
                total_pnl += float(pnl) if pnl else 0
                
                completed_trades.append(StrategyTradeResult(
                    entryTime=entry_time if isinstance(entry_time, datetime) else datetime.fromisoformat(str(entry_time)),
                    exitTime=exit_time if isinstance(exit_time, datetime) else datetime.fromisoformat(str(exit_time)),
                    entryPrice=round(float(entry_price), 5),
                    exitPrice=round(float(exit_price), 5),
                    side=side,
                    pnl=round(float(pnl), 2) if pnl else 0.0,
                    pnlPct=round((float(exit_price) - float(entry_price)) / float(entry_price) * 100, 3) if side == "long" else round((float(entry_price) - float(exit_price)) / float(entry_price) * 100, 3),
                    strategy=strategy,
                    outcome=outcome
                ))
    
    # Add pending signals as future entries
    for signal in strategy_signals:
        sig_time = signal.get("timestamp")
        sig_price = signal.get("price") or signal.get("entry_price")
        sig_side = "long" if signal.get("signal_value") == 1 else "short"
        sig_confidence = signal.get("confidence") or 0.5
        
        if sig_time:
            entries.append(StrategyEntryPoint(
                timestamp=sig_time if isinstance(sig_time, datetime) else datetime.fromisoformat(str(sig_time)),
                price=round(float(sig_price), 5) if sig_price else 0.0,
                side=sig_side,
                strategy=strategy,
                confidence=round(float(sig_confidence), 3),
                regime=signal.get("regime")
            ))
    
    total_trades = len(completed_trades)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
    avg_pnl = (total_pnl / total_trades) if total_trades > 0 else 0.0
    
    return StrategyOverlayData(
        symbol=symbol,
        strategy=strategy,
        timeframe=timeframe,
        entries=entries,
        trades=completed_trades,
        winRate=round(win_rate, 2),
        totalTrades=total_trades,
        avgPnL=round(avg_pnl, 2)
    )


@router.get("/volume-profile-enhanced", response_model=EnhancedVolumeProfile)
def get_volume_profile_enhanced(
    symbol: str = Query(..., description="Trading symbol"),
    rows: int = Query(24, ge=10, le=100, description="Number of price levels"),
    lookback_days: int = Query(7, ge=1, le=30, description="Days to analyze"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Get enhanced volume profile with VPOC (Volume Point of Control).
    
    Returns detailed volume profile including:
    - Volume distribution at price levels
    - VPOC (price level with highest volume)
    - Value Area (70% of volume)
    """
    # Get basic volume profile
    profile_data = chart_data_client.get_volume_profile(
        conn.engine, symbol, rows, lookback_days
    )
    
    if not profile_data:
        raise HTTPException(status_code=404, detail=f"No volume data available for {symbol}")
    
    # Convert to VolumeProfilePoint objects with VPOC flag
    points = []
    max_volume = 0
    vpoc_price = 0
    vpoc_volume = 0
    
    for point in profile_data:
        volume = point.get("volume", 0)
        price = point.get("price", 0)
        
        if volume > max_volume:
            max_volume = volume
            vpoc_price = price
            vpoc_volume = volume
        
        points.append(VolumeProfilePoint(
            price=round(float(price), 5),
            volume=int(volume),
            priceRange=point.get("priceRange", {"min": price, "max": price}),
            isVPOC=False,  # Will set true for VPOC later
            bidVolume=int(volume * 0.5),  # Estimate
            askVolume=int(volume * 0.5)    # Estimate
        ))
    
    # Mark VPOC
    for point in points:
        if point.price == vpoc_price:
            point.isVPOC = True
    
    # Calculate Value Area (70% of volume around VPOC)
    total_volume = sum(p.volume for p in points)
    sorted_points = sorted(points, key=lambda x: abs(x.price - vpoc_price))
    
    value_area_volume = 0
    value_area_points = []
    target_volume = total_volume * 0.70
    
    for point in sorted_points:
        if value_area_volume < target_volume:
            value_area_points.append(point)
            value_area_volume += point.volume
        else:
            break
    
    value_area_high = max(p.price for p in value_area_points) if value_area_points else vpoc_price
    value_area_low = min(p.price for p in value_area_points) if value_area_points else vpoc_price
    
    return EnhancedVolumeProfile(
        symbol=symbol,
        timeframe=f"{lookback_days}D",
        lookbackDays=lookback_days,
        rows=rows,
        points=points,
        vpoc=VolumeProfileVPOC(
            price=round(vpoc_price, 5),
            volume=vpoc_volume,
            timestamp=datetime.now(),
            profileType="session"
        ),
        valueAreaHigh=round(value_area_high, 5),
        valueAreaLow=round(value_area_low, 5),
        valueAreaVolume=int(value_area_volume),
        totalVolume=int(total_volume),
        timestamp=datetime.now()
    )


# =============================================================================
# Trade Markers Endpoint
# =============================================================================

@router.get("/trade-markers")
def get_trade_markers(
    symbol: str = Query(..., description="Trading symbol (e.g., EUR_USD)"),
    lookback_days: int = Query(30, ge=1, le=365, description="Days to look back"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Get trade markers for chart overlay visualization.
    
    Returns entry points, stop losses, take profits, and trade outcomes
    for visualizing trades directly on the price chart.
    """
    from layer5.services import layer4_client, layer2_client
    
    markers = []
    
    # Get trades for this symbol
    try:
        trades = layer4_client.get_live_trades(
            conn.engine,
            limit=100,
            asset=symbol
        )
        
        for trade in trades:
            entry_time = trade.get("timestamp")
            entry_price = trade.get("entry_price") or trade.get("Entry_Price")
            exit_price = trade.get("exit_price") or trade.get("Exit_Price")
            stop_loss = trade.get("stop_loss") or trade.get("Stop_Loss")
            take_profit = trade.get("take_profit") or trade.get("Take_Profit")
            side = "long" if trade.get("signal_value") == 1 or trade.get("Signal_Value") == 1 else "short"
            outcome = trade.get("outcome") or trade.get("Outcome")
            
            # Add entry marker
            if entry_time and entry_price:
                markers.append({
                    "id": f"entry_{trade.get('id', 'unknown')}",
                    "type": "entry",
                    "price": round(float(entry_price), 5),
                    "timestamp": entry_time.isoformat() if isinstance(entry_time, datetime) else str(entry_time),
                    "side": side
                })
            
            # Add SL marker
            if stop_loss and entry_time:
                markers.append({
                    "id": f"sl_{trade.get('id', 'unknown')}",
                    "type": "sl",
                    "price": round(float(stop_loss), 5),
                    "timestamp": entry_time.isoformat() if isinstance(entry_time, datetime) else str(entry_time),
                    "side": side
                })
            
            # Add TP marker
            if take_profit and entry_time:
                markers.append({
                    "id": f"tp_{trade.get('id', 'unknown')}",
                    "type": "tp",
                    "price": round(float(take_profit), 5),
                    "timestamp": entry_time.isoformat() if isinstance(entry_time, datetime) else str(entry_time),
                    "side": side
                })
            
            # Add outcome marker
            if exit_price and outcome:
                exit_time = trade.get("exit_time") or trade.get("closed_at") or entry_time
                markers.append({
                    "id": f"outcome_{trade.get('id', 'unknown')}",
                    "type": "win" if outcome == "win" else "loss",
                    "price": round(float(exit_price), 5),
                    "timestamp": exit_time.isoformat() if isinstance(exit_time, datetime) else str(exit_time),
                    "side": side
                })
    except Exception as e:
        print(f"[Charts API] Error fetching trade markers: {e}")
    
    return {
        "symbol": symbol,
        "markers": markers,
        "count": len(markers)
    }
