# Fix StrategyAnalyzer — Implementation Prompt

## Context

The file to modify is:
```
/home/emmanuel/Documents/Scalable_Brain/scalable-brain/src/layer0/strategy_analyzer.py
```

This is the performance metrics calculator for the Layer 0 strategy qualification pipeline. It consumes `BacktestResult` objects from `backtest_engine.py` and produces `StrategyMetrics` (a `@dataclass`). The `StrategyMetrics` are then used to:
- Gate whether a strategy qualifies for Layer 2 promotion
- Generate JSON/Markdown qualification reports
- Appear in the Layer 2 SQL seed scripts

The `Trade` dataclass it processes lives in `strategy_base.py` and has these relevant fields:
```python
pnl: float = 0.0           # Profit/loss in account currency
r_multiple: float = 0.0    # P/L in R multiples
bars_held: int = 0         # Number of bars position was held
exit_time: Optional[datetime] = None  # None if trade is still open

@property
def is_winner(self) -> bool:
    return self.pnl > 0
```

The equity curve is a `pd.Series` of account equity at each bar timestamp.

Current qualification thresholds (lines 139-144):
```python
MIN_EXPECTANCY_R = 0.05
MIN_PROFIT_FACTOR = 1.30
MIN_WIN_RATE = 0.35
MAX_CONSECUTIVE_LOSSES = 10
MAX_DRAWDOWN_PCT = 0.30
MIN_TRADES = 60
```

---

## Fixes — ordered by priority (high impact first)

### 1. Sharpe/Sortino use arithmetic mean return; Calmar uses geometric — produce inconsistent, non-comparable numbers

**File:** `strategy_analyzer.py`
**Lines involved:** 305-361 (two methods), 239

**The bug:**
- `_calculate_annualized_metrics` (line 328) computes annualized return geometrically: `(1 + total_return) ** (1 / years) - 1`
- `_calculate_sharpe_ratio` (line 357) recomputes its own annualized return using **arithmetic mean scaling**: `avg_return * bars_per_year`
- `_calculate_sortino_ratio` (line 378) also uses arithmetic mean: `returns.mean() * bars_per_year`
- `calmar_ratio` (line 239) feeds from `_calculate_annualized_metrics` — so it uses geometric

For a volatile swing strategy, arithmetic mean overstates annualized return by 15-30% versus geometric compounding. Result: Sharpe and Sortino are inflated relative to Calmar. They are not comparable to each other.

**Fix:**
- Remove the duplicated `bars_per_year` + arithmetic return calculation from both `_calculate_sharpe_ratio` and `_calculate_sortino_ratio`
- Have both methods accept `annualized_return` as a parameter (already computed by `_calculate_annualized_metrics`)
- In `analyze()` (around lines 232-236), pass the already-computed `metrics.annualized_return` into both methods instead of making them recalculate

In `_calculate_sharpe_ratio`:
- Change signature to `_calculate_sharpe_ratio(self, equity_curve, annualized_volatility, annualized_return)`
- Replace lines 350-358 (the entire return + bars_per_year calculation) with `excess_return = annualized_return - self.risk_free_rate`
- Keep `return excess_return / annualized_volatility`
- Remove duplicate bars_per_year calculation entirely

In `_calculate_sortino_ratio`:
- Change signature to `_calculate_sortino_ratio(self, equity_curve, annualized_return)`
- Line 378: replace `avg_return = returns.mean() * bars_per_year` with using the passed-in `annualized_return`
- Line 389: replace `excess_return = avg_return - self.risk_free_rate` with `excess_return = annualized_return - self.risk_free_rate`
- Keep the downside deviation calculation as-is

In `analyze()`:
- Line 233: change to `self._calculate_sharpe_ratio(result.equity_curve, metrics.annualized_volatility, metrics.annualized_return)`
- Line 236: change to `self._calculate_sortino_ratio(result.equity_curve, metrics.annualized_return)`

---

### 2. Breakeven trade detection uses exact float equality — miscategorizes trades near zero

**File:** `strategy_analyzer.py`
**Lines involved:** 176-178

**The bug:**
```python
metrics.winning_trades = sum(1 for t in trades if t.is_winner)      # pnl > 0
metrics.losing_trades = sum(1 for t in trades if t.pnl < 0)         # pnl < 0
metrics.breakeven_trades = sum(1 for t in trades if t.pnl == 0)     # exact zero
```
A trade with `pnl = 0.000001` is classified as a "winning" trade but is effectively breakeven after spread/commission. A trade with `pnl = -0.000003` is classified as a "losing" trade but is effectively breakeven. The breakeven count is almost always zero because floating-point P&L is rarely exactly `0.0`.

**Fix (do NOT modify the Trade.is_winner property — that affects other consumers):**
- Define a tolerance at the top of `analyze()`: `BREAKEVEN_TOLERANCE = 1e-6`
- Change line 176 to: `metrics.winning_trades = sum(1 for t in trades if t.pnl > BREAKEVEN_TOLERANCE)`
- Change line 177 to: `metrics.losing_trades = sum(1 for t in trades if t.pnl < -BREAKEVEN_TOLERANCE)`
- Line 178 stays but with tolerance: `metrics.breakeven_trades = sum(1 for t in trades if abs(t.pnl) <= BREAKEVEN_TOLERANCE)`
- Update lines 185-186 (wins/losses lists) to use the same tolerance:
  ```python
  wins = [t.pnl for t in trades if t.pnl > BREAKEVEN_TOLERANCE]
  losses = [t.pnl for t in trades if t.pnl < -BREAKEVEN_TOLERANCE]
  ```
- Update lines 290-301 in `_calculate_consecutive_trades` to use the same tolerance:
  ```python
  if trade.pnl > BREAKEVEN_TOLERANCE:
      current_wins += 1
      ...
  elif trade.pnl < -BREAKEVEN_TOLERANCE:
      current_losses += 1
      ...
  else:
      # breakeven — do not reset either counter
      pass
  ```

Note: apply the same consecutive-wins/losses behavior change from fix #7 below (do NOT reset either counter on breakeven). See fix #7.

---

### 3. `avg_bars_held` silently excludes same-bar exits — inflates reported hold time

**File:** `strategy_analyzer.py`
**Line involved:** 242

**The bug:**
```python
metrics.avg_bars_held = np.mean([t.bars_held for t in trades if t.bars_held > 0])
```
Trades that enter and exit on the same bar (`bars_held == 0`) are dropped from the average. This inflates the reported hold time and hides a potential churn problem — if a strategy is generating rapid same-bar reversals (noise entries, stop-hunting), you would never see it in this metric.

**Fix:**
- Change line 242 to: `metrics.avg_bars_held = np.mean([t.bars_held for t in trades])`
- Add a new field to `StrategyMetrics` dataclass: `same_bar_exit_pct: float = 0.0` (under line 70, in the "Trade statistics" section)
- After the `avg_bars_held` line, add:
  ```python
  same_bar_exits = sum(1 for t in trades if t.bars_held == 0)
  metrics.same_bar_exit_pct = same_bar_exits / len(trades) if len(trades) > 0 else 0.0
  ```
- Add `'same_bar_exit_pct': self.same_bar_exit_pct` to `StrategyMetrics.to_dict()` (around line 118)
- Add a line in `generate_report()` after `avg_bars_held` to display it:
  ```python
  f"Same-Bar Exits:      {same_bar_exits} ({metrics.same_bar_exit_pct:.2%})",
  ```

---

### 4. No profit concentration ratio — outlier-driven strategies pass qualification undetected

**File:** `strategy_analyzer.py`
**Lines involved:** 184-186 (wins list), 25-124 (dataclass fields)

**The gap:**
A strategy with 1.35 PF that earned 80% of its gross profit from a single 12R outlier passes all qualification gates (`MIN_PROFIT_FACTOR = 1.30`, `MIN_EXPECTANCY_R = 0.05`) but is not robust. There's currently no metric that detects this.

**Fix:**
- Add to `StrategyMetrics` dataclass (under profit factor, around line 52):
  ```python
  profit_concentration_ratio: float = 0.0  # % of gross profit from top 5% of wins
  ```
- In `analyze()`, after the wins list is built (after line 191), add:
  ```python
  if wins and len(wins) > 1:
      top_n = max(1, int(len(wins) * 0.05))
      top_wins = sorted(wins, reverse=True)[:top_n]
      metrics.profit_concentration_ratio = sum(top_wins) / metrics.gross_profit if metrics.gross_profit > 0 else 0.0
  ```
- Add `'profit_concentration_ratio': self.profit_concentration_ratio` to `to_dict()`
- Add a qualification gate in `_check_qualification`: if `profit_concentration_ratio > 0.50` (i.e. more than 50% of profit from top 5% of trades), flag as disqualified with reason `"Profit too concentrated in top wins: X% from top Y trades"`
- Add display line in `generate_report()` under P&L METRICS section

---

### 5. Drawdown calculation returns only depth, not duration

**File:** `strategy_analyzer.py`
**Lines involved:** 255-273 (method), 25-124 (dataclass fields)

**The gap:**
A 25% drawdown that recovers in 2 weeks is vastly different from a 25% drawdown that lasts 8 months. Both pass `MAX_DRAWDOWN_PCT = 0.30` but only one is survivable for a $70k growth target. There's currently no `max_drawdown_duration` metric.

**Fix:**
- Add to `StrategyMetrics` dataclass (next to max_drawdown, around line 55):
  ```python
  max_drawdown_duration: int = 0  # bars from peak to new high
  ```
- In `analyze()` around line 215-217, replace the drawdown call with:
  ```python
  metrics.max_drawdown, metrics.max_drawdown_pct, metrics.max_drawdown_duration = self._calculate_max_drawdown(result.equity_curve)
  ```
- Rewrite `_calculate_max_drawdown` to return a 3-tuple. The new logic:
  ```python
  def _calculate_max_drawdown(self, equity_curve: pd.Series) -> Tuple[float, float, int]:
      rolling_max = equity_curve.expanding().max()
      drawdown = equity_curve - rolling_max
      drawdown_pct = drawdown / rolling_max

      max_dd_idx = drawdown.idxmin()
      max_drawdown_value = drawdown.loc[max_dd_idx]
      max_drawdown_pct_value = abs(drawdown_pct.loc[max_dd_idx])

      # Calculate duration: bars from this peak until equity exceeds (new high)
      # Find the peak date that started this drawdown
      peak_date = rolling_max.loc[max_dd_idx]
      peak_idx = equity_curve.index.get_loc(equity_curve[equity_curve == peak_date].index[0]) if peak_date is not None else max_dd_idx

      # Walk forward from max_dd_idx to find recovery to new high
      dd_idx_pos = equity_curve.index.get_loc(max_dd_idx)
      recovery_bars = 0
      for i in range(dd_idx_pos, len(equity_curve)):
          if equity_curve.iloc[i] >= rolling_max.iloc[i]:
              recovery_bars = i - dd_idx_pos
              break
      if recovery_bars == 0:
          recovery_bars = len(equity_curve) - dd_idx_pos  # never recovered

      return max_drawdown_value, max_drawdown_pct_value, recovery_bars
  ```
- Add `'max_drawdown_duration': self.max_drawdown_duration` to `to_dict()`
- Add display line in `generate_report()` in the RISK METRICS section:
  ```python
  f"Max Drawdown Duration: {metrics.max_drawdown_duration} bars",
  ```

---

### 6. Manual p-value one-tailed conversion — fragile, not a bug but worth cleaning

**File:** `strategy_analyzer.py`
**Lines involved:** 406-412

**Current code:**
```python
t_stat, p_value = stats.ttest_1samp(pnls, 0)
if t_stat > 0:
    p_value = p_value / 2
else:
    p_value = 1 - (p_value / 2)
```
This manual conversion from two-tailed to one-tailed is mathematically correct for symmetric distributions but is brittle and ugly.

**Fix:**
- Replace lines 406-412 with a single line:
  ```python
  t_stat, p_value = stats.ttest_1samp(pnls, 0, alternative='greater')
  ```
That's it. `alternative='greater'` tests the one-tailed hypothesis that the mean > 0. No manual division needed. The `alternative` parameter has been available since scipy 1.6.0.

---

### 7. Breakeven trades reset consecutive-loss counter — masks real losing streaks

**File:** `strategy_analyzer.py`
**Lines involved:** 275-303

**Current behavior:**
```python
else:  # breakeven
    current_losses = 0
    current_wins = 0
```
A sequence of 8 losses, 1 breakeven, 8 more losses registers as `max_consecutive_losses = 8` instead of 16. The breakeven resets both counters. This matters for position sizing and psychological robustness — a 16-trade non-winning streak is punishing even if one was a scratch.

**Fix:**
- Change the `else` block (lines 299-301) from:
  ```python
  else:
      current_losses = 0
      current_wins = 0
  ```
  to:
  ```python
  else:
      # Breakeven — do not reset either streak. A string of losses
      # interrupted by breakevens is still a psychologically meaningful
      # non-winning streak.
      pass
  ```
- Add a new field to `StrategyMetrics`: `max_consecutive_non_wins: int = 0` (next to `max_consecutive_losses` at line 55)
- Track it in the same loop — before the main if/elif/else, increment a `current_non_wins` counter that only resets on a win:
  ```python
  if trade.pnl > BREAKEVEN_TOLERANCE:
      current_non_wins = 0
      ...
  else:
      current_non_wins += 1
      max_non_wins = max(max_non_wins, current_non_wins)
  ```
- Return `max_non_wins` along with the existing tuple
- Add to `to_dict()` and `generate_report()`

---

## What NOT to change

- Do NOT modify `Trade.is_winner` in `strategy_base.py` — it is consumed by `persist_trade_outcomes.py`, `backtest_engine.py`, and the report generator. Changing it could break other parts of the pipeline.
- Do NOT add regime-conditional analysis — that belongs in Layer 1.
- Do NOT add buy-and-hold benchmark alpha — that's a separate feature, not a bug fix.
- Do NOT add Kelly criterion — that's a position sizing concern that belongs at a higher layer.
- Do NOT change the Sortino downside threshold from zero — it's a valid design choice and changing it would alter metric interpretation without fixing a bug.
- Do NOT add multiple comparison correction (Bonferroni) to the t-test — the `is_significant` flag is a per-analysis diagnostic, not a family-wise hypothesis test.
- Do NOT refactor `analyze()` into sub-methods — this is a hygiene concern for a separate PR. The method is 98 lines and manageable.

---

## Verification

After implementing, run the qualification pipeline on a small subset to verify metrics still compute:
```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
python -c "
from src.layer0.strategy_analyzer import StrategyAnalyzer, StrategyMetrics
from src.layer0.backtest_engine import BacktestResult
import pandas as pd
from datetime import datetime, timedelta

# Quick smoke test
result = BacktestResult(strategy_name='test', asset='EUR_USD', granularity='H1')
result.equity_curve = pd.Series([100000, 100100, 100050, 100200, 100080],
    index=pd.date_range('2024-01-01', periods=5, freq='h'))
analyzer = StrategyAnalyzer()
metrics = analyzer.analyze(result)
print(f'Qualified: {metrics.qualified}')
print(f'Breakeven trades: {metrics.breakeven_trades}')
print(f'Profit concentration: {metrics.profit_concentration_ratio}')
print(f'Drawdown duration: {metrics.max_drawdown_duration}')
print(f'Same-bar exit pct: {metrics.same_bar_exit_pct}')
print('Smoke test passed')
"
```

Then run the full qualification on one strategy to confirm no regressions:
```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
python src/layer0/qualify_strategies.py --strategies Trend_EMA_ADX_H1 --granularities H1
```
