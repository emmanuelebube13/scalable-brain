"""
Trend Donchian Strategy
=======================

Trend-following breakout strategy using Donchian Channels.

Entry Logic:
- BUY: Price breaks above upper Donchian band (highest high) + ADX > threshold
- SELL: Price breaks below lower Donchian band (lowest low) + ADX > threshold

The Donchian Channel captures the highest high and lowest low over a period,
making it effective for identifying breakouts and trend continuations.

Multi-Timeframe Confluence:
- H4: Primary breakout signals
- H1: Confirmation and timing
- D1: Macro trend alignment
"""

import pandas as pd
import numpy as np
from typing import Dict, Any
from ..strategy_base import StrategyBase, StrategyConfig, SignalType
from ..indicators import donchian_channel, adx, atr


class TrendDonchianStrategy(StrategyBase):
    """
    Donchian Channel Breakout Strategy.
    
    Parameters:
    - channel_period: Donchian channel period (default: 20)
    - adx_period: ADX calculation period (default: 14)
    - adx_threshold: Minimum ADX for trend confirmation (default: 25)
    - require_adx: Whether to require ADX confirmation (default: True)
    """
    
    def __init__(self,
                 channel_period: int = 20,
                 adx_period: int = 14,
                 adx_threshold: float = 25.0,
                 require_adx: bool = True,
                 custom_config: Dict[str, Any] = None):
        """
        Initialize Trend Donchian Strategy.
        
        Args:
            channel_period: Donchian channel period
            adx_period: ADX period
            adx_threshold: ADX threshold for trend strength
            require_adx: Require ADX confirmation
            custom_config: Override default config
        """
        config = StrategyConfig(
            name="Trend_Donchian",
            description="Donchian Channel breakout with ADX confirmation",
            version="1.0.0",
            assets=["EUR_USD", "GBP_USD", "USD_JPY"],
            granularities=["H4", "H1"],
            use_multi_timeframe=True,
            primary_granularity="H4",
            confirmation_granularity="H1",
            macro_granularity="D1",
            stop_loss_atr=1.5,
            take_profit_atr=3.0,  # Wider for trend following
            require_trend_alignment=True,
            max_bars_hold=50
        )
        
        if custom_config:
            for key, value in custom_config.items():
                setattr(config, key, value)
        
        super().__init__(config)
        
        self.channel_period = channel_period
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.require_adx = require_adx
    
    def calculate_indicators(self, df: pd.DataFrame, asset: str, granularity: str) -> pd.DataFrame:
        """
        Calculate Donchian Channel and ADX indicators.
        
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
            channel_period = self.channel_period // 2
        elif granularity == "D1":
            channel_period = self.channel_period * 2
        else:  # H4
            channel_period = self.channel_period
        
        # Calculate Donchian Channel
        upper, middle, lower = donchian_channel(df['High'], df['Low'], channel_period)
        df['DC_Upper'] = upper
        df['DC_Middle'] = middle
        df['DC_Lower'] = lower
        df['DC_Width'] = upper - lower
        
        # Calculate ADX
        df['ADX'] = adx(df['High'], df['Low'], df['Close'], self.adx_period)
        
        # Calculate ATR
        df['ATR'] = atr(df['High'], df['Low'], df['Close'], self.adx_period)
        
        # Channel squeeze detection (contraction)
        df['DC_Squeeze'] = df['DC_Width'] < df['DC_Width'].rolling(window=50).quantile(0.2)
        
        # Channel expansion (breakout potential)
        df['DC_Expansion'] = df['DC_Width'] > df['DC_Width'].rolling(window=50).quantile(0.8)
        
        # Breakout signals
        df['DC_Breakout_Up'] = (df['Close'] > df['DC_Upper'].shift(1))
        df['DC_Breakout_Down'] = (df['Close'] < df['DC_Lower'].shift(1))
        
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
        
        # Buy condition: Breakout above upper band
        buy_condition = df['DC_Breakout_Up']
        
        # ADX confirmation
        if self.require_adx:
            buy_condition = buy_condition & (df['ADX'] > self.adx_threshold)
        
        # Avoid entering during squeeze (wait for expansion)
        buy_condition = buy_condition & (~df['DC_Squeeze'])
        
        # Sell condition: Breakout below lower band
        sell_condition = df['DC_Breakout_Down']
        
        # ADX confirmation
        if self.require_adx:
            sell_condition = sell_condition & (df['ADX'] > self.adx_threshold)
        
        # Avoid entering during squeeze
        sell_condition = sell_condition & (~df['DC_Squeeze'])
        
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
            'H4': f'Close > DC_Upper({self.channel_period}) AND ADX > {self.adx_threshold}',
            'H1': f'Confirm breakout on H1',
            'D1': f'Align with D1 trend direction',
            'description': 'Breakout above/below Donchian Channel with trend strength'
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
            'trailing_stop': 'Trail below/above DC_Middle',
            'channel_exit': 'Exit on touch of opposite channel band',
            'time_stop': f'Exit after {self.config.max_bars_hold} bars'
        }
    
    def get_required_warmup_bars(self) -> int:
        """Get required warmup bars."""
        return max(self.channel_period, self.adx_period) + 50


class TrendDonchian_H1_Only(TrendDonchianStrategy):
    """H1-only variant of Trend Donchian."""
    
    def __init__(self):
        super().__init__(channel_period=10)
        self.config.name = "Trend_Donchian_H1"
        self.config.use_multi_timeframe = False
        self.config.primary_granularity = "H1"


class TrendDonchian_H4_Only(TrendDonchianStrategy):
    """H4-only variant of Trend Donchian."""
    
    def __init__(self):
        super().__init__(channel_period=20)
        self.config.name = "Trend_Donchian_H4"
        self.config.use_multi_timeframe = False
        self.config.primary_granularity = "H4"


class TrendDonchian_VCP(TrendDonchianStrategy):
    """
    Donchian variant focused on Volatility Contraction Pattern (VCP) breakouts.
    Enters only after a period of low volatility (squeeze) followed by expansion.
    """
    
    def __init__(self):
        super().__init__(channel_period=20)
        self.config.name = "Trend_Donchian_VCP"
        self.config.stop_loss_atr = 1.0  # Tighter stop for VCP
        self.config.take_profit_atr = 4.0  # Wider target for explosive moves
    
    def generate_signals(self, df: pd.DataFrame, asset: str, granularity: str) -> pd.Series:
        """
        Generate VCP-specific signals.
        
        Requires squeeze followed by breakout.
        """
        signals = pd.Series(0, index=df.index)
        
        # Buy: Squeeze in last 5 bars + breakout
        squeeze_recent = df['DC_Squeeze'].rolling(window=5).max().fillna(0).astype(bool)
        buy_condition = df['DC_Breakout_Up'] & squeeze_recent.shift(1)
        
        if self.require_adx:
            buy_condition = buy_condition & (df['ADX'] > self.adx_threshold)
        
        # Sell: Squeeze in last 5 bars + breakdown
        sell_condition = df['DC_Breakout_Down'] & squeeze_recent.shift(1)
        
        if self.require_adx:
            sell_condition = sell_condition & (df['ADX'] > self.adx_threshold)
        
        signals[buy_condition] = 1
        signals[sell_condition] = -1
        
        return signals
