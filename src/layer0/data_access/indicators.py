"""
Technical Indicators Module
===========================

Vectorized technical indicators for strategy development.
All functions accept pandas Series/DataFrame and return Series.
"""

import numpy as np
import pandas as pd
from typing import Optional, Tuple


def ema(series: pd.Series, period: int) -> pd.Series:
    """
    Calculate Exponential Moving Average.
    
    Args:
        series: Price series
        period: EMA period
        
    Returns:
        EMA series
    """
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    """
    Calculate Simple Moving Average.
    
    Args:
        series: Price series
        period: SMA period
        
    Returns:
        SMA series
    """
    return series.rolling(window=period).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate Average True Range.
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        period: ATR period
        
    Returns:
        ATR series
    """
    prev_close = close.shift(1)
    
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    return true_range.ewm(span=period, adjust=False).mean()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate Average Directional Index (ADX).
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        period: ADX period
        
    Returns:
        ADX series (0-100)
    """
    # Calculate +DM and -DM
    plus_dm = high.diff()
    minus_dm = -low.diff()
    
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    
    plus_dm[plus_dm <= minus_dm] = 0
    minus_dm[minus_dm <= plus_dm] = 0
    
    # Calculate TR
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Smooth TR, +DM, -DM
    atr_val = true_range.ewm(span=period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(span=period, adjust=False).mean() / atr_val
    minus_di = 100 * minus_dm.ewm(span=period, adjust=False).mean() / atr_val
    
    # Calculate DX and ADX
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx_val = dx.ewm(span=period, adjust=False).mean()
    
    return adx_val


def bollinger_bands(close: pd.Series, period: int = 20, std_dev: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate Bollinger Bands.
    
    Args:
        close: Close prices
        period: Moving average period
        std_dev: Standard deviation multiplier
        
    Returns:
        Tuple of (upper_band, middle_band, lower_band)
    """
    middle = sma(close, period)
    std = close.rolling(window=period).std()
    
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    
    return upper, middle, lower


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate Relative Strength Index.
    
    Args:
        close: Close prices
        period: RSI period
        
    Returns:
        RSI series (0-100)
    """
    delta = close.diff()
    
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi_val = 100 - (100 / (1 + rs))
    
    return rsi_val


def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, 
               k_period: int = 14, d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
    """
    Calculate Stochastic Oscillator.
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        k_period: %K period
        d_period: %D period
        
    Returns:
        Tuple of (%K, %D)
    """
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()
    
    k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    d = k.rolling(window=d_period).mean()
    
    return k, d


def donchian_channel(high: pd.Series, low: pd.Series, period: int = 20) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate Donchian Channel.
    
    Args:
        high: High prices
        low: Low prices
        period: Channel period
        
    Returns:
        Tuple of (upper_band, middle_band, lower_band)
    """
    upper = high.rolling(window=period).max()
    lower = low.rolling(window=period).min()
    middle = (upper + lower) / 2
    
    return upper, middle, lower


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate MACD.
    
    Args:
        close: Close prices
        fast: Fast EMA period
        slow: Slow EMA period
        signal: Signal line period
        
    Returns:
        Tuple of (macd_line, signal_line, histogram)
    """
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram


def zscore(series: pd.Series, period: int = 20) -> pd.Series:
    """
    Calculate Z-Score (standardized deviation from mean).
    
    Args:
        series: Input series
        period: Lookback period
        
    Returns:
        Z-Score series
    """
    rolling_mean = series.rolling(window=period).mean()
    rolling_std = series.rolling(window=period).std()
    
    return (series - rolling_mean) / rolling_std


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """
    Calculate Volume Weighted Average Price (VWAP).
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        volume: Volume
        
    Returns:
        VWAP series
    """
    typical_price = (high + low + close) / 3
    cum_typical_vol = (typical_price * volume).cumsum()
    cum_volume = volume.cumsum()
    
    return cum_typical_vol / cum_volume


def williams_r(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate Williams %R.
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        period: Lookback period
        
    Returns:
        Williams %R series (-100 to 0)
    """
    highest_high = high.rolling(window=period).max()
    lowest_low = low.rolling(window=period).min()
    
    williams = -100 * (highest_high - close) / (highest_high - lowest_low)
    
    return williams


def cci(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> pd.Series:
    """
    Calculate Commodity Channel Index.
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        period: CCI period
        
    Returns:
        CCI series
    """
    typical_price = (high + low + close) / 3
    tp_sma = typical_price.rolling(window=period).mean()
    tp_std = typical_price.rolling(window=period).std()
    
    cci_val = (typical_price - tp_sma) / (0.015 * tp_std)
    
    return cci_val


def keltner_channel(high: pd.Series, low: pd.Series, close: pd.Series, 
                    ema_period: int = 20, atr_period: int = 10, atr_multiplier: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate Keltner Channel.
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        ema_period: EMA period for middle line
        atr_period: ATR period
        atr_multiplier: ATR multiplier for channel width
        
    Returns:
        Tuple of (upper_band, middle_band, lower_band)
    """
    middle = ema(close, ema_period)
    atr_val = atr(high, low, close, atr_period)
    
    upper = middle + (atr_multiplier * atr_val)
    lower = middle - (atr_multiplier * atr_val)
    
    return upper, middle, lower


def chandelier_exit(high: pd.Series, low: pd.Series, close: pd.Series, 
                    period: int = 22, atr_multiplier: float = 3.0) -> Tuple[pd.Series, pd.Series]:
    """
    Calculate Chandelier Exit (trend-following stop).
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        period: Lookback period for highest high/lowest low
        atr_multiplier: ATR multiplier for stop distance
        
    Returns:
        Tuple of (long_stop, short_stop)
    """
    atr_val = atr(high, low, close, period)
    highest_high = high.rolling(window=period).max()
    lowest_low = low.rolling(window=period).min()
    
    long_stop = highest_high - (atr_multiplier * atr_val)
    short_stop = lowest_low + (atr_multiplier * atr_val)
    
    return long_stop, short_stop


def supertrend(high: pd.Series, low: pd.Series, close: pd.Series, 
               period: int = 10, atr_multiplier: float = 3.0) -> Tuple[pd.Series, pd.Series]:
    """
    Calculate SuperTrend indicator.
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        period: ATR period
        atr_multiplier: ATR multiplier
        
    Returns:
        Tuple of (supertrend_line, trend_direction)
        trend_direction: 1 for uptrend, -1 for downtrend
    """
    atr_val = atr(high, low, close, period)
    
    # Basic upper and lower bands
    hl2 = (high + low) / 2
    upper_band = hl2 + (atr_multiplier * atr_val)
    lower_band = hl2 - (atr_multiplier * atr_val)
    
    # Initialize SuperTrend
    supertrend = pd.Series(index=close.index, dtype=float)
    trend = pd.Series(index=close.index, dtype=int)
    
    for i in range(len(close)):
        if i == 0:
            supertrend.iloc[i] = upper_band.iloc[i]
            trend.iloc[i] = 1
        else:
            if close.iloc[i] > supertrend.iloc[i-1]:
                trend.iloc[i] = 1
                supertrend.iloc[i] = max(lower_band.iloc[i], supertrend.iloc[i-1])
            else:
                trend.iloc[i] = -1
                supertrend.iloc[i] = min(upper_band.iloc[i], supertrend.iloc[i-1])
    
    return supertrend, trend


def volatility_contraction_index(high: pd.Series, low: pd.Series, close: pd.Series, 
                                  lookback: int = 20) -> pd.Series:
    """
    Calculate Volatility Contraction Index for identifying VCP patterns.
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        lookback: Lookback period for volatility measurement
        
    Returns:
        VCI series (lower values indicate contraction)
    """
    atr_val = atr(high, low, close, lookback)
    atr_sma = atr_val.rolling(window=lookback).mean()
    
    # Normalize by price level
    vci = (atr_val / close) / (atr_sma / close).rolling(window=lookback).mean()
    
    return vci


def volume_profile_levels(high: pd.Series, low: pd.Series, close: pd.Series, 
                         volume: pd.Series, lookback: int = 100, num_levels: int = 5) -> pd.DataFrame:
    """
    Calculate key volume profile levels (POC, VAH, VAL).
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        volume: Volume
        lookback: Lookback period
        num_levels: Number of levels to calculate
        
    Returns:
        DataFrame with POC, VAH, VAL columns
    """
    typical_price = (high + low + close) / 3
    
    # Create price bins
    price_range = typical_price.rolling(window=lookback).max() - typical_price.rolling(window=lookback).min()
    bin_size = price_range / num_levels
    
    # For simplicity, return rolling VWAP-based levels
    vwap_val = vwap(high, low, close, volume)
    std = typical_price.rolling(window=lookback).std()
    
    poc = vwap_val
    vah = poc + std
    val = poc - std
    
    return pd.DataFrame({
        'POC': poc,
        'VAH': vah,
        'VAL': val
    }, index=close.index)


def detect_swing_points(high: pd.Series, low: pd.Series, period: int = 5) -> Tuple[pd.Series, pd.Series]:
    """
    Detect swing highs and swing lows.
    
    Args:
        high: High prices
        low: Low prices
        period: Lookback/lookahead period
        
    Returns:
        Tuple of (swing_highs, swing_lows) as boolean series
    """
    # Swing high: higher than 'period' bars before and after
    swing_highs = (high == high.rolling(window=period*2+1, center=True).max()) & \
                  (high > high.shift(period))
    
    # Swing low: lower than 'period' bars before and after
    swing_lows = (low == low.rolling(window=period*2+1, center=True).min()) & \
                 (low < low.shift(period))
    
    return swing_highs, swing_lows


def calculate_pips(price_change: float, asset: str = "EUR_USD") -> float:
    """
    Convert price change to pips.
    
    Args:
        price_change: Price difference
        asset: Asset symbol for pip calculation
        
    Returns:
        Pips
    """
    if "JPY" in asset:
        return price_change * 100  # JPY pairs: 1 pip = 0.01
    else:
        return price_change * 10000  # Standard: 1 pip = 0.0001


def get_pip_value(asset: str = "EUR_USD") -> float:
    """
    Get pip value for an asset.
    
    Args:
        asset: Asset symbol
        
    Returns:
        Pip value (price per pip)
    """
    if "JPY" in asset:
        return 0.01
    else:
        return 0.0001
