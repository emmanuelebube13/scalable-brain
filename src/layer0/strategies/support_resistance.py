"""
Support Resistance Strategy
===========================

Price action strategy based on support and resistance levels.

Entry Logic:
- BUY: Price bounces off support level with confirmation candle
- SELL: Price rejects at resistance level with confirmation candle

Support/Resistance Detection:
- Uses swing highs/lows to identify key levels
- Levels are stronger with multiple touches
- Recent levels are more relevant

Multi-Timeframe Confluence:
- H4: Primary S/R levels
- H1: Entry timing and confirmation
- D1: Major structural levels
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple
from ..strategy_base import StrategyBase, StrategyConfig, SignalType
from ..indicators import atr, detect_swing_points


class SupportResistanceStrategy(StrategyBase):
    """
    Support/Resistance Price Action Strategy.
    
    Parameters:
    - swing_period: Period for swing detection (default: 5)
    - level_lookback: Lookback for S/R level building (default: 50)
    - touch_threshold: Price proximity to level (default: 0.001 = 10 pips)
    - min_touches: Minimum touches to validate level (default: 2)
    """
    
    def __init__(self,
                 swing_period: int = 5,
                 level_lookback: int = 50,
                 touch_threshold: float = 0.001,
                 min_touches: int = 2,
                 custom_config: Dict[str, Any] = None):
        """
        Initialize Support/Resistance Strategy.
        
        Args:
            swing_period: Swing detection period
            level_lookback: Lookback for level building
            touch_threshold: Proximity threshold as price percentage
            min_touches: Minimum touches for valid level
            custom_config: Override default config
        """
        config = StrategyConfig(
            name="Support_Resistance",
            description="Price action at support and resistance levels",
            version="1.0.0",
            assets=["EUR_USD", "GBP_USD", "USD_JPY"],
            granularities=["H4", "H1"],
            use_multi_timeframe=True,
            primary_granularity="H4",
            confirmation_granularity="H1",
            macro_granularity="D1",
            stop_loss_atr=1.0,  # Tighter stops for S/R
            take_profit_atr=2.0,
            require_trend_alignment=False,
            max_bars_hold=20
        )
        
        if custom_config:
            for key, value in custom_config.items():
                setattr(config, key, value)
        
        super().__init__(config)
        
        self.swing_period = swing_period
        self.level_lookback = level_lookback
        self.touch_threshold = touch_threshold
        self.min_touches = min_touches
    
    def _find_support_resistance_levels(self, df: pd.DataFrame) -> Tuple[List[float], List[float]]:
        """
        Find support and resistance levels from swing points.
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            Tuple of (support_levels, resistance_levels)
        """
        # Detect swing points
        swing_highs, swing_lows = detect_swing_points(df['High'], df['Low'], self.swing_period)
        
        # Get swing high/low prices
        resistance_prices = df.loc[swing_highs, 'High'].values
        support_prices = df.loc[swing_lows, 'Low'].values
        
        # Cluster nearby levels (within touch_threshold)
        def cluster_levels(levels: np.ndarray, threshold: float) -> List[float]:
            if len(levels) == 0:
                return []
            
            levels = np.sort(levels)
            clusters = []
            current_cluster = [levels[0]]
            
            for price in levels[1:]:
                if abs(price - np.mean(current_cluster)) / np.mean(current_cluster) <= threshold:
                    current_cluster.append(price)
                else:
                    clusters.append(np.mean(current_cluster))
                    current_cluster = [price]
            
            if current_cluster:
                clusters.append(np.mean(current_cluster))
            
            return clusters
        
        support_levels = cluster_levels(support_prices, self.touch_threshold)
        resistance_levels = cluster_levels(resistance_prices, self.touch_threshold)
        
        return support_levels, resistance_levels
    
    def _count_level_touches(self, df: pd.DataFrame, level: float, 
                            is_support: bool) -> int:
        """
        Count how many times price has touched a level.
        
        Args:
            df: DataFrame
            level: Price level
            is_support: True for support, False for resistance
            
        Returns:
            Number of touches
        """
        threshold = level * self.touch_threshold
        
        if is_support:
            touches = (df['Low'] >= level - threshold) & (df['Low'] <= level + threshold)
        else:
            touches = (df['High'] >= level - threshold) & (df['High'] <= level + threshold)
        
        return touches.sum()
    
    def calculate_indicators(self, df: pd.DataFrame, asset: str, granularity: str) -> pd.DataFrame:
        """
        Calculate support/resistance levels and related indicators.
        
        Args:
            df: OHLCV DataFrame
            asset: Asset symbol
            granularity: Timeframe
            
        Returns:
            DataFrame with indicators
        """
        df = df.copy()
        
        # Adjust parameters based on timeframe
        if granularity == "H1":
            swing_period = self.swing_period // 2
            level_lookback = self.level_lookback // 2
        elif granularity == "D1":
            swing_period = self.swing_period * 2
            level_lookback = self.level_lookback * 2
        else:  # H4
            swing_period = self.swing_period
            level_lookback = self.level_lookback
        
        # Calculate ATR
        df['ATR'] = atr(df['High'], df['Low'], df['Close'], 14)
        
        # Detect swing points
        swing_highs, swing_lows = detect_swing_points(df['High'], df['Low'], swing_period)
        df['Swing_High'] = swing_highs
        df['Swing_Low'] = swing_lows
        
        # Find recent S/R levels (rolling window)
        df['Nearest_Support'] = np.nan
        df['Nearest_Resistance'] = np.nan
        df['Support_Strength'] = 0
        df['Resistance_Strength'] = 0
        
        for i in range(level_lookback, len(df)):
            window = df.iloc[i-level_lookback:i]
            
            # Find levels in window
            support_levels, resistance_levels = self._find_support_resistance_levels(window)
            
            current_price = df['Close'].iloc[i]
            
            # Find nearest support below price
            supports_below = [s for s in support_levels if s < current_price]
            if supports_below:
                nearest_support = max(supports_below)
                df.loc[df.index[i], 'Nearest_Support'] = nearest_support
                df.loc[df.index[i], 'Support_Strength'] = self._count_level_touches(
                    window, nearest_support, True
                )
            
            # Find nearest resistance above price
            resistances_above = [r for r in resistance_levels if r > current_price]
            if resistances_above:
                nearest_resistance = min(resistances_above)
                df.loc[df.index[i], 'Nearest_Resistance'] = nearest_resistance
                df.loc[df.index[i], 'Resistance_Strength'] = self._count_level_touches(
                    window, nearest_resistance, False
                )
        
        # Distance to nearest levels (in ATR multiples)
        df['Dist_To_Support'] = (df['Close'] - df['Nearest_Support']) / df['ATR']
        df['Dist_To_Resistance'] = (df['Nearest_Resistance'] - df['Close']) / df['ATR']
        
        # Price at level (within touch threshold)
        touch_threshold_atr = 0.5  # Within 0.5 ATR
        df['At_Support'] = df['Dist_To_Support'] <= touch_threshold_atr
        df['At_Resistance'] = df['Dist_To_Resistance'] <= touch_threshold_atr
        
        # Bounce signals (price touched level and reversed)
        df['Bounce_Up'] = df['At_Support'] & (df['Close'] > df['Open'])
        df['Bounce_Down'] = df['At_Resistance'] & (df['Close'] < df['Open'])
        
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
        
        # Buy: Bounce off support with strength
        buy_condition = (
            df['Bounce_Up'] &
            (df['Support_Strength'] >= self.min_touches) &
            (df['Dist_To_Resistance'] > 1.0)  # Room to move up
        )
        
        # Sell: Rejection at resistance with strength
        sell_condition = (
            df['Bounce_Down'] &
            (df['Resistance_Strength'] >= self.min_touches) &
            (df['Dist_To_Support'] > 1.0)  # Room to move down
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
            'H4': f'Price at support ({self.min_touches}+ touches) with bullish candle',
            'H1': f'Confirm bounce on H1',
            'D1': f'Consider major D1 S/R levels',
            'description': 'Price action bounce at established support/resistance'
        }
    
    def get_exit_conditions(self) -> Dict[str, str]:
        """
        Get exit condition descriptions.
        
        Returns:
            Dictionary with exit conditions
        """
        return {
            'stop_loss': 'Below support / Above resistance (level invalidation)',
            'take_profit': 'Next S/R level or 2x risk',
            'level_break': 'Exit if level is broken',
            'time_stop': f'Exit after {self.config.max_bars_hold} bars'
        }
    
    def get_required_warmup_bars(self) -> int:
        """Get required warmup bars."""
        return self.level_lookback + 50


class SupportResistance_H1_Only(SupportResistanceStrategy):
    """H1-only variant of Support/Resistance."""
    
    def __init__(self):
        super().__init__(swing_period=3, level_lookback=30)
        self.config.name = "Support_Resistance_H1"
        self.config.use_multi_timeframe = False
        self.config.primary_granularity = "H1"


class SupportResistance_H4_Only(SupportResistanceStrategy):
    """H4-only variant of Support/Resistance."""
    
    def __init__(self):
        super().__init__(swing_period=5, level_lookback=50)
        self.config.name = "Support_Resistance_H4"
        self.config.use_multi_timeframe = False
        self.config.primary_granularity = "H4"


class SupportResistance_Breakout(SupportResistanceStrategy):
    """
    S/R Breakout variant - enters on level break rather than bounce.
    """
    
    def __init__(self):
        super().__init__(swing_period=5, level_lookback=50)
        self.config.name = "Support_Resistance_Breakout"
        self.config.stop_loss_atr = 1.0
        self.config.take_profit_atr = 3.0
    
    def generate_signals(self, df: pd.DataFrame, asset: str, granularity: str) -> pd.Series:
        """
        Generate breakout signals.
        """
        signals = pd.Series(0, index=df.index)
        
        # Buy breakout above resistance
        buy_condition = (
            (df['Close'] > df['Nearest_Resistance'].shift(1)) &
            (df['Close'].shift(1) <= df['Nearest_Resistance'].shift(1)) &
            (df['Resistance_Strength'] >= self.min_touches)
        )
        
        # Sell breakdown below support
        sell_condition = (
            (df['Close'] < df['Nearest_Support'].shift(1)) &
            (df['Close'].shift(1) >= df['Nearest_Support'].shift(1)) &
            (df['Support_Strength'] >= self.min_touches)
        )
        
        signals[buy_condition] = 1
        signals[sell_condition] = -1
        
        return signals
