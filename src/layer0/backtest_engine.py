"""
Backtest Engine
===============

Vectorized backtesting engine for strategy qualification.

Features:
- Event-driven trade simulation
- ATR-based dynamic stop losses and take profits
- Multi-timeframe confluence support
- Commission and slippage modeling
- Position tracking and trade history
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import warnings

from .strategy_base import StrategyBase, Trade, SignalType, StrategyConfig
from .indicators import calculate_pips, get_pip_value


class ExitReason(Enum):
    """Trade exit reasons."""
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TIME_STOP = "time_stop"
    SIGNAL_REVERSE = "signal_reverse"
    END_OF_DATA = "end_of_data"


@dataclass
class BacktestConfig:
    """Backtest configuration."""
    initial_capital: float = 100000.0
    risk_per_trade: float = 0.01  # 1% risk per trade
    commission_per_trade: float = 0.0  # Commission in account currency
    slippage_pips: float = 0.5  # Slippage in pips
    spread_pips: float = 1.0  # Average spread in pips
    allow_pyramiding: bool = False
    max_positions: int = 1
    use_fractional_positions: bool = True


@dataclass
class BacktestResult:
    """Backtest result container."""
    strategy_name: str
    asset: str
    granularity: str
    trades: List[Trade] = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=lambda: pd.Series())
    
    # Performance metrics (calculated by analyzer)
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    expectancy_r: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    max_consecutive_losses: int = 0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    total_return: float = 0.0
    annualized_return: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            'strategy_name': self.strategy_name,
            'asset': self.asset,
            'granularity': self.granularity,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
            'expectancy': self.expectancy,
            'expectancy_r': self.expectancy_r,
            'max_drawdown': self.max_drawdown,
            'max_drawdown_pct': self.max_drawdown_pct,
            'max_consecutive_losses': self.max_consecutive_losses,
            'sharpe_ratio': self.sharpe_ratio,
            'sortino_ratio': self.sortino_ratio,
            'total_return': self.total_return,
            'annualized_return': self.annualized_return,
        }


class BacktestEngine:
    """
    Vectorized backtesting engine for trading strategies.
    """
    
    def __init__(self, config: BacktestConfig = None):
        """
        Initialize backtest engine.
        
        Args:
            config: Backtest configuration
        """
        self.config = config or BacktestConfig()
        self.trades: List[Trade] = []
        self.equity_curve: pd.Series = pd.Series()
    
    def _pnl_to_dollars(self, price_diff: float, asset: str) -> float:
        """Convert raw price difference to dollar PnL (standard lot)."""
        pips = calculate_pips(price_diff, asset)
        # Standard lot ≈ $10 per pip for most FX pairs
        return pips * 10.0
    
    def _apply_friction(self, dollar_pnl: float) -> float:
        """Subtract spread and commission from dollar PnL."""
        spread_cost = self.config.spread_pips * 10.0
        commission = self.config.commission_per_trade
        return dollar_pnl - spread_cost - commission
        
    def run_backtest(self,
                     strategy: StrategyBase,
                     df: pd.DataFrame,
                     asset: str,
                     granularity: str,
                     warmup_bars: int = 200) -> BacktestResult:
        """
        Run a backtest for a single strategy on single asset/timeframe.
        
        Args:
            strategy: Strategy instance
            df: OHLCV DataFrame
            asset: Asset symbol
            granularity: Timeframe
            warmup_bars: Bars to skip for indicator warmup
            
        Returns:
            BacktestResult with trades and equity curve
        """
        # Calculate indicators
        df = strategy.calculate_indicators(df.copy(), asset, granularity)
        
        # Generate signals
        signals = strategy.generate_signals(df, asset, granularity)
        
        # Skip warmup period
        df = df.iloc[warmup_bars:].copy()
        signals = signals.iloc[warmup_bars:].copy()
        
        if len(df) == 0:
            warnings.warn(f"No data after warmup for {asset} {granularity}")
            return BacktestResult(
                strategy_name=strategy.config.name,
                asset=asset,
                granularity=granularity
            )
        
        # Run simulation
        trades = self._simulate_trades(
            strategy, df, signals, asset, granularity
        )
        
        # Build equity curve
        equity_curve = self._build_equity_curve(trades, df)
        
        result = BacktestResult(
            strategy_name=strategy.config.name,
            asset=asset,
            granularity=granularity,
            trades=trades,
            equity_curve=equity_curve
        )
        
        return result
    
    def _simulate_trades(self,
                        strategy: StrategyBase,
                        df: pd.DataFrame,
                        signals: pd.Series,
                        asset: str,
                        granularity: str) -> List[Trade]:
        """
        Simulate trades based on signals.
        
        Args:
            strategy: Strategy instance
            df: DataFrame with indicators
            signals: Signal series
            asset: Asset symbol
            granularity: Timeframe
            
        Returns:
            List of trades
        """
        trades = []
        current_position: Optional[Trade] = None
        
        for i in range(len(df)):
            timestamp = df.index[i]
            signal = signals.iloc[i]
            
            # Check for position exit
            if current_position is not None:
                exit_trade = self._check_exit(
                    current_position, df, i, timestamp, signal, asset, strategy
                )
                
                if exit_trade:
                    trades.append(exit_trade)
                    current_position = None
            
            # Check for position entry
            if current_position is None and signal != 0:
                # Check volatility filter
                if strategy.config.volatility_filter:
                    if not strategy.check_volatility_filter(df.iloc[max(0, i-100):i+1]):
                        continue
                
                # Calculate entry, stop, and target
                entry_price = df['Close'].iloc[i]
                
                # Apply slippage
                slippage = self.config.slippage_pips * get_pip_value(asset)
                if signal == 1:  # Buy
                    entry_price += slippage
                else:  # Sell
                    entry_price -= slippage
                
                # Calculate stop loss and take profit
                # Pass bounded window for performance (base methods only need last 100 rows)
                window_df = df.iloc[max(0, i-100):i+1]
                stop_loss = strategy.calculate_stop_loss(
                    window_df, signal, entry_price, asset
                )
                take_profit = strategy.calculate_take_profit(
                    window_df, signal, entry_price, asset
                )
                
                # Create trade
                trade = Trade(
                    entry_time=timestamp,
                    entry_price=entry_price,
                    direction=signal,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    asset=asset,
                    strategy=strategy.config.name,
                    granularity=granularity,
                    size=1.0
                )
                
                current_position = trade
        
        # Close any open position at end of data
        if current_position is not None and current_position.exit_time is None:
            last_idx = len(df) - 1
            last_timestamp = df.index[last_idx]
            last_price = df['Close'].iloc[last_idx]
            
            current_position.exit_time = last_timestamp
            current_position.exit_price = last_price
            current_position.exit_reason = ExitReason.END_OF_DATA.value
            
            # Calculate P&L
            price_diff = last_price - current_position.entry_price
            if current_position.direction == -1:
                price_diff = -price_diff
            
            current_position.pnl = self._apply_friction(self._pnl_to_dollars(price_diff, asset))
            current_position.pnl_pips = calculate_pips(price_diff, asset)
            
            risk = abs(current_position.entry_price - current_position.stop_loss)
            if risk > 0:
                current_position.r_multiple = price_diff / risk

            trades.append(current_position)
        
        return trades
    
    def _check_exit(self,
                   trade: Trade,
                   df: pd.DataFrame,
                   current_idx: int,
                   timestamp: datetime,
                   current_signal: int,
                   asset: str,
                   strategy: StrategyBase) -> Optional[Trade]:
        """
        Check if a trade should be exited.
        
        Args:
            trade: Current trade
            df: DataFrame
            current_idx: Current bar index
            timestamp: Current timestamp
            current_signal: Current signal
            asset: Asset symbol
            
        Returns:
            Closed trade if exited, None otherwise
        """
        if trade.exit_time is not None:
            return None
        
        high = df['High'].iloc[current_idx]
        low = df['Low'].iloc[current_idx]
        close = df['Close'].iloc[current_idx]
        
        exited = False
        exit_price = close
        exit_reason = ""
        
        # Check stop loss
        if trade.direction == 1:  # Long
            if low <= trade.stop_loss:
                exited = True
                exit_price = trade.stop_loss
                exit_reason = ExitReason.STOP_LOSS.value
        else:  # Short
            if high >= trade.stop_loss:
                exited = True
                exit_price = trade.stop_loss
                exit_reason = ExitReason.STOP_LOSS.value
        
        # Check take profit
        if not exited:
            if trade.direction == 1:  # Long
                if high >= trade.take_profit:
                    exited = True
                    exit_price = trade.take_profit
                    exit_reason = ExitReason.TAKE_PROFIT.value
            else:  # Short
                if low <= trade.take_profit:
                    exited = True
                    exit_price = trade.take_profit
                    exit_reason = ExitReason.TAKE_PROFIT.value
        
        # Check time stop
        if not exited:
            bars_held = current_idx - df.index.get_loc(trade.entry_time)
            max_bars = strategy.config.max_bars_hold if hasattr(strategy, 'config') else 50
            if bars_held >= max_bars:
                exited = True
                exit_price = close
                exit_reason = ExitReason.TIME_STOP.value
        
        # Check signal reversal
        if not exited and current_signal != 0 and current_signal != trade.direction:
            exited = True
            exit_price = close
            exit_reason = ExitReason.SIGNAL_REVERSE.value
        
        if exited:
            # Apply exit slippage (conservative: always worse)
            slippage = self.config.slippage_pips * get_pip_value(asset)
            if trade.direction == 1:  # Long
                exit_price -= slippage
            else:  # Short
                exit_price += slippage
            
            trade.exit_time = timestamp
            trade.exit_price = exit_price
            trade.exit_reason = exit_reason
            trade.bars_held = current_idx - df.index.get_loc(trade.entry_time)
            
            # Calculate P&L
            price_diff = exit_price - trade.entry_price
            if trade.direction == -1:
                price_diff = -price_diff
            
            trade.pnl = self._apply_friction(self._pnl_to_dollars(price_diff, asset))
            trade.pnl_pips = calculate_pips(price_diff, asset)
            
            risk = abs(trade.entry_price - trade.stop_loss)
            if risk > 0:
                trade.r_multiple = price_diff / risk
            
            return trade
        
        return None
    
    def _build_equity_curve(self, trades: List[Trade], df: pd.DataFrame) -> pd.Series:
        """
        Build equity curve from trades.
        
        Args:
            trades: List of trades
            df: DataFrame for timestamps
            
        Returns:
            Equity curve series
        """
        realized_equity = self.config.initial_capital
        equity_values = [realized_equity]
        
        trade_idx = 0
        open_trade = None
        
        closes = df['Close'].values
        timestamps = df.index
        
        for i in range(1, len(df)):
            timestamp = timestamps[i]
            
            # Close realized trade if its exit_time has passed
            if open_trade is not None and open_trade.exit_time is not None and open_trade.exit_time <= timestamp:
                realized_equity += open_trade.pnl if open_trade.pnl is not None else 0.0
                open_trade = None
            
            # Open new trade if entry_time reached and no open trade
            if open_trade is None and trade_idx < len(trades):
                trade = trades[trade_idx]
                if trade.entry_time <= timestamp:
                    open_trade = trade
                    trade_idx += 1
            
            # Update equity with open trade unrealized P&L
            if open_trade is not None and open_trade.exit_time is None:
                current_price = closes[i]
                price_diff = current_price - open_trade.entry_price
                if open_trade.direction == -1:
                    price_diff = -price_diff
                gross_pnl = self._pnl_to_dollars(price_diff, open_trade.asset)
                # Use same friction as closed trades for consistent unrealized mark
                unrealized_pnl = self._apply_friction(gross_pnl)
                equity_values.append(realized_equity + unrealized_pnl)
            else:
                equity_values.append(realized_equity)
        
        return pd.Series(equity_values, index=timestamps)
    
    def run_multi_timeframe_backtest(self,
                                     strategy: StrategyBase,
                                     data: Dict[str, Dict[str, pd.DataFrame]],
                                     asset: str) -> Dict[str, BacktestResult]:
        """
        Run backtest across multiple timeframes for an asset.
        
        Args:
            strategy: Strategy instance
            data: Nested dict of asset -> granularity -> DataFrame
            asset: Asset symbol
            
        Returns:
            Dictionary of granularity -> BacktestResult
        """
        results = {}
        
        for granularity in strategy.config.granularities:
            if granularity not in data.get(asset, {}):
                continue
            
            df = data[asset][granularity]
            result = self.run_backtest(strategy, df, asset, granularity)
            results[granularity] = result
        
        return results
    
    def run_walk_forward_analysis(self,
                                  strategy: StrategyBase,
                                  df: pd.DataFrame,
                                  asset: str,
                                  granularity: str,
                                  train_size: int = 500,
                                  test_size: int = 100,
                                  n_windows: int = 5) -> List[BacktestResult]:
        """
        Run walk-forward analysis.
        
        Args:
            strategy: Strategy instance
            df: DataFrame
            asset: Asset symbol
            granularity: Timeframe
            train_size: Training window size
            test_size: Testing window size
            n_windows: Number of windows
            
        Returns:
            List of BacktestResults for each test window
        """
        results = []
        total_bars = len(df)
        
        for i in range(n_windows):
            start_idx = i * test_size
            train_end = start_idx + train_size
            test_end = min(train_end + test_size, total_bars)
            
            if test_end > total_bars:
                break
            
            # Test on out-of-sample data
            test_df = df.iloc[train_end:test_end].copy()
            
            result = self.run_backtest(
                strategy, test_df, asset, granularity, warmup_bars=0
            )
            results.append(result)
        
        return results
