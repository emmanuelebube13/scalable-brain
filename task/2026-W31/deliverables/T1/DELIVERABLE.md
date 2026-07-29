# T1 — Reconnect the Feedback Loop · Technical Report

**Date:** 2026-07-29 · **Repo:** `scalable-brain` (System 1) · **Status:** COMPLETE

`fact_trade_outcomes` had not been written since **2026-06-23**. The only writer,
`src/layer0/persist_trade_outcomes.py`, died on import, and nothing anywhere reported it.
Every System-1 retrain for the following five weeks re-derived its verdicts from a frozen
outcomes table. The table is now current through **2026-07-24** (last market close), the
import chain is repaired, and this class of failure now fails loudly.

---

## 1. Root cause — the task's original diagnosis was wrong

T1 stated the cause was `src/layer0/strategies/` having no `__init__.py` *and* containing
directories with spaces in their names (`Mean Reversion `,
` Volatility Expansion and Compression `).

**The space-named directories were never the problem.** They contain only `README.md`.
Python never imports them, so they could not have broken anything. They were renamed here
as housekeeping, not as a fix.

The real cause was **three stacked failures** left behind by the `layer0` subpackage reorg
(`core_engine/`, `qualification/`, `data_access/`, `promotion/`):

| # | Break | Symptom |
|---|-------|---------|
| ① | `strategies/__init__.py` was deleted when the strategy modules moved down into `strategies/strategieStaged/`. `layer0.strategies` silently degraded to an **implicit namespace package** with zero attributes. | `ImportError: cannot import name 'TrendEMAADXStrategy' from 'src.layer0.strategies' (unknown location)` |
| ② | The moved modules kept their pre-move relative imports (`from ..strategy_base`, `from ..indicators`) — one level **too shallow**, and pointing at **pre-reorg locations** that no longer exist. | `ModuleNotFoundError: No module named 'src.layer0.strategies.strategy_base'` |
| ③ | `src/layer0/qualify_strategies.py` was an 11-line shim followed by a **verbatim 1,460-line copy** of the entire pre-reorg module, which re-executed everything against the old flat import paths. | `ModuleNotFoundError: No module named 'layer0.strategy_base'` |

### Why it hid for five weeks

The shim's error handling discarded the real failure:

```python
try:
    from .qualification.qualify_strategies import *
except ImportError:
    from qualification.qualify_strategies import *   # <- raises its own, unrelated error
```

The genuine cause (`cannot import name 'TrendEMAADXStrategy'`) was thrown away and replaced
by `No module named 'qualification'` — an error that points at an entirely different
problem. Anyone investigating was sent to the wrong place. This same shim shape existed in
**8 other `layer0` top-level modules**.

See `import_graph.png` for the before/after chain.

---

## 2. Files changed

### Packaging repair — commit `852b5bd`

| File | Change |
|------|--------|
| `src/layer0/strategies/__init__.py` | **Created.** Re-exports the 24 public strategy classes from `.strategieStaged`. Documents why it must not be deleted. |
| `src/layer0/strategies/strategieStaged/trend_ema_adx.py` | `..strategy_base` → `...core_engine.strategy_base`; `..indicators` → `...data_access.indicators` |
| `…/trend_donchian.py` | same |
| `…/range_bollinger.py` | same |
| `…/range_stochastic.py` | same |
| `…/support_resistance.py` | same |
| `…/vcp_breakout.py` | same |
| `strategies/Mean Reversion ` | renamed → `strategies/mean_reversion` (README-only) |
| `strategies/ Volatility Expansion and Compression ` | renamed → `strategies/volatility_expansion_compression` (README-only) |

### Fail-fast repair — commit `fde893b`

| File | Change |
|------|--------|
| `src/layer0/qualify_strategies.py` | Deleted the 1,460-line duplicate body; kept the shim. Verified both defined an **identical set of 16 public names** before deleting. Fallback now re-raises the original error. |
| `backtest_engine.py`, `indicators.py`, `multi_timeframe.py`, `strategy_analyzer.py`, `utils.py`, `layer2_config_adapter.py`, `demo.py`, `seed_dim_asset_test.py` | All 8 shims rewritten: on double failure, `raise _relative_import_error` (the original), never the fallback's. |
| `src/layer0/qualification/demo.py` | **Second live break, found by turning the guard on.** Still used flat pre-reorg imports (`from strategy_base import …`, `from strategies import …`). Retargeted to `..core_engine.*`, `..data_access.*`, `..strategies`. |

### Regression tests — commit `aed6cb4`

`src/layer0/tests/` **did not exist**; it was created here (T1's validation command referenced
a non-existent path).

| Test | Guards |
|------|--------|
| `test_outcomes_writer_imports` | the writer module imports at all — the assertion that would have caught this on day one |
| `test_strategies_is_a_real_package_not_a_namespace_package` | `strategies/__init__.py` exists |
| `test_every_strategy_class_is_importable` (×24) | each public strategy class is exported |
| `test_get_all_strategies_returns_the_full_roster` | roster is 10, not a silently-shortened list |
| `test_no_package_directory_names_contain_spaces` | no un-importable directory names |
| `test_backward_compatible_shims_import` (×9) | every layer0 wrapper resolves |
| `test_shims_do_not_swallow_the_real_import_error` | source-level: shims must `raise _relative_import_error` |
| `test_all_layer0_submodules_are_importable` | sweep — imports every module under `layer0` |
| `test_run_propagates_strategy_import_failure` | `run()` raises rather than writing a partial table |
| `test_run_does_not_wrap_strategy_loading_in_a_bare_except` | source-level: no future try/except around the roster build |
| `test_writer_deletes_before_insert_is_documented_as_destructive` | the destructive DELETE stays visible to callers |

**42 tests, all green.**

---

## 3. Rebuild — what actually happened

Two corrections to T1's step 4 were required and are now written into the task file.

**(a) It is not a backfill.** `persist_trade_outcomes.run()` executes
`DELETE FROM fact_trade_outcomes WHERE strategy_id IN (…)` and **commits**, then re-runs the
entire backtest. There is no `ON CONFLICT` and no way to write only a date window. A crash
between the DELETE and the inserts leaves the table **empty**. A snapshot was taken first:
`fact_trade_outcomes_bak_20260729` (134,520 rows, the 2026-06-24 vintage).

**(b) `--lookback-years` silently controls how much history exists.** The first rebuild used
the **default of 5** and produced only **66,597 rows starting 2021-08** — it did not add the
missing weeks, it *discarded half the history*. That would have gutted the vetting
`oos_months ≥ 60` gate and made any T3 comparison against the incumbent dishonest. The
incumbent vintage was built with **10 years**, so the rebuild was re-run at
`--lookback-years 10`. **Row count alone would not have caught this** — only the min
timestamp did.

### Measured before / after

| Metric | Before (2026-06-24 vintage) | After (2026-07-29) |
|--------|------------------------------|--------------------|
| Total rows | 134,520 | **134,407** |
| H1 span | 2016-06-29 → 2026-06-23 (115,754) | 2016-08-03 → **2026-07-24** (115,668) |
| H4 span | 2016-07-11 → 2026-06-23 (18,766) | 2016-08-16 → **2026-07-24** (18,739) |
| Written | 2026-06-24 | 2026-07-29 |
| OOS / in-sample | — | 93,405 / 41,002 |
| Backtests | — | 100 (10 strategies × 5 pairs × H1/H4), 134,407 trades |

The net **−113 rows is the rolling 10-year window**, not a loss: the rebuild gained 5 weeks
at the recent end and dropped 5 weeks at the 2016 end. **1,059 trades across 4 weeks** were
recovered in the previously dead region — see `outcomes_timeline.png`.

---

## 4. Re-measure on honest data (log-only — nothing promoted)

```
attribution: 134,407 trades · 0 UNKNOWN regime · 80 cells · 3 low-confidence · reconciled
             regime distribution: Ranging 82,239 · Trending-Down 28,215 ·
                                  Trending-Up 18,580 · High-Vol 5,373
vetting:     80 cells → 4 qualifying · STARVATION: High-Vol has no qualifying strategy
             mode=log_only → results/reports/proposed_regime_strategy_map.json
```

### Finding: fresh data barely moves the map

The proposed map is the **same 4 cells, same single strategy** as the incumbent —
`Range_Stochastic_Divergence`, three at H1 and one at H4:

| Cell | Metric | Incumbent (stale) | Proposed (fresh) | Δ |
|------|--------|------------------:|-----------------:|----:|
| Ranging @H1 | profit_factor | 2.9445 | 3.0831 | +0.1386 |
| | sharpe | 3.7968 | 3.9629 | +0.1661 |
| Ranging @H4 | profit_factor | 3.0569 | 2.7866 | −0.2703 |
| | sharpe | 1.7377 | 1.5321 | −0.2056 |
| Trending-Down @H1 | profit_factor | 3.2424 | 2.9798 | −0.2626 |
| | sharpe | 2.5815 | 2.4402 | −0.1413 |
| Trending-Up @H1 | profit_factor | 1.8422 | 1.9185 | +0.0763 |
| | sharpe | 1.0052 | 1.0674 | +0.0622 |

Five missing weeks against an ~84-month OOS window moved the metrics by fractions and
changed no decision. **The process failure was real and serious; its effect on the current
model was small.** T3 should expect its evidence package to confirm rather than overturn the
incumbent map. The known structural problems are untouched by this task: concentration in one
strategy (finding C) and High-Vol starvation both persist on fresh data.

One small-sample artifact was clamped by the existing guard and is worth noting:
strategy 10 / High-Vol / H4 with n=2 produced |sharpe| = 11,420 before clamping — the
sanity bounds from FIX-S1-001 did their job.

---

## 5. Validation

| Check | Result |
|-------|--------|
| `pytest src/layer0/tests/ -q` | **42 passed** |
| `pytest src/system1 -q` | **173 passed** |
| `python -c "import src.layer0.persist_trade_outcomes"` | import OK |
| `get_all_strategies()` | 10 strategies |
| Max outcome timestamp | 2026-07-24 19:00Z — current market close |
| Min outcome timestamp | 2016-08-03 — no history regression |
| Attribution refreshed | `attribution_report_20260729T014755Z.json`, 80 rows written |
| **Live run check:** `python -m src.system1.scheduler.orchestrator` | `{'ran': False, 'promoted': False, 'outcome': 'no_trigger_or_cooldown'}` — PASS |

The orchestrator was confirmed safe to run *before* running it: `triggers.decide()` was
evaluated in isolation (Tuesday, empty metrics → `(False, [])`) so no retrain-and-promote
could fire from a task that has no promotion mandate.

---

## 6. Commits

| SHA | Subject |
|-----|---------|
| `852b5bd` | fix(layer0): restore strategies package and repair post-reorg relative imports |
| `fde893b` | fix(layer0): make import failures loud instead of swallowed |
| `aed6cb4` | test(layer0): guard the outcomes-writer import chain |

No co-author trailer (repo convention). Nothing pushed.

---

## 7. Follow-ups this task surfaced (not fixed here)

1. **`persist_trade_outcomes.run()` is unsafe by construction** — the committed DELETE before
   a long rebuild means any interruption empties the live table. It should build into a temp
   table and swap, or wrap the whole thing in one transaction. Currently mitigated only by
   remembering to take a manual snapshot.
2. **`--lookback-years` has no recorded provenance.** Nothing in the table or the retrain log
   says which window produced the current outcomes, so a silent history truncation is
   invisible downstream. Worth stamping into the run metadata.
3. **Nothing monitors outcome freshness** — that is exactly T4's job, and T1's repair is what
   makes "fresh" definable.
4. The backup table `fact_trade_outcomes_bak_20260729` is still in the database. Keep it until
   T3 signs off, then drop it.
