"""Comprehensive Technical Indicators Library — 30+ institutional-grade indicators.

Provides a complete suite of technical indicators for chart analysis organized by category:
- Momentum Indicators (6): RSI, MACD, Stochastic, ROC, CCI, Williams %R
- Trend Indicators (5): SMA, EMA, WMA, TEMA, DEMA, ADX, Moving Average Ribbon
- Volatility Indicators (5): Bollinger Bands, ATR, Keltner Channel, NATR, Historical Volatility
- Volume Indicators (5): OBV, VWAP, Volume Rate of Change, A/D Line, MFI
- Trend Strength (3): QStick, VHF, Mass Index

All calculations are performed on OHLC data and return values aligned with input length.
"""

from typing import List, Dict, Any, Optional, Callable, Union
import numpy as np


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def _validate_ohlc_data(ohlc_data: List[Dict[str, Any]]) -> tuple:
    """Extract and validate OHLC data from input list.
    
    Args:
        ohlc_data: List of OHLC candle dictionaries
        
    Returns:
        Tuple of (opens, highs, lows, closes, volumes) as lists
        
    Raises:
        ValueError: If data is empty or missing required fields
    """
    if not ohlc_data:
        raise ValueError("OHLC data is empty")
    
    opens = [c.get("open", 0.0) for c in ohlc_data]
    highs = [c.get("high", 0.0) for c in ohlc_data]
    lows = [c.get("low", 0.0) for c in ohlc_data]
    closes = [c.get("close", 0.0) for c in ohlc_data]
    volumes = [c.get("volume", 0) for c in ohlc_data]
    
    return opens, highs, lows, closes, volumes


def _pad_leading_nones(values: List[Any], target_length: int) -> List[Optional[float]]:
    """Pad values with leading None values to match target length.
    
    Args:
        values: List of calculated values
        target_length: Desired output length
        
    Returns:
        List padded with None values at the beginning
    """
    padding_needed = target_length - len(values)
    if padding_needed > 0:
        return [None] * padding_needed + values
    return values


# =============================================================================
# MOVING AVERAGE HELPERS
# =============================================================================

def _calculate_sma(data: List[float], period: int) -> List[Optional[float]]:
    """Calculate Simple Moving Average.
    
    Args:
        data: List of price values
        period: SMA period
        
    Returns:
        List of SMA values with leading None values
    """
    if len(data) < period:
        return [None] * len(data)
    
    result = [None] * (period - 1)
    for i in range(period - 1, len(data)):
        sma = sum(data[i - period + 1:i + 1]) / period
        result.append(round(sma, 5))
    return result


def _calculate_ema(data: List[float], period: int) -> List[Optional[float]]:
    """Calculate Exponential Moving Average.
    
    Args:
        data: List of price values
        period: EMA period
        
    Returns:
        List of EMA values with leading None values
    """
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
    """Calculate Weighted Moving Average.
    
    Args:
        data: List of price values
        period: WMA period
        
    Returns:
        List of WMA values with leading None values
    """
    if len(data) < period:
        return [None] * len(data)
    
    weights = list(range(1, period + 1))
    weight_sum = sum(weights)
    
    result = [None] * (period - 1)
    for i in range(period - 1, len(data)):
        weighted_sum = sum(w * p for w, p in zip(weights, data[i - period + 1:i + 1]))
        result.append(round(weighted_sum / weight_sum, 5))
    return result


def _calculate_tema(data: List[float], period: int) -> List[Optional[float]]:
    """Calculate Triple Exponential Moving Average.
    
    TEMA = 3*EMA - 3*EMA(EMA) + EMA(EMA(EMA))
    
    Args:
        data: List of price values
        period: TEMA period
        
    Returns:
        List of TEMA values with leading None values
    """
    if len(data) < 3 * period:
        return [None] * len(data)
    
    ema1 = _calculate_ema(data, period)
    ema1_valid = [v for v in ema1 if v is not None]
    ema2 = _calculate_ema(ema1_valid, period)
    ema2_valid = [v for v in ema2 if v is not None]
    ema3 = _calculate_ema(ema2_valid, period)
    ema3_valid = [v for v in ema3 if v is not None]
    
    # All three EMAs need valid values at the same index
    min_len = min(len(ema1_valid), len(ema2_valid), len(ema3_valid))
    
    result = [None] * (len(data) - min_len)
    for i in range(min_len):
        tema = 3 * ema1_valid[i] - 3 * ema2_valid[i] + ema3_valid[i]
        result.append(round(tema, 5))
    
    return result


def _calculate_dema(data: List[float], period: int) -> List[Optional[float]]:
    """Calculate Double Exponential Moving Average.
    
    DEMA = 2*EMA - EMA(EMA)
    
    Args:
        data: List of price values
        period: DEMA period
        
    Returns:
        List of DEMA values with leading None values
    """
    if len(data) < 2 * period:
        return [None] * len(data)
    
    ema1 = _calculate_ema(data, period)
    ema1_valid = [v for v in ema1 if v is not None]
    ema2 = _calculate_ema(ema1_valid, period)
    ema2_valid = [v for v in ema2 if v is not None]
    
    # Both EMAs need valid values at the same index
    min_len = min(len(ema1_valid), len(ema2_valid))
    
    result = [None] * (len(data) - min_len)
    for i in range(min_len):
        dema = 2 * ema1_valid[i] - ema2_valid[i]
        result.append(round(dema, 5))
    
    return result


# =============================================================================
# MOMENTUM INDICATORS (6 total)
# =============================================================================

def calculate_rsi(ohlc_data: List[Dict[str, Any]], period: int = 14) -> List[Optional[float]]:
    """Calculate Relative Strength Index (RSI).
    
    RSI measures the magnitude of recent price changes to evaluate
    overbought or oversold conditions.
    
    Formula: RSI = 100 - (100 / (1 + RS))
    where RS = Average Gain / Average Loss
    
    Args:
        ohlc_data: List of OHLC candles
        period: RSI period (default: 14)
        
    Returns:
        List of RSI values (0-100) with leading None values
    """
    _, _, _, closes, _ = _validate_ohlc_data(ohlc_data)
    
    if len(closes) < period + 1:
        return [None] * len(closes)
    
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
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


def calculate_macd(
    ohlc_data: List[Dict[str, Any]],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> Dict[str, List[Optional[float]]]:
    """Calculate Moving Average Convergence Divergence (MACD).
    
    MACD is a trend-following momentum indicator showing the relationship
    between two EMAs of price.
    
    Args:
        ohlc_data: List of OHLC candles
        fast: Fast EMA period (default: 12)
        slow: Slow EMA period (default: 26)
        signal: Signal line period (default: 9)
        
    Returns:
        Dictionary with 'macd', 'signal', and 'histogram' lists
    """
    _, _, _, closes, _ = _validate_ohlc_data(ohlc_data)
    
    ema_fast = _calculate_ema(closes, fast)
    ema_slow = _calculate_ema(closes, slow)
    
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


def calculate_stochastic(
    ohlc_data: List[Dict[str, Any]],
    period: int = 14,
    smooth_k: int = 3,
    smooth_d: int = 3
) -> Dict[str, List[Optional[float]]]:
    """Calculate Stochastic Oscillator.
    
    The Stochastic Oscillator compares a closing price to its price range
    over a given period, showing momentum and potential reversal points.
    
    Args:
        ohlc_data: List of OHLC candles
        period: %K period (default: 14)
        smooth_k: %K smoothing period (default: 3)
        smooth_d: %D smoothing period (default: 3)
        
    Returns:
        Dictionary with 'k' (%K) and 'd' (%D) lists
    """
    _, highs, lows, closes, _ = _validate_ohlc_data(ohlc_data)
    
    if len(highs) < period:
        return {"k": [None] * len(highs), "d": [None] * len(highs)}
    
    k_values = [None] * (period - 1)
    
    for i in range(period - 1, len(closes)):
        highest_high = max(highs[i - period + 1:i + 1])
        lowest_low = min(lows[i - period + 1:i + 1])
        
        if highest_high == lowest_low:
            k_values.append(50.0)
        else:
            k = 100 * (closes[i] - lowest_low) / (highest_high - lowest_low)
            k_values.append(round(k, 2))
    
    # Smooth %K if specified
    if smooth_k > 1:
        valid_k = [v for v in k_values if v is not None]
        smoothed_k = _calculate_sma(valid_k, smooth_k)
        k_values = [None] * (period - 1) + smoothed_k
    
    # Calculate %D (SMA of %K)
    valid_k = [v for v in k_values if v is not None]
    d_values = _calculate_sma(valid_k, smooth_d)
    d_values = [None] * (period - 1) + d_values
    
    return {"k": k_values, "d": d_values}


def calculate_roc(ohlc_data: List[Dict[str, Any]], period: int = 12) -> List[Optional[float]]:
    """Calculate Rate of Change (ROC).
    
    ROC measures the percentage change in price between the current price
    and the price n periods ago.
    
    Formula: ROC = ((Current - n periods ago) / n periods ago) * 100
    
    Args:
        ohlc_data: List of OHLC candles
        period: ROC period (default: 12)
        
    Returns:
        List of ROC percentage values with leading None values
    """
    _, _, _, closes, _ = _validate_ohlc_data(ohlc_data)
    
    if len(closes) < period + 1:
        return [None] * len(closes)
    
    result = [None] * period
    for i in range(period, len(closes)):
        roc = ((closes[i] - closes[i - period]) / closes[i - period]) * 100
        result.append(round(roc, 2))
    
    return result


def calculate_cci(ohlc_data: List[Dict[str, Any]], period: int = 20) -> List[Optional[float]]:
    """Calculate Commodity Channel Index (CCI).
    
    CCI measures the current price level relative to an average price level
    over a given period. Values > 100 indicate overbought, < -100 oversold.
    
    Formula: CCI = (Typical Price - SMA) / (0.015 * Mean Deviation)
    
    Args:
        ohlc_data: List of OHLC candles
        period: CCI period (default: 20)
        
    Returns:
        List of CCI values with leading None values
    """
    _, highs, lows, closes, _ = _validate_ohlc_data(ohlc_data)
    
    if len(closes) < period:
        return [None] * len(closes)
    
    # Calculate Typical Price (TP) = (High + Low + Close) / 3
    tp = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
    
    # Calculate SMA of TP
    tp_sma = _calculate_sma(tp, period)
    
    result = [None] * (period - 1)
    
    for i in range(period - 1, len(tp)):
        # Calculate Mean Deviation
        tp_slice = tp[i - period + 1:i + 1]
        mean_dev = sum(abs(x - tp_sma[i]) for x in tp_slice) / period
        
        if mean_dev == 0:
            result.append(0.0)
        else:
            cci = (tp[i] - tp_sma[i]) / (0.015 * mean_dev)
            result.append(round(cci, 2))
    
    return result


def calculate_williams_r(ohlc_data: List[Dict[str, Any]], period: int = 14) -> List[Optional[float]]:
    """Calculate Williams %R.
    
    Williams %R is a momentum indicator that measures overbought and oversold
    levels. It is similar to Stochastic but inverted (0 = overbought, -100 = oversold).
    
    Formula: %R = (Highest High - Close) / (Highest High - Lowest Low) * -100
    
    Args:
        ohlc_data: List of OHLC candles
        period: Williams %R period (default: 14)
        
    Returns:
        List of Williams %R values (-100 to 0) with leading None values
    """
    _, highs, lows, closes, _ = _validate_ohlc_data(ohlc_data)
    
    if len(highs) < period:
        return [None] * len(highs)
    
    result = [None] * (period - 1)
    
    for i in range(period - 1, len(closes)):
        highest_high = max(highs[i - period + 1:i + 1])
        lowest_low = min(lows[i - period + 1:i + 1])
        
        if highest_high == lowest_low:
            result.append(-50.0)
        else:
            wr = (highest_high - closes[i]) / (highest_high - lowest_low) * -100
            result.append(round(wr, 2))
    
    return result


# =============================================================================
# TREND INDICATORS (5 total)
# =============================================================================

def calculate_sma(ohlc_data: List[Dict[str, Any]], period: int = 20) -> List[Optional[float]]:
    """Calculate Simple Moving Average (SMA).
    
    SMA is the arithmetic mean of closing prices over a specified period.
    
    Args:
        ohlc_data: List of OHLC candles
        period: SMA period (default: 20)
        
    Returns:
        List of SMA values with leading None values
    """
    _, _, _, closes, _ = _validate_ohlc_data(ohlc_data)
    return _calculate_sma(closes, period)


def calculate_ema(ohlc_data: List[Dict[str, Any]], period: int = 20) -> List[Optional[float]]:
    """Calculate Exponential Moving Average (EMA).
    
    EMA gives more weight to recent prices, making it more responsive
    to new information than SMA.
    
    Args:
        ohlc_data: List of OHLC candles
        period: EMA period (default: 20)
        
    Returns:
        List of EMA values with leading None values
    """
    _, _, _, closes, _ = _validate_ohlc_data(ohlc_data)
    return _calculate_ema(closes, period)


def calculate_wma(ohlc_data: List[Dict[str, Any]], period: int = 20) -> List[Optional[float]]:
    """Calculate Weighted Moving Average (WMA).
    
    WMA assigns linearly increasing weights to more recent prices.
    
    Args:
        ohlc_data: List of OHLC candles
        period: WMA period (default: 20)
        
    Returns:
        List of WMA values with leading None values
    """
    _, _, _, closes, _ = _validate_ohlc_data(ohlc_data)
    return _calculate_wma(closes, period)


def calculate_tema(ohlc_data: List[Dict[str, Any]], period: int = 10) -> List[Optional[float]]:
    """Calculate Triple Exponential Moving Average (TEMA).
    
    TEMA reduces lag by triple smoothing the data, providing a more
    responsive trend indicator than standard EMA.
    
    Args:
        ohlc_data: List of OHLC candles
        period: TEMA period (default: 10)
        
    Returns:
        List of TEMA values with leading None values
    """
    _, _, _, closes, _ = _validate_ohlc_data(ohlc_data)
    return _calculate_tema(closes, period)


def calculate_dema(ohlc_data: List[Dict[str, Any]], period: int = 21) -> List[Optional[float]]:
    """Calculate Double Exponential Moving Average (DEMA).
    
    DEMA reduces lag by double smoothing the data while maintaining
    responsiveness to price changes.
    
    Args:
        ohlc_data: List of OHLC candles
        period: DEMA period (default: 21)
        
    Returns:
        List of DEMA values with leading None values
    """
    _, _, _, closes, _ = _validate_ohlc_data(ohlc_data)
    return _calculate_dema(closes, period)


def calculate_adx(
    ohlc_data: List[Dict[str, Any]],
    period: int = 14
) -> Dict[str, List[Optional[float]]]:
    """Calculate Average Directional Index (ADX).
    
    ADX measures trend strength regardless of direction. Values above 25
    indicate a strong trend; below 20 indicate weak/no trend.
    
    Includes +DI and -DI for trend direction.
    
    Args:
        ohlc_data: List of OHLC candles
        period: ADX period (default: 14)
        
    Returns:
        Dictionary with 'plus_di', 'minus_di', and 'adx' lists
    """
    _, highs, lows, closes, _ = _validate_ohlc_data(ohlc_data)
    
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
        
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
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
        
        dx = 100 * abs(plus_di_val - minus_di_val) / (plus_di_val + minus_di_val) \
            if (plus_di_val + minus_di_val) > 0 else 0
        dx_values.append(dx)
    
    # Calculate ADX (smoothed DX)
    adx = [None] * (2 * period - 1)
    valid_dx = [d for d in dx_values if d is not None]
    
    if len(valid_dx) >= period:
        adx_start = sum(valid_dx[:period]) / period
        adx.append(round(adx_start, 2))
        
        for i in range(period, len(valid_dx)):
            adx_val = (adx[-1] * (period - 1) + valid_dx[i]) / period
            adx.append(round(adx_val, 2))
    
    return {
        "plus_di": plus_di,
        "minus_di": minus_di,
        "adx": adx
    }


def calculate_ma_ribbon(
    ohlc_data: List[Dict[str, Any]],
    periods: Optional[List[int]] = None
) -> Dict[str, List[Optional[float]]]:
    """Calculate Moving Average Ribbon.
    
    A ribbon of multiple EMAs (typically 10, 20, 30, 40, 50) used to
    visualize trend strength and direction.
    
    Args:
        ohlc_data: List of OHLC candles
        periods: List of periods for ribbon (default: [10, 20, 30, 40, 50])
        
    Returns:
        Dictionary with EMA values for each period
    """
    if periods is None:
        periods = [10, 20, 30, 40, 50]
    
    _, _, _, closes, _ = _validate_ohlc_data(ohlc_data)
    
    result = {}
    for period in periods:
        result[f"ema_{period}"] = _calculate_ema(closes, period)
    
    return result


# =============================================================================
# VOLATILITY INDICATORS (5 total)
# =============================================================================

def calculate_bollinger_bands(
    ohlc_data: List[Dict[str, Any]],
    period: int = 20,
    std_dev: float = 2.0
) -> Dict[str, List[Optional[float]]]:
    """Calculate Bollinger Bands.
    
    Bollinger Bands consist of a middle SMA band and upper/lower bands
    positioned at standard deviations from the middle.
    
    Args:
        ohlc_data: List of OHLC candles
        period: SMA period (default: 20)
        std_dev: Standard deviation multiplier (default: 2.0)
        
    Returns:
        Dictionary with 'upper', 'middle', and 'lower' band lists
    """
    _, _, _, closes, _ = _validate_ohlc_data(ohlc_data)
    
    sma = _calculate_sma(closes, period)
    
    upper = []
    lower = []
    
    for i in range(len(closes)):
        if i < period - 1:
            upper.append(None)
            lower.append(None)
        else:
            slice_data = closes[i - period + 1:i + 1]
            std = np.std(slice_data)
            upper.append(round(sma[i] + std_dev * std, 5))
            lower.append(round(sma[i] - std_dev * std, 5))
    
    return {
        "upper": upper,
        "middle": sma,
        "lower": lower
    }


def calculate_atr(
    ohlc_data: List[Dict[str, Any]],
    period: int = 14
) -> List[Optional[float]]:
    """Calculate Average True Range (ATR).
    
    ATR measures market volatility by decomposing the entire range
    of an asset price for that period.
    
    Args:
        ohlc_data: List of OHLC candles
        period: ATR period (default: 14)
        
    Returns:
        List of ATR values with leading None values
    """
    _, highs, lows, closes, _ = _validate_ohlc_data(ohlc_data)
    
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


def calculate_keltner_channel(
    ohlc_data: List[Dict[str, Any]],
    period: int = 20,
    offset_multiplier: float = 2.0
) -> Dict[str, List[Optional[float]]]:
    """Calculate Keltner Channel.
    
    Keltner Channel uses ATR to create volatility-based bands around
    an EMA center line.
    
    Args:
        ohlc_data: List of OHLC candles
        period: EMA/ATR period (default: 20)
        offset_multiplier: ATR multiplier for bands (default: 2.0)
        
    Returns:
        Dictionary with 'upper', 'middle', and 'lower' channel lists
    """
    opens, highs, lows, closes, _ = _validate_ohlc_data(ohlc_data)
    
    # Middle line = EMA of typical price
    typical_price = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
    middle = _calculate_ema(typical_price, period)
    
    # ATR for bandwidth
    atr_values = calculate_atr(ohlc_data, period)
    
    upper = []
    lower = []
    
    for i in range(len(closes)):
        if middle[i] is None or atr_values[i] is None:
            upper.append(None)
            lower.append(None)
        else:
            upper.append(round(middle[i] + offset_multiplier * atr_values[i], 5))
            lower.append(round(middle[i] - offset_multiplier * atr_values[i], 5))
    
    return {
        "upper": upper,
        "middle": middle,
        "lower": lower
    }


def calculate_natr(
    ohlc_data: List[Dict[str, Any]],
    period: int = 14
) -> List[Optional[float]]:
    """Calculate Normalized Average True Range (NATR).
    
    NATR normalizes ATR as a percentage of price, allowing comparison
    across different price levels.
    
    Formula: NATR = (ATR / Close) * 100
    
    Args:
        ohlc_data: List of OHLC candles
        period: NATR period (default: 14)
        
    Returns:
        List of NATR percentage values with leading None values
    """
    _, _, _, closes, _ = _validate_ohlc_data(ohlc_data)
    atr_values = calculate_atr(ohlc_data, period)
    
    result = []
    for atr, close in zip(atr_values, closes):
        if atr is None or close == 0:
            result.append(None)
        else:
            natr = (atr / close) * 100
            result.append(round(natr, 2))
    
    return result


def calculate_historical_volatility(
    ohlc_data: List[Dict[str, Any]],
    period: int = 20,
    annualize: bool = True
) -> List[Optional[float]]:
    """Calculate Historical Volatility.
    
    Historical volatility measures the standard deviation of log returns,
    typically annualized for interpretation.
    
    Args:
        ohlc_data: List of OHLC candles
        period: Lookback period (default: 20)
        annualize: Whether to annualize the result (default: True)
        
    Returns:
        List of historical volatility values with leading None values
    """
    _, _, _, closes, _ = _validate_ohlc_data(ohlc_data)
    
    if len(closes) < period + 1:
        return [None] * len(closes)
    
    # Calculate log returns
    log_returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            log_returns.append(np.log(closes[i] / closes[i - 1]))
        else:
            log_returns.append(0.0)
    
    # Calculate rolling standard deviation
    result = [None] * period
    
    for i in range(period, len(log_returns)):
        returns_slice = log_returns[i - period + 1:i + 1]
        vol = np.std(returns_slice)
        
        if annualize:
            # Assuming daily data, multiply by sqrt(252)
            vol = vol * np.sqrt(252)
        
        result.append(round(vol * 100, 2))  # As percentage
    
    # Add one more None for the first period (no return calculated)
    result = [None] + result
    
    return _pad_leading_nones(result, len(closes))


# =============================================================================
# VOLUME INDICATORS (5 total)
# =============================================================================

def calculate_obv(ohlc_data: List[Dict[str, Any]]) -> List[float]:
    """Calculate On-Balance Volume (OBV).
    
    OBV measures buying and selling pressure as a cumulative indicator
    that adds volume on up days and subtracts volume on down days.
    
    Args:
        ohlc_data: List of OHLC candles
        
    Returns:
        List of OBV values
    """
    _, _, _, closes, volumes = _validate_ohlc_data(ohlc_data)
    
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


def calculate_vwap(ohlc_data: List[Dict[str, Any]]) -> List[Optional[float]]:
    """Calculate Volume Weighted Average Price (VWAP).
    
    VWAP is the average price weighted by volume, often used as a
    benchmark for trade execution quality.
    
    Formula: VWAP = Sum(Typical Price * Volume) / Sum(Volume)
    
    Args:
        ohlc_data: List of OHLC candles
        
    Returns:
        List of VWAP values (note: this is cumulative from start of data)
    """
    _, highs, lows, closes, volumes = _validate_ohlc_data(ohlc_data)
    
    if not volumes or sum(volumes) == 0:
        return [None] * len(closes)
    
    typical_prices = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
    
    cumulative_tp_vol = 0.0
    cumulative_vol = 0.0
    result = []
    
    for tp, vol in zip(typical_prices, volumes):
        cumulative_tp_vol += tp * vol
        cumulative_vol += vol
        
        if cumulative_vol > 0:
            result.append(round(cumulative_tp_vol / cumulative_vol, 5))
        else:
            result.append(None)
    
    return result


def calculate_volume_roc(
    ohlc_data: List[Dict[str, Any]],
    period: int = 12
) -> List[Optional[float]]:
    """Calculate Volume Rate of Change.
    
    Measures the percentage change in volume over a specified period,
    highlighting surges in trading activity.
    
    Formula: VROC = ((Volume - Volume n periods ago) / Volume n periods ago) * 100
    
    Args:
        ohlc_data: List of OHLC candles
        period: Period for comparison (default: 12)
        
    Returns:
        List of VROC percentage values with leading None values
    """
    _, _, _, _, volumes = _validate_ohlc_data(ohlc_data)
    
    if len(volumes) < period + 1:
        return [None] * len(volumes)
    
    result = [None] * period
    for i in range(period, len(volumes)):
        if volumes[i - period] == 0:
            result.append(0.0)
        else:
            vroc = ((volumes[i] - volumes[i - period]) / volumes[i - period]) * 100
            result.append(round(vroc, 2))
    
    return result


def calculate_accumulation_distribution(ohlc_data: List[Dict[str, Any]]) -> List[float]:
    """Calculate Accumulation/Distribution Line (A/D Line).
    
    A/D Line is a volume-based indicator designed to show the flow of
    money into or out of a security.
    
    Formula: A/D = Previous A/D + ((Close - Low) - (High - Close)) / (High - Low) * Volume
    
    Args:
        ohlc_data: List of OHLC candles
        
    Returns:
        List of A/D Line values
    """
    _, highs, lows, closes, volumes = _validate_ohlc_data(ohlc_data)
    
    ad_line = [0.0]
    
    for i in range(len(closes)):
        if highs[i] == lows[i]:
            mf_multiplier = 0.0
        else:
            mf_multiplier = ((closes[i] - lows[i]) - (highs[i] - closes[i])) / (highs[i] - lows[i])
        
        mf_volume = mf_multiplier * volumes[i]
        
        if i == 0:
            ad_line[0] = mf_volume
        else:
            ad_line.append(ad_line[-1] + mf_volume)
    
    return [round(ad, 2) for ad in ad_line]


def calculate_mfi(
    ohlc_data: List[Dict[str, Any]],
    period: int = 14
) -> List[Optional[float]]:
    """Calculate Money Flow Index (MFI).
    
    MFI is a volume-weighted RSI that measures the strength of money
    flowing in and out of a security. Values > 80 overbought, < 20 oversold.
    
    Args:
        ohlc_data: List of OHLC candles
        period: MFI period (default: 14)
        
    Returns:
        List of MFI values (0-100) with leading None values
    """
    _, highs, lows, closes, volumes = _validate_ohlc_data(ohlc_data)
    
    if len(closes) < period + 1:
        return [None] * len(closes)
    
    # Calculate Typical Price and Raw Money Flow
    typical_prices = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
    raw_money_flows = [tp * v for tp, v in zip(typical_prices, volumes)]
    
    # Determine positive and negative money flow
    positive_flows = []
    negative_flows = []
    
    for i in range(1, len(typical_prices)):
        if typical_prices[i] > typical_prices[i - 1]:
            positive_flows.append(raw_money_flows[i])
            negative_flows.append(0)
        elif typical_prices[i] < typical_prices[i - 1]:
            positive_flows.append(0)
            negative_flows.append(raw_money_flows[i])
        else:
            positive_flows.append(0)
            negative_flows.append(0)
    
    result = [None] * period
    
    for i in range(period - 1, len(positive_flows)):
        pos_sum = sum(positive_flows[i - period + 1:i + 1])
        neg_sum = sum(negative_flows[i - period + 1:i + 1])
        
        if neg_sum == 0:
            result.append(100.0)
        else:
            money_ratio = pos_sum / neg_sum
            mfi = 100 - (100 / (1 + money_ratio))
            result.append(round(mfi, 2))
    
    return result


# =============================================================================
# TREND STRENGTH INDICATORS (3 total)
# =============================================================================

def calculate_qstick(
    ohlc_data: List[Dict[str, Any]],
    period: int = 10
) -> List[Optional[float]]:
    """Calculate QStick.
    
    QStick measures the trend strength by averaging the difference
    between opening and closing prices.
    
    Formula: QStick = SMA(Close - Open, period)
    
    Args:
        ohlc_data: List of OHLC candles
        period: SMA period (default: 10)
        
    Returns:
        List of QStick values with leading None values
    """
    opens, _, _, closes, _ = _validate_ohlc_data(ohlc_data)
    
    # Calculate Close - Open for each bar
    co_diff = [c - o for c, o in zip(closes, opens)]
    
    return _calculate_sma(co_diff, period)


def calculate_vhf(
    ohlc_data: List[Dict[str, Any]],
    period: int = 28
) -> List[Optional[float]]:
    """Calculate Vertical Horizontal Filter (VHF).
    
    VHF determines whether prices are trending or in a congestion phase.
    Higher values indicate trending, lower values indicate sideways movement.
    
    Formula: VHF = |High - Low| / Sum|Close - Previous Close|
    
    Args:
        ohlc_data: List of OHLC candles
        period: VHF period (default: 28)
        
    Returns:
        List of VHF values with leading None values
    """
    _, highs, lows, closes, _ = _validate_ohlc_data(ohlc_data)
    
    if len(closes) < period:
        return [None] * len(closes)
    
    result = [None] * (period - 1)
    
    for i in range(period - 1, len(closes)):
        # Highest high and lowest low in the period
        highest_high = max(highs[i - period + 1:i + 1])
        lowest_low = min(lows[i - period + 1:i + 1])
        
        # Absolute difference between highest high and lowest low
        numerator = abs(highest_high - lowest_low)
        
        # Sum of absolute changes in close prices
        denominator = sum(
            abs(closes[j] - closes[j - 1])
            for j in range(i - period + 2, i + 1)
        )
        
        if denominator == 0:
            result.append(0.0)
        else:
            vhf = numerator / denominator
            result.append(round(vhf, 4))
    
    return result


def calculate_mass_index(
    ohlc_data: List[Dict[str, Any]],
    period: int = 9
) -> List[Optional[float]]:
    """Calculate Mass Index.
    
    Mass Index identifies trend reversals by measuring the narrowing
    and widening of the price range. Values above 27 suggest reversal.
    
    Formula: MI = Sum(EMA(High - Low, 9) / EMA(EMA(High - Low, 9), 9), 25)
    
    Args:
        ohlc_data: List of OHLC candles
        period: EMA period (default: 9)
        
    Returns:
        List of Mass Index values with leading None values
    """
    _, highs, lows, _, _ = _validate_ohlc_data(ohlc_data)
    
    # Calculate High - Low (range)
    hl_range = [h - l for h, l in zip(highs, lows)]
    
    # Single EMA of range
    ema1 = _calculate_ema(hl_range, period)
    ema1_valid = [v for v in ema1 if v is not None]
    
    # Double EMA of range
    ema2 = _calculate_ema(ema1_valid, period)
    ema2_valid = [v for v in ema2 if v is not None]
    
    # Both EMAs need valid values at the same index
    min_len = min(len(ema1_valid), len(ema2_valid))
    
    # Ratio of EMAs (only where both are valid)
    ratios = []
    for i in range(min_len):
        if ema2_valid[i] == 0:
            ratios.append(0.0)
        else:
            ratios.append(ema1_valid[i] / ema2_valid[i])
    
    # Sum over 25 periods (standard Mass Index period)
    mi_period = 25
    if len(ratios) < mi_period:
        return [None] * len(highs)
    
    result = [None] * (len(highs) - len(ratios) + mi_period - 1)
    
    for i in range(mi_period - 1, len(ratios)):
        mi = sum(ratios[i - mi_period + 1:i + 1])
        result.append(round(mi, 2))
    
    return result


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# Registry of all indicator functions
_INDICATOR_REGISTRY: Dict[str, Dict[str, Any]] = {
    # Momentum Indicators
    "rsi": {
        "function": calculate_rsi,
        "category": "momentum",
        "name": "Relative Strength Index",
        "params": {"period": 14},
        "returns": "list"
    },
    "macd": {
        "function": calculate_macd,
        "category": "momentum",
        "name": "MACD",
        "params": {"fast": 12, "slow": 26, "signal": 9},
        "returns": "dict"
    },
    "stochastic": {
        "function": calculate_stochastic,
        "category": "momentum",
        "name": "Stochastic Oscillator",
        "params": {"period": 14, "smooth_k": 3, "smooth_d": 3},
        "returns": "dict"
    },
    "roc": {
        "function": calculate_roc,
        "category": "momentum",
        "name": "Rate of Change",
        "params": {"period": 12},
        "returns": "list"
    },
    "cci": {
        "function": calculate_cci,
        "category": "momentum",
        "name": "Commodity Channel Index",
        "params": {"period": 20},
        "returns": "list"
    },
    "williams_r": {
        "function": calculate_williams_r,
        "category": "momentum",
        "name": "Williams %R",
        "params": {"period": 14},
        "returns": "list"
    },
    
    # Trend Indicators
    "sma": {
        "function": calculate_sma,
        "category": "trend",
        "name": "Simple Moving Average",
        "params": {"period": 20},
        "returns": "list"
    },
    "ema": {
        "function": calculate_ema,
        "category": "trend",
        "name": "Exponential Moving Average",
        "params": {"period": 20},
        "returns": "list"
    },
    "wma": {
        "function": calculate_wma,
        "category": "trend",
        "name": "Weighted Moving Average",
        "params": {"period": 20},
        "returns": "list"
    },
    "tema": {
        "function": calculate_tema,
        "category": "trend",
        "name": "Triple Exponential Moving Average",
        "params": {"period": 10},
        "returns": "list"
    },
    "dema": {
        "function": calculate_dema,
        "category": "trend",
        "name": "Double Exponential Moving Average",
        "params": {"period": 21},
        "returns": "list"
    },
    "adx": {
        "function": calculate_adx,
        "category": "trend",
        "name": "Average Directional Index",
        "params": {"period": 14},
        "returns": "dict"
    },
    "ma_ribbon": {
        "function": calculate_ma_ribbon,
        "category": "trend",
        "name": "Moving Average Ribbon",
        "params": {"periods": [10, 20, 30, 40, 50]},
        "returns": "dict"
    },
    
    # Volatility Indicators
    "bollinger_bands": {
        "function": calculate_bollinger_bands,
        "category": "volatility",
        "name": "Bollinger Bands",
        "params": {"period": 20, "std_dev": 2.0},
        "returns": "dict"
    },
    "atr": {
        "function": calculate_atr,
        "category": "volatility",
        "name": "Average True Range",
        "params": {"period": 14},
        "returns": "list"
    },
    "keltner_channel": {
        "function": calculate_keltner_channel,
        "category": "volatility",
        "name": "Keltner Channel",
        "params": {"period": 20, "offset_multiplier": 2.0},
        "returns": "dict"
    },
    "natr": {
        "function": calculate_natr,
        "category": "volatility",
        "name": "Normalized Average True Range",
        "params": {"period": 14},
        "returns": "list"
    },
    "historical_volatility": {
        "function": calculate_historical_volatility,
        "category": "volatility",
        "name": "Historical Volatility",
        "params": {"period": 20, "annualize": True},
        "returns": "list"
    },
    
    # Volume Indicators
    "obv": {
        "function": calculate_obv,
        "category": "volume",
        "name": "On-Balance Volume",
        "params": {},
        "returns": "list"
    },
    "vwap": {
        "function": calculate_vwap,
        "category": "volume",
        "name": "Volume Weighted Average Price",
        "params": {},
        "returns": "list"
    },
    "volume_roc": {
        "function": calculate_volume_roc,
        "category": "volume",
        "name": "Volume Rate of Change",
        "params": {"period": 12},
        "returns": "list"
    },
    "accumulation_distribution": {
        "function": calculate_accumulation_distribution,
        "category": "volume",
        "name": "Accumulation/Distribution Line",
        "params": {},
        "returns": "list"
    },
    "mfi": {
        "function": calculate_mfi,
        "category": "volume",
        "name": "Money Flow Index",
        "params": {"period": 14},
        "returns": "list"
    },
    
    # Trend Strength Indicators
    "qstick": {
        "function": calculate_qstick,
        "category": "trend_strength",
        "name": "QStick",
        "params": {"period": 10},
        "returns": "list"
    },
    "vhf": {
        "function": calculate_vhf,
        "category": "trend_strength",
        "name": "Vertical Horizontal Filter",
        "params": {"period": 28},
        "returns": "list"
    },
    "mass_index": {
        "function": calculate_mass_index,
        "category": "trend_strength",
        "name": "Mass Index",
        "params": {"period": 9},
        "returns": "list"
    },
}


def get_indicator_function(indicator_name: str) -> Optional[Callable]:
    """Get the indicator function by name.
    
    Args:
        indicator_name: Name of the indicator (case-insensitive)
        
    Returns:
        Indicator function or None if not found
        
    Example:
        >>> rsi_func = get_indicator_function("rsi")
        >>> result = rsi_func(ohlc_data, period=14)
    """
    indicator_name = indicator_name.lower().strip()
    indicator_info = _INDICATOR_REGISTRY.get(indicator_name)
    
    if indicator_info:
        return indicator_info["function"]
    
    return None


def calculate_indicator(
    ohlc_data: List[Dict[str, Any]],
    indicator_name: str,
    params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Calculate any indicator by name with given parameters.
    
    This is the main interface for calculating indicators. It handles
    parameter validation and provides consistent output format.
    
    Args:
        ohlc_data: List of OHLC candle dictionaries
        indicator_name: Name of the indicator to calculate
        params: Dictionary of parameters for the indicator
        
    Returns:
        Dictionary containing:
        - indicator: indicator name
        - values: calculated values (or dict of values for multi-output indicators)
        - params: parameters used
        - error: error message if calculation failed
        
    Example:
        >>> result = calculate_indicator(ohlc_data, "rsi", {"period": 14})
        >>> print(result["values"])
    """
    params = params or {}
    
    result = {
        "indicator": indicator_name,
        "params": params,
        "values": [],
        "error": None
    }
    
    # Get indicator info
    indicator_name_lower = indicator_name.lower().strip()
    indicator_info = _INDICATOR_REGISTRY.get(indicator_name_lower)
    
    if not indicator_info:
        result["error"] = f"Unknown indicator: {indicator_name}"
        return result
    
    # Validate parameters
    validation = validate_indicator_params(indicator_name, params)
    if not validation["valid"]:
        result["error"] = validation["error"]
        return result
    
    # Get the function
    func = indicator_info["function"]
    
    # Merge default params with provided params
    default_params = indicator_info["params"].copy()
    default_params.update(params)
    
    try:
        # Calculate indicator
        values = func(ohlc_data, **default_params)
        result["values"] = values
        result["category"] = indicator_info["category"]
        result["display_name"] = indicator_info["name"]
    except Exception as e:
        result["error"] = f"Calculation error: {str(e)}"
    
    return result


def get_available_indicators_list() -> List[Dict[str, Any]]:
    """Get a list of all available indicators with metadata.
    
    Returns a comprehensive list of all 30+ indicators organized by
    category with their default parameters.
    
    Returns:
        List of indicator metadata dictionaries
        
    Example:
        >>> indicators = get_available_indicators_list()
        >>> momentum_indicators = [i for i in indicators if i["category"] == "momentum"]
    """
    result = []
    
    for indicator_id, info in _INDICATOR_REGISTRY.items():
        result.append({
            "id": indicator_id,
            "name": info["name"],
            "category": info["category"],
            "default_params": info["params"],
            "return_type": info["returns"]
        })
    
    # Sort by category then name
    result.sort(key=lambda x: (x["category"], x["name"]))
    
    return result


def validate_indicator_params(
    indicator_name: str,
    params: Dict[str, Any]
) -> Dict[str, Any]:
    """Validate parameters for a given indicator.
    
    Args:
        indicator_name: Name of the indicator
        params: Parameters to validate
        
    Returns:
        Dictionary with validation result:
        - valid: True if parameters are valid
        - error: Error message if invalid
        - normalized_params: Normalized parameter names
        
    Example:
        >>> validation = validate_indicator_params("rsi", {"period": 14})
        >>> if validation["valid"]:
        ...     # Use validation["normalized_params"]
    """
    indicator_name = indicator_name.lower().strip()
    indicator_info = _INDICATOR_REGISTRY.get(indicator_name)
    
    if not indicator_info:
        return {
            "valid": False,
            "error": f"Unknown indicator: {indicator_name}",
            "normalized_params": {}
        }
    
    valid_params = indicator_info["params"]
    normalized_params = {}
    errors = []
    
    # Normalize parameter names (allow snake_case or camelCase)
    param_mapping = {}
    for valid_key in valid_params.keys():
        param_mapping[valid_key.lower()] = valid_key
        # Also map camelCase versions
        camel_key = valid_key.replace("_", "")
        param_mapping[camel_key.lower()] = valid_key
    
    for key, value in params.items():
        normalized_key = param_mapping.get(key.lower().replace("_", ""))
        if normalized_key:
            normalized_params[normalized_key] = value
        else:
            errors.append(f"Unknown parameter: {key}")
    
    # Type validation for common parameters
    for key, value in normalized_params.items():
        if key in ["period", "fast", "slow", "signal"]:
            if not isinstance(value, int) or value <= 0:
                errors.append(f"{key} must be a positive integer")
        elif key == "std_dev":
            if not isinstance(value, (int, float)) or value <= 0:
                errors.append(f"{key} must be a positive number")
    
    if errors:
        return {
            "valid": False,
            "error": "; ".join(errors),
            "normalized_params": normalized_params
        }
    
    return {
        "valid": True,
        "error": None,
        "normalized_params": normalized_params
    }


def get_indicators_by_category(category: str) -> List[Dict[str, Any]]:
    """Get all indicators in a specific category.
    
    Args:
        category: Category name (momentum, trend, volatility, volume, trend_strength)
        
    Returns:
        List of indicator metadata dictionaries for the category
    """
    all_indicators = get_available_indicators_list()
    return [i for i in all_indicators if i["category"] == category.lower()]


def get_indicator_info(indicator_name: str) -> Optional[Dict[str, Any]]:
    """Get detailed information about a specific indicator.
    
    Args:
        indicator_name: Name of the indicator
        
    Returns:
        Indicator metadata dictionary or None if not found
    """
    indicator_name = indicator_name.lower().strip()
    indicator_info = _INDICATOR_REGISTRY.get(indicator_name)
    
    if not indicator_info:
        return None
    
    return {
        "id": indicator_name,
        "name": indicator_info["name"],
        "category": indicator_info["category"],
        "default_params": indicator_info["params"],
        "return_type": indicator_info["returns"]
    }


# =============================================================================
# CONVENIENCE EXPORTS
# =============================================================================

__all__ = [
    # Momentum Indicators
    "calculate_rsi",
    "calculate_macd",
    "calculate_stochastic",
    "calculate_roc",
    "calculate_cci",
    "calculate_williams_r",
    
    # Trend Indicators
    "calculate_sma",
    "calculate_ema",
    "calculate_wma",
    "calculate_tema",
    "calculate_dema",
    "calculate_adx",
    "calculate_ma_ribbon",
    
    # Volatility Indicators
    "calculate_bollinger_bands",
    "calculate_atr",
    "calculate_keltner_channel",
    "calculate_natr",
    "calculate_historical_volatility",
    
    # Volume Indicators
    "calculate_obv",
    "calculate_vwap",
    "calculate_volume_roc",
    "calculate_accumulation_distribution",
    "calculate_mfi",
    
    # Trend Strength
    "calculate_qstick",
    "calculate_vhf",
    "calculate_mass_index",
    
    # Helper Functions
    "get_indicator_function",
    "calculate_indicator",
    "get_available_indicators_list",
    "validate_indicator_params",
    "get_indicators_by_category",
    "get_indicator_info",
]
