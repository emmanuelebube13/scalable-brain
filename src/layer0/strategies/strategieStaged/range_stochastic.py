"""
Range Stochastic Strategy
=========================

Mean-reversion strategy using Stochastic Oscillator.

Entry Logic:
- BUY: %K crosses above 20 from below (exit oversold)
- SELL: %K crosses below 80 from above (exit overbought)

This is a classic momentum exhaustion strategy that works well in
range-bound markets.

Multi-Timeframe Confluence:
- H4: Primary signals
- H1: Fine-tune entry timing
- D1: Avoid strong counter-trend trades
"""

import pandas as pd
import numpy as np
from typing import Dict, Any
from ..strategy_base import StrategyBase, StrategyConfig, SignalType
from ..indicators import stochastic, atr


class RangeStochasticStrategy(StrategyBase):
    """
    Stochastic Oscillator Mean Reversion Strategy.
    
    Parameters:
    - k_period: %K period (default: 14)
    - d_period: %D period (default: 3)
    - oversold: Oversold threshold (default: 20)
    - overbought: Overbought threshold (default: 80)
    - smooth_k: Smoothing for %K (default: 3)
    """
    
    def __init__(self,
                 k_period: int = 14,
                 d_period: int = 3,
                 oversold: float = 20.0,
                 overbought: float = 80.0,
                 smooth_k: int = 3,
                 custom_config: Dict[str, Any] = None):
        """
        Initialize Range Stochastic Strategy.
        
        Args:
            k_period: %K period
            d_period: %D period
            oversold: Oversold threshold
            overbought: Overbought threshold
            smooth_k: %K smoothing period
            custom_config: Override default config
        """
        config = StrategyConfig(
            name="Range_Stochastic",
            description="Stochastic oscillator mean reversion",
            version="1.0.0",
            assets=["EUR_USD", "GBP_USD", "USD_JPY"],
            granularities=["H4", "H1"],
            use_multi_timeframe=True,
            primary_granularity="H4",
            confirmation_granularity="H1",
            macro_granularity="D1",
            stop_loss_atr=1.5,
            take_profit_atr=1.5,
            require_trend_alignment=False,
            max_bars_hold=15  # Quick exits for stochastic signals
        )
        
        if custom_config:
            for key, value in custom_config.items():
                setattr(config, key, value)
        
        super().__init__(config)
        
        self.k_period = k_period
        self.d_period = d_period
        self.oversold = oversold
        self.overbought = overbought
        self.smooth_k = smooth_k
    
    def calculate_indicators(self, df: pd.DataFrame, asset: str, granularity: str) -> pd.DataFrame:
        """
        Calculate Stochastic Oscillator indicators.
        
        Args:
            df: OHLCV DataFrame
            asset: Asset symbol
            granularity: Timeframe
            
        Returns:
            DataFrame with indicators
        """
        df = df.copy()
        
        # Adjust periods based on timeframe
        if granularity == "H1":
            k_period = self.k_period // 2
            d_period = self.d_period
        elif granularity == "D1":
            k_period = self.k_period * 2
            d_period = self.d_period * 2
        else:  # H4
            k_period = self.k_period
            d_period = self.d_period
        
        # Calculate Stochastic
        k, d = stochastic(df['High'], df['Low'], df['Close'], k_period, d_period)
        
        # Smooth %K if needed
        if self.smooth_k > 1:
            k = k.rolling(window=self.smooth_k).mean()
        
        df['Stoch_K'] = k
        df['Stoch_D'] = d
        
        # Calculate ATR
        df['ATR'] = atr(df['High'], df['Low'], df['Close'], 14)
        
        # Stochastic state
        df['Stoch_Oversold'] = k < self.oversold
        df['Stoch_Overbought'] = k > self.overbought
        
        # Crossovers
        df['Stoch_Cross_Up'] = (k > self.oversold) & (k.shift(1) <= self.oversold)
        df['Stoch_Cross_Down'] = (k < self.overbought) & (k.shift(1) >= self.overbought)
        
        # %K crossing %D (additional confirmation)
        df['Stoch_KD_Cross_Up'] = (k > d) & (k.shift(1) <= d.shift(1))
        df['Stoch_KD_Cross_Down'] = (k < d) & (k.shift(1) >= d.shift(1))
        
        return df
    
    def generate_signals(self, df: pd.DataFrame, asset: str, granularity: str) -> pd.Series:
        """
        Generate trading signals.
        
        Args:
            df: DataFrame with indicators
            asset: Asset symbol
            granularity: Timeframe
            
        Returns:
            Series with signals (1=buy, -1=sell, 0=hold)
        """
        signals = pd.Series(0, index=df.index)
        
        # Buy: %K crosses above oversold level
        buy_condition = df['Stoch_Cross_Up']
        
        # Additional: %K above %D (momentum turning up)
        buy_condition = buy_condition & (df['Stoch_K'] > df['Stoch_D'])
        
        # Sell: %K crosses below overbought level
        sell_condition = df['Stoch_Cross_Down']
        
        # Additional: %K below %D (momentum turning down)
        sell_condition = sell_condition & (df['Stoch_K'] < df['Stoch_D'])
        
        signals[buy_condition] = 1
        signals[sell_condition] = -1
        
        return signals
    
    def get_entry_conditions(self) -> Dict[str, str]:
        """
        Get entry condition descriptions.
        
        Returns:
            Dictionary with entry conditions
        """
        return {
            'H4': f'%K crosses above {self.oversold} AND %K > %D',
            'H1': f'Confirm on H1 for entry timing',
            'D1': f'Avoid strong counter-trend (optional)',
            'description': 'Stochastic exit from overbought/oversold extremes'
        }
    
    def get_exit_conditions(self) -> Dict[str, str]:
        """
        Get exit condition descriptions.
        
        Returns:
            Dictionary with exit conditions
        """
        return {
            'stop_loss': f'{self.config.stop_loss_atr} * ATR from entry',
            'take_profit': f'{self.config.take_profit_atr} * ATR from entry',
            'stoch_exit': 'Exit when %K reaches opposite extreme',
            'kd_cross_exit': 'Exit on opposite %K/%D cross',
            'time_stop': f'Exit after {self.config.max_bars_hold} bars'
        }
    
    def get_required_warmup_bars(self) -> int:
        """Get required warmup bars."""
        return self.k_period + self.d_period + self.smooth_k + 20


class RangeStochastic_H1_Only(RangeStochasticStrategy):
    """H1-only variant of Range Stochastic."""
    
    def __init__(self):
        super().__init__(k_period=7, d_period=3)
        self.config.name = "Range_Stochastic_H1"
        self.config.use_multi_timeframe = False
        self.config.primary_granularity = "H1"


class RangeStochastic_H4_Only(RangeStochasticStrategy):
    """H4-only variant of Range Stochastic."""
    
    def __init__(self):
        super().__init__(k_period=14, d_period=3)
        self.config.name = "Range_Stochastic_H4"
        self.config.use_multi_timeframe = False
        self.config.primary_granularity = "H4"


class RangeStochastic_Divergence(RangeStochasticStrategy):
    """
    Stochastic strategy with divergence detection.
    Looks for bullish divergence (price lower low, Stoch higher low) 
    and bearish divergence (price higher high, Stoch lower high).
    """
    
    def __init__(self):
        super().__init__(k_period=14, d_period=3)
        self.config.name = "Range_Stochastic_Divergence"
    
    def _detect_bullish_divergence(self, df: pd.DataFrame, lookback: int = 10) -> pd.Series:
        """
        Detect bullish divergence (price lower low, indicator higher low).
        
        Args:
            df: DataFrame with price and Stochastic
            lookback: Lookback period for swing detection
            
        Returns:
            Boolean series indicating bullish divergence
        """
        # Find local price lows
        price_low = df['Low'].rolling(window=lookback, center=True).min() == df['Low']
        
        # Find Stochastic lows at same points
        stoch_low = df['Stoch_K'].rolling(window=lookback, center=True).min() == df['Stoch_K']
        
        # Divergence: price made lower low, but Stochastic made higher low
        divergence = pd.Series(False, index=df.index)
        
        for i in range(lookback, len(df) - lookback):
            if price_low.iloc[i]:
                # Find previous price low
                prev_lows = price_low.iloc[:i]
                if prev_lows.any():
                    prev_idx = prev_lows[prev_lows].index[-1]
                    
                    # Check for divergence
                    price_lower = df['Low'].iloc[i] < df['Low'].loc[prev_idx]
                    stoch_higher = df['Stoch_K'].iloc[i] > df['Stoch_K'].loc[prev_idx]
                    
                    if price_lower and stoch_higher:
                        divergence.iloc[i] = True
        
        return divergence
    
    def _detect_bearish_divergence(self, df: pd.DataFrame, lookback: int = 10) -> pd.Series:
        """
        Detect bearish divergence (price higher high, indicator lower high).
        
        Args:
            df: DataFrame with price and Stochastic
            lookback: Lookback period for swing detection
            
        Returns:
            Boolean series indicating bearish divergence
        """
        # Find local price highs
        price_high = df['High'].rolling(window=lookback, center=True).max() == df['High']
        
        # Find Stochastic highs at same points
        stoch_high = df['Stoch_K'].rolling(window=lookback, center=True).max() == df['Stoch_K']
        
        # Divergence: price made higher high, but Stochastic made lower high
        divergence = pd.Series(False, index=df.index)
        
        for i in range(lookback, len(df) - lookback):
            if price_high.iloc[i]:
                # Find previous price high
                prev_highs = price_high.iloc[:i]
                if prev_highs.any():
                    prev_idx = prev_highs[prev_highs].index[-1]
                    
                    # Check for divergence
                    price_higher = df['High'].iloc[i] > df['High'].loc[prev_idx]
                    stoch_lower = df['Stoch_K'].iloc[i] < df['Stoch_K'].loc[prev_idx]
                    
                    if price_higher and stoch_lower:
                        divergence.iloc[i] = True
        
        return divergence
    
    def generate_signals(self, df: pd.DataFrame, asset: str, granularity: str) -> pd.Series:
        """
        Generate divergence-based signals.
        Buy on bullish divergence + Stochastic cross up.
        Sell on bearish divergence + Stochastic cross down.
        """
        signals = pd.Series(0, index=df.index)
        
        # Detect divergences
        bullish_div = self._detect_bullish_divergence(df)
        bearish_div = self._detect_bearish_divergence(df)
        
        # Buy on bullish divergence + Stochastic cross up
        buy_condition = bullish_div & df['Stoch_Cross_Up']
        
        # Sell on bearish divergence + Stochastic cross down
        sell_condition = bearish_div & df['Stoch_Cross_Down']
        
        signals[buy_condition] = 1
        signals[sell_condition] = -1
        
        return signals
