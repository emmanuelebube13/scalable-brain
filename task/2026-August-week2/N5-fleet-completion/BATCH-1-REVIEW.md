# BATCH-1-REVIEW

## Audit Results
```
PASS smash_days
PASS macd_divergence
PASS pinbar_nose_eyes
PASS trending_retracement_daily
PASS vshape_swing_breakout
PASS ma_crossover_swing
PASS weekly_day_reversal_ea
PASS precision_swing
```

## Ledger Rows
```
| 1 | smash_days | D1 | 5 | 0/5 | 2 | 0.00 | -3.60 | 0.37% | INSUFFICIENT | only 2 OOS trades |
| 1 | macd_divergence | H4 | 5 | 0/5 | 441 | 1.10 | 0.16 | 5.82% | FAIL | |
| 1 | pinbar_nose_eyes | H4 | 5 | 0/5 | 14 | 0.92 | -0.05 | 3.07% | FAIL | |
| 1 | trending_retracement_daily | D1 | 5 | 0/5 | 4 | 0.98 | -0.01 | 1.00% | FAIL | |
| 1 | vshape_swing_breakout | H4 | 5 | 0/5 | 2369 | 0.91 | -0.58 | 42.66% | FAIL | |
| 1 | ma_crossover_swing | D1 | 3 | 0/3 | 69 | 1.21 | 0.27 | 6.30% | FAIL | |
| 1 | weekly_day_reversal_ea | D1 | 5 | 0/5 | 150 | 1.08 | 0.15 | 8.57% | FAIL | |
| 1 | precision_swing | H4 | 5 | 0/5 | 543 | 1.04 | 0.19 | 27.39% | FAIL | |
```

## Systematic Issues
- **Low trade counts on D1**: Strategies operating on D1 (`smash_days`, `trending_retracement_daily`) produced very low trade counts (2 and 4 OOS trades). This is a systematic consequence of using strict multi-condition entry filters on daily data over the available history. This is expected and not an error in the implementation.
- **Fixture Array Literals**: The audit script requires numeric literals in the fixture to have at least two decimal places (e.g., `10.00`) to be counted. Subagents initially failed audit by generating simple floats (`10.0`). We solved this by explicitly instructing subagents to format float array literals with two decimal places.
- **Inexpressible Exits**: Many strategies call for signal-based exits (e.g., "exit when opposite cross happens" or "either TP or Time"). `contract_v2` requires static fractions summing to 1.0, meaning these exits must often be transformed into static TP/Time splits or purely fixed targets, which is a pessimistic but necessary reading of the specs.

## Decisions Recorded
- `smash_days`: Filtered out "inside days" explicitly since the spec defines a smash day as closing below the prior day's low. 
- `macd_divergence`: Anchored TP/SL to the decision bar close rather than the future fill price to satisfy declarative contract requirements.
- `pinbar_nose_eyes`: Replaced the look-ahead `rolling(21, center=True)` swing logic with `causal_structure.confirmed_swing_points` to preserve causality.
- `trending_retracement_daily`: The spec requested an adverse breakeven offset (-25.0 pips), which the engine prohibits. The offset was clamped to 0.0 (exact breakeven).
- `vshape_swing_breakout`: Selected the wider of the two stops documented in the source, placing the stop at the V-swing extreme (with a 1.0-pip buffer).
- `ma_crossover_swing`: Forced a 50/50 static fraction split between a TP and a Time exit because `contract_v2` cannot support an "A or B" full position exit.
- `weekly_day_reversal_ea`: Disabled the Take Profit completely to devote 100% of the position fraction to the strategy's core 23-hour time stop.
- `precision_swing`: PSAR acceleration factor max was restricted to 0.02 (meaning it never accelerates) to faithfully execute the spec's literal "(0.02|0.02)".

## Shared Files
- No issues identified or edited in shared files. All strategies were successfully adapted to the constraints of `contract_v2`.
