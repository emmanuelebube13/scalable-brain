# 2026-08-14 — session log

Matches the existing `task/<date>.md` convention (see `task/2026-07-28.md`).
Companion docs: `docs/goals/VALUE_MILESTONES.md`, `docs/goals/SYSTEM1_METRICS_AND_TARGETS.md`.

**Headline: M1 — honest zero — reached.** The live map is empty, and for the first time it is
telling the truth.

---

## 1. What changed today

### FIX-S1-014 — the contaminated champion is out of the live map

`Range_Stochastic_Divergence` (strategy_id 10) was the *entire* live model across four cells.
The 2026-08-02 audit showed it reads the future via a centred rolling window and emits **zero
signals** computed causally.

**The non-obvious part:** regenerating the map would not have removed it. Its attribution rows
still read PF 1.92 / Sharpe 1.07, because they derive from outcomes produced by the look-ahead
version. A fresh `vet --live` would have re-qualified it; hand-editing the map file would have
been silently undone by the next run.

Fix: `INTEGRITY_DISQUALIFIED` in `vetting/vet.py`, checked **before** the performance gates, in a
separate `integrity_fail` category. Deliberately not in `gates.py` — gates encode performance,
and a gate failure implies "could pass later by improving". This strategy cannot; its metrics
are fiction.

- 8 integrity rejections (4 regimes × 2 granularities)
- `build()` gained an injectable `disqualified` override so weight tests can opt out of
  integrity policy explicitly rather than depending on which ids happen to be barred
- Doc: `docs/proposed-fixes/system-1/FIX-S1-014-*.md`
- Tests: `src/system1/vetting/tests/test_integrity_disqualification.py` (8)

### FIX-S1-012 / 013 applied to the data

Flipped `LABEL_ORDER = "trend_first"` and `CAUSAL_SMOOTHING = True` in `hmm_regime.py`, then
re-fit. **The database had been holding the old rank-based labels — Gemini's code landed after
the previous re-fit, so the fix had never touched the data.**

Result matched the tau-sensitivity prediction to within 0.1pp on every figure:

| | Ranging | Trending-Up | High-Vol | **Trending-Down** | kappa |
|---|---|---|---|---|---|
| D1 | 75.0% | 9.5% | 9.0% | **6.4%** | 0.836 |
| H4 | 74.7% | 8.6% | 9.2% | **7.5%** | **0.833** (was 0.322) |
| H1 | 43.5% | 15.1% | 34.0% | **7.5%** | 0.942 |

The 75% bucket formerly mislabelled `Trending-Down` is correctly `Ranging`. All four labels
populated; every kappa clears the 0.40 gate.

### Finding B re-tested — it STANDS, and is stronger than before

I had hypothesised finding B (`n_discriminating: 0 of 10`) might be an artifact of broken
labels. It was worth testing. **It is not an artifact.**

Re-run against honest labels: still `0 of 10`. The headline `max_spread 0.1333` looks material
against the 0.10 bar — but **that spread belongs to strategy 10**, the disqualified one. Among
the nine clean strategies the max spread is **0.0567**, *below* the previous 0.075 figure.

Regime conditioning does not discriminate win rate for these strategies, now measured correctly.

### Vetting — 0 qualifiers, all four regimes starved

Failure profile across the 72 clean cells shifted but did not break:

| Gate | before | after |
|---|---|---|
| Profit factor | 72 | 72 |
| Sharpe | 72 | 72 |
| MaxDD | 53 | **39** |
| OOS months | 7 | **16** |

Best clean cells — **both in High-Vol, a regime that previously had no coverage at all**:

```
Trend_Donchian_H4@H4   PF 1.33   Sharpe 0.73   n=203
Trend_Donchian_H1@H4   PF 1.31   Sharpe 0.78   n=269
```

Sharpe within 0.02 of the 0.80 gate; PF nowhere near 1.5. Breakout strategies performing best in
volatile markets is economically sensible, and only became visible once High-Vol stopped being a
dumping ground for genuine downtrends.

### Correction recorded

Earlier in the week I said the T6 ATR case-mismatch "taints old verdicts". That is true of **T6
research verdicts only**. All ten live strategies set `df['ATR']` themselves (uppercase), which
is what `StrategyBase.calculate_stop_loss` reads — so the 134,407 `fact_trade_outcomes` rows are
**not** affected by it.

---

## 2. Current state

```
tests            581 passing, 0 failing  (src/system1 + src/layer0)
live map         {} — all four regimes starved
registry         0 strategies is_qualified
prices           H1 2026-08-14 17:00-03, 5 pairs active
regimes          847,151 rows, honest labels, kappa >= 0.83
outcomes         55,756 rows, current to 2026-08-14 (was 134,500 — see below)
attribution      40 cells, 38,610 OOS trades, reconciled
v2 strategies    19 registered, 0 promotable (no path exists)
uncommitted      13 files + the 2026-08-15 granularity fix
```

**2026-08-15 — the row count halved on purpose.** `persist_trade_outcomes` ignored each
strategy's `config.primary_granularity` and backtested every strategy on both H1 and H4.
Two pairs differ *only* in that field, so each pair was one strategy counted twice:
`Range_Bollinger_H1`/`H4` (13,934 identical rows) and `Trend_EMA_ADX_H4`/`MultiTF` (6,306).
The writer now routes each strategy to its declared frame. 134,500 → 55,756 trades and
80 → 40 cells is the double-counting coming out, not evidence being lost.
`Range_Bollinger_H1`/`H4` now diverge (0 identical rows). **`Trend_EMA_ADX_H4`/`MultiTF`
still do not** — they declare the same frame and differ only in `use_multi_timeframe`,
which the legacy engine never reads. That pair stays duplicated until multi-timeframe is
actually implemented; see `task/2026-August-week2/mtf-experiment/`.

---

## 3. What is open

> **Active work, week of 2026-08-17:** the regime-aware trial —
> `task/2026-August-week3/regime-aware/`. Start at its `RUN-ALL.md`; state lives in its
> own `STATE.md`. Gemini builds, Claude reviews. Routing label is the **D1 trend label**,
> not the HMM label (H4 HMM Trending-Up is 0.0% on four of five pairs — see that folder's
> `README.md` §3). Nothing in it promotes anything to live.

### Minutes each, genuinely open

1. **DONE: Sync the live map.** `generated_at_utc: 2026-08-15T09:36:22.110308+00:00`, `run_id: 4f608511-72f2-4451-87c4-956619f80ead`, qualifier count: 0, cells: 40.
2. **Note to Computer 2.** Deferred by owner. They are still holding their pipeline pending this
   exact decision, and the answer now exists.
3. **DONE: Commit.** 13 files — FIX-S1-012/013/014, the integrity blocklist, metrics + milestones docs,
   the v2 harness, plus the new v2 research strategies and SQL.

### Deferred by decision

4. **Repo cleanup** — `task/BACKLOG-repo-structure-and-cleanup.md`. Parked deliberately.
5. **v2 promotion gap** — decided NOT to build (correctly: don't build the door before anyone
   comes through it). But the gap was never *documented*. Time-sensitive only because the 51
   land this weekend and the gap is invisible until someone hits it.

### Known defects, no owner

6. **DONE: Heartbeat cries wolf** — added `regimes` check to the deliberate cron hold, and updated `heartbeat.py` to correctly parse `status="withdrawn"` for the champion bundle so it doesn't fail when no artifacts exist.
7. **T6 ATR case-mismatch** — no FIX doc. Research verdicts only, not the live path.
8. **Outcomes rebuild — DONE 2026-08-15.** Ran twice: once to refresh (134,407 → 134,500,
   current to 2026-08-14), then again after the `primary_granularity` fix (→ 55,756).
   Attribution and vetting were re-run on the result; both are current. Rollback tables:
   `fact_trade_outcomes_bak_20260815` (07-24 vintage) and
   `..._bak_20260815_predupfix` (the 134,500 duplicated vintage).
   Still true of the writer: `DELETE`-then-rebuild with no transaction, so **snapshot first**
   and **pass `--lookback-years 10`** (default 5 silently discards half the history).
   The run takes under 3 minutes — cheaper than the estimate this task carried.
8b. **Regime-aware strategies (model 1) — EXPERIMENT COMPLETE 2026-08-15, decision open.**
   `src/regime_aware/`, isolated and archivable. Framework works (equivalence test passes); the
   result does not support regime conditioning as an edge — the winning arm was pair selection,
   and **every profitable cell in the study has a PF confidence interval straddling 1.0**. The
   durable output is `docs/design/STRATEGY_EXPERIMENT_STANDARD.md`, eight rules to apply to the
   51. Summary + commands: `task/2026-August-week2/deliverables/T3-regime-aware/README.md`.
   Decide: adopt the standard / port more strategies / archive.
9. **Finding A — weight starvation** at 8e-8. Genuinely premature: cannot matter until M2.
10. **`layer2_config_adapter` T-SQL, Pub/Sub unwired** — long-standing, unchanged.

---

## 4. What this settles

**The legacy ten are done.** They were measured against broken labels; the labels were fixed;
they still fail comprehensively on profit factor and Sharpe in every cell — 72 as measured on
2026-08-14, 36 clean cells after the 2026-08-15 de-duplication. Do not re-litigate
whether relabelling rescues them — it was tried, and it did not.

**The path to M2 is new strategies, not re-measuring old ones.** That makes the 51 the whole
game, which is a cleaner position than yesterday.

---

## 5. Rollback assets

| Asset | Covers |
|---|---|
| `fact_market_regime_v2_bak_20260814` | pre-relabel regime labels |
| `fact_strategy_regime_attribution_bak_20260814` | pre-relabel attribution |
| `models/hmm_model.joblib.bak-20260814` | pre-relabel HMM |
| `results/state/regime_strategy_map.json.bak-20260814` | pre-disqualification live map |
| `results/state/strategy_weights.json.bak-20260814` | pre-disqualification weights |
| `results/state/*.json.bak-20260815-pre-t3` | the stale-provenance map + weights, as they stood before the T3 re-sync |

To undo FIX-S1-014: remove the entry from `INTEGRITY_DISQUALIFIED`, re-run `vet --live`. No data
was deleted; `fact_trade_outcomes` untouched.

To undo the relabelling: set `LABEL_ORDER = "volatility_first"` and `CAUSAL_SMOOTHING = False`,
re-fit, or restore the backup tables.

---

## 6. Suggested next actions

Two items, ~35 minutes, close the session cleanly and leave nothing lying:

1. ~~`vet --live` — sync the map~~ — **done 2026-08-15**, see item 1 and
   `task/2026-August-week2/deliverables/T3/DELIVERABLE.md`
2. Commit the files
3. Fix the heartbeat so it knows about the deliberate hold

Then, this weekend: run the 51 through `v2_harness`. That is the M2 measurement, and it is now
the only live question.

---

## 7. The M2 measurement — ANSWERED 2026-08-16

The 51 are built and measured. **47 exist** (4 must not be built), **46 have a harness
verdict**, and the answer to "does anything in the 51 qualify?" is:

- **1 pooled pass** — `nnfx_backtrader` (PF 1.63, Sharpe 0.94) on **113 trades with 0 of 5
  cells passing** and its best cell resting on 16 trades. A concentration artefact until
  someone reconciles the two harness runs it has; do not cite it as a qualifier.
- **1 passing cell in ~230** — `demark_fractal_breakout` on **USD_JPY H4: 610 OOS trades,
  PF 1.51, Sharpe 1.11, MaxDD 7.0%, recovery 9.74, 84 months** — clears every gate. Its
  pooled verdict fails because the other four pairs do not. This is the largest sample
  behind any positive result in the exercise and the only one worth a follow-up question.
- Everything else fails, consistently, on samples up to 3,979 trades. Nine strategies
  produced fewer than five OOS trades and are **not measured**, whatever their row says.

**Start here:** `task/2026-August-week2/N5-fleet-completion/SUMMARY.md` — ledger sorted by
Sharpe, counts, both candidate results in detail, every DECISION a human must rule on, and
12 systematic findings (including: `daily_fib_retracement` emits 254 orders the engine
admits none of; contract v2 has no OCO and it now shows up in the trade counts;
cross-sectional strategies cannot be measured by a one-pair-at-a-time harness).

So M2 is **not** reached: no strategy qualifies on evidence that survives inspection. The
honest next question is the demark USD_JPY cell, not another sweep.

---

## 8. The R3 Regime-Aware Trial — CONCLUDED 2026-08-16

The attempt to rescue the 51 retail strategies via structural regime-filtering (R3) is complete.

1. **The Technical Fix (Success):** A new Causal Structural Regime Model (CSRM) was built (`build_structural_labels` in `context.py`). It uses ADX(14) and a 1-year rolling Z-score of ATR-Percent. It perfectly slices the market into 4 regimes without the look-ahead bias of the legacy system and without the pair-concentration degeneracy of the HMM.
2. **The Quantitative Edge (Failed):** While the structural gate successfully filtered the trades cleanly, the resulting "uplift" on the best strategies (like `weekly_day_reversal_ea` and `mtf_swing_weekly_pivots`) was proven by System 2 to be **statistically insignificant** (OOS P-values of 0.199 and 0.262) and a product of post-hoc selection out of 126 comparisons.
3. **The Verdict:** The label math is a permanent addition to the project, but it does not magically create an edge where none exists. The fleet of 51 retail strategies is officially verified as having zero robust edge. **Do not deploy any of them.** We accept the Null Hypothesis for the V2 suite.
