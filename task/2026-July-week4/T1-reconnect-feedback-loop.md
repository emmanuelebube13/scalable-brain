# T1 — Reconnect the Feedback Loop (trade outcomes frozen since June)

> Paste this whole file as the prompt. Repo: `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`. Venv: `source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate`.
> **First action: read `task/2026-July-week4/STATE.md` and follow its protocol.** Resume from the first non-DONE step.

## Mission

`fact_trade_outcomes` has not been written since June because the only writer, `src/layer0/persist_trade_outcomes.py`, fails on import. Every retrain since then has silently re-derived verdicts from stale outcomes. Fix the packaging, rebuild outcomes, re-run the attribution/OOS pipeline on fresh data, and make this class of failure loud instead of silent.

> **[REVISED 2026-07-29 — the original diagnosis in this section was wrong.]** The space-named directories (`Mean Reversion `, ` Volatility Expansion and Compression `) contain **only README.md**. Python never imports them, so they never broke anything; renaming them is housekeeping, not the fix. The actual break is three stacked failures left by the `layer0` subpackage reorg (`core_engine/`, `qualification/`, `data_access/`, `promotion/`):
> 1. `src/layer0/strategies/__init__.py` was deleted when the strategy modules were moved down into `strategies/strategieStaged/`, degrading `layer0.strategies` to an implicit namespace package → `cannot import name 'TrendEMAADXStrategy' … (unknown location)`.
> 2. The moved modules kept pre-move relative imports (`from ..strategy_base`, `from ..indicators`) — one level too shallow *and* aimed at pre-reorg locations. Correct: `...core_engine.strategy_base`, `...data_access.indicators`.
> 3. `src/layer0/qualify_strategies.py` was an 11-line shim followed by a verbatim 1,460-line copy of the whole pre-reorg module, which re-executed everything against the flat pre-reorg paths.
>
> It stayed invisible for a month because the shim's `except ImportError:` fallback discarded the real error and re-raised `No module named 'qualification'`, sending investigators to the wrong place.

## Read first

- `CLAUDE.md` (repo root) — especially SYSTEM 1 RUNTIME, DATABASE, AGENT RULES
- `src/layer0/persist_trade_outcomes.py` — trace its full import chain before editing anything
- `docs/proposed-fixes/system-1/FIX-S1-008-gatekeeper-leakage-pipeline-unification-gates.md` §6c — the OOS re-measurement this unblocks

## Agent team

- **Agent A (Explore, read-only):** map every import of `layer0.strategies.*` across the repo; list every consumer of `fact_trade_outcomes`; report exact directory names (use `ls -b` to expose trailing spaces). Output: a dependency map. Run this FIRST.
- **Agent B (general-purpose, implementer):** packaging fix + writer repair (steps 1–3).
- **Agent C (general-purpose, data):** backfill + re-measure (steps 4–5).
- **Agent D (general-purpose, hardening):** fail-fast guards + tests (step 6).
B, C, D run sequentially — each depends on the previous. Do not parallelize writes.

## Execution plan

1. **Map (Agent A).** `find src/layer0/strategies -maxdepth 2 | cat -A | head -50` to see exact names. `grep -rn "layer0.strategies\|from strategies\|import strategies" src/ --include=*.py`. Record findings in STATE.md Knowledge notes.
2. **Rename un-importable directories (Agent B).** `git mv` each directory with spaces to snake_case (`mean_reversion`, `volatility_expansion_compression`, check `trend`, `research`, `strategieStaged` → leave names that are already importable alone). Update every import/reference Agent A found, including any path strings in configs. Do NOT touch the intentional `archieved` typo elsewhere in the repo.
3. **Restore the package (Agent B).** Add `src/layer0/strategies/__init__.py` (and `__init__.py` in each strategy subpackage that needs one). Verify: `python -c "import src.layer0.persist_trade_outcomes"` exits 0, and `python -m src.layer0.persist_trade_outcomes --help` (or its documented entry form) runs.
4. **Rebuild outcomes (Agent C).** [REVISED 2026-07-29: this step's premise was wrong in three ways — corrected below.]
   - *It is not a backfill.* `persist_trade_outcomes.run()` does `DELETE FROM fact_trade_outcomes WHERE strategy_id IN (...)` + `commit()` and then re-runs the entire backtest. There is no `ON CONFLICT` and no way to write only a date window. **Snapshot the table first** (`CREATE TABLE fact_trade_outcomes_bak_<date> AS SELECT * FROM fact_trade_outcomes`) — a crash between the DELETE and the inserts leaves it empty.
   - *Pass `--lookback-years 10`.* The default is 5 and would silently discard half the history (the incumbent June vintage is 10y / 134,520 rows; 5y yields 66,597 from 2021-08). Short history would gut the vetting OOS≥60mo gate and make T3's incumbent comparison dishonest.
   - *`psql` has no password on this box* — the `sa` role needs one interactively. Query through the repo helper instead: `python -c "from src.common.db import get_engine; ..."`.
   ```bash
   python -m src.layer0.persist_trade_outcomes --granularities H1,H4 --lookback-years 10
   ```
   Record before/after row counts **and the min/max trade timestamp per granularity** — row count alone hides a history truncation.
5. **Re-measure (Agent C).** With fresh outcomes: `python -m src.system1.attribution.attribute` then `python -m src.system1.vetting.vet` (**log-only, NO `--live`**). This produces the proposed map/weights on honest data — T3 consumes it. Do not promote anything in this task.
6. **Fail-fast (Agent D).** Find every place a pipeline catches ImportError/module-load failure and continues with stale data (start from Agent A's map; check the orchestrator and any `try: import` blocks in layer0/system1). Replace silent fallbacks with a raised error + clear log line. Add a regression test: a suite test that simply imports the outcomes writer module (so a future packaging break fails CI/pytest loudly), and a test that the writer refuses to run if its strategy imports fail.

## Validation

```bash
pytest src/layer0/tests/ src/system1 -v          # all green, including the new import-guard tests
python -c "import src.layer0.persist_trade_outcomes; print('import OK')"
```

[REVISED 2026-07-29: `src/layer0/tests/` did not exist before this task — it is created here, so on a fresh run the first command only works after step 6. And `psql` prompts for a password on this box; query through `src.common.db` instead:]

```bash
python - <<'PY'
from src.common.db import get_engine
from sqlalchemy import text
with get_engine().connect() as c:
    print("rows:", c.execute(text('SELECT count(*) FROM fact_trade_outcomes')).scalar())
    for r in c.execute(text('SELECT granularity, min("timestamp") mn, max("timestamp") mx, count(*) n '
                            'FROM fact_trade_outcomes GROUP BY 1 ORDER BY 1')):
        print(f"  {r.granularity} {r.mn:%Y-%m-%d}..{r.mx:%Y-%m-%d} n={r.n}")
PY
```

Compare against the step-4 'before' numbers: the max timestamp must move to the current week **and the min timestamp must not regress** (a higher max with a truncated min means history was silently discarded — see the `--lookback-years` note).

Freshness check: the max outcome timestamp is within the current week. Attribution output (`fact_strategy_regime_attribution` / `results/state/strategy_regime_attribution.parquet`) has a newer mtime/rows than before.

## Live run check

Run `python -m src.system1.scheduler.orchestrator` (no `--force`) once and confirm it exits cleanly (`no_trigger_or_cooldown` is a PASS — it means the pipeline loads and evaluates without import errors).

## Acceptance criteria

- [x] `src/layer0/strategies` is a proper importable package; no directory names contain spaces
- [x] Outcomes writer runs; `fact_trade_outcomes` max timestamp is 2026-07-24 (last market close, current week)
- [x] Attribution + vetting re-run on fresh data (log-only proposal produced: 80 cells → 4 qualifying)
- [x] Import failures now raise; 42 regression tests added and green (plus 173 system1 tests)
- [x] Committed in small logical commits `852b5bd` / `fde893b` / `aed6cb4`. No co-author trailer.

## Deliverables (required — task is not DONE without them)

Write to `task/2026-July-week4/deliverables/T1/`:

1. **`DELIVERABLE.md`** — detailed technical report: every file renamed/created (before→after names), the full import chain that was broken and how it's now wired, backfill window and row counts (before/after per week), which pipelines got fail-fast guards and where, test names added, commit SHAs.
2. **Visuals (2 PNGs, matplotlib with `Agg` backend, saved not shown):**
   - `outcomes_timeline.png` — weekly row counts of `fact_trade_outcomes` from Jan 2026 → today: the June–July dead gap shaded red, the backfilled region shaded green, annotation for the break date and the fix date. This is the one picture that proves the feedback loop is reconnected.
   - `import_graph.png` — simple before/after diagram of the `layer0.strategies` package: broken nodes (space-named dirs, missing `__init__.py`) in red on the left, repaired package tree in green on the right.
3. **`EXECUTIVE_SUMMARY.md`** — max 1 page, plain language for the system owner: what was broken (the system was retraining on stale trade results since June), what was done, what is now true (outcomes current through <date>, N rows recovered, future breaks crash loudly instead of hiding), and what this unblocks (T3's honest promotion).

## On failure

Append root cause to `## Failure log` below, correct the step above in place, update STATE.md, and stop with a clear message: which step failed, what was changed, and that T1 should be re-pasted.

## Failure log

(empty)
