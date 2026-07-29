# Week 2026-W31 — Execution State Ledger

**Protocol (every agent must follow):**
1. Read this file FIRST, before doing any work.
2. Skip any step marked `DONE`. Resume from the first step marked `IN_PROGRESS` or `PENDING`.
3. After completing each numbered step in a task, append a line to the log below **immediately** (not at the end of the session) — this is what makes credit-limit interruptions survivable.
4. Entry format: `| <UTC timestamp> | <task> | <step> | DONE/FAILED/BLOCKED | <one-line note: what was verified, or why it failed, or what unblocks it> |`
5. On FAILED: also append the root cause to the `## Failure log` section of that task's file, and add the corrected instruction into the task's execution plan.
6. On BLOCKED (needs the user / other computer / VM access): state exactly what the user must do, then move to the next unblocked task.

## Task status board

| Task | Status | Last step completed | Notes |
|------|--------|--------------------|-------|
| T1 reconnect-feedback-loop | **DONE** | 6 + deliverables | Outcomes current through 2026-07-24. 42 new + 173 existing tests green. Deliverables complete. Real root cause differed from the task's premise — task file corrected in place. |
| T2 secrets-and-env | PENDING | — | |
| T3 promote-verified-work | PENDING | — | |
| T4 heartbeat-monitoring | PENDING | — | |
| T5 derisk-money-layer | PENDING | — | |
| T6 research-strategy-engine | PENDING | — | |

## Log (append-only)

| Timestamp (UTC) | Task | Step | Result | Note |
|---|---|---|---|---|
| 2026-07-29T00:20Z | BOOT | baseline commit | DONE | Tree was dirty with ~3 weeks of uncommitted work (not a crashed run). User approved committing it as a baseline. 7 commits `3365805`..`16533cf`; tree now clean. |
| 2026-07-29T00:20Z | T2 | pre-fix | DONE | T2 step 1 embedded a literal fragment of the live DB password; rewritten to read `$OLD_DB_PASS` from `.env` at runtime before it was committed. New step 0 added. |
| 2026-07-29T00:35Z | T1 | 1 (map) | DONE | Root cause is NOT the space-named dirs (they hold only README.md and Python never imports them). Real cause = 3 stacked breaks from the layer0 subpackage reorg. See Knowledge notes. |
| 2026-07-29T00:45Z | T1 | 2-3 (packaging) | DONE | `import src.layer0.persist_trade_outcomes` exits 0; `get_all_strategies()` returns all 10 strategies. |
| 2026-07-29T00:50Z | T1 | 2 (renames) | DONE | `git mv` of the two space-named doc dirs → `mean_reversion`, `volatility_expansion_compression`. No code referenced them (README-only). |
| 2026-07-29T01:20Z | T1 | 6 (fail-fast) | DONE | 8 layer0 shims now re-raise the original ImportError; this immediately exposed a second live break (`qualification/demo.py` on flat pre-reorg imports) — fixed. New `src/layer0/tests/` (42 tests) green; `pytest src/system1` 173 passed. Commits `852b5bd`, `fde893b`, `aed6cb4`. |
| 2026-07-29T01:15Z | T1 | 4 (rebuild) | DONE | **Feedback loop reconnected.** 134,407 rows, H1 2016-08-03..2026-07-24, H4 2016-08-16..2026-07-24, written 2026-07-29. Prior vintage 134,520 rows ending 2026-06-23. Net −113 rows is the rolling 10y window (gained 5 weeks at the end, dropped 5 weeks at the start), not a truncation. OOS split 93,405 / 41,002 IS. First attempt at the 5y default produced only 66,597 rows — discarded, see Knowledge notes. |
| 2026-07-29T01:50Z | T1 | 5 (re-measure) | DONE | Log-only. Attribution: 80 cells, 0 UNKNOWN regime, reconciled. Vetting: 4 qualifying, High-Vol starved. **Finding: the fresh-data map is the same 4 cells / same strategy as the incumbent, metric deltas in the 2nd decimal.** Stale data barely moved the verdict — T3 should expect confirmation, not reversal. |
| 2026-07-29T01:52Z | T1 | live run check | DONE | Orchestrator `no_trigger_or_cooldown`, ran=False, promoted=False. Verified via pure `triggers.decide()` *before* running that no promote could fire. |
| 2026-07-29T02:05Z | T1 | deliverables | DONE | `deliverables/T1/`: DELIVERABLE.md, EXECUTIVE_SUMMARY.md, outcomes_timeline.png, import_graph.png, make_charts.py (regenerable, all figures from live DB queries). |
| 2026-07-29T00:55Z | T1 | CHECKPOINT | — | Before-state: `fact_trade_outcomes` 134,520 rows, max trade ts 2026-06-23 20:00Z, all written 2026-06-24. Prices current to 2026-07-24 20:00Z (last market close). Backup table `fact_trade_outcomes_bak_20260729` created (134,520 rows). Rebuild launched → `logs/t1_outcomes_backfill_20260729.log`. **If interrupted: check that log, then verify row count; restore from the backup table if the table is empty.** |

## Knowledge notes (append discoveries here that later steps need)

- (agents: record here anything the next session must know that isn't obvious from the repo — e.g. "outcomes writer also needed X", "VM reachable at Y", "ratchet lives in Z")
- **Baseline commits (2026-07-29):** all July work is now in git — `3365805` FIX-S1-008/010, `8ffcac0` analytics+publish, `0b72d59` OANDA ingest repair, `117fb99` archived layers 4-7, `884bc0b` docs/CLAUDE.md, `90aecac` task/2026-W31, `16533cf` results state. Nothing pushed. `git status` is clean, so RUN-ALL boot step 3 should now show a clean tree — any dirt from here on IS unexpected.
- `results/state/retrain_log_*.json` (462 hourly cron files) is now gitignored — machine-generated; `retrain_state.json` is the state of record.
- `archieved/layer5/frontend/node_modules` (293 MB) is gitignored; only 119 source files from `archieved/` were committed.
- **T1 real root cause (T1's own mission statement was wrong).** The space-named dirs `Mean Reversion ` and ` Volatility Expansion and Compression ` contain *only README.md* — Python never imports them, so they never broke anything. The actual break is three stacked failures from the `layer0` subpackage reorg (core_engine/ qualification/ data_access/ promotion/):
  1. `src/layer0/strategies/__init__.py` was deleted when the strategy modules moved down into `strategies/strategieStaged/` → `layer0.strategies` became an empty implicit namespace package → `cannot import name 'TrendEMAADXStrategy' ... (unknown location)`.
  2. The moved modules kept their pre-move relative imports (`from ..strategy_base`, `from ..indicators`) — one level too shallow *and* pointing at pre-reorg locations. Correct targets: `...core_engine.strategy_base` and `...data_access.indicators`.
  3. `src/layer0/qualify_strategies.py` was a 1471-line file: an 11-line shim followed by a verbatim copy of the whole pre-reorg module, which re-executed everything against the flat pre-reorg paths. Truncated to the shim (verified identical 16 public names first).
- **`--lookback-years` silently controls how much history exists.** The June 2026 vintage was built with **10 years** (H1 from 2016-06-29, 134,520 rows). The writer's default is **5**, which produces only 66,597 rows from 2021-08 — it does not just add new trades, it *discards half the history*, which would gut the vetting OOS≥60mo gate and make any T3 comparison against the incumbent dishonest. **Always pass `--lookback-years 10`** to match the incumbent vintage. Price data actually reaches back to 2006 (H1/H4), so a longer window is possible, but changing it is a research decision, not a repair — don't do it inside T1.
- **The outcomes writer is a full rebuild, not an incremental backfill.** `persist_trade_outcomes.run()` does `DELETE FROM fact_trade_outcomes WHERE strategy_id IN (...)` + `conn.commit()` and *then* re-runs the whole 5-year backtest. There is no `ON CONFLICT`. Consequences: (a) T1's "backfill the June→today gap" framing does not match the code — you cannot backfill a window, only rebuild everything; (b) a crash between the DELETE and the inserts leaves the table EMPTY. Always snapshot the table before running it (`fact_trade_outcomes_bak_20260729` is the 2026-06-24 vintage, 134,520 rows).
- **Why it stayed invisible for a month:** the shim's `except ImportError: from qualification... ` fallback swallowed the real error and re-raised the unrelated `No module named 'qualification'`. The fallback now re-raises the ORIGINAL error. This is the T1-step-6 fail-fast pattern — look for the same `try/except ImportError` shim shape in `backtest_engine.py`, `indicators.py` and any other layer0 top-level wrapper.
