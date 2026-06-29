# FIX-S3-003 — Kelly position sizing is inert (always capped) and rests on a stale, wrong-signed edge

**Severity:** P1 (a whole subsystem — Kelly sizing — never influences the bet, and its edge premise is empirically false)
**Status:** Proposed
**Author:** Claude (System-3 risk-engine audit)
**Date raised:** 2026-06-26
**Scope:** `src/layer7/oanda_executor.py` — `FIXED_WIN_RATE`, `calculate_kelly_fraction`,
`calculate_position_size`; interaction with `src/layer4_executor/live_pipeline.py` fixed 3:1 RR
**Category:** (4) degenerate output · (3) violated premise
**Risk to live trading:** The advertised "Quarter-Kelly, edge-aware" sizing is theatre — every trade
risks exactly the 2% cap regardless of strategy edge, and the Kelly inputs claim a positive edge the
data contradicts.

---

## 1. Executive summary

The executor markets "Fractional Kelly position sizing (Quarter-Kelly with 2% hard cap)." Two facts
make the Kelly machinery vacuous:

1. **The inputs are constants, not the trade's edge.** Win rate is hardcoded
   `FIXED_WIN_RATE = Decimal('0.45')` and the reward:risk ratio in production is *always* 3.0 (Layer 4
   sets SL = 1×ATR, TP = 3×ATR for every trade). So `K = W − (1−W)/R` is the **same constant 0.2667
   for every signal, asset, strategy, and regime**. Quarter-Kelly is always 6.67%.
2. **That always exceeds the 2% cap, so Kelly never changes the bet.** 6.67% of the \$10,000 assumed
   balance is \$666.67 risk, `min(666.67, 200)` → **\$200 every time**. `final_risk_percent` is always
   exactly 2%. The Kelly fraction, the win rate, and Quarter-Kelly are computed, printed, and then
   discarded — `units = $200 / sl_distance` is the only thing that varies.

Separately, the hardcoded 45% win rate and the implied clean 3:1 payoff are **empirically false**:
the real win rate is 38.4% and the average realized R-multiple is **negative**.

---

## 2. Evidence

**A. Inputs are constant → Kelly is constant → cap always binds (recomputed).**
```
oanda_executor.py:57   FIXED_WIN_RATE   = Decimal('0.45')   # never updated from performance
oanda_executor.py:58   FRACTIONAL_KELLY = Decimal('0.25')
oanda_executor.py:59-60 MAX_RISK_PERCENT = 0.02 → MAX_RISK_DOLLARS = $200
oanda_executor.py:175  kelly = win_rate - ((1 - win_rate) / reward_risk_ratio)
oanda_executor.py:229  risk_capital = min(kelly_risk_dollars, max_risk_dollars)
live_pipeline.py:121-122 DEFAULT_ATR_MULTIPLIER_SL=1.0, DEFAULT_ATR_MULTIPLIER_TP=3.0  → RR always 3.0
```
Recomputation at the production-fixed inputs (W=0.45):

| R (TP/SL) | Kelly K | Quarter-Kelly | risk \$ | capped to | cap binds? |
|---|---|---|---|---|---|
| 1.0 | 0.0000 | 0.00% | \$0 | \$0 | no (units→min 1) |
| 1.5 | 0.0833 | 2.08% | \$208 | \$200 | yes |
| 2.0 | 0.1750 | 4.38% | \$437 | \$200 | yes |
| **3.0 (production)** | **0.2667** | **6.67%** | **\$666.67** | **\$200** | **yes, always** |
| 5.0 | 0.3400 | 8.50% | \$850 | \$200 | yes |

Production RR is fixed at 3.0, so the bottom-relevant row is always hit: risk is **always** \$200.
The Kelly fraction would only matter if RR < ~1.49 (where Quarter-Kelly < 2%), which the pipeline
never produces. The sizing collapses to a constant 2% of a constant \$10,000 — a degenerate output.

**B. The edge premise is false (real data, `fact_trade_outcomes`, n=134,520).**
```
overall win_rate = 0.3837   (hardcoded assumes 0.45)
overall avg r_multiple = -0.0664   (NEGATIVE — the population of strategies loses on average)
per-strategy win_rate spans 0.197 … 0.721
```
Kelly is a function of edge; here the edge input (45% / clean 3:1) is both **stale/wrong** (real 38.4%)
and **uniform** (one number for strategies whose true win rates range 0.197–0.721). With the real 38.4%
win rate at R=3, `K = 0.384 − 0.616/3 = 0.179` is still positive, yet the realized expectancy is
negative (avg R = −0.066) — i.e. the binary "+3R win / −1R loss" model Kelly assumes does not hold
(partial exits, slippage, fees, or wins not reaching full 3R). Kelly would happily up-size a system
the outcome table shows is net-losing.

**C. Even the `ASSUMED_BALANCE` is fixed at \$10,000** (oanda_executor.py:56), so the cap is \$200
regardless of the live account's actual equity — the sizing never scales with real capital.

---

## 3. Root cause

The Kelly path was built to be edge-aware but is fed (a) a hardcoded global win rate, (b) a
pipeline-fixed RR of 3.0, and (c) a hardcoded balance, then clamped by a cap that the constant inputs
always trip. The result is mathematically equivalent to "risk a flat 2% of \$10k" with an unused Kelly
ornament on top. The edge estimate is also never reconciled with `fact_trade_outcomes`, where it would
be revealed as wrong-signed.

## 4. Proposed fix

1. **Feed a real, per-context edge** to `calculate_kelly_fraction`: derive `win_rate` (and, better,
   empirical expectancy / realized average win and loss R) from `fact_trade_outcomes` *for the
   specific strategy_id × granularity × regime*, point-in-time (trailing window, no look-ahead). Pass
   it through Layer 4 instead of the module-global constant.
2. **Gate on expectancy, not just Kelly>0:** because realized avg R is negative, add a hard
   "no positive empirical expectancy → no trade (or minimum size)" check so Kelly cannot up-size a
   losing strategy. (This is the decay/edge-staleness guard the system currently lacks.)
3. **Use live account equity** for the cap base instead of `ASSUMED_BALANCE`, so 2% means 2% of real
   capital.
4. If the design truly intends a flat 2% risk, **delete the Kelly code** and say so — do not present
   inert Kelly math as an edge-aware sizer.

## 5. Validation plan

- Unit test: vary `win_rate`/`R` and assert position size *changes* below the cap; today it is
  invariant at the production RR. Assert that a strategy with negative empirical expectancy is sized
  to 0 (or minimum) under the new expectancy gate.
- Data check: recompute per-strategy expectancy from `fact_trade_outcomes` and confirm the sizer's
  win-rate input matches the strategy's real number (not 0.45).

## 6. Rollout / risk

The edge-lookup is additive and can run log-only first (compute the Kelly fraction it *would* use and
log it next to the current flat 2%). No order behavior changes until the expectancy gate / live-equity
base are turned on. Pure functions in one module; trivially revertible.

## 7. One-paragraph summary

The "Quarter-Kelly with 2% cap" sizer is inert: win rate is hardcoded at 0.45 and Layer 4 fixes RR at
3.0, so Kelly is always the constant 0.2667, Quarter-Kelly always 6.67%, and 6.67% of the fixed
\$10,000 balance (\$666.67) is always clamped to the \$200 cap — every trade risks exactly 2% and the
Kelly math never moves the size. The premise is also wrong: real win rate is 38.4% (not 45%) and the
average realized R-multiple across 134,520 outcomes is *negative* (−0.066), with per-strategy win
rates spanning 0.197–0.721, so a single stale global edge both mis-sizes and could up-size net-losing
strategies. Fix: feed a real point-in-time per-strategy edge, gate on positive empirical expectancy so
Kelly can't size a losing system, base the cap on live equity, and if a flat 2% is actually intended,
delete the Kelly ornament rather than present it as edge-aware.
