# FIX-S3-001 — Correlation & exposure gates are blind to open positions (never fire in production)

**Severity:** P1 (distorts trust / a risk guard that cannot reject)
**Status:** Proposed
**Author:** Claude (System-3 risk-engine audit)
**Date raised:** 2026-06-26
**Scope:** `src/layer4_executor/live_pipeline.py` — `ExecutionPipeline.open_positions`,
`evaluate_correlation_gate`, `write_pre_execution_log` / `log_skipped_trade`
**Category:** (2) validity gap · (5) contract/handoff mismatch
**Risk to live trading:** The two portfolio-level risk guards (correlation ≤ 0.85, max exposure)
silently pass everything, so nothing prevents the book from loading up on correlated positions.

---

## 1. Executive summary

Layer 4 advertises two portfolio risk guards — a correlation gate (max 0.85 pairwise correlation)
and an exposure cap (max 25% / "max correlated positions") — evaluated in `evaluate_correlation_gate`
against `self.open_positions`. **`self.open_positions` is initialized to `[]` on every pipeline
construction and is only ever appended to *after a successful broker fill inside the same process
run*. It is never loaded from the broker or from `fact_live_trades`.** Because Layer 4 runs as an
hourly cron (`shell/cron_layer4_pipeline.sh`) that constructs a fresh `ExecutionPipeline` each time,
every run starts believing the book is empty. Positions opened in prior runs (still open at OANDA)
are invisible. In the common case of ≤1 fill per hourly window, the gate therefore evaluates against
an empty list and **can never reject** — the textbook "guard that never fires" red flag.

A second, compounding defect makes this impossible to even detect from data: the decision/veto fields
the pipeline tries to record (`model_decision`, `veto_reason`, `execution_status`) **do not exist in
the drifted `fact_live_trades` table and are silently dropped by the schema-aware upsert**, so
rejection counts cannot be queried at all.

---

## 2. Evidence

**A. `open_positions` is per-run and never hydrated.**
```
live_pipeline.py:1470   self.open_positions: List[Dict[str, Any]] = []   # in __init__, every run
live_pipeline.py:1719   self.open_positions.append({...})                # only after a successful fill
```
`grep -n open_positions live_pipeline.py` shows the list is read by the gate (1619, 1051, 1060, 1083)
but written **only** at 1719 (post-fill, same run). There is no query of `fact_live_trades` or the
broker `OpenPositions` endpoint anywhere in the module. The cron driver creates a new process per
hour, so state never carries over.

Consequence in `evaluate_correlation_gate` (live_pipeline.py:1050-1121): with `open_positions == []`,
`total_exposure = 0` (passes the cap), the `for position in open_positions` loop body never executes,
`correlated_assets` stays empty, and the function returns `passed=True`. The 0.85 threshold and the
`MAX_CORRELATED_POSITIONS=2` rule are dead unless ≥2 fills land in a single hourly run.

**B. Rejection counts cannot be measured — the audit columns don't exist.**
`fact_live_trades` live columns (queried from `information_schema`):
```
trade_id, timestamp, asset_id, strategy_id, signal_value, entry_price, stop_loss,
take_profit, confidence_score, is_approved, actual_outcome, created_at, updated_at
```
`write_pre_execution_log` (live_pipeline.py:1337-1355) and `log_skipped_trade` (1432-1443) build
`candidate_values` containing `model_decision`, `veto_reason`, `execution_status`, `granularity`,
`symbol`, `atr_value`, `adx_value`, `order_id` — **none of which are present** — and
`_upsert_live_trade` (1376-1383) filters to `cols = [c for c in candidate_values if c in present]`,
dropping them with only a `debug` log. So `VETOED_CORRELATION` / `VETOED_MODEL` reasons are never
persisted; you cannot run "query the gate's rejection counts" because the column was thrown away.
`fact_live_trades` currently holds **0 rows** (verified), consistent with the table being effectively
write-degraded plus practice-only operation.

This is exactly the exemplar bar from FIX-S1-002 ("a gate that never rejects is suspect"), here made
worse because the rejection signal is also unloggable.

---

## 3. Root cause

The pipeline conflates *intra-run* state with *portfolio* state. The correlation/exposure gate was
written as if `ExecutionPipeline` were a long-lived process accumulating positions, but it is invoked
as a stateless hourly batch. No component reconciles the in-memory `open_positions` with the actual
open book (broker positions or unresolved `fact_live_trades`). Separately, the consumer table drifted
to a narrow schema and the producer was never reconciled, so the decision audit trail is dropped.

---

## 4. Proposed fix

1. **Hydrate `open_positions` at run start** from ground truth before processing any signal:
   - Preferred: query OANDA `positions.OpenPositions` for the account and map instruments → asset_id.
   - DB fallback: `SELECT ... FROM fact_live_trades WHERE actual_outcome IS NULL` (still-open trades),
     joined to `dim_asset` for symbol/granularity, to seed the list.
   Do this in `ExecutionPipeline.run()` right after `load_symbol_map()`.
2. **Persist the decision audit** so gates are observable: either widen `fact_live_trades` with
   `model_decision text`, `veto_reason text`, `execution_status text` (paired migration + doc), or
   route skip/veto decisions to `fact_execution_log` (which already exists per CLAUDE.md) instead of
   silently dropping them. Add a one-line WARN (not debug) when candidate columns are dropped so the
   loss is never silent again.
3. **Add a self-test** that fails the run if the correlation gate has *structurally* nothing to act on
   when the broker reports ≥1 open position (detects the blindness regression).

## 5. Validation plan

- Unit test: construct a pipeline, seed `open_positions` via the new hydrator with two correlated
  assets, assert `evaluate_correlation_gate` returns `passed=False`. Today this is unreachable.
- Integration: with ≥2 unresolved rows in `fact_live_trades`, assert the next run's gate sees them.
- After fix, query `fact_live_trades`/`fact_execution_log` and confirm non-zero `VETOED_*` counts
  appear over a backtest replay — i.e. the gate demonstrably rejects.

## 6. Rollout / risk

Read-path change (hydration) is additive and safe to ship behind a flag (`--skip-correlation-check`
already exists for emergency bypass). The schema widening is a paired migration; until then, routing
to `fact_execution_log` is non-destructive. No change to sizing or order placement.

## 7. One-paragraph summary

Layer 4's correlation (≤0.85) and exposure guards evaluate against `self.open_positions`, a list that
is reset to `[]` every hourly cron run and only filled by fills *within that same run*; it is never
loaded from the broker or DB, so each run thinks the book is empty and the guards can never reject —
a guard that never fires. Worse, the veto/decision fields the pipeline tries to log
(`model_decision`, `veto_reason`, `execution_status`) don't exist in the drifted `fact_live_trades`
table and are silently dropped, so the rejection count can't even be queried. Fix: hydrate
`open_positions` from OANDA open positions (or unresolved `fact_live_trades`) at run start, and
persist the decision audit to a column/table that exists so the gate is observable.
