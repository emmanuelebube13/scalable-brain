# AMS-006 — Circuit-Breaker System

- **Task ID**: AMS-006
- **System**: System 3 — Account Management
- **Priority**: P0-Critical
- **Estimated Effort**: 3d
- **Prerequisites**: AMS-004
- **External Dependencies**:
  - **DB (AMS-001)** — write `AMS_Circuit_Breaker_Log`; read/write `AMS_Account_State` via AMS-004. *Why:* every breaker event is an audit record and drives a state transition.
  - **Notification service (AMS-011)** — CRITICAL alerts on trigger (soft dependency; degrade to log if unavailable). *Why:* the operator must know immediately when trading halts.
  - **Flat-all path (EXEC-004 / Layer 4)** — MAX_DRAWDOWN/margin breakers request position closure via the outbound channel. *Why:* System 3 decides; Layer 4 executes the close.

## Objective
Implement the multi-layer circuit-breaker system with automatic actions and `AMS_Circuit_Breaker_Log` logging.

## Current State
**New.** No automatic hard stops exist; risk is only the per-trade correlation/sizing checks in Layer 4/7. There is no daily/weekly/drawdown/consecutive-loss halt.

## Target State
A `CircuitBreakerEngine` re-evaluated on every metric update (from AMS-007 fills and periodic ticks) that fires the eight breakers below, takes the prescribed automatic action via AMS-004 (sub-state transition) and, where needed, requests a flat-all/close, logs every trigger and reset to `AMS_Circuit_Breaker_Log`, and fires a CRITICAL notification. Breakers are evaluated **before** the gate approves anything (Layer B reads the resulting sub-state) and **after** every fill.

## Technical Specification

### The eight breakers (thresholds from `risk_config.json`)
| Breaker | Trigger | Automatic action | Reset condition |
|---------|---------|------------------|-----------------|
| **Soft Stop** | daily loss ≥ 2% equity | −50% size, pause 30 min | manual resume or next UTC day |
| **Daily Limit** | daily loss ≥ 3% equity | STOP 24h | next UTC midnight |
| **Weekly Limit** | weekly loss ≥ 6% equity | STOP for week; 0.5% risk next week | following Monday |
| **Max Drawdown** | peak-to-trough ≥ 20% | **close ALL positions**, enter RECOVERY | manual review + 1-week demo |
| **Consecutive Loss** | 5 losses in a row | STOP, require manual review | after 24h cooling |
| **Margin Proximity** | margin used ≥ 80% | close largest losing position | margin used < 60% |
| **Correlation Shock** | correlated pairs all losing together | close all correlated positions | next trading session |
| **Volatility Spike** | volatility > 2σ | −50% all positions/sizing | volatility normalized |

### Action mapping to state machine (AMS-004)
- Soft Stop → set `CAUTION` (−50%) + a 30-min `cooling_until` in `risk_state`; auto-clear after pause.
- Daily/Weekly/Consecutive → set `PAUSED` (Daily 24h, Weekly to Monday, Consecutive 24h cooling) with `cooling_until`; record reason.
- Max Drawdown → set `CIRCUIT_BROKEN`, set `circuit_break_reason`, request **flat-all** (publish a close-all instruction to Layer 4), then await manual review → RECOVERY (AMS-014).
- Margin / Correlation Shock → request targeted close (largest loser / correlated set) and flag CAUTION.
- Volatility Spike → apply a global −50% size factor written to `risk_state` (consumed by Layer G).

### Evaluation & idempotency
- Re-evaluate on every fill (AMS-007) and on a periodic tick (for margin/volatility from account-summary data relayed by System 2).
- Each breaker is idempotent: if already active, do not re-trigger or re-log; extend `action_taken` only on a worsening value.
- On reset (auto or manual), set `reset_at` + `reset_by` and transition the state machine back appropriately.
- Multiple simultaneous triggers: apply the **most severe** action (CIRCUIT_BROKEN > PAUSED > CAUTION); log each breaker separately.

### Logging contract (`AMS_Circuit_Breaker_Log`)
`triggered_at`, `trigger_type`, `trigger_value`, `threshold`, `action_taken`, `reset_at`, `reset_by`, `notes`. Manual resets (AMS-014) require non-null `notes`.

### Default-safe
If breaker evaluation cannot read state/metrics, **assume the worst and PAUSE** (do not let trading continue unevaluated). Log `EVAL_FAILURE`.

## Testing & Validation
- Unit: each breaker fires exactly at its threshold (2%, 3%, 6%, 20%, 5 losses, 80% margin, 2σ) and not below.
- Action correctness: each trigger drives the right AMS-004 transition and the right close/flat request.
- Idempotency: repeated worse ticks don't double-log or double-close.
- Reset paths: Daily resets at UTC midnight; Weekly at Monday; Soft Stop after 30 min; manual reset requires notes and routes via AMS-014.
- Severity ordering: simultaneous Daily(3%) + Drawdown(20%) → CIRCUIT_BROKEN wins, both logged.
- **March-2020 scenario**: feed a gap + volatility spike + cascading losses → Volatility Spike halves sizes, Drawdown breaker closes all at 20%, RECOVERY entered, all events logged; verify no trade approved during the halt.
- Failure injection: state unreadable → PAUSE (fail closed).

## Rollback Plan
Each breaker is individually flag-gated. Rollback = disable a misbehaving breaker (it logs but does not act) while keeping the others; or set all to log-only in DEMO. Because actions route through AMS-004 + the close channel, disabling a breaker cannot leave the account in an inconsistent state. The append-only log is never rolled back.

## Acceptance Criteria
- [ ] All eight breakers trigger at their exact thresholds with the correct automatic action and AMS-004 transition.
- [ ] Every trigger and reset is logged to `AMS_Circuit_Breaker_Log`; manual resets require notes.
- [ ] Max Drawdown closes all positions and enters RECOVERY; margin/correlation breakers close the correct subset.
- [ ] Simultaneous triggers apply the most severe action; breakers are idempotent.
- [ ] The March-2020-style simulation halts trading correctly with no approvals during the halt; failure to evaluate fails closed (PAUSE).

## Notes & Risks
- The flat-all path crosses to Layer 4 (EXEC-004) — define the close-all/close-subset instruction contract jointly; a missed close during a breaker is catastrophic. Confirm Layer 4 acks the close.
- Margin/volatility inputs originate at the broker via System 2; their relay latency must stay inside the breaker tick budget — stale margin data should bias toward closing, not waiting.
- Weekly/daily boundaries are UTC; clock skew (FND-008/NTP) must be correct or budgets reset wrongly.
