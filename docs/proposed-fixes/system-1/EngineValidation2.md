# Scalable-Brain — Engine Validation, Pass 2

**Supersedes the verdict of `audit/reports/engine_validation/report.md`.** That pass produced
valuable data. Its H_BUG verdict is not supported by the evidence it presents, for reasons
set out in §0. The diagnostic CSVs remain useful and are reused here.

**Objective:** determine definitively whether the strategy bank's negative mean R is caused by
the execution engine, by specific broken cells, by absent edge, or by a combination — and fix
whatever is confirmed.

**Structure:** Part A diagnoses (read-only). Part B fixes, and only what Part A confirms.

---

## 0. What went wrong in pass 1, and the rules that follow from it

Five failures, each with a rule attached. The rules are not stylistic; violating any of them
is what produced an unsupported verdict.

**(1) The cost baseline was inherited, not measured.** Every `C_g` came from V4's
reconstruction of stops as `1.5 × ATR(14)`. But `test2_generator_validity.md` states
`STOP_LOSS_ATR = 1.0` in `ContractStrategyAdapter`. If stops are 1.0 × ATR, every `C_g` is
1.5× larger, H1 sits *above* its cost floor, and the pooled symmetry deviation moves from
−0.033 (outside tolerance) to roughly +0.005 (inside it). The verdict depends entirely on a
number nobody measured.

> **Rule 1 — Measure, never assume, any quantity a verdict depends on.** If it can be
> computed from data, compute it. Cite the query, not the source file.

**(2) A precondition failed and the test proceeded anyway.** `Trend_Donchian_H1` has 10,151
original trades and 12,761 inverted — 26% more. `Trend_Donchian_VCP`: +32%. The report
simultaneously claims 98.7% entry alignment. Both cannot be true. The spec named divergent
trade counts as invalidating, because the symmetry identity assumes the same trades mirrored.

> **Rule 2 — When a precondition fails, report `BLOCKED` and stop that test.** Do not
> proceed and caveat. A caveated invalid test still reaches the summary table as evidence.

**(3) Validity was argued instead of measured.** `test2_generator_validity.md` says "PASSED by
construction" and explicitly declines to compute the requested comparisons. "Matched in
expectation" is not matched in sample — and the stop-distance claim is the weak one, since
real entries are not random with respect to ATR.

> **Rule 3 — No "by construction" arguments.** Every validity claim ships a computed
> statistic. If it cannot be computed, the claim is `UNVERIFIED`.

**(4) An inference was stated as a measurement.** The headline finding — that 19% of D1
trades are forced stop exits from intrabar ambiguity — rests on the claim that "a zero-bar
hold is only possible if the entry bar touches both the stop and the TP." That is false; only
one level need be touched. The direct test (zero-bar trades split by exit reason) is one query
and was never run.

> **Rule 4 — Distinguish measurement from inference explicitly.** Label every finding
> `MEASURED` or `INFERRED`. An inference may not appear in a verdict without a measurement
> supporting it.

**(5) A contaminated and duplicated population was used.** Of seven strategies in Test 1:
`Trend_EMA_ADX_H4` and `Trend_EMA_ADX_MultiTF` are byte-identical (n=456/455, mean
−0.16216613985873274 in both) — one strategy double-weighted. And
`Range_Stochastic_Divergence` is strategy 10, `INTEGRITY_DISQUALIFIED` in `vet.py` for
lookahead. It scored +0.388 original / −0.441 inverted, which is a textbook lookahead
signature and a good independent confirmation of the ban — but it does not belong in a test
population.

> **Rule 5 — Deduplicate and exclude integrity-disqualified strategies before any test.**
> Report the population you actually used, with counts.

### Two further standing rules

> **Rule 6 — Never pool v1 and v2 engine trades.** They are different simulations with
> different fill conventions, different exit vocabularies, and (per §Q3) possibly different
> stop behaviour. Every table in this pass is split by engine or is invalid.

> **Rule 7 — Sign convention, stated once.** `C_g` is a positive magnitude. The expected
> floor is `−C_g`. `gap = mean_R − (−C_g) = mean_R + C_g`. A negative gap means worse than
> the floor. `d2_per_instrument_R.csv` and `d5_direction_split.csv` stored `expected_floor`
> as positive and computed `gap = mean_R − expected_floor`; every gap in those two files is
> wrong by `2 × C_g`. Assert the convention in code and republish both.

---

# PART A — Diagnosis

Read-only. No code changes, no config changes, no database writes. Answer in order; Q1–Q3
are gates.

## Q1 — Is the drag common-mode or localised? `[GATE]`

The cheapest and most decisive question, and pass 1 never asked it. A defect in the shared
execution path drags every strategy by roughly the same amount. Absent edge, or a few broken
cells, produces scatter.

Produce the **distribution of mean R across strategies**, computed per strategy × granularity
× engine, restricted to OOS trades, with a minimum of 30 trades per cell:

- Histogram and the quantiles: min, p5, p25, median, p75, p95, max.
- Standard deviation of the per-strategy means, and the mean of the per-strategy standard
  errors. Compare them: if the spread across strategies is no larger than their individual
  sampling error, the strategies are indistinguishable from one another — the common-mode
  signature. If the spread is much larger, the bank is heterogeneous and pooled statistics
  are misleading.
- The count of strategies above and below zero, and above and below `−C_g`.

**Interpretation:** a tight cluster near a common negative value supports a shared-path
defect. A wide scatter with a few severe outliers supports localised problems and means the
bank-level mean R was never the right statistic to reason about.

**Report both, and state which the data shows.** This determines whether the rest of this
pass is looking for one bug or several.

## Q2 — What is the true cost floor? `[GATE — nothing downstream is interpretable until this resolves]`

**Do not derive it from an ATR multiplier in source. Measure it from realised trades.**

For every trade that exited at its stop, the realised distance travelled *is* the stop
distance (plus exit slippage):

```
stop_distance = |exit_price − entry_price|   -- where exit_reason indicates a stop
```

Note the exit-reason vocabulary differs by engine — v1 writes lowercase (`stop_loss`), v2
writes uppercase (`STOP`). Handle both, and report the count matched under each. A query
filtering on only one vocabulary silently drops that engine's entire population.

Produce, per strategy × granularity × engine:

| column | meaning |
|---|---|
| n_stop_exits | sample size |
| median_stop_pips | measured stop distance |
| median_stop_atr_multiple | the same, divided by ATR(14) at the entry bar |
| implied_C_g | `applied_round_trip_pips / median_stop_pips` |

Then the same aggregated per granularity × engine, trade-weighted.

**Specific questions to answer:**

- Is the ATR multiple 1.0, 1.5, or does it vary by strategy? Two code paths give two answers
  (`ContractStrategyAdapter` says 1.0, `strategy_base.py:321-332` implies 1.5). If it varies,
  a single pooled `C_g` is invalid and every gap must be computed per strategy.
- What is `applied_round_trip_pips` in reality — 1.0 (2 × 0.5 slippage) as V4 found, or
  something else per engine? Measure it: for stop exits, `|exit_price − entry_price|` minus
  the intended stop distance gives realised exit slippage directly.

**Then recompute, with the measured `C_g`:** every gap in E0, D2, D5, and the `−2·C_g`
target in Test 1. Present the corrected E0 table alongside the original so the change is
visible.

**Gate:** if the corrected H1 gap is at or above zero, the pass-1 H_BUG verdict is withdrawn
on its own terms and this must be stated plainly in the report.

## Q3 — Separate the two engines `[GATE]`

The 64,889 OOS trades are a mixture of two simulations. Pass 1 pooled them, so every
bank-level number — including the −0.070 that started this investigation — is a weighted
average of two incomparable populations.

**Q3.1 — Full metric set per engine.** Reproduce E0 in its entirety (granularity, instrument,
direction) split by `engine`, never pooled. Report mean R, median R, sd, n, and the corrected
gap from Q2.

**Q3.2 — Does v2 move stops?** `mean_R_stop` is −0.934 at H1 (71% v1) but −0.697 at H4 (58%
v2) and −0.663 at D1 (100% v2). A static stop should exit near −1.0 R. The v2-dominated
granularities do not. Determine from source and from data whether the v2 `PositionEngine`
implements trailing stops, breakeven moves, or partial exits. If it does, the two engines have
different exit regimes and `r_multiple` does not mean the same thing in each.

**Q3.3 — Why is v2 better on H1 and worse on H4?**

| | v1 | v2 |
|---|---|---|
| H1 | −0.076 (n=30,566) | −0.027 (n=12,348) |
| H4 | −0.059 (n=8,089) | −0.106 (n=11,262) |

v1 fills contemporaneously (optimistic, per D3); v2 fills at the next open (correct). v2 should
therefore be uniformly *worse*. On H1 it is dramatically better. Explain this. Candidate
causes: different strategy populations per engine, different stop regimes (Q3.2), different
date coverage, or a defect in one of them. Check whether the same strategy appears under both
engines — if any does, compare it directly; that is the cleanest possible controlled test.

**Q3.4 — Which engine produced the vetting population?** `attribute.py` reads
`fact_trade_outcomes`, which holds both. So the three gate-qualified cells and the designated
ones were selected from a mixture. Report, for each of the 158 attribution cells, which engine
produced its trades — and whether any cell mixes both. A cell's profit factor may be an
artifact of which engine ran it.

## Q4 — The stop-first ambiguity, measured properly

**Q4.1 — The cheap direct test.** Of zero-bar trades (`bars_held = 0`), what fraction exited
at the stop versus the take-profit, per granularity and engine? Compare against the same split
for all other trades.

If STOP_FIRST is creating bias, zero-bar trades should be overwhelmingly stops relative to the
baseline. If they split like everything else, there is no ambiguity effect and the pass-1
headline finding is withdrawn.

**Q4.2 — The real ambiguity count.** Pass 1 called this "infeasible from the DB alone." It is
feasible. With the measured stop distance from Q2, reconstruct both levels:

```
stop_level = entry_price ∓ stop_distance
tp_level   = entry_price ± (rr_ratio × stop_distance)
```

Determine `rr_ratio` empirically from winning trades (`|exit − entry| / stop_distance` on TP
exits — the Test 2 output shows tight clustering near +1.63 R, so this is well-determined).
Join to `fact_market_prices` on the exit bar and count bars where **both** levels lie within
`[low, high]`.

Report: count and percentage of ambiguous exits, per granularity and engine.

**Q4.3 — The counterfactual.** For every ambiguous trade, recompute R under a TP-first
assumption, and under a 50/50 random assignment. Report the bank's mean R under all three
rules (stop-first as-is, tp-first, coin-flip), per granularity and engine.

The difference between stop-first and coin-flip is the **magnitude of the bias**. That is the
number the pass-1 report asserted was unquantifiable. Quantify it.

## Q5 — USD_JPY H4

−0.228 R on 4,159 trades (≈11σ from zero), against −0.03 to −0.07 for every other H4 pair.
The number pass 1 did not flag: the **median is −1.0022**, versus −0.37 to −0.43 elsewhere.
More than half of these trades exit at the stop. That is a different exit process, not a
degree of underperformance.

- **Q5.1** — Decompose per strategy. One broken strategy or all 21? Report each strategy's n,
  mean R, median R and stop-exit rate on USD_JPY H4, alongside its numbers on other H4 pairs.
- **Q5.2** — Compare the measured stop distance (Q2) in pips *and* in ATR multiples for
  USD_JPY H4 against every other pair-granularity cell. A stop that is anomalously tight in
  ATR terms would produce exactly this median.
- **Q5.3** — Verify ATR(14) on USD_JPY. It should be roughly 100× the value of a non-JPY pair
  in raw price units. Confirm nothing divides or multiplies by a pip factor in the stop
  calculation path for JPY.
- **Q5.4** — Time-localise it. Is the drag uniform across 2005–2026, or concentrated in a
  period? Plot mean R by year for USD_JPY H4 against the other H4 pairs.
- **Q5.5** — Split by engine. Both, or one?

**Report the bank's mean R with this cell excluded.** Preliminary arithmetic suggests it moves
the pooled figure from −0.070 to roughly −0.059, so one cell carries around 16% of the total
drag.

## Q6 — Direction asymmetry, with the obvious null tested first

Longs −0.047, shorts −0.106, ≈6.5σ. Real. But pass 1 reached for engine defects without
testing the simplest explanation.

- **Q6.1 — Market drift control.** Compute the mean per-bar return of each instrument over the
  full sample, and over each strategy's actual trading window. If pairs drifted directionally,
  a roughly symmetric strategy bank produces exactly this asymmetry with no defect at all.
  Report the correlation between per-pair drift and per-pair long/short gap.
- **Q6.2 — Cross-tab.** direction × instrument × granularity × engine. USD_JPY H4 may be
  driving the pooled asymmetry; the current tables cannot rule that out.
- **Q6.3 — Slippage symmetry.** Confirm from source that entry and exit slippage are applied
  with the correct sign for shorts, and that the magnitude is identical to longs. Then confirm
  from data: realised entry and exit slippage, split by direction.
- **Q6.4 — Stop-first interaction.** Recompute the direction split under the coin-flip rule
  from Q4.3. If the asymmetry shrinks materially, the two findings are one finding.

## Q7 — Time localisation

Not in pass 1 and it should have been. Report mean R by year, split by granularity and engine,
for the whole bank.

A defect present since inception looks different from one introduced by a code change or a
data-vendor change. If the drag is concentrated in a period, cross-reference against the git
history and against `fact_market_prices` coverage for that window.

## Q8 — Test 1, re-run correctly

**Population:** exclude strategy 10 (`Range_Stochastic_Divergence`, integrity-disqualified).
Deduplicate `Trend_EMA_ADX_H4` / `Trend_EMA_ADX_MultiTF` — determine whether they are one
strategy registered twice and, if so, keep one. Report the final population with counts.

**Hard precondition, checked before any statistic is computed:** per strategy, `|n_inv −
n_orig| / n_orig ≤ 0.05`. If any cell exceeds it, that cell is `BLOCKED` and excluded, and
the reason is reported. If more than half the population is blocked, Test 1 as a whole is
`BLOCKED`.

Where counts diverge, diagnose why. Inverting direction should not change *when* signals fire.
A 26% increase means the inversion altered signal generation — find out how, because that is
itself a finding about the strategies.

**Then:** recompute the symmetry invariant against the **measured** `−2·C_g` from Q2, per
granularity and per engine.

**Also required:** trade-level pairing where entry timestamps match, so `R_orig + R_inv` can be
computed per matched pair rather than only on aggregates. The distribution of that per-pair
sum is far more informative than its mean — a few extreme pairs versus a uniform shift are
very different findings.

## Q9 — Test 2, re-run correctly

- **200 replications**, per the original spec. If infeasible, report `BLOCKED` with the reason;
  do not run fewer and argue sufficiency.
- **D1 coverage.** Pass 1 blocked D1 because `get_all_strategies()` returns only v1-path
  strategies. D1 has the largest apparent gap, so it is the granularity that most needs a
  floor. Build the v2 `PositionEngine` random-entry harness, or report `BLOCKED` with a
  specific statement of what is missing.
- **Generator validity, measured.** Computed KS statistics for entry hour-of-day and for stop
  distance, real versus synthetic, per granularity. Computed long/short ratio comparison. No
  "by construction" claims.
- **Per engine**, never pooled.

## Q10 — Republish the corrected diagnostics

Regenerate `d2_per_instrument_R.csv` and `d5_direction_split.csv` with the Rule 7 sign
convention and the measured `C_g`. Add an assertion in the generating code that
`expected_floor < 0`. Note in the report that the originals were wrong and by how much.

---

# PART B — Fixes

Only for findings confirmed `MEASURED` in Part A. Each fix ships with a before/after
measurement on the same population.

**Do not fix anything Part A leaves `INFERRED`, `UNVERIFIED` or `BLOCKED`.** Pass 1's headline
finding would have led to a fix for a mechanism that may not exist.

### B1 — Intrabar ambiguity, if Q4 confirms a material bias

The defensible rule is not TP-first — that is optimistic in the opposite direction. Options,
in order of preference:

1. **Resolve with finer data.** If M15 or M5 bars exist for the ambiguous bars, determine which
   level was actually touched first. This is the only correct answer rather than an assumption.
2. **Conservative-but-declared.** Keep stop-first, but record `exit_ambiguous = true` on every
   affected trade and report the ambiguous fraction alongside every metric, so the assumption's
   footprint is always visible.
3. **Coin-flip with a fixed seed.** Unbiased in expectation, reproducible, but adds variance.

Whichever is chosen, the ambiguous fraction becomes a permanently reported statistic. Re-run
the full bank and report the delta.

### B2 — Engine unification

Two engines producing different R for the same strategy is not a defect to be fixed by picking
a winner; it is a defect because both populations sit in one table and feed one attribution
run.

- Add an `engine_version` filter to `attribute.py` and make it **required**, not defaulted.
- Re-run attribution per engine and report both maps.
- Decide which engine is authoritative for vetting — v2 on fill-timing grounds, if Q3.2/Q3.3
  do not surface a defect in it — and record the decision.
- Do not delete the other engine's trades. Tag and exclude them.

### B3 — Contemporaneous fill in v1

D3 confirmed v1 fills at `Close[i]` of the signal-generating bar. That is optimistic; live
execution can act no earlier than bar `i+1`'s open.

If Q3.4 shows v1 trades feed the vetting population, every v1-derived metric is optimistic by
an unmeasured amount. Quantify it: re-run a representative v1 subset under next-open fill and
report the delta in mean R per granularity. Then either migrate to v2 or apply the measured
haircut.

### B4 — USD_JPY H4

Fix depends on Q5. If a stop-sizing defect: fix and re-run. If one broken strategy: quarantine
it. If it is genuine underperformance: leave it and record why. State which.

### B5 — Direction asymmetry

Only if Q6 rules out market drift *and* rules out the Q4.3 interaction. If both survive, the
remaining candidate is slippage or P&L sign handling for shorts, and Q6.3 will have located it.

### B6 — Exit-reason vocabulary

Normalise v1 lowercase and v2 uppercase to one vocabulary at the read layer, and audit every
query in the repo that filters on `exit_reason`. Any that matches one vocabulary silently
drops the other engine's entire population. Report every such query found.

---

## Deliverables

```
audit/reports/engine_validation_2/
  report.md
  q1_strategy_distribution.csv
  q2_measured_cost_floor.csv          <- per strategy × granularity × engine
  q2_corrected_e0.csv                 <- E0 recomputed, original alongside
  q3_engine_split.csv
  q3_same_strategy_both_engines.csv
  q4_zero_bar_by_exit_reason.csv
  q4_ambiguity_count.csv
  q4_counterfactual_R.csv
  q5_usdjpy_h4_by_strategy.csv
  q6_drift_vs_asymmetry.csv
  q6_direction_crosstab.csv
  q7_mean_R_by_year.csv
  q8_inversion_v2.csv
  q8_matched_pair_sums.csv
  q9_floor_distribution_v2.csv
  q9_generator_validity.md            <- computed statistics only
  d2_per_instrument_R.csv             <- corrected, replaces original
  d5_direction_split.csv              <- corrected, replaces original
```

`report.md` opens with a table: every finding, labelled `MEASURED` / `INFERRED` /
`UNVERIFIED` / `BLOCKED`, with the query or file that established it. Only `MEASURED`
findings may appear in the verdict.

It closes with the verdict, which must be one of:

- **ENGINE DEFECT CONFIRMED** — with the mechanism, its magnitude in R, and the affected
  population.
- **LOCALISED DEFECTS ONLY** — with each cell named and quantified, and the bank's mean R
  recomputed with them excluded.
- **NO DEFECT — ABSENT EDGE** — with the corrected `C_g` and the per-strategy distribution
  supporting it.
- **INCONCLUSIVE** — with exactly what is missing and what would resolve it.

"Inconclusive" is an acceptable outcome. An unsupported verdict is not.

And a **"Not in the spec"** section. Pass 1's was the most useful part of its report — the
engine split was buried there, and it may be the largest finding in the whole exercise.

---

## Sequencing

1. **Q1** — is this one problem or several? Cheap, and it frames everything.
2. **Q2** — the measured cost floor. Nothing else is interpretable first.
3. **Q3** — engine separation. Every table after this is split.
4. **Q4** — ambiguity, measured and counterfactualled.
5. **Q5, Q6, Q7** — the specific anomalies.
6. **Q8, Q9** — the re-runs, now against measured baselines.
7. **Q10** — republish.
8. **Part B** — fixes, only for what is confirmed, each with a before/after.

Stop and report at any point where a gate (Q1–Q3) cannot be answered. A blocked gate is a
finding about the system's observability, and it is worth more than a completed test built on
an unmeasured assumption.