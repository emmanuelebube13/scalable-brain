# Top 10 candidates — metrics, rules, and a column for you to assign a regime

Generated 2026-08-23 from qualification run `77f83887`, granularity as measured.
Minimum 30 OOS trades. **Strategy 10 (`Range_Stochastic_Divergence`) excluded** — look-ahead
contaminated, its metrics are fiction.

## Read this before assigning anything

**Two rows are not candidates.**

- **#1 `reference_pullback_continuation` is not a strategy.** Its own docstring: *"This is
  not one of the 51 CSV strategies. It is a deliberately synthetic example that exercises
  every hard feature the real ones need."* It is a test fixture that happens to rank first.
  Do not push it. That it tops the table on PF is a caution about the table, not a find.
- **#6 `Range_Bollinger_Aggressive` has no v2 module**, so its entry and exit are unknown
  rather than absent. It cannot be pushed until it is ported.

**Six of ten were measured in `UNKNOWN` regime.** That is not a regime — it is bars the
labeller could not classify. It means the result is *not* regime-conditional, and it is why
you cannot simply read the "regime measured" column as the regime to assign. Assigning one
by hand is a real decision, not a formality: the cell was never measured under the regime
you give it.

**Nothing here has a profit factor above 1.87.** That is the honest ceiling of this dataset.
Compare the live map — PF 8.28 on 13 trades, PF 13.58 on 20. Those are noise; these are not.

**R:R** = average winner ÷ average loser, derived as `PF × (1−W)/W`. Matches stored `avg_r`.

---

## 1. `reference_pullback_continuation`

| TF | regime measured | n | PF | Win | R:R | MaxDD | Sharpe | Recovery | OOS mo |
|---|---|---|---|---|---|---|---|---|---|
| **H4** | UNKNOWN | **40** | 1.87 | 47.5% | 2.07 | 3.3% | 0.84 | 4.53 | 54 |

- **Entry:** buy_stop
- **Exit:** fixed target
- **Indicators:** confirmed_swing_points, sma
- **What it does:** REFERENCE STRATEGY — the shape every Wave-2 strategy should copy. This is **not** one of the 51 CSV strategies. It is a deliberately synthetic example that exercises every hard feature the real ones need, so there is one correct pattern to imitate instead of 51 inventions: * a **multi-timeframe filter** (D1 trend gating H4 entries) done *causally* * **causal swing structure** ("the second consecutive higher high")

## 2. `nnfx_backtrader`

| TF | regime measured | n | PF | Win | R:R | MaxDD | Sharpe | Recovery | OOS mo |
|---|---|---|---|---|---|---|---|---|---|
| **D1** | UNKNOWN | **82** | 1.56 | 43.9% | 1.99 | 10.6% | 0.81 | 2.66 | 66 |

- **Entry:** market
- **Exit:** fixed target
- **Indicators:** atr

## 3. `h4_crossover_21_89_macd`

| TF | regime measured | n | PF | Win | R:R | MaxDD | Sharpe | Recovery | OOS mo |
|---|---|---|---|---|---|---|---|---|---|
| **H4** | Ranging | **40** | 1.47 | 62.5% | 0.88 | 3.0% | 0.84 | 2.37 | 24 |

- **Entry:** market
- **Exit:** fixed target
- **Indicators:** ema, macd, sma

## 4. `weekly_day_reversal_ea`

| TF | regime measured | n | PF | Win | R:R | MaxDD | Sharpe | Recovery | OOS mo |
|---|---|---|---|---|---|---|---|---|---|
| **D1** | UNKNOWN | **110** | 1.46 | 14.5% | 8.58 | 16.3% | 0.44 | 2.60 | 66 |

- **Entry:** market
- **Exit:** time exit
- **Indicators:** —
- **What it does:** Weekly Day Reversal EA.

## 5. `ma_crossover_swing`

| TF | regime measured | n | PF | Win | R:R | MaxDD | Sharpe | Recovery | OOS mo |
|---|---|---|---|---|---|---|---|---|---|
| **D1** | UNKNOWN | **50** | 1.45 | 40.0% | 2.17 | 6.4% | 0.53 | 1.70 | 54 |

- **Entry:** market
- **Exit:** fixed target, time exit
- **Indicators:** atr, ema, macd, sma
- **What it does:** ma_crossover_swing strategy.

## 6. `Range_Bollinger_Aggressive`

| TF | regime measured | n | PF | Win | R:R | MaxDD | Sharpe | Recovery | OOS mo |
|---|---|---|---|---|---|---|---|---|---|
| **H4** | High-Vol | **142** | 1.33 | 57.7% | 0.97 | 5.2% | 1.21 | 4.13 | 24 |

- **Entry:** — no v2 module
- **Exit:** — no v2 module
- **Indicators:** —

## 7. `weekly_gap_fade`

| TF | regime measured | n | PF | Win | R:R | MaxDD | Sharpe | Recovery | OOS mo |
|---|---|---|---|---|---|---|---|---|---|
| **H1** | High-Vol | **100** | 1.30 | 52.0% | 1.20 | 2.1% | 0.80 | 1.65 | 18 |

- **Entry:** market
- **Exit:** time exit
- **Indicators:** atr, calculate_pips
- **What it does:** Weekly Gap Fade — SPEC-weekly_gap_fade.md (CSV row 3). Fade the weekend gap: at the close of the week's first H1 bar, if the week opened at least 5 pips away from the prior Friday's close, take the opposite side and hold until Friday evening. No take profit, no tactical stop — the exit is time. NOTE 1 — THE DECISION FRAME IS H1, NOT W1 (§2, §10 #3). The gap is first knowable at the close of the week's opening H1 bar;

## 8. `mtf_swing_weekly_pivots`

| TF | regime measured | n | PF | Win | R:R | MaxDD | Sharpe | Recovery | OOS mo |
|---|---|---|---|---|---|---|---|---|---|
| **H4** | Ranging | **43** | 1.27 | 39.5% | 1.95 | 6.8% | 0.53 | 1.02 | 24 |

- **Entry:** market
- **Exit:** fixed target
- **Indicators:** ema, rsi
- **What it does:** Trend-aligned pullback entry using D1 regime and H4 EMA pullbacks.

## 9. `xard_ma_cross_daily_open`

| TF | regime measured | n | PF | Win | R:R | MaxDD | Sharpe | Recovery | OOS mo |
|---|---|---|---|---|---|---|---|---|---|
| **H1** | High-Vol | **172** | 1.25 | 39.5% | 1.91 | 14.5% | 1.13 | 1.91 | 18 |

- **Entry:** market
- **Exit:** fixed target
- **Indicators:** sma
- **What it does:** Xard MA Cross Daily Open strategy.

## 10. `long_wick_pinbar_8ema`

| TF | regime measured | n | PF | Win | R:R | MaxDD | Sharpe | Recovery | OOS mo |
|---|---|---|---|---|---|---|---|---|---|
| **D1** | UNKNOWN | **66** | 1.20 | 37.9% | 1.97 | 8.7% | 0.29 | 0.89 | 66 |

- **Entry:** market
- **Exit:** fixed target
- **Indicators:** ema
- **What it does:** Long Wick Pinbar 8 EMA Strategy.

---

## Assign a regime here

| # | strategy | TF | your regime | push? | note |
|---|---|---|---|---|---|
| 1 | `reference_pullback_continuation` | H4 | — | **no** | synthetic test fixture |
| 2 | `nnfx_backtrader` | D1 | | | 82 trades; two unreconciled harness runs — see notes |
| 3 | `h4_crossover_21_89_macd` | H4 | | | 62.5% win but R:R 0.88 — needs the high hit rate to hold |
| 4 | `weekly_day_reversal_ea` | D1 | | | 14.5% win, R:R 8.58 — one in seven, long losing runs normal |
| 5 | `ma_crossover_swing` | D1 | | | |
| 6 | `Range_Bollinger_Aggressive` | H4 | — | **no** | no v2 module; port first |
| 7 | **`weekly_gap_fade`** | **H1** | | | **best risk profile: 100 trades, 52% win, 2.1% MaxDD** |
| 8 | `mtf_swing_weekly_pivots` | H4 | | | |
| 9 | **`xard_ma_cross_daily_open`** | **H1** | | | 172 trades, largest clean sample here |
| 10 | `long_wick_pinbar_8ema` | D1 | | | |

## What blocks each from qualifying today

Live gates: PF ≥ 1.5 · Sharpe ≥ 0.8 · MaxDD ≤ 25% · Win ≥ 40% · Recovery ≥ 3.0 · OOS ≥ 12mo.

Across all 36 clean H1 cells, **PF and Recovery each fail 36/36** while OOS fails only 2/36.
Recovery ≥ 3.0 alongside PF ≥ 1.5 is asking for something that barely exists in FX — it is
the gate doing the rejecting, not the evidence.

Relaxing to **PF ≥ 1.25 and Recovery ≥ 1.5** admits rows 7 and 9. Both would then be
selected on 100 and 172 trades respectively — *better* evidence than anything currently
live, not worse.

## If you push one, push #7

`weekly_gap_fade` @ H1: fade the weekend gap — at the close of the week's first H1 bar, if
the week opened ≥5 pips from Friday's close, take the opposite side and hold to Friday
evening. **No take-profit and no stop; the exit is time.**

That last part matters for System 3: a time-only exit means `proposed_sl` and `proposed_tp`
are structural rather than tactical, and its 2.1% max drawdown over 100 trades is a
consequence of the gap being small and the hold being bounded — not of a tight stop.
