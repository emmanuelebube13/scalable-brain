"""
VCP Breakout Strategy
=====================

Volatility Contraction Pattern (VCP) Breakout Strategy.
Based on Mark Minervini's VCP concept adapted for forex.

The VCP pattern consists of:
1. A prior uptrend (or downtrend for short)
2. A period of consolidation/volatility contraction
3. A breakout from the contraction with expanding volume/volatility

Entry Logic:
- BUY: Price breaks above contraction range after volatility squeeze
- SELL: Price breaks below contraction range after volatility squeeze

Key Components:
- Volatility Contraction Index (VCI) to identify squeezes
- Range contraction detection
- Breakout confirmation with momentum

Multi-Timeframe Confluence:
- H4: Primary VCP detection
- H1: Entry timing
- D1: Trend alignment
"""

import pandas as pd
import numpy as np
from typing import Dict, Any
from ..strategy_base import StrategyBase, StrategyConfig, SignalType
from ..indicators import atr, donchian_channel, adx, ema


class VCPBreakoutStrategy(StrategyBase):
    """
    Volatility Contraction Pattern Breakout Strategy.
    
    Parameters:
    - vcp_period: Lookback for VCP detection (default: 20)
    - contraction_threshold: VCI threshold for squeeze (default: 0.5)
    - adx_period: ADX period (default: 14)
    - adx_threshold: Minimum ADX for breakout (default: 20)
    - min_contraction_bars: Minimum bars in contraction (default: 5)
    """
    
    def __init__(self,
                 vcp_period: int = 20,
                 contraction_threshold: float = 0.5,
                 adx_period: int = 14,
                 adx_threshold: float = 20.0,
                 min_contraction_bars: int = 5,
                 custom_config: Dict[str, Any] = None):
        """
        Initialize VCP Breakout Strategy.
        
        Args:
            vcp_period: VCP detection period
            contraction_threshold: VCI threshold for squeeze
            adx_period: ADX period
            adx_threshold: ADX threshold for breakout
            min_contraction_bars: Minimum bars in contraction phase
            custom_config: Override default config
        """
        config = StrategyConfig(
            name="VCP_Breakout",
            description="Volatility Contraction Pattern breakout",
            version="1.0.0",
            assets=["EUR_USD", "GBP_USD", "USD_JPY"],
            granularities=["H4", "H1"],
            use_multi_timeframe=True,
            primary_granularity="H4",
            confirmation_granularity="H1",
            macro_granularity="D1",
            stop_loss_atr=1.0,  # Tight stop for VCP
            take_profit_atr=4.0,  # Wide target for explosive moves
            require_trend_alignment=True,
            max_bars_hold=30
        )
        
        if custom_config:
            for key, value in custom_config.items():
                setattr(config, key, value)
        
        super().__init__(config)
        
        self.vcp_period = vcp_period
        self.contraction_threshold = contraction_threshold
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.min_contraction_bars = min_contraction_bars
    
    def calculate_indicators(self, df: pd.DataFrame, asset: str, granularity: str) -> pd.DataFrame:
        """
        Calculate VCP indicators.
        
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
            vcp_period = self.vcp_period // 2
        elif granularity == "D1":
            vcp_period = self.vcp_period * 2
        else:  # H4
            vcp_period = self.vcp_period
        
        # Calculate ATR
        df['ATR'] = atr(df['High'], df['Low'], df['Close'], self.adx_period)
        
        # Calculate normalized ATR (ATR as % of price)
        df['ATR_Pct'] = df['ATR'] / df['Close']
        
        # Volatility Contraction Index (VCI)
        # Current ATR vs historical average
        df['ATR_MA'] = df['ATR_Pct'].rolling(window=vcp_period).mean()
        df['VCI'] = df['ATR_Pct'] / df['ATR_MA']
        
        # Volatility squeeze detection
        df['Squeeze'] = (df['VCI'] < self.contraction_threshold).fillna(False).astype(bool)
        
        # Contraction duration
        df['Squeeze_Duration'] = df['Squeeze'].groupby(
            (df['Squeeze'] != df['Squeeze'].shift()).cumsum()
        ).cumcount() + 1
        df['Squeeze_Duration'] = df['Squeeze_Duration'].where(df['Squeeze'], 0)
        
        # Donchian Channel for range measurement
        upper, middle, lower = donchian_channel(df['High'], df['Low'], vcp_period)
        df['DC_Upper'] = upper
        df['DC_Lower'] = lower
        df['DC_Range'] = upper - lower
        df['DC_Range_Pct'] = df['DC_Range'] / df['Close']
        
        # Range contraction
        df['Range_MA'] = df['DC_Range_Pct'].rolling(window=vcp_period).mean()
        df['Range_Contraction'] = (
            df['DC_Range_Pct'] < (df['Range_MA'] * self.contraction_threshold)
        ).fillna(False).astype(bool)
        
        # Combined squeeze signal
        df['Full_Squeeze'] = (
            df['Squeeze'].fillna(False).astype(bool)
            & df['Range_Contraction'].fillna(False).astype(bool)
        ).astype(bool)
        
        # ADX for trend strength
        df['ADX'] = adx(df['High'], df['Low'], df['Close'], self.adx_period)
        
        # EMA for trend direction
        df['EMA_20'] = ema(df['Close'], 20)
        df['EMA_50'] = ema(df['Close'], 50)
        df['Trend_Up'] = (df['EMA_20'] > df['EMA_50']).fillna(False).astype(bool)
        
        # Breakout signals
        df['Breakout_Up'] = (df['Close'] > df['DC_Upper'].shift(1)).fillna(False).astype(bool)
        df['Breakout_Down'] = (df['Close'] < df['DC_Lower'].shift(1)).fillna(False).astype(bool)
        
        # Recent squeeze (within last N bars)
        df['Recent_Squeeze'] = (
            df['Full_Squeeze']
            .fillna(False)
            .astype(bool)
            .rolling(window=self.min_contraction_bars + 3)
            .max()
            .shift(1)
            .fillna(False)
            .astype(bool)
        )
        
        return df
    
    def generate_signals(self, df: pd.DataFrame, asset: str, granularity: str) -> pd.Series:
        """
        Generate VCP breakout signals.
        
        Args:
            df: DataFrame with indicators
            asset: Asset symbol
            granularity: Timeframe
            
        Returns:
            Series with signals (1=buy, -1=sell, 0=hold)
        """
        signals = pd.Series(0, index=df.index)
        
        # Buy: Breakout up after squeeze + trend alignment
        buy_condition = (
            df['Breakout_Up'].fillna(False).astype(bool) &
            df['Recent_Squeeze'].fillna(False).astype(bool) &
            df['Trend_Up'].fillna(False).astype(bool) &
            (df['ADX'] > self.adx_threshold).fillna(False).astype(bool)
        )
        
        # Sell: Breakout down after squeeze + trend alignment (for shorts)
        sell_condition = (
            df['Breakout_Down'].fillna(False).astype(bool) &
            df['Recent_Squeeze'].fillna(False).astype(bool) &
            (~df['Trend_Up'].fillna(False).astype(bool)) &
            (df['ADX'] > self.adx_threshold).fillna(False).astype(bool)
        )
        
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
            'H4': f'Breakout after VCI < {self.contraction_threshold} squeeze',
            'H1': f'Confirm breakout momentum on H1',
            'D1': f'Align with D1 trend (EMA direction)',
            'description': 'Volatility Contraction Pattern breakout with trend alignment'
        }
    
    def get_exit_conditions(self) -> Dict[str, str]:
        """
        Get exit condition descriptions.
        
        Returns:
            Dictionary with exit conditions
        """
        return {
            'stop_loss': f'{self.config.stop_loss_atr} * ATR below entry (tight)',
            'take_profit': f'{self.config.take_profit_atr} * ATR (wide for explosive moves)',
            'trailing_stop': 'Trail below swing lows / above swing highs',
            'volatility_expansion': 'Exit if volatility contracts again (move complete)',
            'time_stop': f'Exit after {self.config.max_bars_hold} bars'
        }
    
    def get_required_warmup_bars(self) -> int:
        """Get required warmup bars."""
        return max(self.vcp_period, 50) + 20


class VCPBreakout_H1_Only(VCPBreakoutStrategy):
    """H1-only variant of VCP Breakout."""
    
    def __init__(self):
        super().__init__(vcp_period=10)
        self.config.name = "VCP_Breakout_H1"
        self.config.use_multi_timeframe = False
        self.config.primary_granularity = "H1"


class VCPBreakout_H4_Only(VCPBreakoutStrategy):
    """H4-only variant of VCP Breakout."""
    
    def __init__(self):
        super().__init__(vcp_period=20)
        self.config.name = "VCP_Breakout_H4"
        self.config.use_multi_timeframe = False
        self.config.primary_granularity = "H4"


class VCPBreakout_Aggressive(VCPBreakoutStrategy):
    """
    Aggressive VCP variant with earlier entry.
    Enters on first sign of expansion rather than full breakout.
    """
    
    def __init__(self):
        super().__init__(vcp_period=15, contraction_threshold=0.6)
        self.config.name = "VCP_Breakout_Aggressive"
        self.config.stop_loss_atr = 0.8
        self.config.take_profit_atr = 3.0
    
    def generate_signals(self, df: pd.DataFrame, asset: str, granularity: str) -> pd.Series:
        """
        Generate aggressive VCP signals.
        """
        signals = pd.Series(0, index=df.index)
        
        # Buy: Price moving up after squeeze (before full breakout)
        buy_condition = (
            df['Recent_Squeeze'].fillna(False).astype(bool) &
            df['Trend_Up'].fillna(False).astype(bool) &
            (df['Close'] > df['EMA_20']).fillna(False).astype(bool) &
            (df['Close'].shift(1) <= df['EMA_20'].shift(1)).fillna(False).astype(bool) &
            (df['ADX'] > self.adx_threshold).fillna(False).astype(bool)
        )
        
        # Sell: Price moving down after squeeze
        sell_condition = (
            df['Recent_Squeeze'].fillna(False).astype(bool) &
            (~df['Trend_Up'].fillna(False).astype(bool)) &
            (df['Close'] < df['EMA_20']).fillna(False).astype(bool) &
            (df['Close'].shift(1) >= df['EMA_20'].shift(1)).fillna(False).astype(bool) &
            (df['ADX'] > self.adx_threshold).fillna(False).astype(bool)
        )
        
        signals[buy_condition] = 1
        signals[sell_condition] = -1
        
        return signals
