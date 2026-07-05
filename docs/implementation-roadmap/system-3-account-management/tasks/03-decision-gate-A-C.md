# AMS-003 — Decision Gate Layers A–C

- **Task ID**: AMS-003
- **System**: System 3 — Account Management
- **Priority**: P0-Critical
- **Estimated Effort**: 3d
- **Prerequisites**: AMS-002, MODEL-008
- **External Dependencies**:
  - **`Scored_Signal_Queue` (FND-002 contract, produced by MODEL-008)** — the gate's input stream. *Why:* Layer 3 scored signals are what the gate evaluates; without this producer there is nothing to gate.
  - **DB (AMS-001)** — read `AMS_Account_State` / `risk_state`; write `AMS_Decision_Log`. *Why:* gate reads account truth and records every decision.

## Objective
Implement Decision Gate Layers A–C (account mode, circuit-breaker state, daily loss budget) consuming `Scored_Signal_Queue`.

## Current State
**New.** No gate exists. Layer 3 (`src/layer3_ml/`) currently produces approvals consumed directly by Layer 4 (`src/layer4_executor/live_pipeline.py`); System 3 interposes between them. MODEL-008 redirects Layer 3 output to `Scored_Signal_Queue`.

## Target State
The service consumes scored signals, runs the **first three sequential checks**, and either short-circuits to REJECT (logging the failing gate) or passes a partially-evaluated signal context to the rest of the gate (D–J, later tasks). Layer A in DEMO is a **dry-run pass with full logging**. Every signal produces exactly one `AMS_Decision_Log` row. The chain is **default-safe**: any error/missing data → REJECT.

## Technical Specification

### Inbound message contract (`Scored_Signal_Queue`, from MODEL-008)
`signal_id`, `timestamp_utc`, `pair`, `direction` (LONG/SHORT), `strategy_name`, `regime_label`, `xgboost_score`, `proposed_entry`, `proposed_sl`, `proposed_tp`, `timeframe` (H1/H4), `expected_duration_hours` (optional). Reject (with reason `MALFORMED_SIGNAL`) if required fields are missing or the signal is stale beyond the FND-002 staleness window.

### Gate evaluation order (A–C; sequential, fail-fast)
**Layer A — Account mode.** Read `AMS_Account_State.mode`.
- `DEMO`: evaluate all gates as a **dry-run** — log the full decision (incl. computed size from later layers) but mark `decision` so Layer 4 treats it as paper. Never blocks learning.
- `MICRO_LIVE`/`SMALL_LIVE`/`FULL_LIVE`: live evaluation; the stage multiplier (0.5/0.5/0.75/1.0) is applied later in Layer G.

**Layer B — Circuit-breaker / sub-state.** Read `sub_state`:
- `ACTIVE` → pass (full size).
- `CAUTION` → pass but flag a **−50% size** factor for Layer G.
- `PAUSED` → **REJECT** (`gate_failed=B`, reason `ACCOUNT_PAUSED`).
- `CIRCUIT_BROKEN` → **REJECT** (reason `CIRCUIT_BROKEN`).
- `RECOVERY` → pass only highest-confidence; cap risk at 0.5% (flag for Layer G); otherwise REJECT.

**Layer C — Daily loss budget (anti-revenge-trade).** Compute daily realized P&L vs `daily_start_equity`:
- If `daily_pnl ≤ −2% × daily_start_equity` → **REJECT all remaining signals for the rest of the UTC day** (`gate_failed=C`, reason `DAILY_LOSS_BUDGET`). (Note: −2% here is the soft daily-budget reject; the −3% hard daily breaker lives in AMS-006.)
- Else pass remaining daily budget downstream.

### Pseudo-code (decision skeleton)
```
on signal:
    ctx = parse(signal)                 # REJECT MALFORMED on failure
    if stale(ctx): return reject("STALE_SIGNAL", gate="A")
    mode = state.mode
    # Layer A
    dry_run = (mode == DEMO)
    # Layer B
    if sub_state in (PAUSED, CIRCUIT_BROKEN): return reject(reason, gate="B")
    ctx.size_flags += caution/recovery factors
    # Layer C
    if state.daily_pnl <= -0.02 * state.daily_start_equity:
        return reject("DAILY_LOSS_BUDGET", gate="C")
    return PASS_TO_D(ctx)               # hand off to AMS-005 (D–G)
log_decision(ctx, outcome)             # always, one row
```

### Logging
Every outcome → one `AMS_Decision_Log` row with snapshots (`account_balance`, `account_drawdown_pct`, `consecutive_losses`, `daily_pnl`, `xgboost_score`, `gate_failed`, `rejection_reason`). Record `decision_latency_ms` against the AMS-002 metric.

### Default-safe rule
If `AMS_Account_State`/`risk_state` cannot be read, or any exception occurs, **REJECT** with reason `STATE_UNAVAILABLE` and log; never approve on uncertainty.

## Testing & Validation
- Unit: each sub-state (ACTIVE/CAUTION/PAUSED/CIRCUIT_BROKEN/RECOVERY) yields the correct A/B outcome and flags.
- Daily-budget edge: `daily_pnl` exactly at −2% rejects; one cent above passes; budget resets at UTC midnight.
- DEMO dry-run: signal logged as paper, not blocked.
- Malformed/stale signal → REJECT, logged.
- Failure injection: DB read error → REJECT `STATE_UNAVAILABLE` (fail closed).
- Latency: A–C evaluation (with in-memory state) measured **< 100 ms on H1**; assert p95.

## Rollback Plan
Feature-flag the consumer (`AMS_GATE_ENABLED`). Off (or in DEMO) the gate only logs and never blocks live trading. Rollback = disable the flag; signals are logged but not enforced. No state mutation by A–C (read-only except the append-only log), so rollback is clean.

## Acceptance Criteria
- [ ] Service consumes `Scored_Signal_Queue` and writes exactly one `AMS_Decision_Log` row per signal.
- [ ] Layers A, B, C produce the specified pass/reject/flag outcomes including the UTC-day −2% budget lockout.
- [ ] DEMO mode is a full dry-run with logging and never blocks.
- [ ] Any state-read error or malformed/stale signal fails closed (REJECT).
- [ ] A–C decision latency is < 100 ms on H1 (p95 asserted).

## Notes & Risks
- The handoff to D–J must remain in-process (no extra queue hop) to protect the latency budget.
- Keep account state in memory, refreshed by AMS-007 on fills, so the gate avoids a DB round-trip per signal.
- Coordinate the inbound contract precisely with MODEL-008; a field mismatch silently rejecting everything is a real risk — add a contract test shared with System 1.
