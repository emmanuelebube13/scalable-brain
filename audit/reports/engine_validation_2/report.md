# Engine Validation — Pass 2

**Supersedes `audit/reports/engine_validation/report.md`.** That pass's `H_BUG` verdict is
withdrawn — not because its arithmetic was wrong, but because three of the five things it
measured were measured against the wrong baseline, on a contaminated population, or not
measured at all.

Spec: `docs/proposed-fixes/system-1/EngineValidation2.md`.
Everything below is reproducible from four read-only scripts:

| script | produces |
|---|---|
| `src/audit/engine_validation2_replay.py` | `replay_trades.parquet` — both engines re-run through the exact `persist_all` dispatch, keeping the price columns the DB discards |
| `src/audit/engine_validation2_v2_levels.py` | `v2_declared_levels.parquet` — the v2 engine's **own** resolved exit levels, captured by instrumenting `_open_position` |
| `src/audit/engine_validation2_analysis.py` | Q1–Q7, Q10 |
| `src/audit/engine_validation2_q4_v2.py`, `_q8q9.py`, `_b3_fill.py` | corrected Q4 for v2, Q8/Q9, B3 |

No production table, artifact or config was written by any of them.

---

## 0. Why the DB alone could not answer this

`fact_trade_outcomes` stores **no prices**. No `entry_price`, no `exit_price`, no
`stop_loss`; `atr_sl_multiplier` and `atr_tp_multiplier` are 100% NULL across all 93,527
rows (`SELECT count(atr_sl_multiplier) FROM fact_trade_outcomes` → 0). Q2's instruction —
"measure the stop distance from realised trades, `|exit_price − entry_price|`" — is not
executable against the database.

Pass 1 concluded from this that parts of the spec were "infeasible from the DB alone". That
was the right observation and the wrong conclusion: the engines are deterministic and
re-runnable. This pass re-ran them and kept the prices. That single decision is what makes
Q2, Q4 and Q5.2 measurable at all.

**Engine tagging.** Every table below splits on `dim_strategy.engine`, which is
authoritative, not on the exit-reason letter case pass 1 used as a proxy. They agree on all
65,251 OOS rows (0 disagreements), so the proxy was sound — but the column exists and is
now what is used.

---

## 1. Findings table

Only `MEASURED` findings appear in the verdict.

| # | Finding | Label | Established by |
|---|---|---|---|
| F1 | The bank is **heterogeneous, not common-mode**: sd across cell means is 3.07× the mean cell SE | MEASURED | `q1_distribution_summary.csv` |
| F2 | Round-trip cost inside `r_multiple` is **0.5 pips**, not 1.0 — entry slippage cancels because the stop is computed from the slipped entry | MEASURED | `q2_cost_floor_by_engine_granularity.csv` (p25 = p50 = p75 = 0.5 in every cell) |
| F3 | v1 stops are **exactly 1.5 × ATR(14)**; the `ContractStrategyAdapter` value of 1.0 does not apply to these strategies. v2 stops **vary by strategy** (0.53–3.47 × ATR) | MEASURED | same file, `p25/p75_stop_atr_multiple` |
| F4 | Measured `C_g` is **half** pass 1's assumption, so every corrected gap is **worse**, not better. The Q2 gate does **not** trigger | MEASURED | `q2_corrected_e0.csv` |
| F5 | **v2 moves 18–34% of its stops** (breakeven/trailing); v1 moves 0%. `r_multiple` is not the same quantity in the two engines | MEASURED | `q3_stop_regime_by_engine.csv` |
| F6 | **No strategy runs under both engines** — the v1-vs-v2 comparison is fully confounded by strategy population and cannot support any engine claim | MEASURED | `q3_same_strategy_both_engines.csv` |
| F7 | Pass 1's headline (zero-bar trades are forced stop exits) is **false**: v1 has 2 zero-bar trades in 38,837; v2's zero-bar trades are *less* stop-heavy than its baseline at H4 and D1 | MEASURED | `q4_zero_bar_by_exit_reason.csv` |
| F8 | Real intrabar stop-first bias, resolved against **M15 bars**: **+0.003 R** (v1 H1), **+0.026 R** (v2 H4), **+0.029 R** (v2 D1), **+0.001 R** (v2 H1) | MEASURED | `q4_counterfactual_R_v2_measured.csv`, `q4_counterfactual_R.csv` |
| F9 | USD_JPY H4 is **two strategies, not the pair**. Excluding `smashing_forex_2` and `riding_trend_retracement`, USD_JPY H4 goes −0.229 → **+0.012** | MEASURED | `q5_usdjpy_h4_by_strategy.csv` |
| F9b | **Root cause found:** `generate_orders` is never given its pair, so 13 strategies take the pip size from `metadata.pairs[0]` — making every pip quantity **100× too small on USD_JPY**. In 4 of them it is load-bearing on the stop, giving stops **24×–47× too tight** | MEASURED | `q5_pip_idiom_by_strategy.csv`; `smashing_forex_2.py:62,88-90`; `contract_v2.py` |
| F10 | Direction asymmetry tracks **market drift**: Pearson r = 0.85 within H4, 0.71 within D1, 0.60 within H1 | MEASURED | `q6_drift_correlation.csv` |
| F11 | The drag is **not time-localised** — flat across 2019–2026 in every engine × granularity | MEASURED | `q7_mean_R_by_year.csv` |
| F12 | v1's contemporaneous fill is **not** optimistic: moving to next-open fill *improves* mean R by +0.002 (H1) / +0.003 (H4) | MEASURED | `b3_fill_timing_by_granularity.csv` |
| F13 | The **already-registered** orphaned rows (FIX-S1-017 §3, O-3/O-4) are 18.6% of the OOS population and move the bank mean R from −0.0701 to **−0.0776** | MEASURED | `replay_failures.csv` + §N1 |
| F14 | **No production query filters on `exit_reason`** — the B6 risk does not materialise anywhere outside audit scripts | MEASURED | repo-wide grep, §B6 |
| F15 | `Trend_EMA_ADX_H4` / `Trend_EMA_ADX_MultiTF` are **byte-identical trade-for-trade** (669 trades each) | MEASURED | §Q8 population |
| F16 | The **measured zero-edge floor is 1.6×–5.0× more negative than −C_g** in every cell — so every "gap vs −C_g" overstates underperformance | MEASURED | `q9_floor_summary.csv` (200 reps, 5.64M trades) |
| F17 | Inversion and random-entry **agree independently on the floor** (v1 H1: 0.04 σ apart) and on the signal edge (−0.0352 vs −0.0359). v2 H4's signal edge is **+0.0001 on 25,988 trades** — its drag is the exit configuration, not the entries | MEASURED | `q8_inversion_summary.csv`, `q9_floor_summary.csv` |

---

## Q0 — Replay fidelity (not in the spec, but nothing below is trustworthy without it)

| engine | gran | replay n | DB n | n ratio | replay mean R | DB mean R | \|Δ\| |
|---|---|---|---|---|---|---|---|
| backtest_engine_v1 | H1 | 22,239 | 30,699 | 0.724 | −0.0865 | −0.0762 | 0.0103 |
| backtest_engine_v1 | H4 | 4,245 | 8,138 | 0.522 | −0.1006 | −0.0578 | 0.0429 |
| position_engine_v2 | D1 | 2,623 | 2,658 | 0.987 | −0.0834 | −0.0912 | 0.0078 |
| position_engine_v2 | H1 | 12,343 | 12,404 | 0.995 | −0.0269 | −0.0258 | 0.0011 |
| position_engine_v2 | H4 | 11,247 | 11,352 | 0.991 | −0.1057 | −0.1061 | 0.0005 |

v2 reproduces to 0.5–1.3%. **v1 does not, and the shortfall is fully explained**: the three
`Range_Bollinger_*` strategies contribute 8,318 H1 and 3,844 H4 OOS rows to the DB and
cannot be instantiated by the current code — the already-registered O-3/O-4 orphaned rows
(FIX-S1-017 §3), quantified in §N1. 30,699 − 8,318 = 22,381 ≈ 22,239;
8,138 − 3,844 = 4,294 ≈ 4,245. The residual (~0.6%) is boundary drift in the walk-forward
fold assignment.

**Consequence:** every price-derived measurement (Q2, Q4, Q5.2) covers the reproducible
population only. Bank-level mean R statements are taken from the DB.

---

## Q1 — Common-mode or localised? `[GATE]`

Per strategy × granularity × engine, OOS, n ≥ 30. Population after Rule 5:
**46 cells** (52 total − 1 `INTEGRITY_DISQUALIFIED` − 1 duplicate − 4 with n < 30).

| engine | gran | k | min | p5 | p25 | median | p75 | p95 | max | sd of means | mean SE | **ratio** | >0 | >floor |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v1 | H1 | 3 | −0.098 | −0.097 | −0.089 | −0.080 | −0.064 | −0.052 | −0.049 | 0.025 | 0.012 | **2.19** | 0/3 | 0/3 |
| v1 | H4 | 5 | −0.142 | −0.138 | −0.122 | −0.078 | −0.016 | −0.010 | −0.009 | 0.060 | 0.037 | **1.62** | 0/5 | 1/5 |
| v2 | D1 | 16 | −0.616 | −0.548 | −0.114 | −0.057 | +0.031 | +0.370 | +0.476 | 0.274 | 0.132 | **2.07** | 5/16 | 6/16 |
| v2 | H1 | 6 | −0.548 | −0.423 | −0.046 | −0.026 | −0.007 | +0.002 | +0.004 | 0.216 | 0.057 | **3.82** | 1/6 | 2/6 |
| v2 | H4 | 16 | −1.043 | −0.878 | −0.056 | −0.040 | +0.001 | +0.095 | +0.254 | 0.341 | 0.082 | **4.17** | 5/16 | 5/16 |
| **ALL** | | **46** | −1.043 | −0.599 | −0.105 | −0.049 | −0.004 | +0.228 | +0.476 | **0.266** | **0.087** | **3.07** | **11/46** | **14/46** |

**The data shows scatter, not a common mode.** The spread across strategies is 3.07× their
own sampling error. A shared execution-path defect drags everything by roughly the same
amount; that is not what this looks like. The bank spans −1.04 R to +0.48 R, and 14 of 46
cells sit above their measured cost floor.

**Bank-level mean R was never the right statistic**, and this is the finding that frames
everything else. The −0.070 that started the investigation is the average of a population
whose members differ from each other by 4 R.

One qualification, stated because it cuts the other way: **all 8 v1 cells are below their
floor**, and their spread ratio (1.6–2.2) is the lowest in the table. That is the one place
in the bank where a common-mode signature would be visible. It is addressed in Q9.

---

## Q2 — The true cost floor `[GATE]`

**Measured, not derived.** For a trade that exits at a stop that never moved, the engine
writes `exit_price = stop_loss ∓ slippage`, so
`r = −1 − slippage/risk` **exactly**. Therefore `|r| − 1` *is* the per-trade cost in R
units, with no ATR reconstruction anywhere in the chain.

| engine | gran | clean stop exits | median stop (pips) | **stop ÷ ATR(14)** (p25/p50/p75) | median exit slip (pips) | **C_g** |
|---|---|---|---|---|---|---|
| v1 | H1 | 16,057 | 20.56 | 1.50 / **1.50** / 1.50 | **0.5** | **0.0243** |
| v1 | H4 | 4,165 | 40.56 | 1.00 / **1.50** / 1.50 | **0.5** | **0.0123** |
| v2 | D1 | 1,739 | 73.85 | 0.53 / **0.93** / 1.61 | **0.5** | **0.0070** |
| v2 | H1 | 8,085 | 46.80 | 1.98 / **2.17** / 3.47 | **0.5** | **0.0108** |
| v2 | H4 | 5,595 | 56.85 | 0.73 / **1.68** / 3.04 | **0.5** | **0.0089** |

Cross-check: 0.5 pips ÷ 20.56 pips = 0.02432 = the measured v1 H1 `C_g` to five decimals.

**The spec's two specific questions.**

1. **Is the ATR multiple 1.0, 1.5, or does it vary?** For v1 it is **exactly 1.5**
   (p5 = p95 = 1.500 at H1). The `ContractStrategyAdapter` value of 1.0 cited in
   `test2_generator_validity.md` governs a different code path and does not apply to these
   strategies — so §0(1)'s premise is **falsified**, and V4's 1.5× reconstruction was right.
   For **v2 it varies by a factor of six across strategies** (0.53 to 3.47), so a single
   pooled `C_g` is invalid there and per-strategy values are in
   `q2_measured_cost_floor.csv`.
2. **What is `applied_round_trip_pips`?** **0.5, not 1.0.** Both engines apply 0.5 pips
   adverse on entry *and* 0.5 on exit, but the entry slippage **cancels out of the R frame**
   in both — by two different routes, so this is worth stating precisely:

   - **v1:** `backtest_engine.py:229-243` computes the stop *from the already-slipped entry*,
     so the whole trade geometry translates and the risk denominator is unchanged.
   - **v2:** the stop is declared absolutely by the strategy and does **not** move with the
     fill — but `position_engine.realized_r_multiple` (`:146-152`) computes both
     `risk = |entry_price − initial_stop_price|` and the P&L from the same **fill** price, so
     the slippage appears identically in numerator and denominator and cancels again.

   The measurement confirms both: median `|r| − 1` on a clean stop exit is 0.0243 at v1 H1
   (0.5 ÷ 20.56 pips) and 0.0089 at v2 H4 (0.5 ÷ 56.85 pips) — one exit slippage, never two.
   This — not the ATR multiple — is where pass 1's 2× error came from.

### Corrected E0, original alongside

| engine | gran | n | mean R | pass-1 `C_g` | pass-1 gap (as printed) | pass-1 gap (Rule 7) | **measured `C_g`** | **floor** | **gap** |
|---|---|---|---|---|---|---|---|---|---|
| v1 | H1 | 30,699 | −0.0762 | 0.046 | −0.1222 | −0.0302 | 0.0243 | −0.0243 | **−0.0519** |
| v1 | H4 | 8,138 | −0.0578 | 0.022 | −0.0798 | −0.0358 | 0.0123 | −0.0123 | **−0.0454** |
| v2 | D1 | 2,658 | −0.0912 | 0.008 | −0.0992 | −0.0832 | 0.0070 | −0.0070 | **−0.0842** |
| v2 | H1 | 12,404 | −0.0258 | 0.046 | −0.0718 | +0.0202 | 0.0108 | −0.0108 | **−0.0150** |
| v2 | H4 | 11,352 | −0.1061 | 0.022 | −0.1281 | −0.0841 | 0.0089 | −0.0089 | **−0.0972** |

**GATE RESULT: the gate does not trigger, and it fails in the direction the spec did not
anticipate.** The spec expected a smaller stop → a larger `C_g` → H1 rising above its floor.
The opposite happened: the measured cost is *half* what pass 1 assumed, so every floor moved
closer to zero and **every gap got worse**. The corrected v1 H1 gap is −0.0519, not −0.030.

The pass-1 `H_BUG` verdict therefore **cannot be withdrawn on Q2's terms**. It is withdrawn
on the terms in Q1, Q4, Q8 and Q9 instead.

**A more important consequence.** `−C_g` was never the right floor. It is only the
*slippage* term. It says nothing about what a stop-first engine with a 1.5×ATR stop and a
~2:1 target pays a zero-information entry over discrete bars. That is an empirical quantity,
and Q9 measures it.

---

## Q3 — Separating the two engines `[GATE]`

### Q3.1 — Full metric set per engine

`q3_engine_split.csv` (granularity, instrument, direction). The pooled −0.070 decomposes as:

| engine | gran | n | mean R | median R | sd | gap |
|---|---|---|---|---|---|---|
| v1 | H1 | 30,699 | −0.0762 | −1.0049 | 1.170 | −0.0519 |
| v1 | H4 | 8,138 | −0.0578 | −1.0085 | 1.267 | −0.0454 |
| v2 | D1 | 2,658 | −0.0912 | −0.3637 | 1.585 | −0.0842 |
| v2 | H1 | 12,404 | −0.0258 | −0.0365 | 1.122 | −0.0150 |
| v2 | H4 | 11,352 | −0.1061 | −0.2198 | 1.111 | −0.0972 |

The **median** column alone shows these are different simulations: v1's median trade is a
full stop-out (−1.005); v2's is a fractional exit (−0.04 to −0.36).

### Q3.2 — Does v2 move stops? **Yes. MEASURED.**

| engine | gran | trades | **stops moved** | moved favourably | stop exits | **stop exits with positive R** | mean R on stop | median R on stop |
|---|---|---|---|---|---|---|---|---|
| v1 | H1 | 31,981 | **0.0%** | 0.0% | 16,057 | 0.0% | −1.026 | −1.024 |
| v1 | H4 | 6,132 | **0.0%** | 0.0% | 4,165 | 0.0% | −1.013 | −1.012 |
| v2 | D1 | 3,580 | **17.9%** | 17.9% | 2,360 | **12.6%** | −0.667 | −1.004 |
| v2 | H1 | 17,670 | **24.8%** | 24.8% | 10,890 | **23.6%** | −0.754 | −1.010 |
| v2 | H4 | 15,888 | **34.3%** | 34.3% | 11,017 | **20.8%** | −0.504 | −0.992 |

Every stop that moved, moved **favourably** — the engine's documented invariant ("stops never
widen") holds in 100% of 8,000+ observed moves. This is why `mean_R_stop` is −0.50 at v2 H4
while the *median* is −0.99: one fifth of v2's "stop" exits are stopped out **in profit**
after a trailing or breakeven move. Source agrees: `position_engine.py:50-53` keeps the
**initial** stop as the R denominator even after the working stop moves.

Add fractional take-profit legs (measured: 32% of v2 H1 trades have >1 TP leg; 37% of v2 H4
trades carry a trailing rule) and the conclusion is unavoidable: **`r_multiple` does not
denote the same quantity in the two engines.** Pooling them is a category error, and
`attribute.py` was doing exactly that (see §B2).

### Q3.3 — Why is v2 better on H1 and worse on H4?

**The question cannot be answered as posed, and the reason is itself the finding.**

`q3_same_strategy_both_engines.csv`: **0 of the 51 strategies with OOS trades appear under
both engines.** The v1 population is **10** legacy trend/range strategies; the v2 population
is **41** research strategies. (Of 67 registered in `dim_strategy`, 51 have OOS trades.)
There is no controlled comparison available anywhere in the data — the "cleanest possible
controlled test" the spec asks for does not exist.

So the v1/v2 mean-R difference is **fully confounded with strategy population**, and no
engine-quality claim can be extracted from it in either direction. Pass 1's engine split —
which it flagged as possibly its largest finding — is uninterpretable as an engine
comparison. It is a strategy-population comparison.

The three candidate causes the spec lists are settled individually: date coverage is
identical (all five cells span 2019-08 → 2026-09); stop regimes differ (Q3.2, measured);
strategy populations are disjoint (above).

### Q3.4 — Which engine produced the vetting population?

Latest qualification run `7fde532c`, **209 cells** (the spec's 158 is stale):

| engine | granularity | cells | trades |
|---|---|---|---|
| backtest_engine_v1 | H1 | 12 | 30,535 |
| backtest_engine_v1 | H4 | 27 | 8,097 |
| position_engine_v2 | D1 | 80 | 2,635 |
| position_engine_v2 | H1 | 24 | 12,319 |
| position_engine_v2 | H4 | 66 | 11,270 |

**No cell mixes engines, and none can**: `engine` is a property of `strategy_id`, and
attribution groups by `strategy_id`. That closes the specific worry the spec raised. What it
does not close is the one underneath it — the *gates* are applied to a mixture of two
populations whose `r_multiple` means different things, and the profit factor of a v2 cell is
not comparable to that of a v1 cell. Hence §B2.

---

## Q4 — Intrabar ambiguity, measured

### Q4.1 — The cheap direct test. Pass 1's headline is withdrawn.

| engine | gran | class | n | stop frac | tp frac | **excess over baseline** |
|---|---|---|---|---|---|---|
| v1 | H1 | multi-bar | 30,698 | 0.500 | 0.322 | — |
| v1 | H1 | **zero-bar** | **1** | 0.000 | 0.000 | −0.500 |
| v1 | H4 | multi-bar | 8,137 | 0.595 | 0.385 | — |
| v1 | H4 | **zero-bar** | **1** | 0.000 | 0.000 | −0.595 |
| v2 | D1 | multi-bar | 2,152 | 0.663 | 0.147 | — |
| v2 | D1 | **zero-bar** | 506 | 0.569 | 0.427 | **−0.094** |
| v2 | H1 | multi-bar | 12,173 | 0.616 | 0.306 | — |
| v2 | H1 | **zero-bar** | 231 | 0.675 | 0.325 | **+0.059** |
| v2 | H4 | multi-bar | 9,318 | 0.733 | 0.253 | — |
| v2 | H4 | **zero-bar** | 2,034 | 0.506 | 0.494 | **−0.226** |

Pass 1's headline — *"19% of D1 trades are forced stop exits from intrabar ambiguity"* —
rests on the claim that a zero-bar hold implies both levels were touched. The spec already
identified that as false reasoning. The direct query shows it is also false in fact:

- **v1 has 2 zero-bar trades in 38,837**, and both are `end_of_data`, neither a stop. The
  entire zero-bar phenomenon is a v2 artefact.
- At v2 **H4 and D1, zero-bar trades are *less* stop-heavy than the baseline** (0.506 vs
  0.733; 0.569 vs 0.663) — they split almost exactly 50/50 stop/TP at H4 (1,030 vs 1,004).
  That is the signature of a fast fractional exit, not of a forced loss.
- Only v2 H1 shows any excess at all, +5.9 points on 231 trades.

**WITHDRAWN.**

### Q4.2 — The real ambiguity count

Pass 1 called this "infeasible from the DB alone". It is feasible, and the levels do not
even need reconstructing for v2 — `_InstrumentedEngine` records what
`position_engine._open_position` actually resolved (`position_engine.py:729-737`).

A first attempt reconstructed the v2 take-profit from a winner-conditional R:R proxy
(`|exit − entry| / stop_dist` on TP exits) and produced 12.4% ambiguity at H4. **That number
is wrong and is superseded.** `exit_price` is the fraction-weighted average across *all*
exit fills, so on a multi-leg trade it sits far closer to entry than any declared target;
and at D1 the median v2 trade declares **no take-profit leg at all** (measured: `n_tp_legs`
median 0), so there is no second level to be ambiguous about. Those rows are tagged
`SUPERSEDED` in `q4_ambiguity_count.csv`; the authoritative v2 numbers are:

| engine | gran | OOS trades | frac declaring a TP | **ambiguous** | **% of OOS** |
|---|---|---|---|---|---|
| v2 | D1 | 2,623 | 0.426 | 92 | **3.51%** |
| v2 | H1 | 12,343 | 0.924 | 675 | **5.47%** |
| v2 | H4 | 11,247 | 0.631 | 734 | **6.53%** |
| v1 | H1 | 22,239 | 1.000 | 95 | **0.43%** |
| v1 | H4 | 4,245 | 1.000 | 4 | **0.09%** |

(v1's levels are the *declared* ones — `take_profit_price` is recorded on every v1 trade, so
no proxy is involved there. The declared R:R varies by strategy: 1.0, 1.667, 2.0 and 4.0
across just six strategies, which is itself why a single pooled R:R would have been invalid.)

### Q4.3 — The counterfactual, and Q4.4 — resolving it with real M15 bars

The spec's B1 option 1 — "resolve with finer data" — is available: `fact_market_prices`
holds **2.6M M15 bars back to 2006**. For every ambiguous exit, the M15 bars inside that
exit bar were walked to find which level the market touched **first**. This is measurement,
not an assumption.

| engine | gran | ambiguous | M15: stop first | M15: TP first | M15: same bar | **mean R as-is** | coin-flip | **M15-resolved** | **bias vs M15 truth** |
|---|---|---|---|---|---|---|---|---|---|
| v1 | H1 | 95 | 38 | 25 | 32 | −0.0865 | −0.0804 | −0.0833 | **+0.0032** |
| v1 | H4 | 4 | 2 | 2 | 0 | −0.1006 | −0.0991 | −0.0987 | **+0.0019** |
| v2 | D1 | 92 | 22 | **68** | 2 | −0.0834 | −0.0618 | −0.0548 | **+0.0286** |
| v2 | H1 | 675 | 113 | **441** | 121 | −0.0269 | −0.0255 | −0.0262 | **+0.0007** |
| v2 | H4 | 734 | 206 | 175 | **353** | −0.1057 | −0.0447 | −0.0799 | **+0.0257** |

**This is the number pass 1 asserted was unquantifiable.** The stop-first rule is
pessimistic, and by how much is now known:

- **v1: +0.003 R.** Negligible — 6% of its −0.052 gap. The v1 population's underperformance
  is not the intrabar rule.
- **v2 H4: +0.026 R, v2 D1: +0.029 R.** Real, and about a quarter to a third of those cells'
  gaps (−0.097, −0.084). Worth fixing; not the whole story.
- **v2 H1: +0.001 R.** M15 says 441 of 675 resolved the wrong way, yet the R impact is
  nil — because those are fractional TP legs, so flipping them moves little R.

**Honest limit of the data:** 353 of the 734 ambiguous v2 H4 exits (48%) are unresolvable
even at M15 — both levels sit inside the same 15-minute bar. M5 would shrink that; it is not
ingested.

---

## Q5 — USD_JPY H4

### Q5.1 — Two strategies, not the pair

| strategy | engine | mean R USD_JPY | mean R other H4 | n JPY | n other | **Δ** | JPY share of its H4 trades |
|---|---|---|---|---|---|---|---|
| `riding_trend_retracement` | v2 | **−2.461** | −0.083 | 19 | 42 | **−2.379** | 31% |
| `smashing_forex_2` | v2 | **−1.081** | +0.018 | **883** | 1,040 | **−1.099** | **46%** |
| `liquidity_sweep_ob` | v2 | −1.306 | −0.986 | 7 | 32 | −0.321 | 18% |
| `Range_Bollinger_H4` | v1 | −0.078 | +0.008 | 245 | 1,036 | −0.085 | 19% |
| … 20 further strategies | | | | | | −0.04 … **+0.38** | ~18% each |

Most H4 strategies are **fine or better** on USD_JPY. `smashing_forex_2` alone contributes
883 of the cell's 4,190 trades at −1.081 R — and it trades USD_JPY at 46% weight against the
~18% an even split would give, so it is simultaneously the worst and the most concentrated.

**Arithmetic:**

| population | n | mean R |
|---|---|---|
| USD_JPY H4, all | 4,190 | **−0.229** |
| USD_JPY H4, excluding those two strategies | 3,288 | **+0.012** |
| Bank, all | 65,251 | −0.0701 |
| Bank, excluding USD_JPY H4 entirely | 61,061 | −0.0592 |
| Bank, excluding `smashing_forex_2` everywhere | 63,328 | **−0.0575** |

The spec's preliminary arithmetic (−0.070 → ≈−0.059, ~16% of the drag) is confirmed. But the
better framing is the last row: **one strategy carries 18% of the bank's total drag**, and
removing it does more than removing the whole pair-granularity cell.

### Q5.2 / Q5.3 — Stop geometry and the JPY pip factor. **There is a pip-scaling defect, and this is the root cause.**

The spec asked for the measured stop distance on USD_JPY H4 "in pips **and** in ATR
multiples", noting that "a stop that is anomalously tight in ATR terms would produce exactly
this median". It does, and it is:

| engine | symbol | n | median stop (pips) | median ATR (pips) | **stop ÷ ATR** |
|---|---|---|---|---|---|
| v1 | AUD_USD | 1,216 | 34.1 | 24.3 | 1.500 |
| v1 | EUR_USD | 1,242 | 38.2 | 27.9 | 1.500 |
| v1 | GBP_USD | 1,205 | 51.7 | 36.9 | 1.500 |
| v1 | USD_CAD | 1,228 | 42.1 | 29.9 | 1.500 |
| v1 | **USD_JPY** | 1,241 | 44.7 | 32.8 | **1.500** |
| v2 | AUD_USD | 3,031 | 77.2 | 25.4 | 2.848 |
| v2 | EUR_USD | 3,010 | 89.5 | 29.3 | 2.945 |
| v2 | GBP_USD | 3,456 | 100.8 | 39.5 | 2.595 |
| v2 | USD_CAD | 2,789 | 88.9 | 32.0 | 2.737 |
| v2 | **USD_JPY** | 3,602 | **59.8** | 34.8 | **1.872** (p25 = **0.097**) |

**Q5.3 first — the engine's pip handling is correct.** v1 lands on exactly 1.500 × ATR for
USD_JPY, identical to every other pair. `get_pip_value` returns 0.01 for JPY against 0.0001
elsewhere, and the measured exit slippage is 0.5 pips on USD_JPY exactly as everywhere (Q2).
`r_multiple` is a pure price ratio and never touches a pip factor. **Nothing in
`backtest_engine`, `position_engine` or `indicators` mishandles JPY.**

**Q5.2 — the defect is in the strategies.** The v2 USD_JPY p25 of **0.097 × ATR** is the
tell: a quarter of v2's USD_JPY H4 trades run a stop under a tenth of an ATR. Decomposed per
strategy (`q5_pip_idiom_by_strategy.csv`):

> **Population note.** Q5.1 above is the **DB OOS** subset (what vetting reads); the stop
> geometry below is the **full replay**, which is better powered for a mechanical measurement
> and needs the prices the DB does not store. So `smashing_forex_2` shows n = 883 / mean
> −1.081 in Q5.1 and n = 1,239 / mean −1.065 here. Same defect, two populations, both stated.

| strategy | stop÷ATR other pairs | stop÷ATR **USD_JPY** | **ratio** | mean R other | mean R **USD_JPY** |
|---|---|---|---|---|---|
| `riding_trend_retracement` | 3.083 | **0.065** | **0.021** (47× tighter) | +0.218 | **−4.585** |
| `smashing_forex_2` | 1.786 | **0.075** | **0.042** (24× tighter) | −0.055 | **−1.065** |
| `three_candle_swing_reversal` | 0.715 | 0.335 | 0.468 | +0.057 | **−1.153** |
| `liquidity_sweep_ob` | 0.628 | 0.510 | 0.813 | −0.744 | −1.271 |
| *(every other strategy with JPY trades)* | — | — | **0.87 – 1.02** | — | — |

**The mechanism, from source.** `smashing_forex_2.py:62`:

```python
pip = float(get_pip_value(self.metadata.pairs[0]))   # pairs[0] == "EUR_USD"
```

The pip value is resolved **once, from a hard-coded first element of the pairs list**, and
then reused for every pair the strategy trades. On USD_JPY it is 0.0001 instead of 0.01, so
every pip-denominated quantity is **100× too small**. In this strategy that reaches the stop
directly — `dist_cap = self.STOP_CAP_PIPS * pip` and `dist = min(dist_ema, dist_cap)`
(`:88-90`), so the 100×-too-small cap almost always wins. It also shrinks the declared
"fixed 200-pip profit" (`:111`) to 2 pips.

Same idiom, same consequence, in the other three: `riding_trend_retracement:167-171` binds
the stop with `max(entry − STOP_MAX_PIPS·pip, sl_conf − STOP_SWING_BUFFER_PIPS·pip)`;
`three_candle_swing_reversal:93` with `max(trig − 50·pip, min(lows) − 15·pip)`.

**The underlying cause is a contract gap, not 13 independent slips.**
`double_bottom_measured_move.py:47-53` names it exactly:

> *"`generate_orders` receives frames only, never the pair, so
> `get_pip_value(metadata.pairs[0])` would silently apply the EUR_USD pip (0.0001) to USD_JPY
> trades too — and USD_JPY is one of this strategy's five live pairs."*

`StrategyV2.generate_orders(frames)` has **no pair argument** (`contract_v2.py`). Three
strategies — `amazing_crossover`, `holy_grail_pullback`, `double_bottom_measured_move` —
noticed and wrote `_pip_size_from_price`, which infers the quote convention from the decision
bar's own close. The other thirteen reached for `pairs[0]`. The hazard was documented in the
repo before this audit; what was missing was any measurement of who had fallen into it.

**Why only four of the fourteen.** A repo-wide scan (`q5_pip_idiom_by_strategy.csv`) finds
**13 research strategies calling `get_pip_value(self.metadata.pairs[0])` in code** against
10 that resolve the pip per pair. But the bug only bites where a pip-denominated term is **load-bearing
on the stop** — a cap, a floor, or the stop itself. Where it is only a small buffer on a
price-derived level it is immaterial: `liquidity_grab_fade:190` uses
`stop_level = grab_extreme − 4.0 * pip`, so the error shifts the stop by 3.96 pips out of a
swing-derived distance and its ratio is 0.968, indistinguishable from the correctly-scaled
group.

The correctly-scaled group's ratios span 0.82–1.12, so **USD_JPY does genuinely carry a
slightly tighter ATR-relative stop when computed properly** — a real volatility
characteristic, not a defect. The four strategies above are 24×–47× outside that band.

One further note on `riding_trend_retracement`'s **−4.585 R**: with a stop 47× too tight, the
R *denominator* is tiny, so any ordinary adverse move is an enormous multiple of it. That is
why its mean sits far below −1 R, which would otherwise be impossible on a respected stop.

### Q5.4 — Time localisation: none

USD_JPY H4 mean R by year: −0.34, −0.25, −0.21, −0.13, −0.29, −0.14, −0.29, −0.27
(2019→2026) against −0.03 to +0.04 for the other pairs. **Uniformly bad, every year.** Not a
regime, not a data-vendor event, not a code change.

### Q5.5 — By engine

| engine | n | mean R | median R |
|---|---|---|---|
| backtest_engine_v1 | 1,610 | **−0.020** | −1.006 |
| position_engine_v2 | 2,580 | **−0.360** | −0.628 |

Entirely v2 — and within v2, entirely the two strategies in Q5.1.

---

## Q6 — Direction asymmetry, with the null tested first

Longs −0.048, shorts −0.093 across the OOS bank (n = 32,885 / 32,366).

### Q6.1 — Market drift control. **This is the explanation.**

| granularity | Pearson r (drift vs long−short gap) | Spearman | k |
|---|---|---|---|
| H4 | **0.855** | 0.837 | 10 |
| D1 | **0.707** | 0.500 | 5 |
| H1 | **0.600** | 0.271 | 10 |
| all 25 cells | 0.475 | 0.477 | 25 |

USD_JPY has by far the largest drift in the sample (mean bar return 3.8e−5 at H4, 2.3e−4 at
D1 — 4–7× every other pair; the yen went from ~105 to ~155 over the window) **and** the
largest long−short gap in four of five engine × granularity cells (+0.239, +0.193, +0.181,
+0.154). Mean long−short gap: **+0.162 for USD_JPY, +0.031 for everything else.**

Excluding USD_JPY, the pooled asymmetry falls from 0.0446 to **0.0273** — a 39% reduction
from removing one pair of five.

### Q6.2 — Cross-tab

`q6_direction_crosstab.csv`, all 50 direction × instrument × granularity × engine cells. The
gap is **not uniform: it is negative in 6 of the 25 pair-cells** — EUR_USD H1 v1 (−0.014),
AUD_USD H4 v1 (−0.013), EUR_USD H4 v1 (−0.062), USD_CAD H4 v1 (−0.0004), EUR_USD D1 v2
(−0.045), USD_CAD H4 v2 (−0.055). A slippage or sign-handling defect would not change sign
by instrument. Drift does.

### Q6.3 — Slippage symmetry

From source: `backtest_engine.py:233-236` (entry) and `:370-374` (exit) apply the identical
magnitude with opposite sign per direction; `position_engine.py:17-18` documents the same.

From data (`q6_slippage_symmetry.csv`), realised exit slippage on clean stop exits, split by
direction — **computed, not asserted**:

| engine | gran | long n | long p25/med/p75 | short n | short p25/med/p75 |
|---|---|---|---|---|---|
| v1 | H1 | 8,025 | 0.5 / 0.5 / 0.5 | 8,032 | 0.5 / 0.5 / 0.5 |
| v1 | H4 | 2,131 | 0.5 / 0.5 / 0.5 | 2,034 | 0.5 / 0.5 / 0.5 |
| v2 | D1 | 768 | 0.5 / 0.5 / 0.5 | 971 | 0.5 / 0.5 / 0.5 |
| v2 | H1 | 3,897 | 0.5 / 0.5 / 0.5 | 4,188 | 0.5 / 0.5 / 0.5 |
| v2 | H4 | 2,895 | 0.5 / 0.5 / 0.5 | 2,700 | 0.5 / 0.5 / 0.5 |

Every quartile is **exactly 0.5 pips** in all ten direction × cell combinations, on 35,641
trades. **Symmetric, confirmed both ways.** There is nothing here for a sign-handling defect
to hide in.

### Q6.4 — Interaction with Q4.3

The M15-resolved rule moves v2 H4 by +0.026 R and v2 D1 by +0.029 R, and those are the two
cells carrying the largest USD_JPY-driven asymmetry. The two findings are not independent,
but the drift correlation (0.855 at H4) survives the correction — the asymmetry is
predominantly drift, with the intrabar rule a second-order contributor.

**B5 is therefore not raised.** The spec's condition ("only if Q6 rules out market drift")
is not met: drift is not ruled out, it is the leading explanation.

---

## Q7 — Time localisation

| year | v1 H1 | v1 H4 | v2 D1 | v2 H1 | v2 H4 | bank |
|---|---|---|---|---|---|---|
| 2019 | −0.082 | +0.006 | −0.486 | −0.104 | −0.105 | −0.095 |
| 2020 | −0.057 | −0.059 | −0.119 | −0.014 | −0.115 | −0.062 |
| 2021 | −0.094 | −0.094 | −0.028 | −0.065 | −0.098 | −0.087 |
| 2022 | −0.073 | −0.046 | +0.020 | −0.021 | −0.103 | −0.061 |
| 2023 | −0.089 | −0.103 | −0.103 | +0.009 | −0.117 | −0.077 |
| 2024 | −0.071 | −0.034 | +0.047 | −0.048 | −0.102 | −0.063 |
| 2025 | −0.096 | −0.071 | −0.145 | +0.027 | −0.136 | −0.077 |
| 2026 | −0.038 | +0.004 | −0.175 | −0.072 | −0.054 | −0.049 |

**Flat.** The bank sits in a −0.049 … −0.095 band for eight consecutive years. v1 H1's
yearly sd is 0.020, v2 H4's 0.024 — both smaller than a single year's sampling error on the
smaller cells. The only outlier is v2 D1 2019 (−0.486), which is a **135-trade partial year** (the OOS
window opens in 2019-09).

A defect introduced by a code change or a data-vendor switch would produce a step. There is
no step. **Whatever this is, it has been there the whole time** — which is consistent with
absent edge and with a stop-first convention that has never changed, and inconsistent with
a regression.

---

## Q10 — Corrected diagnostics republished

`d2_per_instrument_R.csv` and `d5_direction_split.csv` are regenerated with the Rule 7 sign
convention and the measured per-engine `C_g`, split by engine, with
`assert expected_floor < 0` and `assert gap == mean_R − expected_floor` enforced in code
(`engine_validation2_analysis.py:_assert_rule7`).

**How wrong the originals were.** Both stored `expected_floor` as a *positive* number and
computed `gap = mean_R − expected_floor`, so every gap in those two files is wrong by
`2 × C_g` — compounded by pass 1's inflated `C_g` and by pooling the engines. Illustrated at
granularity level (`q2_corrected_e0.csv` carries all three columns side by side): for H1 the
figure as printed was **−0.122**, the same convention with the measured `C_g` gives −0.100,
and the correct Rule 7 gap for v1 H1 is **−0.052**. **The published number was 2.4× the real
one, and pass 1's headline gaps inherited that.**

---

## Q8 — Test 1, inversion, re-run

### Population (Rule 5, reported with counts)

Excluded before any statistic was computed: `Range_Stochastic_Divergence`
(`INTEGRITY_DISQUALIFIED`) and `Trend_EMA_ADX_MultiTF` (byte-identical duplicate of
`Trend_EMA_ADX_H4` — see N4). Remaining: **65 strategies**, 5 symbols.

Pass 1's Test 1 ran on 7 strategies, of which 2 were the same strategy and 1 was
integrity-disqualified — an effective population of 5.

### Three inversion constructions, because one does not fit both engines

| construction | engine | how |
|---|---|---|
| `inv_naive` | v1 | flip every bar's signal — what pass 1 did |
| `inv_pinned` | v1 | zero everywhere except the **original run's realised entry bars**, where the sign is flipped |
| `inv_mirror` | v2 | reflect each `OrderIntent` about its decision-bar close: direction flips, entry kind flips (`buy_stop`↔`sell_stop`, `buy_limit`↔`sell_limit`), and every absolute price (`entry_price`, `stop.price`, `price`-declared TP legs) maps `p' = 2·close − p` |

**Mirror validity, computed (Rule 3):** `q8_mirror_failures.csv` is **empty** — every v2
intent mirrored without a single geometry rejection, so `OrderIntent.__post_init__`'s
stop-side and target-side validation and the engine's `_stop_geometry_ok` admission check both
accepted 100% of mirrored intents. The mirror is not "valid by construction"; it is valid by
zero observed failures out of every intent the bank emits.

`inv_mirror` is the construction pass 1 did not have. It preserves stop and target distances
**exactly**, so the mirrored trade has identical geometry and only the direction differs —
which is what the symmetry invariant actually assumes. It also makes Q8 answerable for v2 at
all; a v2 strategy emits `OrderIntent`s, not a signal series, so a signal flip is undefined
there.

### Hard precondition, checked before any statistic

`|n_inv − n_orig| / n_orig ≤ 0.05` per cell. Failing cells are excluded and reported; a
variant with >50% of cells blocked is `BLOCKED` as a whole.

| variant | engine | gran | cells | passed | blocked | **verdict** | median divergence |
|---|---|---|---|---|---|---|---|
| `inv_pinned` | v1 | H4 | 15 | 11 | 27% | **TESTED** | 0.041 |
| `inv_pinned` | v1 | H1 | 10 | 6 | 40% | **TESTED** | 0.033 |
| `inv_mirror` | v2 | H1 | 30 | 21 | 30% | **TESTED** | 0.037 |
| `inv_mirror` | v2 | H4 | 76 | 42 | 45% | **TESTED** | 0.045 |
| `inv_naive` | v1 | H1 | 10 | 5 | 50% | **TESTED** | 0.126 |
| `inv_naive` | v1 | H4 | 15 | 5 | 67% | **BLOCKED** | 0.276 |
| `inv_mirror` | v2 | D1 | 84 | 33 | 61% | **BLOCKED** | 0.061 |

The pinned and mirror constructions cut the median divergence by 3–7× against the naive flip,
which is what they were built to do. **The divergence itself is diagnosed in N3** — it is
confined to event-driven signals (Donchian +25% to +34%) and absent from state-driven ones
(EMA_ADX −0.8%), and it is a property of a single-position engine's path dependence, not a
defect.

### Result on the TESTED cells, against the **measured** −2·C_g

| variant | engine | gran | n orig | mean R orig | mean R inv | **sum** | −2·C_g | **deviation** |
|---|---|---|---|---|---|---|---|---|
| `inv_pinned` | v1 | H1 | 33,100 | −0.0852 | −0.0149 | −0.1001 | −0.0486 | **−0.0515** |
| `inv_pinned` | v1 | H4 | 6,768 | −0.0501 | +0.0011 | −0.0490 | −0.0247 | **−0.0243** |
| `inv_mirror` | v2 | H1 | 24,244 | −0.0214 | −0.0257 | −0.0471 | −0.0216 | **−0.0255** |
| `inv_mirror` | v2 | H4 | 25,988 | −0.1217 | −0.1218 | −0.2434 | −0.0179 | **−0.2256** |
| `inv_naive` | v1 | H1 | 24,415 | −0.0884 | −0.0257 | −0.1142 | −0.0486 | **−0.0655** |

Every deviation is negative and outside pass 1's ±0.020 tolerance. Taken at face value this
*reinforces* pass 1's reading. **It should not be taken at face value, and the next two
subsections say why.**

### What the sum actually decomposes into

The sum and the difference are two independent quantities, and separating them is the whole
value of the test:

```
exit_tax    = (mean_R_orig + mean_R_inv) / 2     direction-INDEPENDENT cost per trade
signal_edge = (mean_R_orig − mean_R_inv) / 2     directional edge of the signal
```

| variant | engine | gran | **exit tax** | **signal edge** | −C_g | tax ÷ C_g |
|---|---|---|---|---|---|---|
| `inv_pinned` | v1 | H1 | **−0.0501** | **−0.0352** | −0.0243 | **2.06×** |
| `inv_pinned` | v1 | H4 | **−0.0245** | **−0.0256** | −0.0123 | **1.99×** |
| `inv_mirror` | v2 | H1 | **−0.0235** | **+0.0022** | −0.0108 | **2.18×** |
| `inv_mirror` | v2 | H4 | **−0.1217** | **+0.0001** | −0.0089 | **13.62×** |
| `inv_naive` | v1 | H1 | −0.0571 | −0.0314 | −0.0243 | 2.35× |

Three things fall out, and none of them is visible in the sum alone.

**1. v2 H4's drag is direction-symmetric to four decimal places.** Original −0.1217,
mirrored −0.1218, signal edge **+0.0001** on 25,988 trades. Flipping every trade's direction
changes nothing. A negative-edge signal would become positive under inversion; this does not.
**Whatever costs v2 H4 its 0.12 R per trade is a property of the exit configuration, not of
the entries.** Q4.3 attributes +0.026 R of it to the stop-first rule; the remainder is the
fractional-take-profit and trailing-stop regime (measured in Q3.2: 34% of stops move, R:R
0.745 — the first target is *closer* than the stop), which caps winners while leaving losers
at full size.

**2. v1's drag is not.** At v1 H1 the signal edge is **−0.035**: the original signals do
measurably worse than their own inverses. These are trend-following strategies, and over
2019–2026 on these pairs they were on the wrong side. That is absent (indeed negative) edge,
and no engine fix addresses it.

**3. The exit tax is ~2× C_g in four of five cells.** That is the honest structural cost of
running a stop-first, discrete-bar simulation with an ATR stop and a ~2:1 target, and it is
*not* what `−C_g` measures. `C_g` counts slippage only. **The symmetry invariant's target
should never have been −2·C_g; it should be 2·F, where F is the engine's zero-edge floor.**
Q9 measures F directly.

### Matched-pair sums

Where entry timestamps coincide exactly, `R_orig + R_inv` is computed per pair rather than on
aggregates (`q8_matched_pair_sums.csv`, n = 131,000+):

| variant | engine | gran | n pairs | mean | median | sd | p5 | p95 |
|---|---|---|---|---|---|---|---|---|
| `inv_pinned` | v1 | H1 | 64,483 | −0.105 | **+0.167** | 1.081 | −2.056 | +0.972 |
| `inv_pinned` | v1 | H4 | 10,299 | −0.048 | **+0.648** | 1.688 | −2.039 | +2.969 |
| `inv_mirror` | v2 | H1 | 29,464 | −0.048 | **+0.310** | 1.116 | −2.033 | +0.974 |
| `inv_mirror` | v2 | H4 | 21,132 | −0.310 | −0.073 | 1.301 | −2.403 | +1.035 |
| `inv_mirror` | v2 | D1 | 6,123 | −0.132 | −0.250 | 2.194 | −2.033 | +2.638 |

**The median pair sum is positive in three of five cells while the mean is negative** — the
distribution is left-skewed, not uniformly shifted. The p5 sits at ≈ −2.04 in every cell,
which is the both-sides-stopped-out case (−1 each, plus slippage): the mass that drags the
mean is trades where *both* the original and its mirror hit their stops, i.e. bars that
whipsawed through both barriers. That is a real cost of the geometry, and it is a very
different finding from "a uniform shift", which is what a mean alone would have suggested.
Pass 1 reported only aggregate means and could not have seen this.

### What Q8 does not establish

The TESTED subsets are 27–45% of their cells. Those are the cells whose trade counts happened
to match within 5%, which is a **selected** subset, not a random one — and N3 shows the
selection is not neutral (event-signal strategies are the ones that diverge, so they are
systematically under-represented in the TESTED set). The `exit_tax` and `signal_edge` figures
above are therefore sound for the cells they cover and should not be extrapolated to the
blocked ones without saying so. `v2 D1` and `v1 H4 naive` are `BLOCKED` outright and
contribute nothing.

This is the trade-off the precondition buys: a valid test on part of the population, instead
of an invalid one on all of it.

## Q9 — Test 2, random-entry floor, re-run

**200 replications per engine × granularity, as specified — 5,637,548 synthetic trades.**
Not fewer with an argument for sufficiency.

A zero-information entry (uniform random bar, fair-coin direction) run through the **real
engine** on the **real bars**, with the stop/target geometry taken from Q2's measurement of
the actual bank (`t2_geometry.json`). **D1 is covered** — pass 1 blocked it because
`get_all_strategies()` returns only v1-path strategies; building the intent directly against
`PositionEngine` removes that limit.

### The measured floor

| engine | gran | reps | trades/rep | **floor mean R** | sd of rep means | floor p5 | floor p95 | **−C_g** | **floor ÷ −C_g** |
|---|---|---|---|---|---|---|---|---|---|
| v1 | H1 | 200 | 7,130 | **−0.0506** | 0.0155 | −0.0726 | −0.0249 | −0.0243 | **2.1×** |
| v1 | H4 | 200 | 5,315 | **−0.0201** | 0.0181 | −0.0509 | +0.0095 | −0.0123 | **1.6×** |
| v2 | D1 | 200 | 3,232 | **−0.0353** | 0.0134 | −0.0565 | −0.0155 | −0.0070 | **5.0×** |
| v2 | H1 | 200 | 5,989 | **−0.0342** | 0.0174 | −0.0617 | −0.0057 | −0.0108 | **3.2×** |
| v2 | H4 | 200 | 6,519 | **−0.0269** | 0.0091 | −0.0413 | −0.0113 | −0.0089 | **3.0×** |

**The zero-edge floor is 1.6×–5.0× more negative than `−C_g` in every cell.** This is the
single most important number in the pass, because it retires the yardstick both the original
brief and pass 1 reasoned with. `C_g` counts slippage; the floor counts what a stop-first,
discrete-bar simulation with an ATR stop and a fixed target actually pays a coin flip. Any
"gap versus −C_g" — including every gap in §Q2's corrected E0 table — overstates
underperformance by the difference.

### Cross-validation against Q8 — two independent methods, one answer

Q8 derived a direction-independent **exit tax** from inverting real strategies. Q9 derives a
**floor** from random entries. They are computed from different populations by different
mechanisms and never share an intermediate. Where the synthetic geometry faithfully
reproduces the real one, they agree:

| engine | gran | Q8 exit tax | Q9 floor | difference | **in sd of the floor** |
|---|---|---|---|---|---|
| v1 | H1 | −0.0501 | −0.0506 | +0.0006 | **0.04 σ** |
| v1 | H4 | −0.0245 | −0.0201 | −0.0044 | **0.24 σ** |
| v2 | H1 | −0.0235 | −0.0342 | +0.0106 | **0.61 σ** |
| v2 | H4 | −0.1217 | −0.0269 | −0.0948 | **10.4 σ** ← does **not** agree |

Three of four agree inside a fraction of a standard deviation; v1 H1 agrees to 0.0006 R.
Two independent estimates of an unobservable quantity landing that close is the strongest
evidence in this report that both are measuring what they claim to.

**The fourth disagreement is explained, and the explanation is testable.** The synthetic
strategy declares one full-fraction take-profit and a time exit — a *static* geometry. v1's
real strategies are also static (1.5 × ATR, one target, a stop that never moves), and there
the two methods agree. v2 H4's real strategies are **not**: 34% of their stops move
(Q3.2) and they scale out fractionally. Test 2 therefore measures the floor for a
*simpler* strategy than the ones actually running at v2 H4.

**Consequence, stated rather than smoothed over:** for v1 (all granularities) and v2 H1 the
Q9 floor is the right baseline. **For v2 H4 and D1 it is not** — there, Q8's exit tax
(−0.1217 at H4), which uses each strategy's own real geometry via the intent mirror, is the
better estimate. This is a limitation of the Q9 construction, not a contradiction between
findings.

### The bank against its floor

| engine | gran | bank mean R | floor | **bank − floor** | **z** |
|---|---|---|---|---|---|
| v1 | H1 | −0.0865 | −0.0506 | −0.0359 | **−2.31** |
| v1 | H4 | −0.1006 | −0.0201 | −0.0806 | **−4.45** |
| v2 | D1 | −0.0834 | −0.0353 | −0.0481 | **−3.59** |
| v2 | **H1** | −0.0269 | −0.0342 | **+0.0073** | **+0.42** |
| v2 | H4 | −0.1057 | −0.0269 | −0.0788 | −8.63 *(geometry caveat above)* |

Pass 1's one surviving supporting number is here: it reported strategies at **−3.81 σ** below
the random floor at H4, and v1 H4 measures **−4.45 σ**. That finding is **confirmed**.

But it means something different once the floor is measured rather than assumed. **v1's
strategies are worse than random entries through the same engine** — and Q8 says by how much
and why: its signal edge is **−0.0352**, against a bank-minus-floor of **−0.0359**. Those two
numbers, again from independent tests, agree to 0.0007 R. The v1 shortfall *is* its negative
signal edge. There is nothing left for an engine defect to explain.

And **v2 H1 sits at its floor** (+0.42 σ, n = 12,343) — indistinguishable from random, which
is what "no edge and no defect" looks like.

### Cells above the measured floor

Against `−C_g`, 14 of 46 cells cleared the bar. Against the **measured** floor,
**20 of 46 do** (`q9_cells_vs_measured_floor.csv`) — 43% of the bank rather than 30%. The
wrong yardstick was not only inflating the deficit, it was mis-ranking the bank.

The largest excesses are all thin (`weekly_day_reversal_ea` +0.512 R on n=142 with SE 0.339;
`nnfx_backtrader` +0.370 on n=115 with SE 0.139), which is §N2 restated: the cells that look
best are the ones least able to prove it.

### Generator validity — computed, never argued

`q9_generator_validity.md` / `.csv`. Rule 3 forbids "by construction", so every claim is a
statistic, including the ones that fail:

| axis | result | reading |
|---|---|---|
| entry hour-of-day (KS) | **fails** in 4 of 5 cells (D up to 0.155) | **Expected and intended.** A zero-information entry is *supposed* to be unmatched on timing; matching it would import the strategies' timing edge into the control. Reported, not hidden. |
| direction share (χ²) | passes v1 H1 (p=0.118) and v2 H1 (p=0.313); **fails** v1 H4 (p=0.005), v2 D1 (p=0.0008), v2 H4 (p=3.4e−6) | The generator is a fair coin (0.4993–0.5005 long); the real bank runs 0.466–0.522 long. The mismatch is real and bounded: at the measured pooled long−short gap of 0.045 R, a 2.2 pp difference in mix moves the floor by **≈0.001 R** — two orders below the effects being discussed. |
| bars held (KS) | fails, D up to 0.50 | `bars_held` is an **outcome, not an input**. It differs because the exits differ, which is the thing being measured. Not a validity failure. |

The stop-distance axis the spec asked about is not compared here because it is not a free
parameter: the synthetic geometry is *set* from Q2's measured distribution, so a comparison
would be circular. What is reported instead is the input itself (`t2_geometry.json`, per
engine × granularity, with `rr_source` naming where each R:R came from).

---

# PART B — Fixes

Only findings labelled `MEASURED` in Part A are acted on.

### B1 — Intrabar ambiguity `[MEASURED: quantified, fix specified, not applied]`

Confirmed and quantified (Q4.3): **+0.026 R** at v2 H4, **+0.029 R** at v2 D1, **+0.003 R**
at v1 H1, **+0.001 R** at v2 H1 — measured against M15 ground truth, not assumed.

The spec's preference order resolves cleanly here, because option 1 is available:
`fact_market_prices` holds 2.6M M15 bars back to 2006, and the resolution has already been
computed for every ambiguous exit in the bank (`q4_m15_resolution*.csv`).

**Recommended (owner decision, not applied here):** option 1 for the resolvable 52%, option 2
for the rest.

1. Have `position_engine` resolve a same-bar stop/TP collision against M15 bars where they
   exist. This is the only correct answer rather than an assumption, and it is now known to
   be worth ~0.026 R at the granularity that matters most.
2. For the **48% of v2 H4 collisions unresolvable even at M15** (both levels inside the same
   15-minute bar), keep stop-first and record `exit_ambiguous = true`, reporting the
   ambiguous fraction alongside every metric.

**Why this is not applied in this pass.** Changing the engine's exit rule invalidates every
row of `fact_trade_outcomes`, which forces a full `persist_all` rebuild, which re-derives
attribution, the map and the weights. That is a pipeline-wide re-baselining, not a fix, and
it must be an explicit owner decision with a before/after published against a frozen
population. The before/after measurement it would need already exists in
`q4_counterfactual_R_v2_measured.csv`.

### B2 — Engine unification `[MEASURED: APPLIED]`

Confirmed by F5/F6: two engines, disjoint strategy populations, different stop regimes,
`r_multiple` not the same quantity. `attribute.py` was reading both into one table.

**Applied:**

- `attribute._load_trades(engine, engine_version)` — `engine_version` is now a **required
  positional argument with no default**, validated against `VALID_ENGINES`, and the filter is
  a parameterised `JOIN dim_strategy ... WHERE ds.engine = :engine_version`.
- `attribute.run(engine_version, ...)` and `--engine-version` on the CLI, `required=True`.
  `engine_version` is stamped into the attribution report JSON.
- A named opt-in, `attribute.POOLED`, for the three **read-only** callers that legitimately
  want the whole bank (`vetting/rank_all.py` — the selection report ranks everything;
  `vetting/designate.py` — looks up one named strategy; `analytics/publish_strategy_stats.py`
  — a descriptive export for System 3). It logs a `WARNING` naming the hazard. Pooling is now
  always a decision somebody made, never something that just happened.
- `scheduler/orchestrator.py` — the single governed promotion path — reads
  `attribute.AUTHORITATIVE_ENGINE_FOR_VETTING`, which is deliberately **`None`**, and raises
  with a pointer to this report if a retrain is attempted. Which engine may qualify a
  strategy is an owner decision, and Q3.3 established there is no data-driven tie-break: no
  strategy runs under both, so the engines cannot be compared. Setting that constant unblocks
  promotion.
- No trades were deleted. The other engine's rows are tagged and excluded, per the spec.

**Coverage — four new tests, all passing:**

| test | asserts |
|---|---|
| `test_load_trades_requires_an_engine_version` | a bare call raises `TypeError`; a bad value raises `ValueError` |
| `test_load_trades_engine_filter_partitions_the_population` | the two slices are non-empty, disjoint by `strategy_id`, and sum to the pooled total (verified live: 56,033 + 37,494 = 93,527) |
| `test_default_pipeline_refuses_to_run_until_an_engine_is_chosen` | `_default_pipeline` raises `RuntimeError` while the constant is `None` |
| `test_default_pipeline_passes_the_chosen_engine_through` | once set, that value is what reaches `attribute.run` — not a default |

Two existing tests (`test_load_trades_schema_aware_fallback` / `_present`) were updated for
the new signature.

**Before/after:** attribution is not re-run here because that writes to
`fact_strategy_regime_attribution`. The per-engine cell split it would produce is already
reported in Q3.4 (39 v1 cells / 170 v2 cells, no cell mixing).

### B3 — Contemporaneous fill in v1 `[MEASURED: no fix warranted]`

D3 was right that `backtest_engine.py:229` fills at `Close[i]` of the signal bar. Pass 1
called that "optimistic by an unmeasured amount". **Measured, it is not optimistic at all.**

`_NextOpenFillEngine` (an audit-only subclass overriding nothing but the entry leg) re-ran
the v1 bank filling at `Open[i+1]`:

| granularity | n (as-is) | n (next-open) | mean R as-is | mean R next-open | **Δ** |
|---|---|---|---|---|---|
| H1 | 22,206 | 22,191 | −0.08694 | −0.08489 | **+0.00205** |
| H4 | 3,480 | 3,477 | −0.10427 | −0.10085 | **+0.00342** |

Trade counts match to 0.07%, so this is a clean matched comparison. Moving to the honest fill
makes results **very slightly better**, not worse — and the magnitude (+0.002 to +0.003 R) is
an order of magnitude below the −0.045 to −0.052 v1 gap.

**No haircut is warranted and no migration is justified on these grounds.** Per-strategy
detail in `b3_fill_timing_by_strategy.csv`; the only cell that moves adversely is
`Trend_EMA_ADX_H4` at −0.004 R on 656 trades.

This also removes fill timing as a candidate explanation for v1's gap, which matters for the
verdict: the one identified v1 engine deviation is *conservative*, so v1's shortfall cannot
be an engine artefact that flatters the numbers.

### B4 — USD_JPY H4 `[MEASURED: a stop-sizing defect, and it is a one-line fix]`

The spec offers three outcomes — a stop-sizing defect, one broken strategy, or genuine
underperformance. **It is a stop-sizing defect** (Q5.2), located in strategy code rather than
the engine, affecting four strategies rather than one.

**The defect.** `get_pip_value(self.metadata.pairs[0])` resolves the pip value **once from a
hard-coded first pair** and reuses it for every pair the strategy trades. On USD_JPY that is
0.0001 instead of 0.01, so every pip-denominated quantity is 100× too small.

**Why it happens:** `StrategyV2.generate_orders(frames)` never receives the pair it is
running on, so a strategy that needs a pip size has to get it from somewhere else.

**The fix** has two levels. Per file: resolve the pip per pair inside the loop, or adopt the
existing `_pip_size_from_price` helper, which infers the convention from the decision bar's
close — `amazing_crossover`, `holy_grail_pullback` and `double_bottom_measured_move` already
do. Structurally: give `generate_orders` the pair, so the gap cannot be fallen into again.
That is a v2 contract change and belongs to whoever owns `contract_v2.py`.

**Scope, measured — do not fix all fourteen blindly:**

| priority | strategy | stop÷ATR ratio (JPY ÷ other) | mean R on USD_JPY | action |
|---|---|---|---|---|
| 1 | `riding_trend_retracement` | **0.021** | −4.585 | fix and re-run |
| 1 | `smashing_forex_2` | **0.042** | −1.065 | fix and re-run |
| 2 | `three_candle_swing_reversal` | 0.468 | −1.153 | fix and re-run |
| 3 | `liquidity_sweep_ob` | 0.813 | −1.271 | fix; note its non-JPY mean is −0.744, so the pip bug is not its main problem |
| — | the other 9 constant-pip strategies | 0.87 – 1.02, or no JPY trades | — | correct the idiom for hygiene; **no material effect measured** |

**Expected effect, already computed.** Removing the two priority-1 strategies takes USD_JPY
H4 from **−0.229 to +0.012**, and removing `smashing_forex_2` alone takes the bank from
−0.0701 to **−0.0575**. A *fix* is not the same as a removal — a correctly-scaled stop may
still lose — so those figures bound the opportunity rather than predict the outcome. The
honest before/after requires re-running the four strategies with the corrected pip
resolution, which is the natural next task.

**Not applied here.** Part A is read-only and Part B is scoped to the engine; editing four
research strategies changes what `persist_all` produces, which re-derives outcomes,
attribution, the map and the weights. It also needs a `forex-strategist` and `leakage-hunter`
pass per `src/layer0/CLAUDE.md`. Recorded as **O-28**. Neither priority-1 strategy is in the
live map today (`results/state/regime_strategy_map.json`, 12 cells — checked), so nothing
live is affected.

### B5 — Direction asymmetry `[NOT RAISED — precondition not met]`

The spec gates B5 on Q6 ruling out market drift **and** the Q4.3 interaction. Neither is
ruled out: drift correlates with the per-pair long/short gap at r = 0.85 (H4), 0.71 (D1),
0.60 (H1); the single highest-drift pair carries a +0.162 mean gap against +0.031 for the
rest; and removing it cuts the pooled asymmetry by 39%. Slippage symmetry was confirmed from
source **and** from data (Q6.3).

There is no residual for a P&L sign-handling defect to explain. **No fix.**

### B6 — Exit-reason vocabulary `[MEASURED: no fix needed, and the audit is the deliverable]`

The spec asks for every repo query that filters on `exit_reason` to be audited, because one
matching a single vocabulary would silently drop an entire engine's population.

**Repo-wide grep result: no production query filters on `exit_reason` at all.** It is written
by `persist_all.py:203/275` and `layer0/persist_trade_outcomes.py:307`, asserted on in
`tests/test_position_engine.py`, and read nowhere else.
`attribute.py`, `vet.py`, `metrics.py`, `gates.py`, `discrimination.py` and the gatekeeper do
not reference the column. `_load_trades` does not even `SELECT` it.

The one place the hazard did materialise is `src/audit/engine_validation_run.py:449-470` — pass
1's own `run_d1_intrabar`, whose docstring notes it filters `'stop_loss' (or 'STOP')`. So the
vocabulary split cost exactly one thing: a diagnostic in the report that raised the alarm.

**No normalisation layer is added.** Adding one would be a change with no caller, and this
repo's rule is that unused abstractions drift. What is worth having is the fact recorded:
`dim_strategy.engine` is the authoritative discriminator, and any future query that filters
on `exit_reason` must handle both cases or join to `dim_strategy` instead.

---

## Not in the spec

Four items. N1 and N4 are **prior-art credited** — they quantify or verify things already
registered elsewhere. N3 answers a sub-question the spec did raise (Q8: "diagnose why [the
counts diverge], because that is itself a finding about the strategies") and lives here for
length. Only N2 is genuinely unprompted.

### N1 — quantifying a known issue: the orphaned rows are 11% of the bank's headline

**This is not a new finding and is not claimed as one.** It is `FIX-S1-017 §3` ("Orphaned
rows — the upsert never deletes"), registered as **O-3** and **O-4** in `task/OPEN.md`, which
already names strategy_ids 7/8/9, the 17,583 orphaned rows, the `--reconcile` fix, and the
fact that none is in the live map ("that is luck, not design"). What this pass adds is its
**effect on the number the investigation was launched to explain**, which no prior document
quantifies.

The three strategies hold **12,162 OOS trades** (of 17,583 rows total) and cannot be
instantiated:

```
Range_Bollinger_H1          8,318 OOS trades   "not found in get_all_strategies()"
Range_Bollinger_Aggressive  2,563 OOS trades   "not found in get_all_strategies()"
Range_Bollinger_H4          1,281 OOS trades   "not found in get_all_strategies()"
```

Their newest trade is dated **2026-08-14** and their rows were last written **2026-08-15/16**
— three weeks stale, while live strategies carry trades to 2026-09-04. `persist_all`'s upsert
never deletes, so they persist indefinitely.

Detection already exists — FIX-S1-017 shipped `ghost_rows` into the writer state file and
surfaced it on the heartbeat. The gap was never detection; it is that nobody had priced the
consequence.

**New in this pass — the measured consequence:**

- They occupy **12 of the 209 cells** in the latest attribution run and contribute 18.6% of
  its trades.
- They move the bank's headline: mean R is −0.0701 with them, **−0.0776 without**. The
  −0.070 that started this whole investigation is 11% composed of code that no longer exists.
- They are the **entire** explanation for v1's poor replay fidelity (Q0).
- None currently passes the gates (best profit factor 1.33 < 1.50) and none is in the live
  12-cell map — so there is no live exposure **today**. That is luck, not design.

**The fix already exists and is already owner-gated:** `python -m src.outcomes.persist_all
--reconcile` (FIX-S1-017 §3, O-4), which deletes in the same transaction as the insert. Not
run here — it deletes production rows, and those rows are evidence for this report until it
is read. The contribution of this pass is a reason to prioritise it: **every bank-level
mean-R figure in both validation passes, including the −0.070 in the original brief, is 11%
composed of code that no longer exists.**

The nine `*_RA` strategies that fail with `No module named 'src.regime_aware'` are also
already registered under O-3, which further records that the module was **removed on purpose**
after the R3 trial — stale `dim_strategy` rows to deactivate, not code to restore. They have
produced no trades, so they affect no number here.

### N2 — The entire live qualification rests on cells of n = 5 to 66

Applying the documented gates (PF ≥ 1.5, Sharpe ≥ 0.8, WinRate ≥ 40%, MaxDD ≤ 25%,
Recovery ≥ 3.0, OOS ≥ 12mo) to the latest attribution run yields **5 cells**:

| strategy | engine | regime | gran | **trades** | PF | Sharpe | avg R |
|---|---|---|---|---|---|---|---|
| `Range_Stochastic_Divergence` | v1 | UNKNOWN | H4 | 66 | 3.40 | 2.34 | 1.000 |
| `liquidity_grab_fade` | v2 | Trending-Down | H4 | **13** | 8.28 | 1.74 | 3.679 |
| `macd_divergence` | v2 | High-Vol | H4 | **20** | 13.58 | 2.92 | 4.527 |
| `reference_pullback_continuation` | v2 | UNKNOWN | H4 | 40 | 1.87 | 0.84 | 2.069 |
| `weekly_day_reversal_ea` | v2 | High-Vol | D1 | **5** | 6.76 | 0.85 | 10.144 |

The top row is strategy 10 — `INTEGRITY_DISQUALIFIED`, correctly barred by `vet.py` before
the gates. The other four are v2 cells of 5, 13, 20 and 40 trades, three of which report an
avg R above 2.0 and one above 10.

`CLAUDE.md:212` already records that there is **no minimum-trade-count gate** and that
`trade_count` is only a ranking tie-break, "so a cell can pass everything on a small sample".
That is the design, stated. Q1 puts a number on what it costs: the mean per-cell standard
error across the bank is **0.087 R**, and these cells are an order of magnitude thinner than
the bank average. A profit factor of 13.58 on 20 trades is not a measurement of edge.

This is not a defect in the engine. It is the reason the bank-level question ("is the engine
broken?") was the wrong question to be asking.

### N3 — Why inversion changes trade counts (answers Q8's "diagnose why")

The spec asked why pass 1's inverted runs produced 26–32% more trades and called it "itself a
finding about the strategies". Measured, the divergence is **entirely confined to the
Donchian family**:

| strategy | n orig | n inverted | Δ | mean bars held (orig → inv) | signal_reverse frac |
|---|---|---|---|---|---|
| `Trend_Donchian_H1` | 42,662 | 53,382 | **+25.1%** | 8.92 → 7.94 | 0.216 → 0.310 |
| `Trend_Donchian_H4` | 5,579 | 7,106 | **+27.4%** | 11.62 → 11.35 | 0.021 → 0.038 |
| `Trend_Donchian_VCP` | 3,023 | 4,039 | **+33.6%** | 9.32 → 8.96 | 0.019 → 0.056 |
| `Trend_EMA_ADX_H1` | 24,415 | 24,220 | **−0.8%** | 7.68 → 6.78 | 0.233 → 0.309 |
| `Trend_EMA_ADX_H4` | 2,110 | 2,106 | **−0.2%** | 9.42 → 9.07 | 0.018 → 0.073 |

The mechanism: `BacktestEngine` holds one position at a time, so the set of bars on which it
is *available to enter* is path-dependent. Inverting turns a breakout that ran into a fade
that got stopped, so holds shorten and the engine is flat more often.

Why that adds trades for Donchian and not for EMA_ADX: **Donchian emits event signals**
(non-zero only on a breakout bar), so extra flat time exposes it to genuinely more distinct
events. **EMA_ADX emits state signals** (non-zero on most bars while the condition holds), so
its trade count is bounded by state transitions and extra flat time just means re-entering on
the next bar.

Neither is a bug. It is why the symmetry test's precondition fails and why the entry-pinned
inversion construction (§Q8) is the right one.

### N4 — `Trend_EMA_ADX_H4` and `Trend_EMA_ADX_MultiTF` are the same strategy

**The spec found this** (§0(5): "byte-identical (n=456/455, mean −0.16216613985873274 in
both)"). Verified here more strongly than equal means: **byte-identical trade-for-trade** —
669 OOS trades each, matching on symbol, entry time, direction, `r_multiple` to 10 decimals
and exit reason, checked by SHA256 over the sorted trade tuple. Two `strategy_id`s (2 and 3),
one strategy, double weight in every pooled statistic.

Effect on the bank is small (−0.0701 → −0.0694 deduplicated) because both are small cells.
Effect on pass 1's Test 1 was not small: 2 of its 7 strategies were the same one.

**What is new:** a repo-wide sweep for identical OOS trade-set hashes across all 52
strategy × granularity cells found **exactly one such pair** — this one. The rest of the bank
is genuinely distinct, so no further deduplication is needed and no other pooled statistic is
double-counting.

---

## Verdict

## **LOCALISED DEFECTS ONLY**

Pass 1's `H_BUG` is **withdrawn**. Not because the engine was never suspect, but because the
suspicion rested on comparing the bank to `−C_g`, and `−C_g` is 1.6×–5.0× too shallow a bar
(Q9). Measured against the floor the engine actually produces, the picture resolves into
named cells and a residual that is not a defect at all.

### The defects, each named and quantified

| # | defect | mechanism | magnitude | population |
|---|---|---|---|---|
| 1 | **Pip-scaling in strategy code** | `generate_orders` is never passed its pair, so 13 strategies take the pip size from `metadata.pairs[0]`; on USD_JPY every pip quantity is **100× too small** | stops **24×–47×** too tight; **+0.0180 R** to the bank when removed | 4 strategies (`riding_trend_retracement`, `smashing_forex_2`, `three_candle_swing_reversal`, `liquidity_sweep_ob`) |
| 2 | **Orphaned rows** *(already O-3/O-4)* | `ON CONFLICT DO UPDATE` never deletes, so strategies that stopped loading keep their trades | **−0.0075 R** — they were *flattering* the bank | 12,162 OOS trades, 12 of 209 attribution cells |
| 3 | **Duplicate registration** | one strategy under two `strategy_id`s, byte-identical trades | +0.0007 R | 669 trades |
| 4 | **Look-ahead** *(already known)* | strategy 10, `INTEGRITY_DISQUALIFIED` | −0.0007 R | 91 trades |

### The bank recomputed

| population | n | mean R |
|---|---|---|
| as published — the −0.070 that opened the investigation | 65,251 | **−0.0701** |
| − integrity-disqualified, − duplicate | 64,491 | −0.0701 |
| − orphaned rows (code that no longer loads) | 52,329 | −0.0776 |
| **− the four pip-scaling-defect strategies** | **50,161** | **−0.0596** |

The four pip-bug strategies are worth **+0.0180 R** — a larger correction than removing the
entire USD_JPY H4 cell, and the single biggest lever found in either pass.

### What is left after the defects, and why it is not one

The residual **−0.0596** sits below zero and below most cells' floors, and three independent
lines of evidence say that is **absent-to-negative edge**, not a further defect:

- **v1 H1**: signal edge **−0.0352** (Q8 inversion) against bank-minus-floor **−0.0359**
  (Q9 random control). Two independent tests, agreeing to 0.0007 R. The shortfall *is* the
  signals being on the wrong side; trend-following on these five pairs over 2019–2026.
- **v2 H1**: **+0.42 σ** above its floor on 12,343 trades. Indistinguishable from random —
  exactly what no-edge-and-no-defect looks like.
- **v1's one engine deviation is conservative, not optimistic.** Moving the fill from
  `Close[i]` to `Open[i+1]` *improves* mean R by +0.002/+0.003 R (B3). There is no direction
  in which fill timing flatters v1's numbers.

### The one genuine engine-level effect, and why it is not called a defect

The stop-first rule on bars containing both levels costs, against **M15 ground truth**:
**+0.026 R** (v2 H4), **+0.029 R** (v2 D1), **+0.003 R** (v1 H1), **+0.001 R** (v2 H1). Real,
and about a quarter of the v2 H4/D1 gaps.

It is a **documented, deliberately conservative convention**, not an error — the spec itself
notes that TP-first "is optimistic in the opposite direction". What was missing was its price.
It now has one, and B1 specifies the fix: resolve against M15 where possible (52% of
collisions), flag `exit_ambiguous` on the rest.

The larger v2 H4 exit cost — **−0.1217 R**, direction-symmetric to **+0.0001 R** on 25,988
trades — is the *configured* exit regime doing what it was configured to do: a first target
at 0.745 R (nearer than the stop) with trailing on 34% of positions caps winners while
leaving losers whole. That is a strategy-design question, not an engine fault.

### What was measured, and what it cost to assume instead

Every pass-1 supporting number, re-measured:

| pass-1 claim | outcome |
|---|---|
| symmetry deviates −0.033 R from −2·C_g | **wrong baseline.** −2·C_g is not the target; 2×floor is. Against the measured floor the v1 H1 sum agrees to **0.0006 R** |
| shorts materially worse — direction-dependent defect | **explained by market drift** (r = 0.85 within H4); B5 not raised |
| USD_JPY H4 is an extreme outlier | **true, and now root-caused** to a 100× pip error in 4 strategies |
| 19% of D1 trades are forced stop exits | **false.** v1 has 2 zero-bar trades in 38,837; v2's are *less* stop-heavy than baseline |
| strategies are −3.81 σ below the random floor at H4 | **confirmed** (v1 H4: −4.45 σ) — and it means absent edge, not a bug |

One of five survives, and it points the opposite way from the verdict it was used to support.

### Confidence, and what would change it

**High** for: the pip-scaling defect (source-level, with an ATR-normalised measurement and a
mechanism), the floor being far below `−C_g` (200 replications, two methods agreeing to
0.04 σ), and the withdrawal of the zero-bar finding (a single query).

**Lower** for: the v2 H4/D1 numbers, where the Q9 floor does not reproduce the trailing and
fractional-leg regime (10.4 σ disagreement with Q8, explained but not resolved), and for the
Q8 TESTED subsets, which are a **selected** 27–45% of their cells.

**What would resolve the remainder:** a Test 2 variant whose synthetic intents carry each
strategy's own declared exit legs and trailing rule rather than a pooled median geometry.
That is a contained piece of work and it would close the one place where two measurements
disagree.

---

*Pass 2 conducted 2026-09-05 against `docs/proposed-fixes/system-1/EngineValidation2.md`.
Part A read-only. Part B applied: B2 only. Full test suite after the change: **716 passed,
7 failed** — all seven pre-existing failures in modules this pass did not touch
(`attribution` C5 metric guard ×2, `signals` ledger ×3, `designate` CLI ×2), verified against
a clean checkout.*
