# MODEL-009 — Retraining Scheduler

**Task ID:** MODEL-009
**System:** System 1 — Model Building
**Priority:** P2-Medium
**Estimated Effort:** 3d
**Prerequisites:** MODEL-007
**External Dependencies:**
- **Scheduler / cron** on Computer 1 — triggers the weekly job (existing pattern: `shell/cron_layer4_pipeline.sh`, `shell/retrain_tournament.sh`).
- **`ForexBrainDB` (PostgreSQL 16 + TimescaleDB, FND-004)** — read live performance metrics for triggers; via `src/common/db.py`. *(DB = PostgreSQL 16 + TimescaleDB; any historical SQL-Server mention is obsolete.)*
- **MLflow** — compare candidate vs incumbent for deployment gates.
- **Object storage** (FND-001, via MODEL-007) — publish the new bundle on successful retrain.
- **Queue / telemetry** (FND-002) — receive circuit-breaker / performance signals from System 2/3.

## Objective
Implement weekly scheduled retraining (Sunday 00:00 UTC) plus performance-triggered retraining (rolling 14-day Sharpe < 0.3, regime accuracy < 70%, or any circuit-breaker event).

## Current State
- Retraining is manual: `shell/retrain_tournament.sh` and the Layer 3 promotion command are run by hand. There is no scheduled cadence and no automatic, performance-triggered retraining. MODEL-001→007 produce the artifacts a scheduler would orchestrate.

## Target State
An orchestrator that runs the full System 1 retrain pipeline on a **weekly schedule (Sunday 00:00 UTC)** and **on demand when performance degrades**. It evaluates trigger conditions, runs the pipeline (ingest delta → features → regime → attribution → vetting → gatekeeper → serialize/publish via MODEL-007), applies **deployment gates** before promotion, and rolls forward `latest.json` only if the candidate passes. All runs are logged with lineage; failures alert and never promote a worse model.

## Technical Specification

**Schedule:** cron entry firing **Sunday 00:00 UTC**, sized to finish within the weekend window before markets reopen (per the compute/latency budget in dependencies). Reuses the established shell-cron pattern.

**Performance triggers (any fires a retrain):**
- **Rolling 14-day Sharpe < 0.3** — computed from live trade outcomes (System 2/3 telemetry / `Fact_Live_Trades` equivalent surfaced to System 1).
- **Regime accuracy < 70%** — HMM predicted vs realized regime over the recent window (MODEL-003 metric).
- **Any circuit-breaker event** — a signal raised by System 2/3 (e.g., drawdown breach, anomaly) delivered via queue/telemetry.
Triggers are evaluated on a frequent poll (e.g., hourly); a debounce prevents repeated retrains within a cooldown window.

**Retrain pipeline (orchestration order):** incremental ingest (MODEL-001 delta) → feature build (MODEL-002 new version) → regime fit (MODEL-003) → per-regime attribution (MODEL-004) → vetting + maps (MODEL-005) → gatekeeper + dynamic threshold + OOS uplift (MODEL-006) → serialize + publish (MODEL-007).

**Deployment gates (must pass before promoting `latest.json`):**
- HMM convergence + regime accuracy ≥ 70%.
- Vetting produces a non-empty `regime_strategy_map.json`.
- Gatekeeper OOS uplift non-negative and significant, and **≥ incumbent** on the OOS comparison (MODEL-006 + MLflow compare).
- Bundle checksums verified (MODEL-007).
A candidate failing any gate is **not promoted**; the incumbent `latest.json` stays. Optionally run the candidate in **shadow/canary** (scored but not pointed-to) before promotion.

**State / lineage:** each run records trigger reason (scheduled vs which performance trigger), pipeline step outcomes, gate results, candidate vs incumbent metrics, and final promote/skip decision — to MLflow and `results/state/`.

**Pseudo-code (clarifying only):**
```
on schedule(Sunday 00:00 UTC) or on trigger(sharpe14<0.3 | regime_acc<0.70 | circuit_breaker):
  if within_cooldown(): return
  candidate = run_pipeline(MODEL-001..006)
  if not deployment_gates_pass(candidate): log("skip, keep incumbent"); alert(); return
  bundle = serialize_and_upload(candidate)        # MODEL-007
  promote_latest(bundle.version)                  # atomic latest.json update
  log_run(trigger, gates, candidate_vs_incumbent)
```

## Testing & Validation
- **Schedule test:** cron fires at Sunday 00:00 UTC (simulate clock); job runs end-to-end on a small dataset within the budget.
- **Trigger tests:** inject 14-day Sharpe < 0.3, regime accuracy < 70%, and a circuit-breaker message — each independently fires a retrain; cooldown debounce prevents storms.
- **Gate tests:** a deliberately degraded candidate is **not** promoted (incumbent `latest.json` unchanged); a passing candidate promotes atomically.
- **Idempotency/restart:** an interrupted retrain resumes or restarts cleanly without partial promotion (relies on MODEL-007 atomic pointer).
- **Edge cases:** concurrent scheduled + triggered run (single-flight lock), missing live metrics (fail safe = do not promote), pipeline step failure (abort, alert, keep incumbent).

## Rollback Plan
Promotion is gated and atomic; if a promoted model misbehaves, roll back via MODEL-007's `latest.json` pointer revert to the previous bundle. The scheduler can be disabled (cron off / flag) reverting to manual retrains using the existing `retrain_tournament.sh` flow with no other change.

## Acceptance Criteria
- [ ] Weekly retrain fires at Sunday 00:00 UTC and completes within the compute/latency budget.
- [ ] Performance triggers (14-day Sharpe<0.3, regime accuracy<70%, circuit-breaker) each independently initiate a retrain, with cooldown debounce.
- [ ] Deployment gates block promotion of a candidate that fails quality/uplift/checksum checks; incumbent stays.
- [ ] A passing candidate is serialized, published, and `latest.json` promoted atomically (via MODEL-007).
- [ ] Every run logs trigger reason, gate results, candidate-vs-incumbent metrics, and the promote/skip decision.

## Notes & Risks
- Auto-promoting a worse champion is the key risk — the must-beat-incumbent OOS gate plus optional shadow/canary and one-click pointer rollback are the controls.
- Performance triggers depend on live metrics flowing back from System 2/3; define that contract (queue/telemetry) so System 1 can read Sharpe/regime-accuracy/circuit-breaker signals.
- Single-flight locking prevents a scheduled and a triggered run colliding.
