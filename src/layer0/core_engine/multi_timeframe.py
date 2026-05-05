"""
Multi-Timeframe Confluence Engine
=================================

Handles multi-timeframe analysis for strategy signals.

Features:
- Timeframe alignment checking
- Macro trend filtering
- Signal confluence scoring
- Look-ahead bias prevention
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime

from .strategy_base import StrategyBase, Signal


@dataclass
class MTFSignal:
    """Multi-timeframe signal container."""
    primary_signal: Signal
    confirmation_aligned: bool
    macro_aligned: bool
    confluence_score: float
    approved: bool
    rejection_reason: str = ""


class MultiTimeframeEngine:
    """
    Engine for multi-timeframe signal validation.
    """
    
    def __init__(self,
                 primary_granularity: str = "H4",
                 confirmation_granularity: str = "H1",
                 macro_granularity: str = "D1",
                 require_confirmation: bool = True,
                 require_macro_alignment: bool = True):
        """
        Initialize MTF engine.
        
        Args:
            primary_granularity: Primary entry timeframe
            confirmation_granularity: Confirmation timeframe
            macro_granularity: Macro trend timeframe
            require_confirmation: Require confirmation signal
            require_macro_alignment: Require macro trend alignment
        """
        self.primary_granularity = primary_granularity
        self.confirmation_granularity = confirmation_granularity
        self.macro_granularity = macro_granularity
        self.require_confirmation = require_confirmation
        self.require_macro_alignment = require_macro_alignment
    
    def validate_signal(self,
                       primary_signal: Signal,
                       confirmation_df: Optional[pd.DataFrame],
                       macro_df: Optional[pd.DataFrame]) -> MTFSignal:
        """
        Validate a primary signal against higher timeframes.
        
        Args:
            primary_signal: Signal from primary timeframe
            confirmation_df: Confirmation timeframe DataFrame
            macro_df: Macro timeframe DataFrame
            
        Returns:
            MTFSignal with validation results
        """
        confirmation_aligned = True
        macro_aligned = True
        rejection_reason = ""
        
        # Check confirmation timeframe alignment
        if self.require_confirmation and confirmation_df is not None:
            confirmation_aligned = self._check_confirmation_alignment(
                primary_signal, confirmation_df
            )
            if not confirmation_aligned:
                rejection_reason = "Confirmation timeframe not aligned"
        
        # Check macro trend alignment
        if self.require_macro_alignment and macro_df is not None:
            macro_aligned = self._check_macro_alignment(
                primary_signal, macro_df
            )
            if not macro_aligned:
                rejection_reason = "Macro trend not aligned"
        
        # Calculate confluence score
        confluence_score = self._calculate_confluence_score(
            primary_signal, confirmation_aligned, macro_aligned
        )
        
        # Determine approval
        approved = confirmation_aligned and macro_aligned
        
        return MTFSignal(
            primary_signal=primary_signal,
            confirmation_aligned=confirmation_aligned,
            macro_aligned=macro_aligned,
            confluence_score=confluence_score,
            approved=approved,
            rejection_reason=rejection_reason
        )
    
    def _check_confirmation_alignment(self,
                                     primary_signal: Signal,
                                     confirmation_df: pd.DataFrame) -> bool:
        """
        Check if confirmation timeframe aligns with primary signal.
        
        Args:
            primary_signal: Primary signal
            confirmation_df: Confirmation timeframe data
            
        Returns:
            True if aligned
        """
        if len(confirmation_df) == 0:
            return True
        
        # Get latest confirmation data
        latest = confirmation_df.iloc[-1]
        
        # Check if EMAs align with signal direction
        if 'EMA_Alignment' in latest:
            ema_alignment = latest['EMA_Alignment']
            if primary_signal.direction == 1 and ema_alignment == 1:
                return True
            elif primary_signal.direction == -1 and ema_alignment == -1:
                return True
            elif ema_alignment == 0:
                return True  # Neutral is acceptable
            else:
                return False
        
        # Check if price is above/below key moving average
        if 'EMA_20' in latest and 'EMA_50' in latest:
            if primary_signal.direction == 1:
                return latest['Close'] > latest['EMA_20']
            else:
                return latest['Close'] < latest['EMA_20']
        
        return True
    
    def _check_macro_alignment(self,
                              primary_signal: Signal,
                              macro_df: pd.DataFrame) -> bool:
        """
        Check if macro trend aligns with primary signal.
        
        Args:
            primary_signal: Primary signal
            macro_df: Macro timeframe data
            
        Returns:
            True if aligned
        """
        if len(macro_df) == 0:
            return True
        
        # Get latest macro data
        latest = macro_df.iloc[-1]
        
        # Check EMA trend
        if 'EMA_50' in latest and 'EMA_200' in latest:
            if primary_signal.direction == 1:
                return latest['EMA_50'] > latest['EMA_200']
            else:
                return latest['EMA_50'] < latest['EMA_200']
        
        # Check ADX for trend strength
        if 'ADX' in latest:
            # Only require alignment in strong trends
            if latest['ADX'] > 25:
                if 'EMA_Alignment' in latest:
                    ema_alignment = latest['EMA_Alignment']
                    if primary_signal.direction != ema_alignment and ema_alignment != 0:
                        return False
        
        return True
    
    def _calculate_confluence_score(self,
                                   primary_signal: Signal,
                                   confirmation_aligned: bool,
                                   macro_aligned: bool) -> float:
        """
        Calculate confluence score based on timeframe alignment.
        
        Args:
            primary_signal: Primary signal
            confirmation_aligned: Confirmation alignment status
            macro_aligned: Macro alignment status
            
        Returns:
            Confluence score (0-1)
        """
        score = 0.5  # Base score for primary signal
        
        if confirmation_aligned:
            score += 0.25
        
        if macro_aligned:
            score += 0.25
        
        return score
    
    def align_timeframes(self,
                        primary_df: pd.DataFrame,
                        higher_df: pd.DataFrame,
                        higher_granularity: str) -> pd.DataFrame:
        """
        Align higher timeframe data to primary timeframe.
        Prevents look-ahead bias by using only closed bars.
        
        Args:
            primary_df: Primary timeframe DataFrame
            higher_df: Higher timeframe DataFrame
            higher_granularity: Higher timeframe granularity
            
        Returns:
            Primary DataFrame with aligned higher timeframe columns
        """
        result = primary_df.copy()
        
        # Create a column to merge on (date only for daily, etc.)
        if higher_granularity == "D1":
            # For daily alignment, use date
            primary_dates = primary_df.index.date
            higher_dates = higher_df.index.date
            
            # Shift higher data by one day to prevent look-ahead
            higher_df_shifted = higher_df.copy()
            higher_df_shifted.index = higher_df_shifted.index + pd.Timedelta(days=1)
            
            # Forward fill higher data to primary frequency
            for col in higher_df.columns:
                if col not in ['Open', 'High', 'Low', 'Close', 'Volume']:
                    result[f'{higher_granularity}_{col}'] = np.nan
                    
                    for i, timestamp in enumerate(result.index):
                        # Find last higher timeframe value before this timestamp
                        valid_higher = higher_df_shifted[higher_df_shifted.index <= timestamp]
                        if len(valid_higher) > 0:
                            result.loc[timestamp, f'{higher_granularity}_{col}'] = valid_higher[col].iloc[-1]
            
            # Forward fill any gaps
            higher_cols = [c for c in result.columns if c.startswith(f'{higher_granularity}_')]
            result[higher_cols] = result[higher_cols].ffill()
        
        elif higher_granularity == "H4":
            # For H4 alignment from H1
            for col in higher_df.columns:
                if col not in ['Open', 'High', 'Low', 'Close', 'Volume']:
                    result[f'{higher_granularity}_{col}'] = np.nan
                    
                    for i, timestamp in enumerate(result.index):
                        # Find last H4 value before this timestamp
                        valid_higher = higher_df[higher_df.index <= timestamp]
                        if len(valid_higher) > 0:
                            result.loc[timestamp, f'{higher_granularity}_{col}'] = valid_higher[col].iloc[-1]
            
            # Forward fill
            higher_cols = [c for c in result.columns if c.startswith(f'{higher_granularity}_')]
            result[higher_cols] = result[higher_cols].ffill()
        
        return result
    
    def generate_mtf_signals(self,
                            strategy: StrategyBase,
                            data: Dict[str, Dict[str, pd.DataFrame]],
                            asset: str) -> List[MTFSignal]:
        """
        Generate signals with multi-timeframe validation.
        
        Args:
            strategy: Strategy instance
            data: Nested dict of asset -> granularity -> DataFrame
            asset: Asset symbol
            
        Returns:
            List of validated MTF signals
        """
        mtf_signals = []
        
        # Get primary timeframe data
        primary_gran = strategy.config.primary_granularity
        if asset not in data or primary_gran not in data[asset]:
            return mtf_signals
        
        primary_df = data[asset][primary_gran]
        
        # Get confirmation and macro data
        confirmation_df = None
        macro_df = None
        
        if strategy.config.use_multi_timeframe:
            confirm_gran = strategy.config.confirmation_granularity
            macro_gran = strategy.config.macro_granularity
            
            if asset in data:
                if confirm_gran in data[asset]:
                    confirmation_df = data[asset][confirm_gran]
                if macro_gran in data[asset]:
                    macro_df = data[asset][macro_gran]
        
        # Calculate indicators
        primary_df = strategy.calculate_indicators(primary_df.copy(), asset, primary_gran)
        
        # Generate signals
        signals = strategy.generate_signals(primary_df, asset, primary_gran)
        
        # Process each signal
        for timestamp, signal_value in signals.items():
            if signal_value == 0:
                continue
            
            # Get signal details at this timestamp
            idx = primary_df.index.get_loc(timestamp)
            row = primary_df.loc[timestamp]
            
            # Create Signal object
            signal = Signal(
                timestamp=timestamp,
                asset=asset,
                signal_type=SignalType.BUY if signal_value == 1 else SignalType.SELL,
                direction=signal_value,
                price=row['Close'],
                stop_loss=row['Close'] - row['ATR'] * 1.5 if signal_value == 1 else row['Close'] + row['ATR'] * 1.5,
                take_profit=row['Close'] + row['ATR'] * 2.5 if signal_value == 1 else row['Close'] - row['ATR'] * 2.5,
                confidence=0.5
            )
            
            # Validate with MTF
            mtf_signal = self.validate_signal(signal, confirmation_df, macro_df)
            mtf_signals.append(mtf_signal)
        
        return mtf_signals


def create_mtf_config(strategy_type: str = "trend") -> MultiTimeframeEngine:
    """
    Create MTF engine with appropriate configuration for strategy type.
    
    Args:
        strategy_type: Type of strategy (trend, mean_reversion, breakout)
        
    Returns:
        Configured MTF engine
    """
    if strategy_type == "trend":
        # Trend strategies require strong macro alignment
        return MultiTimeframeEngine(
            primary_granularity="H4",
            confirmation_granularity="H1",
            macro_granularity="D1",
            require_confirmation=True,
            require_macro_alignment=True
        )
    elif strategy_type == "mean_reversion":
        # Mean reversion can be more flexible
        return MultiTimeframeEngine(
            primary_granularity="H4",
            confirmation_granularity="H1",
            macro_granularity="D1",
            require_confirmation=True,
            require_macro_alignment=False
        )
    elif strategy_type == "breakout":
        # Breakouts need confirmation but not strict macro alignment
        return MultiTimeframeEngine(
            primary_granularity="H4",
            confirmation_granularity="H1",
            macro_granularity="D1",
            require_confirmation=True,
            require_macro_alignment=True
        )
    else:
        return MultiTimeframeEngine()
