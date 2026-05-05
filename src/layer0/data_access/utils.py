"""
Utility Functions
=================

Helper functions for Layer 0 strategy qualification.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import json


def resample_ohlcv(df: pd.DataFrame, 
                   target_granularity: str,
                   source_granularity: str = None) -> pd.DataFrame:
    """
    Resample OHLCV data to a different timeframe.
    
    Args:
        df: OHLCV DataFrame
        target_granularity: Target timeframe (H1, H4, D1)
        source_granularity: Source timeframe (optional)
        
    Returns:
        Resampled DataFrame
    """
    if target_granularity == "H1":
        rule = "1h"
    elif target_granularity == "H4":
        rule = "4h"
    elif target_granularity == "D1":
        rule = "1d"
    else:
        raise ValueError(f"Unknown granularity: {target_granularity}")
    
    resampled = df.resample(rule).agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    }).dropna()
    
    return resampled


def merge_timeframes(primary_df: pd.DataFrame,
                    higher_df: pd.DataFrame,
                    higher_granularity: str) -> pd.DataFrame:
    """
    Merge higher timeframe data into primary timeframe.
    Prevents look-ahead bias.
    
    Args:
        primary_df: Primary timeframe DataFrame
        higher_df: Higher timeframe DataFrame
        higher_granularity: Higher timeframe granularity
        
    Returns:
        Merged DataFrame
    """
    result = primary_df.copy()
    
    # Shift higher data to prevent look-ahead
    higher_df_shifted = higher_df.shift(1)
    
    # Reindex to primary timeframe
    for col in higher_df.columns:
        if col not in ['Open', 'High', 'Low', 'Close', 'Volume']:
            result[f'{higher_granularity}_{col}'] = higher_df_shifted[col].reindex(
                result.index, method='ffill'
            )
    
    return result


def calculate_correlation_matrix(returns_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate correlation matrix for strategy returns.
    
    Args:
        returns_df: DataFrame with strategy returns as columns
        
    Returns:
        Correlation matrix
    """
    return returns_df.corr()


def detect_regime(df: pd.DataFrame, 
                  adx_threshold: float = 25.0,
                  bb_width_threshold: float = 0.02) -> pd.Series:
    """
    Detect market regime (trending, ranging, volatile).
    
    Args:
        df: DataFrame with indicators
        adx_threshold: ADX threshold for trending
        bb_width_threshold: Bollinger Band width threshold
        
    Returns:
        Series with regime labels
    """
    regime = pd.Series('unknown', index=df.index)
    
    if 'ADX' in df.columns and 'BB_Width' in df.columns:
        trending = df['ADX'] > adx_threshold
        ranging = (df['ADX'] <= adx_threshold) & (df['BB_Width'] < bb_width_threshold)
        volatile = (df['ADX'] > adx_threshold) & (df['BB_Width'] >= bb_width_threshold)
        
        regime[trending] = 'trending'
        regime[ranging] = 'ranging'
        regime[volatile] = 'volatile'
    
    return regime


def calculate_position_size(account_balance: float,
                           risk_per_trade: float,
                           stop_loss_pips: float,
                           pip_value: float,
                           atr: Optional[float] = None) -> float:
    """
    Calculate position size based on risk.
    
    Args:
        account_balance: Account balance
        risk_per_trade: Risk percentage (e.g., 0.01 for 1%)
        stop_loss_pips: Stop loss in pips
        pip_value: Value per pip
        atr: Optional ATR for volatility adjustment
        
    Returns:
        Position size in lots
    """
    risk_amount = account_balance * risk_per_trade
    
    # Adjust for ATR if provided
    if atr:
        volatility_factor = 1.0 / (1 + atr * 10)  # Reduce size in high volatility
        risk_amount *= volatility_factor
    
    position_size = risk_amount / (stop_loss_pips * pip_value)
    
    return max(0.01, position_size)  # Minimum 0.01 lots


def kelly_criterion(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Calculate Kelly Criterion position size.
    
    Args:
        win_rate: Probability of winning
        avg_win: Average win amount
        avg_loss: Average loss amount (positive value)
        
    Returns:
        Kelly fraction (0-1)
    """
    if avg_loss == 0:
        return 0.0
    
    win_loss_ratio = avg_win / avg_loss
    kelly = win_rate - ((1 - win_rate) / win_loss_ratio)
    
    return max(0.0, min(1.0, kelly))


def fractional_kelly(win_rate: float, 
                     avg_win: float, 
                     avg_loss: float,
                     fraction: float = 0.25) -> float:
    """
    Calculate fractional Kelly position size.
    
    Args:
        win_rate: Probability of winning
        avg_win: Average win amount
        avg_loss: Average loss amount
        fraction: Kelly fraction (default 0.25 for quarter-Kelly)
        
    Returns:
        Fractional Kelly position size
    """
    kelly = kelly_criterion(win_rate, avg_win, avg_loss)
    return kelly * fraction


def monte_carlo_simulation(returns: List[float],
                          n_simulations: int = 1000,
                          n_trades: int = 100) -> Dict[str, float]:
    """
    Run Monte Carlo simulation on trade returns.
    
    Args:
        returns: Historical trade returns
        n_simulations: Number of simulations
        n_trades: Trades per simulation
        
    Returns:
        Dictionary with simulation statistics
    """
    if len(returns) == 0:
        return {
            'median_final_equity': 0.0,
            'worst_case': 0.0,
            'best_case': 0.0,
            'probability_of_profit': 0.0
        }
    
    final_equities = []
    
    for _ in range(n_simulations):
        # Sample with replacement
        sample_returns = np.random.choice(returns, size=n_trades, replace=True)
        final_equity = np.prod([1 + r for r in sample_returns])
        final_equities.append(final_equity)
    
    return {
        'median_final_equity': np.median(final_equities),
        'worst_case': np.percentile(final_equities, 5),
        'best_case': np.percentile(final_equities, 95),
        'probability_of_profit': np.mean([e > 1 for e in final_equities])
    }


def parameter_sensitivity(strategy_class,
                         param_name: str,
                         param_values: List[Any],
                         df: pd.DataFrame,
                         asset: str,
                         granularity: str) -> pd.DataFrame:
    """
    Test strategy sensitivity to parameter changes.
    
    Args:
        strategy_class: Strategy class to test
        param_name: Parameter name to vary
        param_values: List of values to test
        df: DataFrame with price data
        asset: Asset symbol
        granularity: Timeframe
        
    Returns:
        DataFrame with sensitivity results
    """
    from ..core_engine.backtest_engine import BacktestEngine
    from ..core_engine.strategy_analyzer import StrategyAnalyzer
    
    results = []
    
    for value in param_values:
        # Create strategy with modified parameter
        strategy = strategy_class(**{param_name: value})
        
        # Run backtest
        engine = BacktestEngine()
        backtest_result = engine.run_backtest(strategy, df, asset, granularity)
        
        # Analyze
        analyzer = StrategyAnalyzer()
        metrics = analyzer.analyze(backtest_result)
        
        results.append({
            'parameter_value': value,
            'total_trades': metrics.total_trades,
            'win_rate': metrics.win_rate,
            'expectancy_r': metrics.expectancy_r,
            'profit_factor': metrics.profit_factor,
            'max_drawdown_pct': metrics.max_drawdown_pct,
            'qualified': metrics.qualified
        })
    
    return pd.DataFrame(results)


def save_results_to_json(results: Dict, filepath: str):
    """
    Save results to JSON file.
    
    Args:
        results: Results dictionary
        filepath: Output file path
    """
    with open(filepath, 'w') as f:
        json.dump(results, f, indent=2, default=str)


def load_results_from_json(filepath: str) -> Dict:
    """
    Load results from JSON file.
    
    Args:
        filepath: Input file path
        
    Returns:
        Results dictionary
    """
    with open(filepath, 'r') as f:
        return json.load(f)


def format_currency(value: float, currency: str = '$') -> str:
    """
    Format value as currency string.
    
    Args:
        value: Numeric value
        currency: Currency symbol
        
    Returns:
        Formatted string
    """
    return f"{currency}{value:,.2f}"


def format_percentage(value: float, decimals: int = 2) -> str:
    """
    Format value as percentage string.
    
    Args:
        value: Numeric value (0.1 = 10%)
        decimals: Number of decimal places
        
    Returns:
        Formatted string
    """
    return f"{value:.{decimals}%}"


def print_trade_summary(trades: List, n: int = 10):
    """
    Print summary of recent trades.
    
    Args:
        trades: List of trades
        n: Number of trades to show
    """
    print(f"\nLast {n} trades:")
    print("-" * 80)
    print(f"{'Entry Time':<20} {'Dir':<4} {'Entry':<10} {'Exit':<10} {'P&L':<10} {'R':<6}")
    print("-" * 80)
    
    for trade in trades[-n:]:
        direction = "Long" if trade.direction == 1 else "Short"
        pnl = f"${trade.pnl:.2f}" if trade.pnl else "Open"
        r = f"{trade.r_multiple:.2f}" if trade.r_multiple else "-"
        exit_price = f"{trade.exit_price:.5f}" if trade.exit_price else "Open"
        
        print(f"{str(trade.entry_time):<20} {direction:<4} {trade.entry_price:.5f} "
              f"{exit_price:<10} {pnl:<10} {r:<6}")


def get_strategy_family(strategy_name: str) -> str:
    """
    Get strategy family from name.
    
    Args:
        strategy_name: Strategy name
        
    Returns:
        Strategy family (trend, mean_reversion, breakout, support_resistance)
    """
    name_lower = strategy_name.lower()
    
    if 'trend' in name_lower or 'ema' in name_lower or 'donchian' in name_lower:
        return 'trend'
    elif 'range' in name_lower or 'bollinger' in name_lower or 'stochastic' in name_lower:
        return 'mean_reversion'
    elif 'breakout' in name_lower or 'vcp' in name_lower:
        return 'breakout'
    elif 'support' in name_lower or 'resistance' in name_lower:
        return 'support_resistance'
    else:
        return 'unknown'


def compare_strategies(results: List[Dict], 
                      metric: str = 'expectancy_r') -> pd.DataFrame:
    """
    Compare multiple strategies on a specific metric.
    
    Args:
        results: List of strategy results
        metric: Metric to compare
        
    Returns:
        Comparison DataFrame
    """
    comparisons = []
    
    for result in results:
        agg = result.get('aggregate', {})
        comparisons.append({
            'strategy': result['strategy_name'],
            'qualified': result['overall_qualified'],
            metric: agg.get(metric, 0),
            'total_trades': agg.get('total_trades', 0),
            'win_rate': agg.get('avg_win_rate', 0),
            'profit_factor': agg.get('avg_profit_factor', 0),
        })
    
    df = pd.DataFrame(comparisons)
    return df.sort_values(metric, ascending=False)
