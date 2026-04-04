"""
Strategy Analyzer
=================

Performance metrics calculator for backtest results.

Calculates:
- Trade-level metrics (win rate, expectancy, profit factor)
- Risk metrics (max drawdown, consecutive losses)
- Return metrics (Sharpe ratio, total return)
- Statistical significance tests
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from scipy import stats
import warnings

from .backtest_engine import BacktestResult, BacktestConfig
from .strategy_base import Trade


@dataclass
class StrategyMetrics:
    """Comprehensive strategy performance metrics."""
    
    # Trade counts
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    
    # Win/Loss metrics
    win_rate: float = 0.0
    loss_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    
    # Expectancy metrics
    expectancy: float = 0.0  # Average P&L per trade
    expectancy_r: float = 0.0  # Average R multiple per trade
    
    # Profit factor
    profit_factor: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    
    # Risk metrics
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    max_consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    
    # Return metrics
    total_return: float = 0.0
    total_return_pct: float = 0.0
    annualized_return: float = 0.0
    annualized_volatility: float = 0.0
    
    # Risk-adjusted metrics
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    
    # Trade statistics
    avg_bars_held: float = 0.0
    avg_trade_pnl: float = 0.0
    avg_trade_pnl_pips: float = 0.0
    
    # Statistical significance
    t_statistic: float = 0.0
    p_value: float = 1.0
    is_significant: bool = False
    
    # Qualification status
    qualified: bool = False
    qualification_reasons: List[str] = None
    
    def __post_init__(self):
        if self.qualification_reasons is None:
            self.qualification_reasons = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'breakeven_trades': self.breakeven_trades,
            'win_rate': self.win_rate,
            'loss_rate': self.loss_rate,
            'avg_win': self.avg_win,
            'avg_loss': self.avg_loss,
            'largest_win': self.largest_win,
            'largest_loss': self.largest_loss,
            'expectancy': self.expectancy,
            'expectancy_r': self.expectancy_r,
            'profit_factor': self.profit_factor,
            'gross_profit': self.gross_profit,
            'gross_loss': self.gross_loss,
            'max_drawdown': self.max_drawdown,
            'max_drawdown_pct': self.max_drawdown_pct,
            'max_consecutive_losses': self.max_consecutive_losses,
            'max_consecutive_wins': self.max_consecutive_wins,
            'total_return': self.total_return,
            'total_return_pct': self.total_return_pct,
            'annualized_return': self.annualized_return,
            'annualized_volatility': self.annualized_volatility,
            'sharpe_ratio': self.sharpe_ratio,
            'sortino_ratio': self.sortino_ratio,
            'calmar_ratio': self.calmar_ratio,
            'avg_bars_held': self.avg_bars_held,
            'avg_trade_pnl': self.avg_trade_pnl,
            'avg_trade_pnl_pips': self.avg_trade_pnl_pips,
            't_statistic': self.t_statistic,
            'p_value': self.p_value,
            'is_significant': self.is_significant,
            'qualified': self.qualified,
            'qualification_reasons': self.qualification_reasons,
        }


class StrategyAnalyzer:
    """
    Analyzer for calculating strategy performance metrics.
    """
    
    # Qualification thresholds
    # Demanding but realistic for a swing-trading development pipeline.
    # After fixing spread/slippage/commission in the backtest engine, most
    # strategies cluster just below ultra-strict prop-firm gates. These
    # thresholds ensure positive expectancy (ExpR > 0), stronger robustness
    # against execution friction (PF > 1.30), reasonable win rate,
    # and adequate sample size.
    MIN_EXPECTANCY_R = 0.05
    MIN_PROFIT_FACTOR = 1.30
    MIN_WIN_RATE = 0.35
    MAX_CONSECUTIVE_LOSSES = 10
    MAX_DRAWDOWN_PCT = 0.30
    MIN_TRADES = 60
    
    def __init__(self, risk_free_rate: float = 0.02):
        """
        Initialize analyzer.
        
        Args:
            risk_free_rate: Annual risk-free rate for Sharpe calculation
        """
        self.risk_free_rate = risk_free_rate
    
    def analyze(self, result: BacktestResult, 
                initial_capital: float = 100000.0) -> StrategyMetrics:
        """
        Analyze backtest result and calculate all metrics.
        
        Args:
            result: BacktestResult from backtest engine
            initial_capital: Initial capital for calculations
            
        Returns:
            StrategyMetrics with all performance metrics
        """
        metrics = StrategyMetrics()
        
        trades = [t for t in result.trades if t.exit_time is not None]
        
        if len(trades) == 0:
            return metrics
        
        # Basic trade counts
        metrics.total_trades = len(trades)
        metrics.winning_trades = sum(1 for t in trades if t.is_winner)
        metrics.losing_trades = sum(1 for t in trades if t.pnl < 0)
        metrics.breakeven_trades = sum(1 for t in trades if t.pnl == 0)
        
        # Win/Loss rates
        metrics.win_rate = metrics.winning_trades / metrics.total_trades
        metrics.loss_rate = metrics.losing_trades / metrics.total_trades
        
        # P&L statistics
        wins = [t.pnl for t in trades if t.is_winner]
        losses = [t.pnl for t in trades if t.pnl < 0]
        
        if wins:
            metrics.avg_win = np.mean(wins)
            metrics.largest_win = max(wins)
            metrics.gross_profit = sum(wins)
        
        if losses:
            metrics.avg_loss = np.mean(losses)
            metrics.largest_loss = min(losses)
            metrics.gross_loss = abs(sum(losses))
        
        # Profit factor
        if metrics.gross_loss > 0:
            metrics.profit_factor = metrics.gross_profit / metrics.gross_loss
        elif metrics.gross_profit > 0:
            metrics.profit_factor = float('inf')
        
        # Expectancy
        pnls = [t.pnl for t in trades]
        metrics.expectancy = np.mean(pnls)
        
        # Expectancy in R multiples
        r_multiples = [t.r_multiple for t in trades if t.r_multiple is not None]
        if r_multiples:
            metrics.expectancy_r = np.mean(r_multiples)
        
        # Drawdown analysis
        if not result.equity_curve.empty:
            metrics.max_drawdown, metrics.max_drawdown_pct = self._calculate_max_drawdown(
                result.equity_curve
            )
        
        # Consecutive losses/wins
        metrics.max_consecutive_losses, metrics.max_consecutive_wins = \
            self._calculate_consecutive_trades(trades)
        
        # Return metrics
        if not result.equity_curve.empty:
            metrics.total_return = result.equity_curve.iloc[-1] - initial_capital
            metrics.total_return_pct = metrics.total_return / initial_capital
            
            # Annualized metrics
            metrics.annualized_return, metrics.annualized_volatility = \
                self._calculate_annualized_metrics(result.equity_curve)
            
            # Risk-adjusted metrics
            metrics.sharpe_ratio = self._calculate_sharpe_ratio(
                result.equity_curve, metrics.annualized_volatility
            )
            metrics.sortino_ratio = self._calculate_sortino_ratio(result.equity_curve)
            
            if metrics.max_drawdown_pct > 0:
                metrics.calmar_ratio = metrics.annualized_return / metrics.max_drawdown_pct
        
        # Trade statistics
        metrics.avg_bars_held = np.mean([t.bars_held for t in trades if t.bars_held > 0])
        metrics.avg_trade_pnl = np.mean(pnls)
        metrics.avg_trade_pnl_pips = np.mean([t.pnl_pips for t in trades])
        
        # Statistical significance
        metrics.t_statistic, metrics.p_value, metrics.is_significant = \
            self._calculate_significance(pnls)
        
        # Qualification check
        metrics.qualified, metrics.qualification_reasons = self._check_qualification(metrics)
        
        return metrics
    
    def _calculate_max_drawdown(self, equity_curve: pd.Series) -> Tuple[float, float]:
        """
        Calculate maximum drawdown.
        
        Args:
            equity_curve: Equity curve series
            
        Returns:
            Tuple of (max_drawdown_value, max_drawdown_percentage)
        """
        rolling_max = equity_curve.expanding().max()
        drawdown = equity_curve - rolling_max
        drawdown_pct = drawdown / rolling_max
        
        max_dd_idx = drawdown.idxmin()
        max_drawdown = drawdown.loc[max_dd_idx]
        max_drawdown_pct = drawdown_pct.loc[max_dd_idx]
        
        return max_drawdown, abs(max_drawdown_pct)
    
    def _calculate_consecutive_trades(self, trades: List[Trade]) -> Tuple[int, int]:
        """
        Calculate maximum consecutive losses and wins.
        
        Args:
            trades: List of trades
            
        Returns:
            Tuple of (max_consecutive_losses, max_consecutive_wins)
        """
        max_losses = 0
        max_wins = 0
        current_losses = 0
        current_wins = 0
        
        for trade in trades:
            if trade.is_winner:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            elif trade.pnl < 0:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)
            else:
                current_losses = 0
                current_wins = 0
        
        return max_losses, max_wins
    
    def _calculate_annualized_metrics(self, equity_curve: pd.Series) -> Tuple[float, float]:
        """
        Calculate annualized return and volatility.
        
        Args:
            equity_curve: Equity curve series
            
        Returns:
            Tuple of (annualized_return, annualized_volatility)
        """
        # Calculate returns
        returns = equity_curve.pct_change().dropna()
        
        if len(returns) == 0:
            return 0.0, 0.0
        
        # Determine bars per year based on data frequency
        avg_bar_duration = (equity_curve.index[-1] - equity_curve.index[0]) / len(equity_curve)
        bars_per_year = pd.Timedelta(days=365) / avg_bar_duration
        
        # Annualized return
        total_return = (equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1
        years = len(equity_curve) / bars_per_year
        annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
        
        # Annualized volatility
        annualized_volatility = returns.std() * np.sqrt(bars_per_year)
        
        return annualized_return, annualized_volatility
    
    def _calculate_sharpe_ratio(self, equity_curve: pd.Series, 
                                annualized_volatility: float) -> float:
        """
        Calculate Sharpe ratio.
        
        Args:
            equity_curve: Equity curve series
            annualized_volatility: Annualized volatility
            
        Returns:
            Sharpe ratio
        """
        if annualized_volatility == 0:
            return 0.0
        
        returns = equity_curve.pct_change().dropna()
        avg_return = returns.mean()
        
        # Determine bars per year
        avg_bar_duration = (equity_curve.index[-1] - equity_curve.index[0]) / len(equity_curve)
        bars_per_year = pd.Timedelta(days=365) / avg_bar_duration
        
        annualized_return = avg_return * bars_per_year
        excess_return = annualized_return - self.risk_free_rate
        
        return excess_return / annualized_volatility
    
    def _calculate_sortino_ratio(self, equity_curve: pd.Series) -> float:
        """
        Calculate Sortino ratio (downside deviation only).
        
        Args:
            equity_curve: Equity curve series
            
        Returns:
            Sortino ratio
        """
        returns = equity_curve.pct_change().dropna()
        
        # Determine bars per year
        avg_bar_duration = (equity_curve.index[-1] - equity_curve.index[0]) / len(equity_curve)
        bars_per_year = pd.Timedelta(days=365) / avg_bar_duration
        
        avg_return = returns.mean() * bars_per_year
        downside_returns = returns[returns < 0]
        
        if len(downside_returns) == 0:
            return float('inf')
        
        downside_deviation = downside_returns.std() * np.sqrt(bars_per_year)
        
        if downside_deviation == 0:
            return 0.0
        
        excess_return = avg_return - self.risk_free_rate
        return excess_return / downside_deviation
    
    def _calculate_significance(self, pnls: List[float]) -> Tuple[float, float, bool]:
        """
        Calculate statistical significance of results.
        
        Args:
            pnls: List of trade P&Ls
            
        Returns:
            Tuple of (t_statistic, p_value, is_significant)
        """
        if len(pnls) < 2:
            return 0.0, 1.0, False
        
        # One-sample t-test (test if mean > 0)
        t_stat, p_value = stats.ttest_1samp(pnls, 0)
        
        # One-tailed test
        if t_stat > 0:
            p_value = p_value / 2
        else:
            p_value = 1 - (p_value / 2)
        
        is_significant = p_value < 0.05 and t_stat > 0
        
        return t_stat, p_value, is_significant
    
    def _check_qualification(self, metrics: StrategyMetrics) -> Tuple[bool, List[str]]:
        """
        Check if strategy meets qualification criteria.
        
        Args:
            metrics: Strategy metrics
            
        Returns:
            Tuple of (qualified, reasons)
        """
        qualified = True
        reasons = []
        
        if metrics.total_trades < self.MIN_TRADES:
            qualified = False
            reasons.append(f"Insufficient trades: {metrics.total_trades} < {self.MIN_TRADES}")
        
        if metrics.expectancy_r < self.MIN_EXPECTANCY_R:
            qualified = False
            reasons.append(f"Expectancy too low: {metrics.expectancy_r:.3f}R < {self.MIN_EXPECTANCY_R}R")
        
        if metrics.profit_factor < self.MIN_PROFIT_FACTOR:
            qualified = False
            reasons.append(f"Profit factor too low: {metrics.profit_factor:.3f} < {self.MIN_PROFIT_FACTOR}")
        
        if metrics.win_rate < self.MIN_WIN_RATE:
            qualified = False
            reasons.append(f"Win rate too low: {metrics.win_rate:.2%} < {self.MIN_WIN_RATE:.2%}")
        
        if metrics.max_consecutive_losses > self.MAX_CONSECUTIVE_LOSSES:
            qualified = False
            reasons.append(f"Too many consecutive losses: {metrics.max_consecutive_losses} > {self.MAX_CONSECUTIVE_LOSSES}")
        
        if metrics.max_drawdown_pct > self.MAX_DRAWDOWN_PCT:
            qualified = False
            reasons.append(f"Drawdown too high: {metrics.max_drawdown_pct:.2%} > {self.MAX_DRAWDOWN_PCT:.2%}")
        
        if qualified:
            reasons.append("Strategy meets all qualification criteria")
        
        return qualified, reasons
    
    def generate_report(self, metrics: StrategyMetrics) -> str:
        """
        Generate a formatted report of strategy metrics.
        
        Args:
            metrics: Strategy metrics
            
        Returns:
            Formatted report string
        """
        lines = [
            "=" * 60,
            "STRATEGY PERFORMANCE REPORT",
            "=" * 60,
            "",
            "TRADE STATISTICS",
            "-" * 40,
            f"Total Trades:        {metrics.total_trades}",
            f"Winning Trades:      {metrics.winning_trades} ({metrics.win_rate:.2%})",
            f"Losing Trades:       {metrics.losing_trades} ({metrics.loss_rate:.2%})",
            f"Breakeven Trades:    {metrics.breakeven_trades}",
            "",
            "P&L METRICS",
            "-" * 40,
            f"Gross Profit:        ${metrics.gross_profit:,.2f}",
            f"Gross Loss:          ${metrics.gross_loss:,.2f}",
            f"Profit Factor:       {metrics.profit_factor:.3f}",
            f"Expectancy:          ${metrics.expectancy:,.2f}",
            f"Expectancy (R):      {metrics.expectancy_r:.3f}R",
            f"Average Win:         ${metrics.avg_win:,.2f}",
            f"Average Loss:        ${metrics.avg_loss:,.2f}",
            f"Largest Win:         ${metrics.largest_win:,.2f}",
            f"Largest Loss:        ${metrics.largest_loss:,.2f}",
            "",
            "RISK METRICS",
            "-" * 40,
            f"Max Drawdown:        ${metrics.max_drawdown:,.2f} ({metrics.max_drawdown_pct:.2%})",
            f"Max Consecutive Losses: {metrics.max_consecutive_losses}",
            f"Max Consecutive Wins:   {metrics.max_consecutive_wins}",
            "",
            "RETURN METRICS",
            "-" * 40,
            f"Total Return:        ${metrics.total_return:,.2f} ({metrics.total_return_pct:.2%})",
            f"Annualized Return:   {metrics.annualized_return:.2%}",
            f"Annualized Volatility: {metrics.annualized_volatility:.2%}",
            f"Sharpe Ratio:        {metrics.sharpe_ratio:.3f}",
            f"Sortino Ratio:       {metrics.sortino_ratio:.3f}",
            f"Calmar Ratio:        {metrics.calmar_ratio:.3f}",
            "",
            "STATISTICAL SIGNIFICANCE",
            "-" * 40,
            f"T-Statistic:         {metrics.t_statistic:.3f}",
            f"P-Value:             {metrics.p_value:.4f}",
            f"Significant:         {'Yes' if metrics.is_significant else 'No'}",
            "",
            "QUALIFICATION STATUS",
            "-" * 40,
            f"Qualified:           {'YES' if metrics.qualified else 'NO'}",
        ]
        
        if metrics.qualification_reasons:
            lines.append("")
            lines.append("Qualification Details:")
            for reason in metrics.qualification_reasons:
                lines.append(f"  - {reason}")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
