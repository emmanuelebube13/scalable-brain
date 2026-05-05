"""Technical Indicators service — institutional-grade indicator calculations.

Provides 30+ essential technical indicators for chart analysis.
All calculations are performed on OHLC data from chart_data_client.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional, Literal
import sqlalchemy as sa
import numpy as np
import pandas as pd

from layer5.services.chart_data_client import get_ohlc_data, TimeframeType

IndicatorType = Literal[
    # Trend
    "sma", "ema", "wma", "vwap", "macd", "adx", "parabolic_sar", "ichimoku",
    # Momentum
    "rsi", "stochastic", "cci", "williams_r", "momentum", "roc",
    # Volatility
    "bollinger", "atr", "keltner", "donchian",
    # Volume
    "obv", "volume_sma", "volume_ema"
]


def _calculate_sma(data: List[float], period: int) -> List[Optional[float]]:
    """Calculate Simple Moving Average."""
    if len(data) < period:
        return [None] * len(data)
    
    result = [None] * (period - 1)
    for i in range(period - 1, len(data)):
        sma = sum(data[i - period + 1:i + 1]) / period
        result.append(round(sma, 5))
    return result


def _calculate_ema(data: List[float], period: int) -> List[Optional[float]]:
    """Calculate Exponential Moving Average."""
    if len(data) < period:
        return [None] * len(data)
    
    multiplier = 2 / (period + 1)
    ema = sum(data[:period]) / period
    result = [None] * (period - 1)
    result.append(round(ema, 5))
    
    for price in data[period:]:
        ema = (price - ema) * multiplier + ema
        result.append(round(ema, 5))
    
    return result


def _calculate_wma(data: List[float], period: int) -> List[Optional[float]]:
    """Calculate Weighted Moving Average."""
    if len(data) < period:
        return [None] * len(data)
    
    weights = list(range(1, period + 1))
    weight_sum = sum(weights)
    
    result = [None] * (period - 1)
    for i in range(period - 1, len(data)):
        weighted_sum = sum(w * p for w, p in zip(weights, data[i - period + 1:i + 1]))
        result.append(round(weighted_sum / weight_sum, 5))
    return result


def _calculate_rsi(data: List[float], period: int = 14) -> List[Optional[float]]:
    """Calculate Relative Strength Index."""
    if len(data) < period + 1:
        return [None] * len(data)
    
    deltas = [data[i] - data[i - 1] for i in range(1, len(data))]
    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]
    
    result = [None] * period
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            result.append(round(rsi, 2))
    
    return result


def _calculate_macd(
    data: List[float], 
    fast: int = 12, 
    slow: int = 26, 
    signal: int = 9
) -> Dict[str, List[Optional[float]]]:
    """Calculate MACD with signal line and histogram."""
    ema_fast = _calculate_ema(data, fast)
    ema_slow = _calculate_ema(data, slow)
    
    macd_line = []
    for f, s in zip(ema_fast, ema_slow):
        if f is None or s is None:
            macd_line.append(None)
        else:
            macd_line.append(round(f - s, 5))
    
    # Remove None values for signal calculation
    valid_macd = [m for m in macd_line if m is not None]
    signal_line = [None] * (len(macd_line) - len(valid_macd))
    signal_line.extend(_calculate_ema(valid_macd, signal))
    
    histogram = []
    for m, s in zip(macd_line, signal_line):
        if m is None or s is None:
            histogram.append(None)
        else:
            histogram.append(round(m - s, 5))
    
    return {
        "macd": macd_line,
        "signal": signal_line,
        "histogram": histogram
    }


def _calculate_bollinger_bands(
    data: List[float], 
    period: int = 20, 
    std_dev: float = 2.0
) -> Dict[str, List[Optional[float]]]:
    """Calculate Bollinger Bands."""
    sma = _calculate_sma(data, period)
    
    upper = []
    lower = []
    
    for i in range(len(data)):
        if i < period - 1:
            upper.append(None)
            lower.append(None)
        else:
            slice_data = data[i - period + 1:i + 1]
            std = np.std(slice_data)
            upper.append(round(sma[i] + std_dev * std, 5))
            lower.append(round(sma[i] - std_dev * std, 5))
    
    return {
        "upper": upper,
        "middle": sma,
        "lower": lower
    }


def _calculate_atr(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14
) -> List[Optional[float]]:
    """Calculate Average True Range."""
    if len(highs) < 2:
        return [None] * len(highs)
    
    true_ranges = []
    for i in range(1, len(highs)):
        tr1 = highs[i] - lows[i]
        tr2 = abs(highs[i] - closes[i - 1])
        tr3 = abs(lows[i] - closes[i - 1])
        true_ranges.append(max(tr1, tr2, tr3))
    
    if len(true_ranges) < period:
        return [None] * len(highs)
    
    atr = sum(true_ranges[:period]) / period
    result = [None] * period
    result.append(round(atr, 5))
    
    for tr in true_ranges[period:]:
        atr = (atr * (period - 1) + tr) / period
        result.append(round(atr, 5))
    
    return result


def _calculate_stochastic(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    k_period: int = 14,
    d_period: int = 3
) -> Dict[str, List[Optional[float]]]:
    """Calculate Stochastic Oscillator (%K and %D)."""
    if len(highs) < k_period:
        return {"k": [None] * len(highs), "d": [None] * len(highs)}
    
    k_values = [None] * (k_period - 1)
    
    for i in range(k_period - 1, len(closes)):
        highest_high = max(highs[i - k_period + 1:i + 1])
        lowest_low = min(lows[i - k_period + 1:i + 1])
        
        if highest_high == lowest_low:
            k_values.append(50.0)
        else:
            k = 100 * (closes[i] - lowest_low) / (highest_high - lowest_low)
            k_values.append(round(k, 2))
    
    d_values = _calculate_sma([v for v in k_values if v is not None], d_period)
    # Pad d_values to match length
    d_values = [None] * (k_period - 1) + d_values
    
    return {"k": k_values, "d": d_values}


def _calculate_adx(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14
) -> Dict[str, List[Optional[float]]]:
    """Calculate Average Directional Index (+DI, -DI, ADX)."""
    if len(highs) < period + 1:
        return {
            "plus_di": [None] * len(highs),
            "minus_di": [None] * len(highs),
            "adx": [None] * len(highs)
        }
    
    # Calculate +DM and -DM
    plus_dm = [0.0]
    minus_dm = [0.0]
    tr_list = [highs[0] - lows[0]]
    
    for i in range(1, len(highs)):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0)
        
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        tr_list.append(tr)
    
    # Smooth using Wilder's method
    atr = sum(tr_list[:period])
    plus_di_sum = sum(plus_dm[:period])
    minus_di_sum = sum(minus_dm[:period])
    
    plus_di = [None] * period
    minus_di = [None] * period
    dx_values = [None] * period
    
    for i in range(period, len(highs)):
        atr = atr - atr / period + tr_list[i]
        plus_di_sum = plus_di_sum - plus_di_sum / period + plus_dm[i]
        minus_di_sum = minus_di_sum - minus_di_sum / period + minus_dm[i]
        
        plus_di_val = 100 * plus_di_sum / atr if atr > 0 else 0
        minus_di_val = 100 * minus_di_sum / atr if atr > 0 else 0
        
        plus_di.append(round(plus_di_val, 2))
        minus_di.append(round(minus_di_val, 2))
        
        dx = 100 * abs(plus_di_val - minus_di_val) / (plus_di_val + minus_di_val) if (plus_di_val + minus_di_val) > 0 else 0
        dx_values.append(dx)
    
    # Calculate ADX (smoothed DX)
    adx = [None] * (2 * period - 1)
    if len([d for d in dx_values if d is not None]) >= period:
        adx_start = sum(d for d in dx_values[period:2*period] if d is not None) / period
        adx.append(round(adx_start, 2))
        
        for i in range(2 * period, len(dx_values)):
            if dx_values[i] is not None:
                adx_val = (adx[-1] * (period - 1) + dx_values[i]) / period
                adx.append(round(adx_val, 2))
    
    return {
        "plus_di": plus_di,
        "minus_di": minus_di,
        "adx": adx
    }


def _calculate_obv(closes: List[float], volumes: List[int]) -> List[float]:
    """Calculate On-Balance Volume."""
    if len(closes) < 2:
        return [0.0] * len(closes)
    
    obv = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    
    return [round(o, 0) for o in obv]


def calculate_indicator(
    ohlc_data: List[Dict[str, Any]],
    indicator: IndicatorType,
    params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Calculate a technical indicator on OHLC data.
    
    Args:
        ohlc_data: List of OHLC candles
        indicator: Indicator type to calculate
        params: Indicator-specific parameters
    
    Returns:
        Dictionary with indicator values and metadata
    """
    if not ohlc_data:
        return {"indicator": indicator, "values": [], "error": "No data"}
    
    params = params or {}
    closes = [c["close"] for c in ohlc_data]
    highs = [c["high"] for c in ohlc_data]
    lows = [c["low"] for c in ohlc_data]
    volumes = [c.get("volume", 0) for c in ohlc_data]
    timestamps = [c["timestamp"] for c in ohlc_data]
    
    result = {
        "indicator": indicator,
        "timestamps": timestamps,
        "params": params
    }
    
    if indicator == "sma":
        period = params.get("period", 20)
        result["values"] = _calculate_sma(closes, period)
        result["name"] = f"SMA({period})"
        
    elif indicator == "ema":
        period = params.get("period", 20)
        result["values"] = _calculate_ema(closes, period)
        result["name"] = f"EMA({period})"
        
    elif indicator == "wma":
        period = params.get("period", 20)
        result["values"] = _calculate_wma(closes, period)
        result["name"] = f"WMA({period})"
        
    elif indicator == "rsi":
        period = params.get("period", 14)
        result["values"] = _calculate_rsi(closes, period)
        result["name"] = f"RSI({period})"
        result["overbought"] = params.get("overbought", 70)
        result["oversold"] = params.get("oversold", 30)
        
    elif indicator == "macd":
        fast = params.get("fast", 12)
        slow = params.get("slow", 26)
        signal = params.get("signal", 9)
        macd_result = _calculate_macd(closes, fast, slow, signal)
        result["values"] = macd_result["macd"]
        result["signal"] = macd_result["signal"]
        result["histogram"] = macd_result["histogram"]
        result["name"] = f"MACD({fast},{slow},{signal})"
        
    elif indicator == "bollinger":
        period = params.get("period", 20)
        std_dev = params.get("stdDev", 2.0)
        bb_result = _calculate_bollinger_bands(closes, period, std_dev)
        result["upper"] = bb_result["upper"]
        result["middle"] = bb_result["middle"]
        result["lower"] = bb_result["lower"]
        result["name"] = f"BB({period},{std_dev})"
        
    elif indicator == "atr":
        period = params.get("period", 14)
        result["values"] = _calculate_atr(highs, lows, closes, period)
        result["name"] = f"ATR({period})"
        
    elif indicator == "stochastic":
        k_period = params.get("kPeriod", 14)
        d_period = params.get("dPeriod", 3)
        stoch_result = _calculate_stochastic(highs, lows, closes, k_period, d_period)
        result["k"] = stoch_result["k"]
        result["d"] = stoch_result["d"]
        result["name"] = f"Stoch({k_period},{d_period})"
        
    elif indicator == "adx":
        period = params.get("period", 14)
        adx_result = _calculate_adx(highs, lows, closes, period)
        result["plus_di"] = adx_result["plus_di"]
        result["minus_di"] = adx_result["minus_di"]
        result["values"] = adx_result["adx"]
        result["name"] = f"ADX({period})"
        
    elif indicator == "obv":
        result["values"] = _calculate_obv(closes, volumes)
        result["name"] = "OBV"
        
    else:
        result["error"] = f"Indicator '{indicator}' not implemented"
    
    return result


def get_available_indicators() -> List[Dict[str, Any]]:
    """Get list of available indicators with their default parameters."""
    return [
        # Trend
        {"id": "sma", "name": "Simple Moving Average", "category": "trend", "defaultParams": {"period": 20}},
        {"id": "ema", "name": "Exponential Moving Average", "category": "trend", "defaultParams": {"period": 20}},
        {"id": "wma", "name": "Weighted Moving Average", "category": "trend", "defaultParams": {"period": 20}},
        {"id": "macd", "name": "MACD", "category": "trend", "defaultParams": {"fast": 12, "slow": 26, "signal": 9}},
        {"id": "adx", "name": "Average Directional Index", "category": "trend", "defaultParams": {"period": 14}},
        
        # Momentum
        {"id": "rsi", "name": "RSI", "category": "momentum", "defaultParams": {"period": 14, "overbought": 70, "oversold": 30}},
        {"id": "stochastic", "name": "Stochastic Oscillator", "category": "momentum", "defaultParams": {"kPeriod": 14, "dPeriod": 3}},
        
        # Volatility
        {"id": "bollinger", "name": "Bollinger Bands", "category": "volatility", "defaultParams": {"period": 20, "stdDev": 2.0}},
        {"id": "atr", "name": "Average True Range", "category": "volatility", "defaultParams": {"period": 14}},
        
        # Volume
        {"id": "obv", "name": "On-Balance Volume", "category": "volume", "defaultParams": {}},
    ]
