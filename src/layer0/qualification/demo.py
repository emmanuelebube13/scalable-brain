"""
Layer 0 Strategy Qualification Demo
===================================

Demonstrates how to use the Layer 0 Strategy Qualification Engine.

This demo:
1. Creates sample price data
2. Instantiates strategies
3. Runs backtests
4. Analyzes results
5. Generates reports
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)
logger = logging.getLogger(__name__)

# Import Layer 0 components
from strategy_base import StrategyConfig
from backtest_engine import BacktestEngine, BacktestConfig, BacktestResult
from strategy_analyzer import StrategyAnalyzer, StrategyMetrics
from indicators import calculate_pips

# Import strategies
from strategies import (
    TrendEMAADXStrategy,
    RangeBollingerStrategy,
    TrendDonchianStrategy,
    VCPBreakoutStrategy,
)


def generate_sample_data(n_bars: int = 2000, 
                        trend_strength: float = 0.3,
                        volatility: float = 0.008) -> pd.DataFrame:
    """
    Generate realistic sample price data.
    
    Args:
        n_bars: Number of bars to generate
        trend_strength: Strength of trend (0-1)
        volatility: Volatility level
        
    Returns:
        DataFrame with OHLCV data
    """
    np.random.seed(42)
    
    # Generate returns with trend and mean reversion
    returns = np.random.normal(0.00005, volatility, n_bars)
    
    # Add trend component
    trend = np.sin(np.linspace(0, 4*np.pi, n_bars)) * trend_strength * volatility
    returns += trend
    
    # Add some momentum clustering
    for i in range(1, n_bars):
        if np.random.random() < 0.3:  # 30% chance of momentum continuation
            returns[i] += returns[i-1] * 0.3
    
    # Calculate prices
    prices = 1.1000 * np.exp(np.cumsum(returns))
    
    # Generate OHLC
    timestamps = pd.date_range(end=datetime.now(), periods=n_bars, freq='4H')
    
    df = pd.DataFrame(index=timestamps)
    df['Close'] = prices
    
    # Generate realistic OHLC from close
    df['Open'] = df['Close'].shift(1)
    df.loc[df.index[0], 'Open'] = df['Close'].iloc[0] * (1 + np.random.normal(0, 0.001))
    
    # High and Low based on volatility
    daily_range = volatility * 2
    df['High'] = df[['Open', 'Close']].max(axis=1) * (1 + np.abs(np.random.normal(0, daily_range/2, n_bars)))
    df['Low'] = df[['Open', 'Close']].min(axis=1) * (1 - np.abs(np.random.normal(0, daily_range/2, n_bars)))
    
    # Volume
    df['Volume'] = np.random.randint(1000, 10000, n_bars)
    
    return df


def run_single_strategy_demo():
    """Demo running a single strategy."""
    logger.info("="*60)
    logger.info("SINGLE STRATEGY DEMO")
    logger.info("="*60)
    
    # Generate sample data
    logger.info("\nGenerating sample data...")
    df = generate_sample_data(n_bars=2000)
    logger.info(f"Generated {len(df)} bars of H4 data")
    logger.info(f"Date range: {df.index[0]} to {df.index[-1]}")
    
    # Create strategy
    logger.info("\nCreating Trend EMA ADX Strategy...")
    strategy = TrendEMAADXStrategy(
        fast_ema=20,
        slow_ema=50,
        adx_threshold=25.0
    )
    
    # Run backtest
    logger.info("\nRunning backtest...")
    engine = BacktestEngine(BacktestConfig(initial_capital=100000))
    result = engine.run_backtest(
        strategy, df, "EUR_USD", "H4", warmup_bars=200
    )
    
    logger.info(f"Backtest complete: {len(result.trades)} trades generated")
    
    # Analyze results
    logger.info("\nAnalyzing results...")
    analyzer = StrategyAnalyzer()
    metrics = analyzer.analyze(result, initial_capital=100000)
    
    # Print report
    print("\n" + analyzer.generate_report(metrics))
    
    return result, metrics


def run_multiple_strategies_demo():
    """Demo running multiple strategies."""
    logger.info("\n" + "="*60)
    logger.info("MULTIPLE STRATEGIES DEMO")
    logger.info("="*60)
    
    # Generate sample data
    df = generate_sample_data(n_bars=2000)
    
    # Define strategies to test
    strategies = [
        ("Trend EMA ADX", TrendEMAADXStrategy()),
        ("Range Bollinger", RangeBollingerStrategy()),
        ("Trend Donchian", TrendDonchianStrategy()),
        ("VCP Breakout", VCPBreakoutStrategy()),
    ]
    
    results = []
    
    for name, strategy in strategies:
        logger.info(f"\nTesting {name}...")
        
        engine = BacktestEngine(BacktestConfig(initial_capital=100000))
        backtest_result = engine.run_backtest(
            strategy, df, "EUR_USD", "H4", warmup_bars=200
        )
        
        analyzer = StrategyAnalyzer()
        metrics = analyzer.analyze(backtest_result, initial_capital=100000)
        
        results.append({
            'name': name,
            'strategy': strategy,
            'backtest_result': backtest_result,
            'metrics': metrics
        })
        
        logger.info(f"  Trades: {metrics.total_trades}")
        logger.info(f"  Win Rate: {metrics.win_rate:.2%}")
        logger.info(f"  Expectancy: {metrics.expectancy_r:.3f}R")
        logger.info(f"  Profit Factor: {metrics.profit_factor:.3f}")
        logger.info(f"  Qualified: {metrics.qualified}")
    
    # Compare strategies
    logger.info("\n" + "="*60)
    logger.info("STRATEGY COMPARISON")
    logger.info("="*60)
    
    comparison = pd.DataFrame([
        {
            'Strategy': r['name'],
            'Trades': r['metrics'].total_trades,
            'Win Rate': f"{r['metrics'].win_rate:.2%}",
            'Expectancy (R)': f"{r['metrics'].expectancy_r:.3f}",
            'Profit Factor': f"{r['metrics'].profit_factor:.3f}",
            'Max DD': f"{r['metrics'].max_drawdown_pct:.2%}",
            'Qualified': 'Yes' if r['metrics'].qualified else 'No'
        }
        for r in results
    ])
    
    print("\n" + comparison.to_string(index=False))
    
    # Rank by expectancy
    best = max(results, key=lambda x: x['metrics'].expectancy_r)
    logger.info(f"\nBest Strategy by Expectancy: {best['name']}")
    logger.info(f"  Expectancy: {best['metrics'].expectancy_r:.3f}R")
    
    return results


def run_parameter_sensitivity_demo():
    """Demo parameter sensitivity analysis."""
    logger.info("\n" + "="*60)
    logger.info("PARAMETER SENSITIVITY DEMO")
    logger.info("="*60)
    
    # Generate sample data
    df = generate_sample_data(n_bars=1500)
    
    # Test different ADX thresholds
    adx_thresholds = [20, 25, 30, 35]
    
    logger.info("\nTesting different ADX thresholds for Trend EMA ADX Strategy:")
    
    results = []
    for threshold in adx_thresholds:
        strategy = TrendEMAADXStrategy(adx_threshold=threshold)
        
        engine = BacktestEngine(BacktestConfig(initial_capital=100000))
        backtest_result = engine.run_backtest(
            strategy, df, "EUR_USD", "H4", warmup_bars=200
        )
        
        analyzer = StrategyAnalyzer()
        metrics = analyzer.analyze(backtest_result, initial_capital=100000)
        
        results.append({
            'adx_threshold': threshold,
            'trades': metrics.total_trades,
            'win_rate': metrics.win_rate,
            'expectancy_r': metrics.expectancy_r,
            'profit_factor': metrics.profit_factor,
            'qualified': metrics.qualified
        })
        
        logger.info(f"\nADX Threshold: {threshold}")
        logger.info(f"  Trades: {metrics.total_trades}")
        logger.info(f"  Win Rate: {metrics.win_rate:.2%}")
        logger.info(f"  Expectancy: {metrics.expectancy_r:.3f}R")
        logger.info(f"  Qualified: {metrics.qualified}")
    
    # Show sensitivity table
    sensitivity_df = pd.DataFrame(results)
    print("\n" + "="*60)
    print("SENSITIVITY ANALYSIS RESULTS")
    print("="*60)
    print(sensitivity_df.to_string(index=False))
    
    # Find optimal parameter
    best_idx = sensitivity_df['expectancy_r'].idxmax()
    best = sensitivity_df.loc[best_idx]
    logger.info(f"\nOptimal ADX Threshold: {best['adx_threshold']}")
    logger.info(f"  Expectancy: {best['expectancy_r']:.3f}R")
    
    return results


def run_walk_forward_demo():
    """Demo walk-forward analysis."""
    logger.info("\n" + "="*60)
    logger.info("WALK-FORWARD ANALYSIS DEMO")
    logger.info("="*60)
    
    # Generate longer sample data
    df = generate_sample_data(n_bars=3000)
    
    strategy = TrendEMAADXStrategy()
    engine = BacktestEngine(BacktestConfig(initial_capital=100000))
    analyzer = StrategyAnalyzer()
    
    # Run walk-forward analysis
    logger.info("\nRunning walk-forward analysis...")
    logger.info("  Window size: 500 bars")
    logger.info("  Test size: 100 bars")
    logger.info("  Number of windows: 5")
    
    wf_results = engine.run_walk_forward_analysis(
        strategy, df, "EUR_USD", "H4",
        train_size=500, test_size=100, n_windows=5
    )
    
    logger.info(f"\nCompleted {len(wf_results)} walk-forward windows")
    
    # Analyze each window
    print("\n" + "="*60)
    print("WALK-FORWARD RESULTS BY WINDOW")
    print("="*60)
    
    for i, result in enumerate(wf_results):
        metrics = analyzer.analyze(result, initial_capital=100000)
        
        print(f"\nWindow {i+1}:")
        print(f"  Trades: {metrics.total_trades}")
        print(f"  Win Rate: {metrics.win_rate:.2%}")
        print(f"  Expectancy: {metrics.expectancy_r:.3f}R")
        print(f"  Profit Factor: {metrics.profit_factor:.3f}")
    
    # Aggregate results
    all_metrics = [analyzer.analyze(r, initial_capital=100000) for r in wf_results]
    
    avg_expectancy = np.mean([m.expectancy_r for m in all_metrics])
    avg_win_rate = np.mean([m.win_rate for m in all_metrics])
    avg_pf = np.mean([m.profit_factor for m in all_metrics])
    
    print("\n" + "="*60)
    print("WALK-FORWARD AGGREGATE RESULTS")
    print("="*60)
    print(f"Average Expectancy: {avg_expectancy:.3f}R")
    print(f"Average Win Rate: {avg_win_rate:.2%}")
    print(f"Average Profit Factor: {avg_pf:.3f}")
    
    return wf_results


def main():
    """Run all demos."""
    logger.info("\n" + "="*60)
    logger.info("LAYER 0 STRATEGY QUALIFICATION ENGINE DEMO")
    logger.info("="*60)
    logger.info("\nThis demo shows how to use the Layer 0 engine to:")
    logger.info("  1. Run backtests on trading strategies")
    logger.info("  2. Calculate performance metrics")
    logger.info("  3. Compare multiple strategies")
    logger.info("  4. Test parameter sensitivity")
    logger.info("  5. Perform walk-forward analysis")
    logger.info("")
    
    # Run demos
    try:
        # Demo 1: Single strategy
        run_single_strategy_demo()
        
        # Demo 2: Multiple strategies
        run_multiple_strategies_demo()
        
        # Demo 3: Parameter sensitivity
        run_parameter_sensitivity_demo()
        
        # Demo 4: Walk-forward
        run_walk_forward_demo()
        
    except Exception as e:
        logger.error(f"Demo error: {e}")
        import traceback
        traceback.print_exc()
    
    logger.info("\n" + "="*60)
    logger.info("DEMO COMPLETE")
    logger.info("="*60)
    logger.info("\nFor production use, run: python qualify_strategies.py")


if __name__ == "__main__":
    main()
