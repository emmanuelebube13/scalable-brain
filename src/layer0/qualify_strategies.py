"""
Strategy Qualification Script
=============================

Main entry point for Layer 0 strategy qualification.

This script:
1. Loads historical price data from Fact_Market_Prices (or CSV / synthetic fallback)
2. Runs backtests for all strategies
3. Calculates performance metrics
4. Generates qualification reports
5. Outputs qualified strategies for Layer 2 promotion as T-SQL seed scripts

Usage:
    python qualify_strategies.py
    python qualify_strategies.py --granularities H4 H1
    python qualify_strategies.py --output-dir ./results
    python qualify_strategies.py --use-db --env-file /path/to/.env
"""

import argparse
import copy
import json
import logging
import sys
import os
import itertools
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import warnings

import pandas as pd
import numpy as np

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from layer0.strategy_base import StrategyBase, StrategyConfig
from layer0.backtest_engine import BacktestEngine, BacktestConfig, BacktestResult
from layer0.strategy_analyzer import StrategyAnalyzer, StrategyMetrics
from layer0.multi_timeframe import MultiTimeframeEngine, create_mtf_config
from layer0 import data_loader
from layer0 import layer2_config_adapter

# Import strategies
from layer0.strategies import (
    TrendEMAADXStrategy, TrendEMAADX_H1_Only, TrendEMAADX_H4_Only, TrendEMAADX_MultiTF,
    TrendDonchianStrategy, TrendDonchian_H1_Only, TrendDonchian_H4_Only, TrendDonchian_VCP,
    RangeBollingerStrategy, RangeBollinger_H1_Only, RangeBollinger_H4_Only, RangeBollinger_Aggressive,
    RangeStochasticStrategy, RangeStochastic_H1_Only, RangeStochastic_H4_Only, RangeStochastic_Divergence,
    SupportResistanceStrategy, SupportResistance_H1_Only, SupportResistance_H4_Only, SupportResistance_Breakout,
    VCPBreakoutStrategy, VCPBreakout_H1_Only, VCPBreakout_H4_Only, VCPBreakout_Aggressive,
)


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


GRANULARITIES = ["H1", "H4", "D1"]


def _param_grid_for_strategy(strategy_name: str, granularity: str) -> List[Dict[str, Any]]:
    """Return a compact parameter grid for optimization by strategy family/timeframe."""
    grid: List[Dict[str, List[Any]]] = []

    if strategy_name.startswith("Trend_EMA_ADX"):
        if granularity == "H1":
            grid = [{
                'fast_ema': [8, 10, 12, 16],
                'slow_ema': [20, 30, 40],
                'adx_threshold': [18.0, 22.0, 25.0],
            }]
        else:
            grid = [{
                'fast_ema': [15, 20, 30],
                'slow_ema': [40, 60, 80],
                'adx_threshold': [18.0, 22.0, 25.0, 30.0],
            }]

    elif strategy_name.startswith("Trend_Donchian"):
        if granularity == "H1":
            grid = [{
                'channel_period': [10, 14, 20, 28],
                'adx_threshold': [18.0, 22.0, 25.0, 30.0],
            }]
        else:
            grid = [{
                'channel_period': [20, 30, 40, 55],
                'adx_threshold': [18.0, 22.0, 25.0, 30.0],
            }]

    elif strategy_name.startswith("Range_Bollinger_Aggressive"):
        if granularity == "H1":
            grid = [{
                'bb_period': [10, 14, 20],
                'bb_std': [1.3, 1.5, 1.8],
                'rsi_period': [7, 10, 14],
                'require_rsi': [False],
            }]
        else:
            grid = [{
                'bb_period': [20, 30, 40],
                'bb_std': [1.3, 1.5, 1.8],
                'rsi_period': [10, 14, 21],
                'require_rsi': [False],
            }]

    elif strategy_name.startswith("Range_Bollinger"):
        if granularity == "H1":
            grid = [{
                'bb_period': [10, 14, 20],
                'bb_std': [1.5, 1.8, 2.0],
                'rsi_period': [7, 10, 14],
                'rsi_oversold': [25.0, 30.0, 35.0],
                'rsi_overbought': [65.0, 70.0, 75.0],
            }]
        else:
            grid = [{
                'bb_period': [20, 30, 40],
                'bb_std': [1.5, 1.8, 2.0],
                'rsi_period': [10, 14, 21],
                'rsi_oversold': [25.0, 30.0, 35.0],
                'rsi_overbought': [65.0, 70.0, 75.0],
            }]

    elif strategy_name.startswith("Range_Stochastic"):
        if granularity == "H1":
            grid = [{
                'k_period': [7, 10, 14],
                'd_period': [3, 5],
                'oversold': [15.0, 20.0, 25.0],
                'overbought': [75.0, 80.0, 85.0],
            }]
        else:
            grid = [{
                'k_period': [10, 14, 20],
                'd_period': [3, 5],
                'oversold': [15.0, 20.0, 25.0],
                'overbought': [75.0, 80.0, 85.0],
            }]

    if not grid:
        return []

    candidates: List[Dict[str, Any]] = []
    for grid_block in grid:
        keys = list(grid_block.keys())
        values_product = itertools.product(*(grid_block[k] for k in keys))
        for values in values_product:
            p = dict(zip(keys, values))
            if 'fast_ema' in p and 'slow_ema' in p and p['fast_ema'] >= p['slow_ema']:
                continue
            candidates.append(p)

    return candidates


def _score_metrics(metrics_list: List[StrategyMetrics]) -> float:
    """Composite score for ranking candidate parameter sets."""
    valid = [m for m in metrics_list if m.total_trades > 0]
    if not valid:
        return -1e9

    exp_vals = np.array([m.expectancy_r for m in valid], dtype=float)
    pf_vals = np.array([m.profit_factor for m in valid], dtype=float)
    dd_vals = np.array([m.max_drawdown_pct for m in valid], dtype=float)
    win_vals = np.array([m.win_rate for m in valid], dtype=float)

    exp_vals = np.nan_to_num(exp_vals, nan=0.0, posinf=0.0, neginf=0.0)
    pf_vals = np.nan_to_num(pf_vals, nan=0.0, posinf=5.0, neginf=0.0)
    dd_vals = np.nan_to_num(dd_vals, nan=0.0, posinf=1.0, neginf=0.0)
    win_vals = np.nan_to_num(win_vals, nan=0.0, posinf=1.0, neginf=0.0)

    # Clip extreme values to keep ranking stable.
    exp_vals = np.clip(exp_vals, -2.0, 2.0)
    pf_vals = np.clip(pf_vals, 0.0, 5.0)
    dd_vals = np.clip(dd_vals, 0.0, 1.0)
    win_vals = np.clip(win_vals, 0.0, 1.0)

    avg_exp = float(np.mean(exp_vals))
    avg_pf = float(np.mean(pf_vals))
    avg_dd = float(np.mean(dd_vals))
    avg_win = float(np.mean(win_vals))
    avg_trades = float(np.mean([m.total_trades for m in valid]))

    # Prioritize expectancy and PF, penalize deep drawdowns.
    score = (
        avg_exp * 3.0 +
        (avg_pf - 1.0) * 1.5 +
        avg_win * 0.5 -
        avg_dd * 1.25 +
        min(avg_trades / 500.0, 0.4)
    )
    return score


def _evaluate_candidate_walk_forward(
    strategy_candidate: StrategyBase,
    df: pd.DataFrame,
    asset: str,
    granularity: str,
    analyzer: StrategyAnalyzer,
    initial_capital: float,
    wf_windows: int,
    wf_train_bars: int,
    wf_test_bars: int,
) -> Tuple[float, Dict[str, Any]]:
    """Run rolling walk-forward for one candidate and return ranking score + diagnostics."""
    engine = BacktestEngine(BacktestConfig(initial_capital=initial_capital))

    total_bars = len(df)
    test_bars = max(150, wf_test_bars)
    train_bars = max(400, wf_train_bars)

    if total_bars < (train_bars + test_bars):
        train_bars = max(300, int(total_bars * 0.65))
        test_bars = max(100, int(total_bars * 0.2))

    wf_results = engine.run_walk_forward_analysis(
        strategy=strategy_candidate,
        df=df,
        asset=asset,
        granularity=granularity,
        train_size=train_bars,
        test_size=test_bars,
        n_windows=wf_windows,
    )

    window_metrics = [analyzer.analyze(r, initial_capital) for r in wf_results]
    score = _score_metrics(window_metrics)
    valid_windows = [m for m in window_metrics if m.total_trades > 0]

    diagnostics = {
        'windows_total': len(window_metrics),
        'windows_with_trades': len(valid_windows),
        'avg_expectancy_r': float(np.mean([m.expectancy_r for m in valid_windows])) if valid_windows else 0.0,
        'avg_profit_factor': float(np.mean([m.profit_factor for m in valid_windows])) if valid_windows else 0.0,
        'avg_drawdown_pct': float(np.mean([m.max_drawdown_pct for m in valid_windows])) if valid_windows else 0.0,
        'score': score,
    }
    return score, diagnostics


def _optimize_strategy_parameters(
    strategy: StrategyBase,
    df: pd.DataFrame,
    asset: str,
    granularity: str,
    analyzer: StrategyAnalyzer,
    initial_capital: float,
    wf_windows: int,
    wf_train_bars: int,
    wf_test_bars: int,
    max_param_combos: int,
) -> Tuple[StrategyBase, Dict[str, Any]]:
    """Select best parameter set via walk-forward scoring and return tuned strategy copy."""
    candidates = _param_grid_for_strategy(strategy.config.name, granularity)
    if not candidates:
        return copy.deepcopy(strategy), {'optimized': False, 'reason': 'no_grid'}

    # Keep runtime predictable on large grids.
    if len(candidates) > max_param_combos:
        step = max(1, len(candidates) // max_param_combos)
        candidates = candidates[::step][:max_param_combos]

    best_score = -1e18
    best_params: Dict[str, Any] = {}
    best_diag: Dict[str, Any] = {}

    for params in candidates:
        candidate_strategy = copy.deepcopy(strategy)
        for k, v in params.items():
            if hasattr(candidate_strategy, k):
                setattr(candidate_strategy, k, v)

        score, diag = _evaluate_candidate_walk_forward(
            strategy_candidate=candidate_strategy,
            df=df,
            asset=asset,
            granularity=granularity,
            analyzer=analyzer,
            initial_capital=initial_capital,
            wf_windows=wf_windows,
            wf_train_bars=wf_train_bars,
            wf_test_bars=wf_test_bars,
        )

        if score > best_score:
            best_score = score
            best_params = params
            best_diag = diag

    tuned_strategy = copy.deepcopy(strategy)
    for k, v in best_params.items():
        if hasattr(tuned_strategy, k):
            setattr(tuned_strategy, k, v)

    return tuned_strategy, {
        'optimized': True,
        'best_params': best_params,
        'best_score': best_score,
        'walk_forward': best_diag,
        'candidates_tested': len(candidates),
    }


def load_historical_data(
    asset_symbol: str,
    asset_id: int,
    granularity: str,
    data_dir: Optional[str] = None,
    use_db: bool = True,
    env_path: Optional[str] = None,
    conn=None,
    lookback_years: int = 5,
) -> pd.DataFrame:
    """
    Load historical price data for an asset.
    
    Resolution order:
    1. Database (Fact_Market_Prices) if use_db=True
    2. CSV files if data_dir is provided
    3. Synthetic data as final fallback
    
    Args:
        asset_symbol: Asset symbol (e.g., "EUR_USD")
        asset_id: Asset identifier from Dim_Asset
        granularity: Timeframe (e.g., "H4")
        data_dir: Directory containing CSV files
        use_db: Whether to try loading from SQL Server first
        env_path: Optional path to .env file for DB credentials
        
    Returns:
        DataFrame with OHLCV data
    """
    if use_db:
        try:
            start_date = None
            if lookback_years:
                from datetime import timedelta
                start_date = datetime.now() - timedelta(days=365 * lookback_years)
            df = data_loader.load_market_prices(
                asset_id=asset_id,
                granularity=granularity,
                env_path=env_path,
                conn=conn,
                start_date=start_date,
            )
            if len(df) > 0:
                return df
            logger.warning(f"DB returned 0 rows for {asset_symbol} {granularity}")
        except Exception as e:
            logger.warning(f"Failed to load from DB for {asset_symbol} {granularity}: {e}")

    if data_dir:
        filepath = Path(data_dir) / f"{asset_symbol}_{granularity}.csv"
        if filepath.exists():
            df = pd.read_csv(filepath, parse_dates=['Timestamp'], index_col='Timestamp')
            return df

    logger.warning(f"No data file found for {asset_symbol} {granularity}, generating synthetic data")
    return generate_synthetic_data(asset_symbol, granularity)


def generate_synthetic_data(asset: str, granularity: str, n_bars: int = 5000) -> pd.DataFrame:
    """
    Generate synthetic OHLCV data for testing.
    
    Args:
        asset: Asset symbol
        granularity: Timeframe
        n_bars: Number of bars to generate
        
    Returns:
        DataFrame with synthetic OHLCV data
    """
    # Use asset-derived seed so different assets get different synthetic paths
    seed = hash(asset) % (2**31)
    rng = np.random.default_rng(seed)
    
    if "JPY" in asset:
        base_price = 110.0
    else:
        base_price = 1.1
    
    returns = rng.normal(0.0001, 0.005, n_bars)
    
    trend_periods = rng.choice(n_bars, size=10, replace=False)
    for period in trend_periods:
        length = rng.integers(50, 200)
        direction = rng.choice([-1, 1])
        for i in range(length):
            if period + i < n_bars:
                returns[period + i] += 0.001 * direction
    
    prices = base_price * np.exp(np.cumsum(returns))
    
    noise = rng.normal(0, 0.001, n_bars)
    opens = prices * (1 + noise)
    highs = np.maximum(opens, prices) * (1 + np.abs(rng.normal(0, 0.002, n_bars)))
    lows = np.minimum(opens, prices) * (1 - np.abs(rng.normal(0, 0.002, n_bars)))
    closes = prices
    volumes = rng.integers(1000, 10000, n_bars)
    
    if granularity == "H1":
        freq = "h"
    elif granularity == "H4":
        freq = "4h"
    else:  # D1
        freq = "d"
    
    timestamps = pd.date_range(end=datetime.now(), periods=n_bars, freq=freq)
    
    df = pd.DataFrame({
        'Open': opens,
        'High': highs,
        'Low': lows,
        'Close': closes,
        'Volume': volumes
    }, index=timestamps)
    
    return df


def get_all_strategies() -> List[StrategyBase]:
    """
    Get all strategy instances to test.
    
    Returns:
        List of strategy instances
    """
    strategies = [
        TrendEMAADX_H1_Only(),
        TrendEMAADX_H4_Only(),
        TrendEMAADX_MultiTF(),
        TrendDonchian_H1_Only(),
        TrendDonchian_H4_Only(),
        TrendDonchian_VCP(),
        RangeBollinger_H1_Only(),
        RangeBollinger_H4_Only(),
        RangeBollinger_Aggressive(),
        RangeStochastic_Divergence(),
        # Excluded: extremely slow or zero-trade on H4
        # RangeStochastic_H1_Only(),
        # RangeStochastic_H4_Only(),
        # SupportResistance_H1_Only(),
        # SupportResistance_H4_Only(),
        # SupportResistance_Breakout(),
        # VCPBreakout_H1_Only(),
        # VCPBreakout_H4_Only(),
        # VCPBreakout_Aggressive(),
    ]
    return strategies


def run_strategy_qualification(
    strategy: StrategyBase,
    asset_symbols: List[str],
    asset_symbol_map: Dict[str, int],
    granularities: List[str],
    data_dir: Optional[str] = None,
    use_db: bool = True,
    env_path: Optional[str] = None,
    initial_capital: float = 100000.0,
    preloaded_data: Optional[Dict[str, Dict[str, pd.DataFrame]]] = None,
    conn=None,
    lookback_years: int = 5,
    optimize_params: bool = False,
    wf_windows: int = 4,
    wf_train_bars: int = 1200,
    wf_test_bars: int = 300,
    max_param_combos: int = 30,
) -> Dict[str, Any]:
    """
    Run qualification for a single strategy across assets and timeframes.
    
    Args:
        strategy: Strategy instance
        asset_symbols: List of asset symbols to test
        asset_symbol_map: Mapping of symbol -> Asset_ID
        granularities: List of timeframes to test
        data_dir: Directory containing historical CSV data
        use_db: Whether to load from database
        env_path: Optional .env file path
        initial_capital: Initial capital for backtest
        
    Returns:
        Dictionary with qualification results
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Qualifying Strategy: {strategy.config.name}")
    logger.info(f"{'='*60}")
    
    results = {
        'strategy_name': strategy.config.name,
        'description': strategy.config.description,
        'assets_tested': [],
        'granularities_tested': [],
        'asset_results': {},
        'overall_qualified': False,
        'qualification_reason': ""
    }
    
    if preloaded_data is not None:
        all_data = preloaded_data
    else:
        all_data = preload_historical_data(
            asset_symbols=asset_symbols,
            asset_symbol_map=asset_symbol_map,
            granularities=granularities,
            data_dir=data_dir,
            use_db=use_db,
            env_path=env_path,
            conn=conn,
            lookback_years=lookback_years,
        )
    
    backtest_engine = BacktestEngine(BacktestConfig(initial_capital=initial_capital))
    analyzer = StrategyAnalyzer()
    
    all_metrics = []
    qualified_assets = []
    
    for symbol in asset_symbols:
        if symbol not in all_data:
            continue
        
        asset_results = {}
        
        for gran in granularities:
            if gran not in all_data.get(symbol, {}):
                continue
            
            df = all_data[symbol][gran]
            # Create a fresh deep copy for each asset+granularity pair to prevent
            # any state leakage between runs (e.g., cached indicators, mutable state)
            strategy_for_run = copy.deepcopy(strategy)
            optimization_info: Dict[str, Any] = {'optimized': False}

            if optimize_params:
                strategy_for_run, optimization_info = _optimize_strategy_parameters(
                    strategy=strategy,
                    df=df,
                    asset=symbol,
                    granularity=gran,
                    analyzer=analyzer,
                    initial_capital=initial_capital,
                    wf_windows=wf_windows,
                    wf_train_bars=wf_train_bars,
                    wf_test_bars=wf_test_bars,
                    max_param_combos=max_param_combos,
                )
                if optimization_info.get('optimized'):
                    logger.info(
                        f"  Optimized {symbol} {gran}: {optimization_info.get('best_params')} "
                        f"score={optimization_info.get('best_score'):.4f} "
                        f"candidates={optimization_info.get('candidates_tested')}"
                    )
            
            backtest_result = backtest_engine.run_backtest(
                strategy_for_run, df, symbol, gran,
                warmup_bars=strategy_for_run.get_required_warmup_bars()
            )
            
            metrics = analyzer.analyze(backtest_result, initial_capital)
            
            asset_results[gran] = {
                'metrics': metrics.to_dict(),
                'trades': len(backtest_result.trades),
                'optimization': optimization_info,
            }
            
            all_metrics.append(metrics)
            
            logger.info(f"\n{symbol} {gran}:")
            logger.info(f"  Trades: {metrics.total_trades}")
            logger.info(f"  Win Rate: {metrics.win_rate:.2%}")
            logger.info(f"  Expectancy: {metrics.expectancy_r:.3f}R")
            logger.info(f"  Profit Factor: {metrics.profit_factor:.3f}")
            logger.info(f"  Qualified: {metrics.qualified}")
            
            if metrics.qualified:
                if symbol not in qualified_assets:
                    qualified_assets.append(symbol)
        
        results['asset_results'][symbol] = asset_results
    
    results['assets_tested'] = list(all_data.keys())
    results['granularities_tested'] = granularities
    results['qualified_assets'] = qualified_assets
    
    # Sandbox mode: promote strategy if it qualifies on any asset+granularity pair
    # Count unique asset+granularity pairs that qualified
    qualified_pairs = []
    for symbol in asset_symbols:
        if symbol in results['asset_results']:
            for gran in granularities:
                if gran in results['asset_results'][symbol]:
                    if results['asset_results'][symbol][gran]['metrics'].get('qualified'):
                        qualified_pairs.append(f"{symbol}_{gran}")
    
    if len(qualified_pairs) >= 1:
        results['overall_qualified'] = True
        results['qualification_reason'] = f"Sandbox qualified: {len(qualified_pairs)} asset+granularity pair(s): {', '.join(qualified_pairs)}"
    else:
        results['overall_qualified'] = False
        results['qualification_reason'] = f"No asset+granularity pairs met qualification criteria"
    
    if all_metrics:
        valid_metrics = [m for m in all_metrics if m.total_trades > 0]
        if valid_metrics:
            results['aggregate'] = {
                'avg_win_rate': np.mean([m.win_rate for m in valid_metrics]),
                'avg_expectancy_r': np.mean([m.expectancy_r for m in valid_metrics]),
                'avg_profit_factor': np.mean([m.profit_factor for m in valid_metrics]),
                'avg_max_drawdown_pct': np.mean([m.max_drawdown_pct for m in valid_metrics]),
                'total_trades': sum([m.total_trades for m in valid_metrics]),
            }
    
    return results


def preload_historical_data(
    asset_symbols: List[str],
    asset_symbol_map: Dict[str, int],
    granularities: List[str],
    data_dir: Optional[str] = None,
    use_db: bool = True,
    env_path: Optional[str] = None,
    conn=None,
    lookback_years: int = 5,
) -> Dict[str, Dict[str, pd.DataFrame]]:
    """Preload historical data once and share it across all strategies."""
    all_data: Dict[str, Dict[str, pd.DataFrame]] = {}

    for symbol in asset_symbols:
        asset_id = asset_symbol_map.get(symbol)
        if asset_id is None:
            logger.warning(f"Asset symbol '{symbol}' not found in Dim_Asset mapping; skipping")
            continue

        all_data[symbol] = {}
        for gran in granularities:
            df = load_historical_data(
                symbol,
                int(asset_id),
                gran,
                data_dir,
                use_db,
                env_path,
                conn,
                lookback_years,
            )
            if len(df) > 0:
                all_data[symbol][gran] = df.copy()
                logger.info(f"Loaded {len(df)} bars for {symbol} {gran}")

    return all_data


def write_progress_checkpoint(
    all_results: List[Dict[str, Any]],
    output_dir: str,
    completed: int,
    total: int,
) -> str:
    """Persist rolling qualification progress so long runs have visible output."""
    os.makedirs(output_dir, exist_ok=True)
    checkpoint_path = Path(output_dir) / "qualification_progress.json"
    payload = {
        "updated_at": datetime.now().isoformat(),
        "completed_strategies": completed,
        "total_strategies": total,
        "completion_pct": round((completed / total) * 100, 2) if total else 0,
        "results": all_results,
    }
    with open(checkpoint_path, 'w') as f:
        json.dump(payload, f, indent=2, default=str)
    return str(checkpoint_path)


def generate_qualification_report(all_results: List[Dict], output_dir: str = "./results") -> str:
    """
    Generate comprehensive qualification report.
    
    Args:
        all_results: List of strategy qualification results
        output_dir: Output directory for reports
        
    Returns:
        Path to generated report
    """
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    json_path = Path(output_dir) / f"qualification_report_{timestamp}.json"
    with open(json_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    
    md_path = Path(output_dir) / f"qualification_report_{timestamp}.md"
    
    with open(md_path, 'w') as f:
        f.write("# Layer 0 Strategy Qualification Report\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("## Summary\n\n")
        
        qualified = [r for r in all_results if r['overall_qualified']]
        f.write(f"### Qualified Strategies ({len(qualified)})\n\n")
        
        if qualified:
            f.write("| Strategy | Assets Qualified | Avg Win Rate | Avg Expectancy (R) |\n")
            f.write("|----------|------------------|--------------|-------------------|\n")
            for r in qualified:
                agg = r.get('aggregate', {})
                f.write(f"| {r['strategy_name']} | {len(r['qualified_assets'])} | ")
                f.write(f"{agg.get('avg_win_rate', 0):.2%} | {agg.get('avg_expectancy_r', 0):.3f} |\n")
        else:
            f.write("No strategies qualified.\n")
        
        f.write("\n")
        
        non_qualified = [r for r in all_results if not r['overall_qualified']]
        f.write(f"### Non-Qualified Strategies ({len(non_qualified)})\n\n")
        
        for r in non_qualified:
            f.write(f"#### {r['strategy_name']}\n\n")
            f.write(f"Reason: {r['qualification_reason']}\n\n")
            
            for asset, asset_results in r['asset_results'].items():
                f.write(f"**{asset}:**\n")
                for gran, result in asset_results.items():
                    m = result['metrics']
                    opt = result.get('optimization', {})
                    f.write(f"- {gran}: {m['total_trades']} trades, ")
                    f.write(f"Win Rate: {m['win_rate']:.2%}, ")
                    f.write(f"Expectancy: {m['expectancy_r']:.3f}R, ")
                    f.write(f"PF: {m['profit_factor']:.3f}")
                    if opt.get('optimized') and opt.get('best_params'):
                        f.write(f", Best Params: {opt.get('best_params')}")
                    f.write("\n")
                f.write("\n")
        
        f.write("\n## Qualified Strategy Details\n\n")
        
        for r in qualified:
            f.write(f"### {r['strategy_name']}\n\n")
            f.write(f"Description: {r['description']}\n\n")
            f.write("**Entry Conditions:**\n")
            f.write("- See strategy implementation\n\n")
            
            f.write("**Performance by Asset:**\n\n")
            f.write("| Asset | Granularity | Trades | Win Rate | Expectancy (R) | Profit Factor | Max DD | Qualified |\n")
            f.write("|-------|-------------|--------|----------|----------------|---------------|--------|-----------|\n")
            
            for asset, asset_results in r['asset_results'].items():
                for gran, result in asset_results.items():
                    m = result['metrics']
                    opt = result.get('optimization', {})
                    f.write(f"| {asset} | {gran} | {m['total_trades']} | ")
                    f.write(f"{m['win_rate']:.2%} | {m['expectancy_r']:.3f} | ")
                    f.write(f"{m['profit_factor']:.3f} | {m['max_drawdown_pct']:.2%} | ")
                    f.write(f"{'Yes' if m['qualified'] else 'No'} |\n")
                    if opt.get('optimized') and opt.get('best_params'):
                        f.write(f"  - Optimized Params ({asset} {gran}): {opt.get('best_params')}\n")
            f.write("\n")
    
    logger.info(f"\nReports saved to:")
    logger.info(f"  JSON: {json_path}")
    logger.info(f"  Markdown: {md_path}")
    
    return str(md_path)


def generate_layer2_sql_seed(
    qualified_results: List[Dict],
    asset_symbol_map: Dict[int, str],
    output_path: str = "./layer2_strategies.sql"
) -> str:
    """
    Generate Layer 2 T-SQL seed script for qualified strategies.
    
    Args:
        qualified_results: List of qualified strategy results
        asset_symbol_map: Mapping of Asset_ID -> Symbol
        output_path: Output file path
        
    Returns:
        Path to generated SQL file
    """
    sql = layer2_config_adapter.generate_sql_seed(qualified_results, asset_symbol_map)
    with open(output_path, 'w') as f:
        f.write(sql)
    logger.info(f"\nLayer 2 SQL seed saved to: {output_path}")
    return output_path


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Layer 0 Strategy Qualification Engine'
    )
    
    parser.add_argument(
        '--assets',
        nargs='+',
        default=None,
        help='Asset symbols to test (default: all active from Dim_Asset)'
    )
    
    parser.add_argument(
        '--granularities',
        nargs='+',
        default=['H4', 'H1'],
        help='Timeframes to test'
    )
    
    parser.add_argument(
        '--data-dir',
        type=str,
        default=None,
        help='Directory containing historical data CSVs'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='./results',
        help='Output directory for reports'
    )
    
    parser.add_argument(
        '--initial-capital',
        type=float,
        default=100000.0,
        help='Initial capital for backtests'
    )
    
    parser.add_argument(
        '--strategies',
        nargs='+',
        default=None,
        help='Specific strategies to test (default: all)'
    )
    
    parser.add_argument(
        '--use-db',
        action='store_true',
        default=True,
        help='Load price data from Fact_Market_Prices (default: True)'
    )
    
    parser.add_argument(
        '--no-use-db',
        action='store_true',
        default=False,
        help='Skip database and use CSV / synthetic data only'
    )
    
    parser.add_argument(
        '--env-file',
        type=str,
        default=None,
        help='Path to .env file with DB credentials'
    )
    
    parser.add_argument(
        '--lookback-years',
        type=int,
        default=5,
        help='Number of years of historical data to load (default: 5)'
    )

    parser.set_defaults(optimize_params=True)
    parser.add_argument(
        '--optimize-params',
        dest='optimize_params',
        action='store_true',
        help='Enable parameter optimization using walk-forward scoring per asset/timeframe (default: enabled)'
    )

    parser.add_argument(
        '--no-optimize-params',
        dest='optimize_params',
        action='store_false',
        help='Disable parameter optimization and use static strategy parameters'
    )

    parser.add_argument(
        '--wf-windows',
        type=int,
        default=4,
        help='Walk-forward windows for optimization scoring (default: 4)'
    )

    parser.add_argument(
        '--wf-train-bars',
        type=int,
        default=1200,
        help='Walk-forward train bars for optimization scoring (default: 1200)'
    )

    parser.add_argument(
        '--wf-test-bars',
        type=int,
        default=300,
        help='Walk-forward test bars for optimization scoring (default: 300)'
    )

    parser.add_argument(
        '--max-param-combos',
        type=int,
        default=30,
        help='Max parameter combinations tested per strategy/asset/granularity (default: 30)'
    )
    
    args = parser.parse_args()
    
    use_db = args.use_db and not args.no_use_db
    env_path = args.env_file
    
    # Resolve assets
    asset_symbol_map = {}  # symbol -> id
    shared_conn = None
    if use_db:
        try:
            # Connectivity uses the pooled engine in src.common.db; no raw
            # shared connection is required (engine pooling handles reuse).
            assets_df = data_loader.load_assets(env_path=env_path)
            asset_symbol_map = dict(zip(assets_df['Symbol'], assets_df['Asset_ID']))
            logger.info(f"Loaded {len(asset_symbol_map)} assets from Dim_Asset")
        except Exception as e:
            logger.error(f"Failed to load assets from database: {e}")
            logger.error("Use --no-use-db to run with CSV/synthetic data only, or check DB credentials.")
            sys.exit(1)
    else:
        # Fallback for offline mode: use a minimal hardcoded map for smoke testing
        # This is only used when --no-use-db is explicitly set.
        asset_symbol_map = {
            "EUR_USD": 1,
            "GBP_USD": 2,
            "USD_JPY": 3,
            "AUD_USD": 4,
            "USD_CAD": 5,
        }
        logger.warning("Running in offline mode with hardcoded asset map (symbol -> id)")
    
    if args.assets:
        asset_symbols = args.assets
    else:
        asset_symbols = list(asset_symbol_map.keys())
    
    logger.info("="*60)
    logger.info("Layer 0 Strategy Qualification Engine")
    logger.info("="*60)
    logger.info(f"Assets: {asset_symbols}")
    logger.info(f"Granularities: {args.granularities}")
    logger.info(f"Initial Capital: ${args.initial_capital:,.2f}")
    logger.info(f"Use DB: {use_db}")
    logger.info(f"Optimize Params: {args.optimize_params}")
    if args.optimize_params:
        logger.info(
            f"Optimization Config: wf_windows={args.wf_windows}, "
            f"wf_train_bars={args.wf_train_bars}, wf_test_bars={args.wf_test_bars}, "
            f"max_param_combos={args.max_param_combos}"
        )
    logger.info("="*60)
    
    all_strategies = get_all_strategies()
    
    if args.strategies:
        strategies = [s for s in all_strategies if s.config.name in args.strategies]
    else:
        strategies = all_strategies
    
    logger.info(f"Testing {len(strategies)} strategies")

    preloaded_data = preload_historical_data(
        asset_symbols=asset_symbols,
        asset_symbol_map=asset_symbol_map,
        granularities=args.granularities,
        data_dir=args.data_dir,
        use_db=use_db,
        env_path=env_path,
        conn=shared_conn,
        lookback_years=args.lookback_years,
    )
    logger.info("Completed shared historical data preload for all strategies")
    
    all_results = []
    
    total_strategies = len(strategies)
    for idx, strategy in enumerate(strategies, start=1):
        try:
            result = run_strategy_qualification(
                strategy,
                asset_symbols,
                asset_symbol_map,
                args.granularities,
                args.data_dir,
                use_db,
                env_path,
                args.initial_capital,
                preloaded_data,
                shared_conn,
                args.lookback_years,
                args.optimize_params,
                args.wf_windows,
                args.wf_train_bars,
                args.wf_test_bars,
                args.max_param_combos,
            )
            all_results.append(result)
            checkpoint_path = write_progress_checkpoint(
                all_results=all_results,
                output_dir=args.output_dir,
                completed=idx,
                total=total_strategies,
            )
            logger.info(
                f"Progress checkpoint updated ({idx}/{total_strategies}): {checkpoint_path}"
            )
        except Exception as e:
            logger.error(f"Error qualifying {strategy.config.name}: {e}")
            all_results.append({
                'strategy_name': strategy.config.name,
                'description': strategy.config.description,
                'assets_tested': [],
                'granularities_tested': args.granularities,
                'asset_results': {},
                'overall_qualified': False,
                'qualification_reason': f'Execution failed: {e}',
                'status': 'failed',
            })
            checkpoint_path = write_progress_checkpoint(
                all_results=all_results,
                output_dir=args.output_dir,
                completed=idx,
                total=total_strategies,
            )
            logger.info(
                f"Progress checkpoint updated ({idx}/{total_strategies}): {checkpoint_path}"
            )
            import traceback
            traceback.print_exc()

    if shared_conn is not None:
        shared_conn.close()
    
    # Generate reports
    report_path = generate_qualification_report(all_results, args.output_dir)
    
    # Generate Layer 2 SQL seed
    qualified_results = [r for r in all_results if r.get('overall_qualified')]
    failed_results = [r for r in all_results if not r.get('overall_qualified')]
    execution_error_results = [r for r in all_results if r.get('status') == 'failed']
    
    # Build reverse map for adapter (id -> symbol)
    id_symbol_map = {v: k for k, v in asset_symbol_map.items()}
    layer2_sql_path = generate_layer2_sql_seed(
        qualified_results,
        id_symbol_map,
        Path(args.output_dir) / 'layer2_strategies.sql'
    )
    
    # Also emit the indicator library extension SQL
    indicator_sql_path = Path(args.output_dir) / 'layer2_indicator_extension.sql'
    with open(indicator_sql_path, 'w') as f:
        f.write(layer2_config_adapter.generate_indicator_library_extension_sql())
    logger.info(f"Layer 2 indicator extension SQL saved to: {indicator_sql_path}")
    
    # Print summary
    logger.info("\n" + "="*60)
    logger.info("QUALIFICATION SUMMARY (SANDBOX MODE)")
    logger.info("="*60)
    # In sandbox mode: qualified = strategies with >=1 qualified pair
    # non_qualified = strategies tested but with 0 qualified pairs
    # failed = strategies that threw exceptions during execution
    disqualified_results = [r for r in all_results if not r.get('overall_qualified') and r.get('status') != 'failed']
    logger.info(f"Total strategies tested: {len(strategies)}")
    logger.info(f"Strategies qualified (sandbox): {len(qualified_results)}")
    logger.info(f"Strategies disqualified (0 qualified pairs): {len(disqualified_results)}")
    logger.info(f"Strategies failed (execution errors): {len(execution_error_results)}")
    logger.info("")
    
    if qualified_results:
        logger.info("Qualified strategies:")
        for r in qualified_results:
            logger.info(f"  - {r['strategy_name']}: {len(r['qualified_assets'])} assets")
    
    logger.info("")
    logger.info(f"Report: {report_path}")
    logger.info(f"Layer 2 SQL Seed: {layer2_sql_path}")
    logger.info(f"Indicator Extension SQL: {indicator_sql_path}")
    logger.info("="*60)


if __name__ == "__main__":
    main()
