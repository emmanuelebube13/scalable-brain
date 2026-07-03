# AMS-007 — Post-Trade Processor

- **Task ID**: AMS-007
- **System**: System 3 — Account Management
- **Priority**: P0-Critical
- **Estimated Effort**: 3d
- **Prerequisites**: AMS-004, EXEC-005
- **External Dependencies**:
  - **`AMS_Inbound_Queue` (FND-002 contract, produced by EXEC-005)** — fill/close confirmations from Layer 4. *Why:* this is the only way System 3 learns what actually executed; it drives all state updates.
  - **DB (AMS-001)** — write `trade_journal`, `equity_curve`; update `AMS_Account_State`; trigger AMS-006. *Why:* persisted account truth and audit.
  - **OANDA account-data (relayed by System 2)** — periodic account summary for reconciliation. *Why:* detect missed/duplicate fills vs broker truth (System 2 holds the key, not System 3).

## Objective
Build the post-trade processor consuming `AMS_Inbound_Queue` fill confirmations to update balance/equity/drawdown/consecutive counters/P&L and re-evaluate breakers.

## Current State
**New.** Layer 4 logs trades to `Fact_Live_Trades` and Layer 6 reconciles outcomes post-hoc, but no component maintains live account state from fills. Consecutive-loss/daily-P&L/drawdown counters do not exist.

## Target State
A queue consumer that processes each fill/close confirmation **idempotently** (keyed on broker order id), writes a `trade_journal` row (open on fill, completed on close), appends to `equity_curve`, updates `AMS_Account_State` (balance, equity, peak_equity, drawdown, daily/weekly P&L, consecutive win/loss, total_trades_today) via AMS-004, then re-runs the circuit-breaker engine (AMS-006) and the state-machine auto-transitions. Periodically reconciles against the broker summary.

## Technical Specification

### Inbound message contract (`AMS_Inbound_Queue`, from EXEC-005)
`event_type` (FILL | CLOSE | PARTIAL_CLOSE | REJECT), `broker_order_id`, `decision_id` (links back to `AMS_Decision_Log`), `pair`, `direction`, `fill_price`, `fill_time_utc`, `units/lots`, `realized_pnl_usd` (on CLOSE), `exit_reason` (SL/TP/TIME/MANUAL on CLOSE), `slippage_pips`, `equity_after`, `balance_after`, `margin_used_pct`. Reject/log malformed messages; never silently drop.

### Processing pipeline (per message)
```
on confirmation:
    if seen(broker_order_id, event_type): return    # idempotent (unique index)
    if FILL:   open trade_journal row (pre-trade snapshot from decision_id)
    if CLOSE:  complete trade_journal row (exit price/time/pnl/reason/duration/slippage)
    update AccountState:
        balance/equity = from message (authoritative) or recompute
        peak_equity = max(peak_equity, equity)        # monotonic
        drawdown_pct = (peak_equity - equity) / peak_equity * 100
        daily_pnl += realized_pnl (UTC-day scoped); weekly_pnl += ...
        if CLOSE win:  consecutive_wins += 1; consecutive_losses = 0
        if CLOSE loss: consecutive_losses += 1; consecutive_wins = 0
        total_trades_today += 1 on FILL
    append equity_curve point
    AMS-004.apply_metrics(...)        # auto-transitions
    AMS-006.evaluate()                # re-run breakers
    persist atomically; log
```

### Idempotency & ordering
- Unique index on `trade_journal.broker_order_id` (AMS-001) enforces dedupe; out-of-order FILL/CLOSE handled by upserting the journal row.
- All `AMS_Account_State` updates are a single atomic transaction so a crash mid-update never leaves partial counters.

### UTC-day / week rollover
- A scheduled rollover at UTC midnight: snapshot `daily_summary`, reset `daily_pnl`, set `daily_start_equity`. Weekly rollover Monday 00:00 UTC resets `weekly_pnl`/`weekly_start_equity`. Rollovers also clear day-scoped breaker locks (Daily Limit) where due.

### Reconciliation
- Periodically compare AMS `current_balance`/open-position set against the broker account summary relayed by System 2. On divergence beyond tolerance: log, alert (AMS-011), and bias safe (do not over-credit equity). Reconciliation never silently overwrites without an audit row.

### Restart recovery
- On startup, the processor replays unacked inbound messages (FND-002 semantics) and trusts the persisted `AMS_Account_State`; idempotency prevents double-counting.

## Testing & Validation
- Unit: FILL opens journal row; CLOSE completes it with correct realized P&L, duration, slippage.
- Counter logic: win resets consecutive_losses; loss increments; daily/weekly P&L accumulate and roll over at UTC boundaries.
- Drawdown: peak_equity is monotonic; drawdown recomputed correctly after a loss then a recovery.
- Idempotency: replaying the same CLOSE twice changes nothing.
- Out-of-order: CLOSE arriving before its FILL still yields a correct completed row.
- Breaker hook: a loss that makes it the 5th consecutive triggers AMS-006; a loss crossing 20% DD triggers Max Drawdown.
- Reconciliation: injected divergence is detected, alerted, and audited.
- Crash recovery: kill mid-batch; on restart counters are exactly right (no double count).

## Rollback Plan
The consumer is flag-gated; off, fills are not processed (acceptable only in DEMO/manual operation — the operator is alerted). Because processing is idempotent and atomic, re-enabling and replaying the queue rebuilds state. Rollback never deletes `trade_journal`/`equity_curve` history.

## Acceptance Criteria
- [ ] Consumes `AMS_Inbound_Queue`, writing/completing `trade_journal` rows and appending `equity_curve` points idempotently.
- [ ] Updates balance/equity/peak_equity/drawdown/daily+weekly P&L/consecutive counters atomically and correctly across UTC rollovers.
- [ ] Re-runs AMS-006 breakers and AMS-004 transitions after every close.
- [ ] Idempotent and out-of-order safe; crash mid-batch leaves no double-counting on restart.
- [ ] Periodic reconciliation vs broker summary detects, alerts, and audits divergence.

## Notes & Risks
- This is the heartbeat that keeps the gate honest — if fills are missed, every downstream check uses stale state. Dedupe and reconciliation are non-negotiable.
- Trust the broker's `equity_after`/`balance_after` as authoritative where present; recompute only as a cross-check.
- Coordinate the inbound contract with EXEC-005; share a contract test with System 2.
