# Layer 0: Strategy Qualification Engine

Last updated: 2026-04-05

## Overview

Layer 0 is the **Strategy Qualification Engine** for the Scalable Brain quantitative trading system. It provides a comprehensive framework for backtesting, analyzing, and qualifying trading strategies before they are promoted to Layer 2 (Live Signal Generation).

## Philosophy

The core principle of Layer 0 is **mathematical verification of edge**. Before any strategy touches live market data, it must demonstrate:

- **Positive Expectancy**: Average benefit per trade > 0.2R
- **Profit Factor**: Gross Profit / Gross Loss > 1.3
- **Win Rate**: >= 45% for swing trades
- **Risk Control**: Max drawdown <= 25%, max consecutive losses <= 6
- **Statistical Significance**: >= 100 trades per asset
- **Cross-Asset Robustness**: Works on at least 2 of 3 major FX pairs

## Architecture

```
src/layer0/
 __init__.py                    # Module initialization
 strategy_base.py               # Abstract base class for all strategies
 indicators.py                  # Technical indicators (EMA, ATR, ADX, etc.)
 backtest_engine.py             # Vectorized backtesting engine
 strategy_analyzer.py           # Performance metrics calculator
 multi_timeframe.py             # Multi-timeframe confluence engine
 qualify_strategies.py          # Main qualification script
 utils.py                       # Utility functions
 demo.py                        # Demo script
 strategies/                    # Strategy implementations
    __init__.py
    trend_ema_adx.py           # EMA crossover + ADX filter
    trend_donchian.py          # Donchian channel breakout
    range_bollinger.py         # Bollinger Band mean reversion
    range_stochastic.py        # Stochastic oscillator signals
    support_resistance.py      # S/R price action
    vcp_breakout.py            # Volatility Contraction Pattern
```

## Strategy Families

### 1. Trend-Following Strategies

**Trend_EMA_ADX**
- Entry: EMA crossover with ADX > 25 (trend strength)
- Exit: ATR-based stops or opposite crossover
- Best for: Trending markets

**Trend_Donchian**
- Entry: Breakout above/below Donchian Channel
- Exit: Channel midpoint or trailing stop
- Best for: Breakout and trend continuation

### 2. Mean-Reversion Strategies

**Range_Bollinger**
- Entry: Price at band extreme + RSI confirmation
- Exit: Mean reversion to middle band
- Best for: Range-bound markets

**Range_Stochastic**
- Entry: %K cross above 20 / below 80
- Exit: Opposite extreme or time stop
- Best for: Short-term reversals

### 3. Breakout Strategies

**VCP_Breakout**
- Entry: Breakout after volatility contraction
- Exit: Wide targets for explosive moves
- Best for: Pre-trend explosive moves

### 4. Support/Resistance Strategies

**Support_Resistance**
- Entry: Bounce off validated S/R levels
- Exit: Next level or level invalidation
- Best for: Key structural levels

## Multi-Timeframe Architecture

The system implements a hierarchical timeframe approach:

| Timeframe | Role | Key Inputs |
|-----------|------|------------|
| **D1** | Macro trend filter | EMA alignment, major S/R |
| **H4** | Primary signals | Entry generation |
| **H1** | Confirmation | Fine-tune entry timing |

### Timeframe Confluence Rules

1. **Trend Strategies**: Require D1 trend alignment
2. **Mean Reversion**: Optional D1 filter (avoid strong counter-trend)
3. **Breakouts**: Require H1 confirmation

## Backtest Engine Features

### Vectorized Simulation
- Fast event-driven backtesting
- ATR-based dynamic stops
- Realistic slippage and spread modeling

### Trade Management
- Dynamic position sizing
- Multiple exit conditions (stop, target, time, reversal)
- Comprehensive trade history

### Risk Management
- Per-trade risk limits
- Drawdown monitoring
- Consecutive loss tracking

## Performance Metrics

### Trade-Level Metrics
- **Win Rate**: Percentage of winning trades
- **Expectancy**: Average P&L per trade (in $ and R)
- **Profit Factor**: Gross Profit / Gross Loss
- **R-Multiple**: Risk-adjusted return per trade

### Risk Metrics
- **Max Drawdown**: Peak-to-trough decline
- **Max Consecutive Losses**: Worst losing streak
- **Sharpe Ratio**: Risk-adjusted return
- **Sortino Ratio**: Downside risk-adjusted return

### Statistical Metrics
- **T-Statistic**: Significance of edge
- **P-Value**: Probability of random results
- **Monte Carlo**: Future performance simulation

## Qualification Criteria

A strategy is qualified for Layer 2 when:

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| Expectancy | >= 0.2R | Minimum positive edge |
| Profit Factor | >= 1.3 | Sustainable profitability |
| Win Rate | >= 45% | Manageable drawdowns |
| Max Consecutive Losses | <= 6 | Psychological tolerance |
| Max Drawdown | <= 25% | Capital preservation |
| Min Trades | >= 100 | Statistical significance |
| Cross-Asset | >= 2 pairs | Robustness validation |

## Usage

### Basic Usage

```bash
# Run qualification on all strategies
python qualify_strategies.py

# Test specific assets
python qualify_strategies.py --assets EUR_USD GBP_USD

# Test specific timeframes
python qualify_strategies.py --granularities H4 H1

# Custom output directory
python qualify_strategies.py --output-dir ./my_results
```

### Programmatic Usage

```python
from layer0.strategies import TrendEMAADXStrategy
from layer0.backtest_engine import BacktestEngine, BacktestConfig
from layer0.strategy_analyzer import StrategyAnalyzer

# Create strategy
strategy = TrendEMAADXStrategy()

# Load data
df = load_historical_data("EUR_USD", "H4")

# Run backtest
engine = BacktestEngine(BacktestConfig(initial_capital=100000))
result = engine.run_backtest(strategy, df, "EUR_USD", "H4")

# Analyze
analyzer = StrategyAnalyzer()
metrics = analyzer.analyze(result)

# Check qualification
if metrics.qualified:
    print(f"Strategy qualified! Expectancy: {metrics.expectancy_r:.3f}R")
```

### Parameter Sensitivity

```python
from layer0.utils import parameter_sensitivity

# Test different ADX thresholds
results = parameter_sensitivity(
    TrendEMAADXStrategy,
    'adx_threshold',
    [20, 25, 30, 35],
    df, "EUR_USD", "H4"
)

print(results)
```

### Walk-Forward Analysis

```python
# Run walk-forward analysis
wf_results = engine.run_walk_forward_analysis(
    strategy, df, "EUR_USD", "H4",
    train_size=500, test_size=100, n_windows=5
)
```

## Output Files

### Qualification Report (JSON)
```json
{
  "strategy_name": "Trend_EMA_ADX",
  "overall_qualified": true,
  "qualified_assets": ["EUR_USD", "GBP_USD"],
  "aggregate": {
    "avg_win_rate": 0.48,
    "avg_expectancy_r": 0.35,
    "avg_profit_factor": 1.52
  },
  "asset_results": {
    "EUR_USD": {
      "H4": {
        "metrics": {
          "total_trades": 247,
          "win_rate": 0.48,
          "expectancy_r": 0.35,
          "profit_factor": 1.52,
          "qualified": true
        }
      }
    }
  }
}
```

### Layer 2 Config
```json
{
  "generated_at": "2026-04-03T10:00:00",
  "strategies": [
    {
      "name": "Trend_EMA_ADX",
      "qualified_assets": ["EUR_USD", "GBP_USD"],
      "ready_for_layer2": true
    }
  ]
}
```

## Demo

Run the demo to see the engine in action:

```bash
python demo.py
```

The demo includes:
1. Single strategy backtest
2. Multiple strategy comparison
3. Parameter sensitivity analysis
4. Walk-forward validation

## Best Practices

### Strategy Development
1. Start with simple, well-understood edges
2. Use ATR-based dynamic risk (not fixed pips)
3. Test across multiple assets
4. Validate with walk-forward analysis

### Parameter Selection
1. Avoid over-optimization
2. Test parameter sensitivity
3. Prefer robust parameters over optimal
4. Use out-of-sample validation

### Risk Management
1. Never risk more than 2% per trade
2. Use fractional Kelly (25-33%)
3. Reduce size in high volatility
4. Monitor consecutive losses

## Integration with Other Layers

### Layer 1: Market Regime Detection
- Layer 0 strategies are tested across all regimes
- Regime-specific performance is tracked
- Strategies can be regime-filtered in Layer 2

### Layer 2: Signal Generation
- Qualified strategies are promoted to Layer 2
- Same entry/exit logic is used
- Signals are generated on live data

### Layer 3: ML Meta-Labeling
- Layer 0 trade history trains the ML gatekeeper
- Features include strategy + regime context
- ML filters Layer 2 signals in real-time

## Future Enhancements

1. **Additional Strategies**: MACD, Ichimoku, Keltner Channel
2. **Portfolio Optimization**: Correlation-aware sizing
3. **Machine Learning**: Auto-strategy discovery
4. **Real-Time Monitoring**: Live performance tracking
5. **Cloud Execution**: Distributed backtesting

## References

- Minervini, M. (2013). Trade Like a Stock Market Wizard
- Chan, E. (2009). Quantitative Trading
- Grinold, R. & Kahn, R. (2000). Active Portfolio Management

## License

Proprietary - Scalable Brain Trading System
