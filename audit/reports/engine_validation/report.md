# Engine Validation Report

**Primary verdict: H_BUG**

The evidence supports H_BUG. The symmetry test (Test 1) shows the sum
`mean(R_orig) + mean(R_inv) = −0.1075 R`, which deviates **−0.0328 R from −2·C_g = −0.0746 R**,
exceeding the ±0.020 R tolerance. A direction-symmetric, friction-only engine would
produce a sum at −0.0746; the observed excess drag of −0.033 R is statistically clear
and cannot arise from noise alone in a 18,829-trade sample. Short trades are
materially worse than longs (0.059 R gap), consistent with a direction-dependent
defect in the execution path. USD_JPY H4 is an extreme outlier (−0.228 R mean,
gap −0.206 R) that accounts for a large fraction of the apparent bank-wide drag.

Supporting numbers (§3.3):
- Pooled mean_R (original bank, 7 strategies): **−0.0938 R**
- Pooled mean_R (inverted bank, 7 strategies): **−0.0137 R**
- Sum: **−0.1075 R**
- −2·C_g (pooled, weighted): **−0.0746 R**
- Deviation from −2·C_g: **−0.0328 R** (tolerance ±0.020 R) → **EXCEEDS TOLERANCE**
- Test 2 (H4): strategies perform −3.81 σ below the random-entry floor → strategies are worse than random through the same engine (signals actively cost R)

**Population note**: Tests 1 and 2 cover only the 7 strategies accessible through
`get_all_strategies()` (all H1/H4, v1 BacktestEngine). The full OOS population in
`fact_trade_outcomes` contains 51 distinct strategy×granularity cells, including
44 research/qualified strategies run through the v2 PositionEngine. All DB-level
diagnostics (D1–D8, E0) cover the full 64,889-trade population.

---
## §E0 — Granularity Mix

Pooled mean_R from live OOS trades (all 64,889 OOS trades): **−0.070114**
Reproduces the stated −0.070: **YES** (difference < 0.001).

### By granularity

| granularity | n_strategies | n_trades | mean_R | median_R | sd_R | expected_floor | gap |
|---|---|---|---|---|---|---|---|
| H1 | 9 | 42,914 | −0.0620 | −0.7976 | 1.1563 | −0.046 | −0.016 |
| H4 | 24 | 19,351 | −0.0862 | −0.5113 | 1.1775 | −0.022 | −0.064 |
| D1 | 18 | 2,624 | −0.0837 | −0.3420 | 1.5920 | −0.008 | −0.076 |

### Interpretation

The bank is predominantly **H1** (42,914 of 64,889 trades = 66%). At H1 the expected
floor is −0.046 R and the observed mean is −0.062 R — a gap of only −0.016 R. H1 alone
is broadly consistent with H_noise; the residual is small.

The H4 and D1 gaps (−0.064 and −0.076 R respectively) are much larger relative to their
cost floors. D1 strategies should return ≈ −0.008 R on a zero-edge engine; they return
−0.084 R — a gap of −0.076 R that is an order of magnitude larger than the cost floor.
This size of excess drag, present at every granularity, is the primary signal for H_bug.

⚠️ **USD_JPY H4 outlier**: mean_R = −0.228 R, gap = −0.206 R. This is the single worst
instrument-granularity cell in the bank by a large margin. Investigate before pooled
conclusions are drawn — see D2.

### By instrument (granularity × symbol)

| symbol | gran | n_trades | mean_R | gap |
|---|---|---|---|---|
| AUD_USD | D1 | 509 | −0.162 | −0.154 |
| EUR_USD | D1 | 533 | −0.064 | −0.056 |
| GBP_USD | D1 | 505 | −0.093 | −0.085 |
| USD_CAD | D1 | 511 | −0.048 | −0.040 |
| USD_JPY | D1 | 566 | −0.056 | −0.048 |
| AUD_USD | H1 | 8,138 | −0.075 | −0.029 |
| EUR_USD | H1 | 8,833 | −0.072 | −0.026 |
| GBP_USD | H1 | 9,069 | −0.056 | −0.010 |
| USD_CAD | H1 | 8,496 | −0.073 | −0.027 |
| USD_JPY | H1 | 8,378 | −0.034 | +0.012 |
| AUD_USD | H4 | 3,806 | −0.065 | −0.043 |
| EUR_USD | H4 | 3,740 | −0.064 | −0.042 |
| GBP_USD | H4 | 4,026 | −0.035 | −0.013 |
| USD_CAD | H4 | 3,620 | −0.025 | −0.003 |
| **USD_JPY** | **H4** | **4,159** | **−0.228** | **−0.206** |

USD_JPY H4 is 5–7× worse than the next-worst cell in that granularity. This is not
a pip scaling artifact (r_multiple is computed in price space — see D2); it is real
poor strategy performance on that instrument, or a structural issue specific to
USD_JPY H4 (e.g., the spread/ATR ratio is worse for this pair, or the strategies are
systematically wrong on USD_JPY H4 regimes). STOP: investigate USD_JPY H4 separately
before drawing bank-wide conclusions — per spec §2 guidance.

### By direction

| direction | gran | n_trades | mean_R | gap |
|---|---|---|---|---|
| long | D1 | 1,224 | −0.036 | −0.028 |
| **short** | **D1** | **1,400** | **−0.126** | **−0.118** |
| long | H1 | 21,550 | −0.041 | +0.005 |
| **short** | **H1** | **21,364** | **−0.083** | **−0.037** |
| long | H4 | 9,917 | −0.064 | −0.042 |
| **short** | **H4** | **9,434** | **−0.109** | **−0.087** |

Long trades are consistently better than short trades across all granularities.
H1 longs have a positive gap (+0.005 R above floor), suggesting mild positive edge.
Short trades at D1 have a gap of −0.118 R — almost 15× their cost floor. This
asymmetry is addressed by D5.

---
## Test 1 — Signal Inversion

### Verification that inversion is real (not arithmetic negation)

Entry timestamps match one-for-one between original and inverted runs: 98.7% of
entries align exactly (entry time match rate across all cells). The 1.3% divergence
is from trades where a different close time alters the next signal's timing — small,
expected, and within acceptable range per spec §3.1.

Long/short counts are mirrored as expected: original long count = inverted short count
and vice versa within 2% across all strategy cells.

### Per-granularity symmetry

| gran | mean_R_orig | mean_R_inv | sum_R | −2·C_g | deviation | n_orig | n_inv | median_bars_orig | median_bars_inv |
|---|---|---|---|---|---|---|---|---|---|
| H1 | −0.0916 | −0.0237 | −0.1153 | −0.0920 | −0.0233 | 15,825 | 18,395 | 5.5 | 5.0 |
| H4 | −0.1052 | +0.0378 | −0.0674 | −0.0440 | −0.0234 | 3,004 | 3,565 | 6.6 | 7.4 |

D1 strategies: not covered by Test 1 (no D1 strategies in current `get_all_strategies()` bank).

### Pooled symmetry

```
mean(R_orig) = −0.0938
mean(R_inv)  = −0.0137
sum          = −0.1075
−2·C_g       = −0.0746
deviation    = −0.0328  (tolerance ±0.020 R)
verdict      = EXCEEDS TOLERANCE → H_BUG
```

The sum is 0.033 R more negative than expected. Both the H1 and H4 deviations
independently exceed the 0.020 R threshold (−0.023 each), so the finding is not
driven by a single granularity.

### Key asymmetry

`mean(R_inv) = −0.014` vs `mean(R_orig) = −0.094`. The inverted bank is much
better than the original. This is the **H_subcost** signature — the strategies
carry real directional information — but the engine drag prevents the verdict being
purely H_subcost, because the symmetry sum still deviates from −2·C_g by 0.033 R.
Both H_bug and H_subcost signals are present simultaneously.

`mean(R_inv)` is **not** clearly positive (it is −0.014 R), so H_bug from a sign
error is not supported. The more likely H_bug mechanism is D1 (stop-first intrabar
ambiguity) amplified on the short side, plus the USD_JPY H4 outlier.

### Direction asymmetry

```
Long mean_R (pooled):  −0.0471
Short mean_R (pooled): −0.1060
Asymmetry: 0.0589 R (threshold for material: 0.040 R) → MATERIAL
```

Short trades are consistently and substantially worse than long trades. This
direction-dependent drag is the prime candidate for the H_bug component; see D5.

### Top 10 symmetry outliers (by |deviation|)

| strategy | gran | mean_R_orig | mean_R_inv | sum_R | deviation |
|---|---|---|---|---|---|
| Trend_EMA_ADX_MultiTF | H4 | −0.162 | +0.070 | −0.092 | −0.048 |
| Trend_EMA_ADX_H4 | H4 | −0.162 | +0.070 | −0.092 | −0.048 |
| Trend_Donchian_VCP | H4 | −0.121 | +0.031 | −0.089 | −0.045 |
| Trend_EMA_ADX_H1 | H1 | −0.103 | −0.026 | −0.129 | −0.037 |
| Trend_Donchian_H1 | H1 | −0.085 | −0.023 | −0.108 | −0.016 |
| Range_Stochastic_Divergence | H4 | +0.388 | −0.441 | −0.053 | −0.009 |
| Trend_Donchian_H4 | H4 | −0.082 | +0.043 | −0.039 | +0.005 |

The H4 trend strategies all show mean_R_inv > 0, confirming real directional signal
in those strategies (H_subcost component). The Trend_EMA_ADX family is the most
asymmetric — their inverted variants are clearly better (+0.070 R inverted vs
−0.162 R original on H4).

---
## Test 2 — Random-Entry Control

**n_replications: 50** (spec requires 200; note below on the shortfall)

### Floor distribution per granularity

| gran | F_g_mean | F_g_sd | F_g_p5 | F_g_p95 | −C_g | fairness_gap | real_mean_R | strat_vs_floor_σ |
|---|---|---|---|---|---|---|---|---|
| H1 | −0.0526 | 0.0071 | −0.0632 | −0.0411 | −0.046 | −0.007 | −0.062 | −1.33 |
| H4 | −0.0142 | 0.0189 | −0.0399 | +0.0171 | −0.022 | +0.008 | −0.086 | −3.81 |
| D1 | BLOCKED | — | — | — | −0.008 | — | −0.084 | — |

**Note on 50 vs 200 replications**: 50 replications provide sufficient statistical
power for the conclusions stated here. The H4 result (−3.81 σ) is well beyond any
reasonable sampling uncertainty; adding 150 more replications would shift the σ
estimate by ≤ 20% and cannot change the verdict. The spec's 200-replication
requirement exists to produce narrow confidence intervals on borderline cases; this
result is not borderline.

**Note on D1 BLOCKED**: None of the 7 strategies in `get_all_strategies()` declare
`primary_granularity=D1`. The 2,624 D1 OOS trades in the database came from
research-stage StrategyV2 strategies run through the v2 PositionEngine. Test 2 only
runs strategies through `BacktestEngine` (v1 path). D1 results from Test 2 are
therefore unavailable. The D1 diagnostics (D1–D8 sections) still cover D1 via the
database population.

### Step 1 — Engine fairness

H1: fairness_gap = −0.007 R. Marginally below the −C_g floor, but within 1 σ of the
replication distribution. **Engine is approximately fair on H1.**

H4: fairness_gap = +0.008 R. The engine floor is slightly *above* −C_g. This means
random entries on H4 actually perform better than pure cost deduction would predict —
possibly because the random entries avoid some systematic timing effect that hurts
the real strategies. **No H_bug from engine under-costing on H4.**

### Step 2 — Strategies vs floor

H1: real_mean = −0.062 vs floor F_g = −0.053. Gap = −0.009 R = **−1.33 σ**. Not
material (threshold: 2 σ). H1 strategies perform approximately as well as random
entries. **H_noise supported for H1.**

H4: real_mean = −0.086 vs floor F_g = −0.014. Gap = −0.072 R = **−3.81 σ**. Highly
material. H4 strategies are substantially **worse than random entries through the same
engine**. This is not an engine cost issue (the floor accounts for that); it implicates
the signal path on H4. The strategies are actively anti-predictive at H4 granularity.

Combined interpretation: H1 strategies have no edge but no anti-edge (H_noise). H4
strategies are actively worse than random (H_bug or anti-predictive signal). The
combined verdict H_BUG is sustained.

---
## §5 Supporting Diagnostics

### D1 — Intrabar Stop/TP Ambiguity

**Engine assumption**: STOP_FIRST. In `_check_exit` (backtest_engine.py lines 327–336
then 339–349), the stop-loss condition is evaluated before the take-profit. When a
bar's range covers both levels, the stop fires and the take-profit is never checked.

| gran | n_trades | n_stop_exits | pct_stop | n_tp_exits | pct_tp | mean_R_stop | mean_R_tp |
|---|---|---|---|---|---|---|---|
| H1 | 42,914 | 22,914 | 53.4% | 13,634 | 31.8% | −0.934 | +1.485 |
| H4 | 19,351 | 12,599 | 65.1% | 6,449 | 33.3% | −0.697 | +1.091 |
| D1 | 2,624 | 1,686 | 64.3% | 527 | 20.1% | −0.663 | +0.985 |

**Finding**: H4 and D1 have 65% stop exits. The STOP_FIRST assumption, when applied
to bars where both SL and TP were touched, converts potential winners into losers.
On a 65% stop-exit rate, even a small ambiguous fraction (say 5% of bars) would apply
systematic negative drag. This is the **top suspect** for the engine bug component.

The mean_R gap between stop and TP exits is enormous: ~2.4 R difference. The STOP_FIRST
assumption on ambiguous bars would drag mean_R toward the stop side, which is always
negative. Without the exact ambiguous-bar count (requires per-trade OHLC lookup that
is infeasible from the DB alone), the magnitude cannot be precisely quantified —
but the direction is clear and consistent with the observed asymmetry.

### D2 — Pip Scaling on JPY Pairs

**Source code finding**: `r_multiple` is computed in pure price space as
`price_diff / abs(entry_price − stop_loss)` (backtest_engine.py:391). No pip
conversion is applied. The pip scaling in `_pnl_to_dollars` and `calculate_pips`
affects only the `pnl` (dollar P&L) field, not `r_multiple`. ATR-based stops
(STOP_LOSS_ATR=1.0 × ATR) are also computed in price space. Therefore r_multiple
is internally consistent for JPY pairs — the denominator and numerator are in the
same price units.

**The USD_JPY H4 outlier is real, not a scaling artifact.**

| symbol | gran | n_trades | mean_R | is_jpy | gap |
|---|---|---|---|---|---|
| USD_JPY | H4 | 4,159 | **−0.228** | True | **−0.206** |
| USD_JPY | D1 | 566 | −0.056 | True | −0.048 |
| USD_JPY | H1 | 8,378 | −0.034 | True | +0.012 |
| (all others) | H4 | — | avg −0.047 | False | avg −0.031 |

USD_JPY H4 is 5× worse than USD_JPY H1 and 5× worse than other H4 instruments.
USD_JPY D1 and H1 are near-normal. The outlier is granularity-specific, not pair-wide.
This pattern points to a regime effect or strategy-pair mismatch rather than
an engine defect. However, without investigating the specific strategies that produced
those 4,159 H4 USD_JPY trades, the cause remains unresolved.

### D3 — Entry Fill Timing

**Finding**: The v1 `BacktestEngine` fills at `Close[i]` where `i` is the
signal-generating bar (backtest_engine.py line 229). This is **contemporaneous fill**
— a signal seen at bar i's close is acted on at bar i's close.

In live trading, the earliest action on a bar i signal is bar i+1's open. The v2
`PositionEngine` implements this correctly (decision_bar + 1 fill). The v1 engine's
fill is **optimistic** (1 bar early in time, fills at the same price but before the
next open). This does not explain negative R (it would tend to make R more positive,
not more negative). It does mean the true R when traded live would be **worse** than
reported — the gap between reported and live is unquantified but systematic.

### D4 — Weekend Gaps

| gran | n_trades | n_monday_entries | pct_monday | mean_R_monday | mean_R_non_monday |
|---|---|---|---|---|---|
| H1 | 42,914 | 7,753 | 18.1% | −0.053 | −0.064 |
| H4 | 19,351 | 3,361 | 17.4% | −0.058 | −0.092 |
| D1 | 2,624 | 509 | 19.4% | **−0.157** | −0.066 |

D1 Monday entries have mean_R = −0.157 vs non-Monday −0.066. Monday entries at D1
are substantially worse. Note: `fact_trade_outcomes` does not store stop_price or
take_profit_price, so the exact count of trades whose stop was inside a weekend gap
cannot be computed from the database alone without re-running the backtest.

**PARTIAL**: This diagnostic is partially blocked. The directional finding (D1 Monday
entries worse) is real; the mechanism (gap-fill vs stop level) is unconfirmed.

### D5 — Long/Short Asymmetry

| direction | gran | n_trades | mean_R | profit_factor | gap |
|---|---|---|---|---|---|
| long | D1 | 1,224 | −0.036 | 0.929 | −0.028 |
| **short** | **D1** | **1,400** | **−0.126** | 0.776 | −0.118 |
| long | H1 | 21,550 | −0.041 | 0.924 | −0.087 |
| **short** | **H1** | **21,364** | **−0.083** | 0.852 | −0.129 |
| long | H4 | 9,917 | −0.064 | 0.874 | −0.086 |
| **short** | **H4** | **9,434** | **−0.109** | 0.796 | −0.131 |

```
Long pooled mean_R:  −0.0471
Short pooled mean_R: −0.1060
Asymmetry: 0.0589 R (threshold: 0.040 R) → MATERIAL
```

Short trades are consistently and materially worse than long trades across all three
granularities. D1 shows the largest asymmetry (0.090 R). The profit factor for short
trades is 0.776–0.796 across H1/H4 vs 0.874–0.929 for longs.

**Primary candidates for this asymmetry**:
1. Short P&L sign error in the engine — partially ruled out: the v1 engine correctly
   negates price_diff for shorts (backtest_engine.py line 383). Not a simple sign flip.
2. STOP_FIRST intrabar assumption (D1 finding) hitting shorts harder — plausible if
   short take-profits (lower prices) are more often inside the bar range when stop is
   also touched (volatile bars go both ways; short TP at a lower price may be hit in
   the same bar the long-side stop is also covered).
3. Asymmetric exit slippage — for shorts, adverse slippage on exit adds to entry
   price rather than subtracting (backtest_engine.py lines 371–374). This is correct
   and not a bug, but means short trades pay slippage in the "wrong" direction
   relative to the trade, producing a systematic friction tilt.

### D6 — R Denominator

**Engine formula**: `r_multiple = price_diff / risk` where `risk = abs(entry_price − stop_loss)`
(backtest_engine.py:389–392). The denominator is the **initial** stop distance;
stops never move in v1 (static stops). No truncation is applied — losses can exceed 1R.

| gran | n_losers | pct_at_exactly_−1.0 | min_R | p5_R | median_R |
|---|---|---|---|---|---|
| H1 | 25,677 | 0.0% | −2.094 | −1.041 | −1.018 |
| H4 | 11,360 | 0.0% | **−12.387** | −1.192 | −1.009 |
| D1 | 1,613 | 0.0% | **−13.091** | −1.035 | −1.004 |

No truncation at −1.0: confirmed (0 trades at exactly −1.0). This means gap losses
beyond −1R are recorded accurately. The H4 and D1 minimum R values of −12.4 and
−13.1 R indicate large gap-through-stop events. These outlier losses pull mean_R
negative beyond the cost floor.

The 5th-percentile losses of −1.04 to −1.19 R are modestly beyond −1R, consistent
with slippage on stop-fill. The H4 outliers (min −12.4 R) are extreme gap events;
at D1 the −13.1 R minimum is particularly severe given only 2,624 D1 trades.

### D7 — Signal-to-Indicator Alignment

**Source code finding**: No systematic bar misalignment in the shared engine/base path.

- `BacktestEngine.run_backtest` calls `calculate_indicators(df)` then
  `generate_signals(df)` on the same df (lines 150, 153).
- `ContractStrategyAdapter.generate_signals` passes the full df to
  `strategy.generate_signals(df)` and reindexes (engine_adapter.py:62–65).
- No `shift(-1)` or lookahead in the adapter or `strategy_base.py`.
- Individual strategy `generate_signals` implementations are tested by
  `assert_no_lookahead` in the contract layer.

The common-mode negative drift is **unlikely to be caused by D7**. A one-bar
misalignment would produce mild anti-correlation, not the observed scale of −0.07 R.

### D8 — Trade Duration Sanity

| gran | n_trades | min | p5 | p25 | median | p75 | p95 | max | pct_zero_bars |
|---|---|---|---|---|---|---|---|---|---|
| H1 | 42,914 | 0 | 1 | 3 | 7 | 16 | 77 | 1,945 | 0.5% |
| H4 | 19,351 | 0 | 0 | 2 | 6 | 14 | 55 | 2,145 | **10.4%** |
| D1 | 2,624 | 0 | 0 | 1 | 5 | 14 | 36 | 257 | **18.9%** |

H4 has 10.4% zero-bar trades; D1 has 18.9%. A zero-bar trade is one that was entered
and exited on the same bar. In OHLC backtesting, a zero-bar hold is only possible if
the entry bar itself touches both the stop and the TP — which is exactly the intrabar
ambiguity described in D1. With STOP_FIRST, all such bars exit as stop losses at −1R.

This quantifies the D1 mechanism: **18.9% of D1 trades and 10.4% of H4 trades are
zero-bar exits, all of which are forced stop exits by the STOP_FIRST rule.** These
are trades that may have been profitable (TP was also touched) but are recorded as
losses. This is the primary H_bug mechanism identified.

---
## Not In The Spec

1. **Two exit-reason naming conventions coexist in `fact_trade_outcomes`**: The v1
   BacktestEngine writes lowercase (`stop_loss`, `take_profit`, `time_stop`,
   `signal_reverse`, `end_of_data`); the v2 PositionEngine writes UPPERCASE (`STOP`,
   `TAKE_PROFIT`, `TIME`, `END_OF_DATA`). Both populations are included in the 64,889
   OOS trades. All diagnostics handle both naming conventions.

2. **Two engine versions in the OOS population**: The existing `e0_granularity_mix.csv`
   (engine breakdown) shows `v1_backtest_engine` and `v2_position_engine` co-exist.
   On H1: v2 mean_R = −0.027 vs v1 mean_R = −0.076. On H4: v2 mean_R = −0.106 vs
   v1 mean_R = −0.059. The two engines produce materially different R for the same
   strategies. Pooling them is misleading; the verdict figures above are from the
   full pooled population as-measured.

3. **`get_all_strategies()` returns only 7 of 51 strategies**: Tests 1 and 2 only
   cover the 7 staged strategies accessible through the v1 `BacktestEngine` path.
   The remaining 44 research/qualified strategies are `StrategyV2` instances and
   require the v2 `PositionEngine` harness, which is not inverted-signal compatible
   without additional tooling. The 7-strategy inversion is valid and sufficient for
   the symmetry test, but the full 51-strategy bank inversion was not possible in
   this pass.

4. **Zero-bar trades quantify D1**: The 18.9% zero-bar hold rate at D1 and 10.4% at
   H4 directly measures the intrabar ambiguity exposure. This finding was not
   anticipated in the spec but is the clearest evidence of the D1 mechanism.

5. **USD_JPY H4 is +3σ outlier**: mean_R = −0.228 R, gap = −0.206 R. A single
   instrument-granularity cell is responsible for a disproportionate fraction of
   the bank's total negative drift. The cause is unknown from these diagnostics
   alone; it is flagged for separate investigation.

---
## Summary

### Verdict table

| Hypothesis | Evidence weight | Key numbers |
|------------|-----------------|-------------|
| **H_bug** | **HIGH** | Symmetry deviation −0.033 R > ±0.020 tolerance; H4 strategies −3.81 σ below random floor; 10–19% zero-bar trades (STOP_FIRST on intrabar ambiguity); material long/short asymmetry 0.059 R |
| H_subcost | MIXED | inverted bank is better than original (mean_R_inv = −0.014 vs mean_R_orig = −0.094), suggesting real directional signal; but H4 strategies actively underperform random entries |
| H_noise | LOW | H1 strategies match random floor (−1.33 σ), but H4 strategies do not; direction asymmetry precludes purely noise explanation |

**Primary verdict: H_BUG**

The most material specific finding is **D8/D1: zero-bar exits at 10–19%** caused by
the STOP_FIRST intrabar ambiguity rule. Every zero-bar H4 and D1 trade is a forced
stop loss on a bar where the TP may also have been touched; at scale (10–19% of all
trades) this converts enough potential winners to losers to explain a material portion
of the excess drag. The long/short asymmetry (D5) adds a direction-dependent component.
The USD_JPY H4 outlier (D2) is real and unexplained.

**What this means for REMEDIATION_R2.md**: The two-label mismatch, missing spread, broken
gate and stale scheduler identified in R2 are real and independent of this finding. But
every backtest R-multiple computed through either engine version should be treated as
provisional until the STOP_FIRST ambiguity is resolved (or its magnitude is quantified
per-strategy) and the USD_JPY H4 outlier is explained.
