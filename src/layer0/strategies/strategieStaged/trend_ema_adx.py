"""
Trend EMA ADX Strategy
======================

Trend-following strategy using EMA crossovers with ADX confirmation.

Entry Logic:
- BUY: Fast EMA crosses above Slow EMA AND ADX > threshold (trend strength)
- SELL: Fast EMA crosses below Slow EMA AND ADX > threshold

Multi-Timeframe Confluence:
- H4: Primary entry signals
- H1: Entry confirmation (EMA alignment)
- D1: Macro trend filter (optional)
"""

import pandas as pd
import numpy as np
from typing import Dict, Any
from ..strategy_base import StrategyBase, StrategyConfig, SignalType
from ..indicators import ema, adx, atr


class TrendEMAADXStrategy(StrategyBase):
    """
    EMA Crossover with ADX Filter Strategy.
    
    Parameters:
    - fast_ema: Fast EMA period (default: 20 for H4, 10 for H1)
    - slow_ema: Slow EMA period (default: 50 for H4, 20 for H1)
    - adx_period: ADX calculation period (default: 14)
    - adx_threshold: Minimum ADX for trend confirmation (default: 25)
    """
    
    def __init__(self, 
                 fast_ema: int = 20,
                 slow_ema: int = 50,
                 adx_period: int = 14,
                 adx_threshold: float = 25.0,
                 custom_config: Dict[str, Any] = None):
        """
        Initialize Trend EMA ADX Strategy.
        
        Args:
            fast_ema: Fast EMA period
            slow_ema: Slow EMA period
            adx_period: ADX period
            adx_threshold: ADX threshold for trend strength
            custom_config: Override default config
        """
        config = StrategyConfig(
            name="Trend_EMA_ADX",
            description="EMA crossover with ADX trend strength filter",
            version="1.0.0",
            assets=["EUR_USD", "GBP_USD", "USD_JPY"],
            granularities=["H4", "H1"],
            use_multi_timeframe=True,
            primary_granularity="H4",
            confirmation_granularity="H1",
            macro_granularity="D1",
            stop_loss_atr=1.5,
            take_profit_atr=2.5,
            require_trend_alignment=True
        )
        
        if custom_config:
            for key, value in custom_config.items():
                setattr(config, key, value)
        
        super().__init__(config)
        
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
    
    def calculate_indicators(self, df: pd.DataFrame, asset: str, granularity: str) -> pd.DataFrame:
        """
        Calculate EMA and ADX indicators.
        
        Args:
            df: OHLCV DataFrame
            asset: Asset symbol
            granularity: Timeframe
            
        Returns:
            DataFrame with indicators
        """
        df = df.copy()
        
        # Adjust EMA periods based on timeframe
        if granularity == "H1":
            fast = self.fast_ema // 2  # 10 for H1
            slow = self.slow_ema // 2  # 20 for H1
        elif granularity == "D1":
            fast = self.fast_ema * 2   # 40 for D1
            slow = self.slow_ema * 2   # 100 for D1
        else:  # H4
            fast = self.fast_ema
            slow = self.slow_ema
        
        # Calculate EMAs
        df[f'EMA_{fast}'] = ema(df['Close'], fast)
        df[f'EMA_{slow}'] = ema(df['Close'], slow)
        
        # Calculate ADX
        df['ADX'] = adx(df['High'], df['Low'], df['Close'], self.adx_period)
        
        # Calculate ATR for stop loss
        df['ATR'] = atr(df['High'], df['Low'], df['Close'], self.adx_period)
        
        # EMA alignment (trend direction)
        df['EMA_Alignment'] = np.where(
            df[f'EMA_{fast}'] > df[f'EMA_{slow}'], 1,
            np.where(df[f'EMA_{fast}'] < df[f'EMA_{slow}'], -1, 0)
        )
        
        # EMA crossover signals
        df['EMA_Cross'] = df['EMA_Alignment'].diff()
        
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
        
        # Get EMA column names
        if granularity == "H1":
            fast_col = f'EMA_{self.fast_ema // 2}'
        elif granularity == "D1":
            fast_col = f'EMA_{self.fast_ema * 2}'
        else:
            fast_col = f'EMA_{self.fast_ema}'
        
        # Buy signal: EMA cross up + ADX > threshold
        buy_condition = (
            (df['EMA_Cross'] == 2) &  # Crossed from -1 to 1 (or 0 to 1)
            (df['ADX'] > self.adx_threshold)
        )
        
        # Sell signal: EMA cross down + ADX > threshold
        sell_condition = (
            (df['EMA_Cross'] == -2) &  # Crossed from 1 to -1 (or 0 to -1)
            (df['ADX'] > self.adx_threshold)
        )
        
        # Alternative: Use alignment change
        buy_condition = (
            (df['EMA_Alignment'] == 1) &
            (df['EMA_Alignment'].shift(1) <= 0) &
            (df['ADX'] > self.adx_threshold)
        )
        
        sell_condition = (
            (df['EMA_Alignment'] == -1) &
            (df['EMA_Alignment'].shift(1) >= 0) &
            (df['ADX'] > self.adx_threshold)
        )
        
        signals[buy_condition] = 1
        signals[sell_condition] = -1
        
        return signals
    
    def get_entry_conditions(self) -> Dict[str, str]:
        """
        Get entry condition descriptions.
        
        Returns:
            Dictionary with entry conditions per timeframe
        """
        return {
            'H4': f'EMA({self.fast_ema}) crosses EMA({self.slow_ema}) AND ADX > {self.adx_threshold}',
            'H1': f'EMA({self.fast_ema // 2}) aligned with H4 direction (confirmation)',
            'D1': f'EMA({self.fast_ema * 2}) > EMA({self.slow_ema * 2}) for long bias (macro trend)',
            'description': 'Trend-following entry on EMA crossover with momentum confirmation'
        }
    
    def get_exit_conditions(self) -> Dict[str, str]:
        """
        Get exit condition descriptions.
        
        Returns:
            Dictionary with exit conditions
        """
        return {
            'stop_loss': f'{self.config.stop_loss_atr} * ATR({self.adx_period}) from entry',
            'take_profit': f'{self.config.take_profit_atr} * ATR({self.adx_period}) from entry',
            'trailing_stop': 'Optional: Trail below/above slow EMA',
            'time_stop': f'Exit after {self.config.max_bars_hold} bars',
            'trend_reversal': 'Exit on opposite EMA cross'
        }
    
    def get_required_warmup_bars(self) -> int:
        """Get required warmup bars."""
        return max(self.slow_ema, self.adx_period) + 50


class TrendEMAADX_H1_Only(TrendEMAADXStrategy):
    """H1-only variant of Trend EMA ADX."""
    
    def __init__(self):
        super().__init__(fast_ema=10, slow_ema=20)
        self.config.name = "Trend_EMA_ADX_H1"
        self.config.use_multi_timeframe = False
        self.config.primary_granularity = "H1"


class TrendEMAADX_H4_Only(TrendEMAADXStrategy):
    """H4-only variant of Trend EMA ADX."""
    
    def __init__(self):
        super().__init__(fast_ema=20, slow_ema=50)
        self.config.name = "Trend_EMA_ADX_H4"
        self.config.use_multi_timeframe = False
        self.config.primary_granularity = "H4"


class TrendEMAADX_MultiTF(TrendEMAADXStrategy):
    """Multi-timeframe variant with H4 entry and H1 confirmation."""
    
    def __init__(self):
        super().__init__(fast_ema=20, slow_ema=50)
        self.config.name = "Trend_EMA_ADX_MultiTF"
        self.config.use_multi_timeframe = True
        self.config.primary_granularity = "H4"
        self.config.confirmation_granularity = "H1"
        self.config.macro_granularity = "D1"
