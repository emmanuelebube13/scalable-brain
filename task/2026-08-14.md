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
tests            538 passing, 0 failing  (src/system1 + src/layer0/strategies)
live map         {} — all four regimes starved
registry         0 strategies is_qualified
prices           H1 2026-08-11 13:00Z, 5 pairs active
regimes          847,151 rows, honest labels, kappa >= 0.83
outcomes         134,407 rows — 14 DAYS STALE
attribution      80 cells, 93,405 OOS trades, reconciled
v2 strategies    19 registered, 0 promotable (no path exists)
uncommitted      13 files
```

---

## 3. What is open

### Minutes each, genuinely open

1. **Sync the live map.** This morning's `vet --live` ran against the *old* attribution; today's
   re-run was log-only. Same verdict (0 qualifiers), stale provenance.
   `python -m src.system1.vetting.vet --live`
2. **Note to Computer 2.** Deferred by owner. They are still holding their pipeline pending this
   exact decision, and the answer now exists.
3. **Commit.** 13 files — FIX-S1-012/013/014, the integrity blocklist, metrics + milestones docs,
   the v2 harness. None of it is in git.

### Deferred by decision

4. **Repo cleanup** — `task/BACKLOG-repo-structure-and-cleanup.md`. Parked deliberately.
5. **v2 promotion gap** — decided NOT to build (correctly: don't build the door before anyone
   comes through it). But the gap was never *documented*. Time-sensitive only because the 51
   land this weekend and the gap is invisible until someone hits it.

### Known defects, no owner

6. **Heartbeat cries wolf** — 2 of its 3 alerts are the deliberate cron hold. ~30 min. An alarm
   that is 67% noise trains you to ignore the third one. *Highest value of the remainder.*
7. **T6 ATR case-mismatch** — no FIX doc. Research verdicts only, not the live path.
8. **Outcomes 14 days stale** — needs `persist_trade_outcomes`, which does `DELETE`-then-rebuild
   with no transaction. Own session, snapshot first, **pass `--lookback-years 10`** (default 5
   silently discards half the history).
9. **Finding A — weight starvation** at 8e-8. Genuinely premature: cannot matter until M2.
10. **`layer2_config_adapter` T-SQL, Pub/Sub unwired** — long-standing, unchanged.

---

## 4. What this settles

**The legacy ten are done.** They were measured against broken labels; the labels were fixed;
they still fail comprehensively on profit factor and Sharpe in all 72 cells. Do not re-litigate
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

To undo FIX-S1-014: remove the entry from `INTEGRITY_DISQUALIFIED`, re-run `vet --live`. No data
was deleted; `fact_trade_outcomes` untouched.

To undo the relabelling: set `LABEL_ORDER = "volatility_first"` and `CAUSAL_SMOOTHING = False`,
re-fit, or restore the backup tables.

---

## 6. Suggested next actions

Three items, ~40 minutes, close the session cleanly and leave nothing lying:

1. `vet --live` — sync the map
2. Commit the 13 files
3. Fix the heartbeat so it knows about the deliberate hold

Then, this weekend: run the 51 through `v2_harness`. That is the M2 measurement, and it is now
the only live question.
