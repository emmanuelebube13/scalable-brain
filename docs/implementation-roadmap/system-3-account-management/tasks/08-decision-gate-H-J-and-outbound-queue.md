# AMS-008 — Decision Gate H–J + Outbound Queue

- **Task ID**: AMS-008
- **System**: System 3 — Account Management
- **Priority**: P0-Critical
- **Estimated Effort**: 3d
- **Prerequisites**: AMS-005, AMS-006
- **External Dependencies**:
  - **`AMS_Outbound_Queue` (FND-002 contract, consumed by EXEC-004)** — the approved-order channel to Layer 4. *Why:* this is System 3's output; Layer 4 executes only what lands here.
  - **DB (AMS-001)** — read open positions/`risk_state`; write `AMS_Decision_Log`. *Why:* exposure/correlation checks and full decision logging.
  - **`Fact_Macro_Events`** — for time-based news rules (Gate Layer I). *Why:* avoid entering near major events.
  - **Weekend/holiday manager (AMS-013)** — supplies Friday-close / Sunday-open / holiday windows for Layer I (soft dependency; Layer I has built-in Friday/Sunday defaults until AMS-013 lands).

## Objective
Implement Decision Gate Layers H–J (open-position & correlation limits, time-based rules, final approval) and publish approved orders to `AMS_Outbound_Queue` with full decision logging.

## Current State
**New** as a gate. The correlation/exposure logic exists in `src/layer4_executor/live_pipeline.py` (`MAX_TOTAL_EXPOSURE_PCT=0.25`, `CORRELATION_THRESHOLD=0.85`, `CORRELATION_LOOKBACK_BARS=100`) and **moves here**, tightened to the AMS limits (max 5 concurrent, 6%/pair, 10% correlated). There is no time-based gating today.

## Target State
Given the sized signal from AMS-005, the gate runs Layers H and I, and on full pass writes an approved order to `AMS_Outbound_Queue` (Layer J) — closing the end-to-end gate (A–J). Every signal, approved or rejected at any layer, has its final `AMS_Decision_Log` row written here (the single point that finalizes logging for the whole chain).

## Technical Specification

### Layer H — Open-position & correlation
Read current open positions (from `AMS_Account_State` / live position registry maintained by AMS-007) and `correlation_groups` from `risk_config.json`:
- **Max concurrent trades: 5** → if open count ≥ 5, REJECT (`gate_failed=H`, `MAX_CONCURRENT`).
- **Max exposure per pair: 6% of equity** → if this pair's exposure + new ≥ 6%, REJECT (`PAIR_EXPOSURE`).
- **Max correlated exposure: 10% of equity** → compute exposure across the signal's correlation group; if ≥ 10%, REJECT (`CORRELATED_EXPOSURE`).
- Reuse the migrated Pearson correlation logic (lookback ~100 bars, threshold 0.85) to assign/confirm groups; prevent opposing positions in highly-correlated pairs.

### Layer I — Time-based rules (all UTC)
- **Friday after 18:00 UTC** → REJECT (`FRIDAY_CLOSE`, weekend gap risk).
- **First 4h after Sunday open (22:00 UTC)** → REJECT (`SUNDAY_GAP_WINDOW`).
- **Within 2h of a major `Fact_Macro_Events` event** for the signal's currencies → REJECT or REDUCE (apply a size reduction flag) per event severity.
- **≥ 3 losing trades today AND after 20:00 UTC** → REJECT (`END_OF_DAY_PROTECTION`).
- Holiday windows from AMS-013 → REJECT.

### Layer J — Final approval & publish
```
if all layers passed:
    order = build_order(signal, approved_lots, sl, tp, decision_id)
    publish(AMS_Outbound_Queue, order)        # idempotent: keyed by signal_id/decision_id
    decision = APPROVED (or REDUCED if any reduce flag set)
else:
    decision = REJECTED (gate_failed set by the failing layer)
finalize AMS_Decision_Log row (suggested_size, approved_size, gate_failed, reason, snapshots)
record decision_latency_ms (A->J end to end)
```

### Outbound message contract (`AMS_Outbound_Queue`, consumed by EXEC-004)
`decision_id`, `signal_id`, `pair`, `direction`, `approved_lots`, `entry`, `stop_loss`, `take_profit`, `mode` (DEMO ⇒ paper), `issued_at_utc`, `expires_at_utc` (staleness — Layer 4 must not act on an expired approval), `idempotency_key`. DEMO approvals are published flagged as paper so Layer 4 dry-runs them.

### Default-safe & staleness
- Any error in H/I, or inability to read open positions → REJECT (`STATE_UNAVAILABLE`).
- Each approval carries `expires_at_utc`; combined with EXEC-008 (Layer 4 pauses on stale outbound queue), this guarantees no stale approval is ever executed.

## Testing & Validation
- Unit: H rejects at 5 concurrent, 6%/pair, 10% correlated; correlated-group math matches the migrated Layer 4 logic.
- Unit: I rejects on Friday 18:00+, the Sunday 22:00–02:00 window, within 2h of a macro event, and ≥3 losses after 20:00; passes otherwise.
- Approval publish: a full-pass signal lands on `AMS_Outbound_Queue` with a correct, idempotent, expiring message; a duplicate signal_id does not double-publish.
- REDUCED path: a near-event reduce flag yields `decision=REDUCED` with a smaller `approved_size`.
- End-to-end: a signal flows A→J; one `AMS_Decision_Log` row captures the whole chain; latency A→J < 100 ms on H1 (p95).
- Staleness: an approval past `expires_at_utc` is ignored by Layer 4 (joint test with EXEC-008).

## Rollback Plan
Flag-gated publish (`AMS_OUTBOUND_ENABLED`). Off, the gate evaluates and logs but publishes nothing → Layer 4 pauses (EXEC-008), i.e. **safe no-trade**, not unguarded trading. Rolling back H/I to log-only reverts to DEMO behavior. Correlation logic remains available in Layer 4 as a backstop during transition.

## Acceptance Criteria
- [ ] Layer H enforces 5 concurrent / 6% per pair / 10% correlated using the migrated correlation logic.
- [ ] Layer I enforces Friday-close, Sunday-open window, ±2h macro events, and end-of-day loss protection (UTC).
- [ ] Full-pass signals publish an idempotent, expiring approval to `AMS_Outbound_Queue`; DEMO approvals are flagged paper.
- [ ] Every signal finalizes exactly one `AMS_Decision_Log` row; end-to-end A→J latency < 100 ms on H1.
- [ ] On any read error the gate fails closed; stale approvals are never executed (with EXEC-008).

## Notes & Risks
- This task closes the gate — after it, removing System 3 means Layer 4 has nothing to execute, so EXEC-008's safe-pause must be verified in lockstep before any live mode.
- Moving correlation out of Layer 4 must not regress its behavior; keep a contract test comparing AMS Layer H output to the old `evaluate_correlation_gate` for the same inputs during transition.
- The macro-event check depends on `Fact_Macro_Events` freshness; if the table is stale, bias toward REJECT near scheduled events.
