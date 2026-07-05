"""
Range Bollinger Strategy
========================

Mean-reversion strategy using Bollinger Bands with RSI confirmation.

Entry Logic:
- BUY: Price touches or closes below lower Bollinger Band AND RSI < 30 (oversold)
- SELL: Price touches or closes above upper Bollinger Band AND RSI > 70 (overbought)

Exit Logic:
- Exit at middle band (mean reversion target)
- Or exit when price crosses opposite band

Multi-Timeframe Confluence:
- H4: Primary signals at band extremes
- H1: Fine-tune entry timing
- D1: Avoid counter-trend trades in strong trends
"""

import pandas as pd
import numpy as np
from typing import Dict, Any
from ..strategy_base import StrategyBase, StrategyConfig, SignalType
from ..indicators import bollinger_bands, rsi, atr


class RangeBollingerStrategy(StrategyBase):
    """
    Bollinger Band Mean Reversion Strategy.
    
    Parameters:
    - bb_period: Bollinger Band moving average period (default: 20)
    - bb_std: Standard deviation multiplier (default: 2.0)
    - rsi_period: RSI period (default: 14)
    - rsi_oversold: RSI oversold threshold (default: 30)
    - rsi_overbought: RSI overbought threshold (default: 70)
    - require_rsi: Whether to require RSI confirmation (default: True)
    """
    
    def __init__(self,
                 bb_period: int = 20,
                 bb_std: float = 2.0,
                 rsi_period: int = 14,
                 rsi_oversold: float = 30.0,
                 rsi_overbought: float = 70.0,
                 require_rsi: bool = True,
                 custom_config: Dict[str, Any] = None):
        """
        Initialize Range Bollinger Strategy.
        
        Args:
            bb_period: Bollinger Band period
            bb_std: Standard deviation multiplier
            rsi_period: RSI period
            rsi_oversold: RSI oversold threshold
            rsi_overbought: RSI overbought threshold
            require_rsi: Require RSI confirmation
            custom_config: Override default config
        """
        config = StrategyConfig(
            name="Range_Bollinger",
            description="Bollinger Band mean reversion with RSI confirmation",
            version="1.0.0",
            assets=["EUR_USD", "GBP_USD", "USD_JPY"],
            granularities=["H4", "H1"],
            use_multi_timeframe=True,
            primary_granularity="H4",
            confirmation_granularity="H1",
            macro_granularity="D1",
            stop_loss_atr=1.5,
            take_profit_atr=1.5,  # Tighter for mean reversion
            require_trend_alignment=False,  # Mean reversion can work against trend
            max_bars_hold=20  # Shorter hold for mean reversion
        )
        
        if custom_config:
            for key, value in custom_config.items():
                setattr(config, key, value)
        
        super().__init__(config)
        
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.require_rsi = require_rsi
    
    def calculate_indicators(self, df: pd.DataFrame, asset: str, granularity: str) -> pd.DataFrame:
        """
        Calculate Bollinger Bands and RSI indicators.
        
        Args:
            df: OHLCV DataFrame
            asset: Asset symbol
            granularity: Timeframe
            
        Returns:
            DataFrame with indicators
        """
        df = df.copy()
        
        # Adjust periods based on timeframe.
        # Keep H1 windows above practical floors so 2-sigma band touches remain reachable.
        if granularity == "H1":
            bb_period = max(10, self.bb_period // 2)
            rsi_period = max(7, self.rsi_period // 2)
        elif granularity == "D1":
            bb_period = self.bb_period
            rsi_period = self.rsi_period
        else:  # H4
            bb_period = self.bb_period
            rsi_period = self.rsi_period
        
        # Calculate Bollinger Bands
        upper, middle, lower = bollinger_bands(df['Close'], bb_period, self.bb_std)
        df['BB_Upper'] = upper
        df['BB_Middle'] = middle
        df['BB_Lower'] = lower
        df['BB_Width'] = (upper - lower) / middle  # Normalized bandwidth
        
        # Calculate RSI
        df['RSI'] = rsi(df['Close'], rsi_period)
        
        # Calculate ATR
        df['ATR'] = atr(df['High'], df['Low'], df['Close'], 14)
        
        # Price position within bands (0 = lower, 1 = upper)
        df['BB_Position'] = (df['Close'] - lower) / (upper - lower)
        
        # Band squeeze detection (low volatility)
        df['BB_Squeeze'] = df['BB_Width'] < df['BB_Width'].rolling(window=50).quantile(0.2)
        
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
        
        # Buy condition: Price at/below lower band AND RSI oversold
        buy_condition = df['Close'] <= df['BB_Lower']
        
        if self.require_rsi:
            buy_condition = buy_condition & (df['RSI'] < self.rsi_oversold)
        
        # Additional: Not in extreme squeeze (avoid low volatility)
        buy_condition = buy_condition & (~df['BB_Squeeze'])
        
        # Sell condition: Price at/above upper band AND RSI overbought
        sell_condition = df['Close'] >= df['BB_Upper']
        
        if self.require_rsi:
            sell_condition = sell_condition & (df['RSI'] > self.rsi_overbought)
        
        # Additional: Not in extreme squeeze
        sell_condition = sell_condition & (~df['BB_Squeeze'])
        
        # Require price to cross INTO the extreme zone (not just stay there)
        buy_condition = buy_condition & (df['Close'].shift(1) > df['BB_Lower'].shift(1))
        sell_condition = sell_condition & (df['Close'].shift(1) < df['BB_Upper'].shift(1))
        
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
            'H4': f'Close <= BB_Lower({self.bb_period}, {self.bb_std}) AND RSI < {self.rsi_oversold}',
            'H1': f'Price reaches BB extreme on H1 for timing',
            'D1': f'Avoid trades against strong D1 trend (optional)',
            'description': 'Mean reversion at Bollinger Band extremes with RSI exhaustion'
        }
    
    def get_exit_conditions(self) -> Dict[str, str]:
        """
        Get exit condition descriptions.
        
        Returns:
            Dictionary with exit conditions
        """
        return {
            'stop_loss': f'{self.config.stop_loss_atr} * ATR beyond extreme band',
            'take_profit': 'BB_Middle (mean reversion target)',
            'alternative_tp': 'Opposite Bollinger Band',
            'time_stop': f'Exit after {self.config.max_bars_hold} bars',
            'rsi_exit': 'Exit when RSI returns to neutral (40-60)'
        }
    
    def get_required_warmup_bars(self) -> int:
        """Get required warmup bars."""
        return max(self.bb_period, self.rsi_period) + 50


class RangeBollinger_H1_Only(RangeBollingerStrategy):
    """H1-only variant of Range Bollinger."""
    
    def __init__(self):
        # Use bb_period=20 so H1 scaling (max(10, // 2)) yields a viable 10-bar lookback
        # and rsi_period=14 so it scales to max(7, // 2) = 7
        super().__init__(bb_period=20, bb_std=2.0, rsi_period=14)
        self.config.name = "Range_Bollinger_H1"
        self.config.use_multi_timeframe = False
        self.config.primary_granularity = "H1"


class RangeBollinger_H4_Only(RangeBollingerStrategy):
    """H4-only variant of Range Bollinger."""
    
    def __init__(self):
        super().__init__(bb_period=20, bb_std=2.0, rsi_period=14)
        self.config.name = "Range_Bollinger_H4"
        self.config.use_multi_timeframe = False
        self.config.primary_granularity = "H4"


class RangeBollinger_Aggressive(RangeBollingerStrategy):
    """Aggressive variant with tighter bands and no RSI requirement."""
    
    def __init__(self):
        super().__init__(bb_period=20, bb_std=1.5, rsi_period=14, require_rsi=False)
        self.config.name = "Range_Bollinger_Aggressive"
        self.config.stop_loss_atr = 1.0
        self.config.take_profit_atr = 1.0
