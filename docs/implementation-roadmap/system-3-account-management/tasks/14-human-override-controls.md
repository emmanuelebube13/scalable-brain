# AMS-014 — Human-Override Controls

- **Task ID**: AMS-014
- **System**: System 3 — Account Management
- **Priority**: P1-High
- **Estimated Effort**: 2d
- **Prerequisites**: AMS-006
- **External Dependencies**:
  - **DB (AMS-001)** — write `AMS_Circuit_Breaker_Log` (all overrides), drive AMS-004. *Why:* every override is an audited event with mandatory notes.
  - **Notification / Telegram (AMS-011, FND-003)** — override entry point and confirmation. *Why:* the solo operator needs to act from mobile; commands and confirmations flow over Telegram with auth.
  - **Flat-all/close channel (EXEC-004 / Layer 4)** — emergency flat-all execution. *Why:* System 3 issues the close; Layer 4 executes.

## Objective
Implement audited human-override controls (instant PAUSE, emergency flat-all, circuit-breaker reset with mandatory notes, force stage change, live risk-param adjustment).

## Current State
**New.** There is no manual control surface; the operator cannot pause, flatten, or reset anything except by killing processes. All risk constants are code-level.

## Target State
A small, authenticated command surface (Telegram commands and/or an authenticated local API on the Computer-3 health server) that lets the operator perform the five override actions below. Every action routes through AMS-004/AMS-006 (never raw SQL), requires authentication, requires **mandatory notes** for breaker reset, and is fully logged to `AMS_Circuit_Breaker_Log` with the acting user and timestamp, then confirmed via notification.

## Technical Specification

### Override actions
| Command | Action | Routing | Notes required |
|---------|--------|---------|----------------|
| **PAUSE** | Instant halt of new approvals | AMS-004 → `PAUSED` | optional |
| **RESUME** | Leave PAUSE | AMS-004 → `ACTIVE` | optional |
| **FLAT_ALL** | Emergency close all positions | publish close-all to Layer 4 (EXEC-004) + set `PAUSED`/`CIRCUIT_BROKEN` | recommended |
| **RESET_BREAKER** | Clear a circuit breaker / exit CIRCUIT_BROKEN | AMS-006 reset → AMS-004 `CIRCUIT_BROKEN`→`RECOVERY` | **mandatory** |
| **FORCE_STAGE** | Change capital stage | AMS-004 `set_mode` (used by AMS-012 escalation confirm) | mandatory |
| **SET_RISK_PARAM** | Live-adjust a `risk_config.json` risk parameter | validated config update + reload | mandatory |

### Authentication & safety
- Telegram commands accepted only from the configured operator chat id (FND-003); local API requires an auth token. Reject + log unauthorized attempts.
- Two-step confirm for destructive actions (FLAT_ALL, RESET_BREAKER, FORCE_STAGE): the command returns a confirmation token the operator must echo, preventing fat-finger triggers.
- `RESET_BREAKER` and `FORCE_STAGE` and `SET_RISK_PARAM` **require non-null notes** (enforced) — recorded in `AMS_Circuit_Breaker_Log.notes`.
- `SET_RISK_PARAM` is **bounded**: only whitelisted keys, validated against safe ranges (e.g. cannot raise `max_risk_per_trade_percent` above 2.0, cannot disable a breaker entirely); out-of-range → rejected + logged. Changes hot-reload the config (AMS-002 loader) and are versioned.

### Logging contract
Every override → an `AMS_Circuit_Breaker_Log` row: `trigger_type=MANUAL`, `triggered_at`, `action_taken` (the command + params), `reset_by` (operator), `notes`, and for resets `reset_at`. Mirror an audit entry to the structured log + a HIGH notification (AMS-011).

### Interface (pseudo-code)
```
on_command(cmd, args, actor):
    if not authorized(actor): log_denied(); return
    if destructive(cmd) and not confirmed(args): return confirm_token()
    if requires_notes(cmd) and not args.notes: return error("notes required")
    route(cmd, args)                 # via AMS-004 / AMS-006 / config loader / Layer4 close
    log_circuit_breaker(MANUAL, cmd, actor, notes)
    notify(HIGH, "override executed", details)
```

### Default-safe
- If a routed action cannot complete (e.g. Layer 4 doesn't ack FLAT_ALL), do **not** report success; retry/escalate and set the safest state (PAUSED). FLAT_ALL failure is CRITICAL.

## Testing & Validation
- Unit: each command routes through the correct manager and produces the right state transition.
- Auth: commands from a non-operator chat id / bad token are rejected and logged; not executed.
- Mandatory notes: RESET_BREAKER/FORCE_STAGE/SET_RISK_PARAM without notes are rejected.
- Confirmation: destructive commands require the echoed token; a single message does not trigger them.
- Bounded params: SET_RISK_PARAM rejecting out-of-range/whitelist values; in-range value hot-reloads and is versioned.
- FLAT_ALL: issues close-all, waits for Layer 4 ack; on no-ack, escalates to CRITICAL and forces PAUSED (does not falsely report success).
- Audit: every action appears in `AMS_Circuit_Breaker_Log` with actor + notes.

## Rollback Plan
Override surface is additive and flag-gated per command. Rollback = disable the command channel; automatic risk controls (gate, breakers, state machine) continue unaffected — the operator simply loses manual controls, which is safe (the system stays default-safe on its own). No data migration; the audit log is append-only.

## Acceptance Criteria
- [ ] All five overrides (PAUSE, FLAT_ALL, RESET_BREAKER, FORCE_STAGE, SET_RISK_PARAM) work and route through AMS-004/AMS-006/config, never raw SQL.
- [ ] Only the authenticated operator can issue commands; unauthorized attempts are rejected and logged.
- [ ] Destructive commands require confirmation; RESET_BREAKER/FORCE_STAGE/SET_RISK_PARAM require mandatory notes; SET_RISK_PARAM is range-bounded.
- [ ] Every override is logged to `AMS_Circuit_Breaker_Log` with actor + notes and notified (HIGH).
- [ ] FLAT_ALL that fails to ack escalates to CRITICAL and forces a safe state rather than reporting success.

## Notes & Risks
- The override channel is a powerful attack/mistake surface — auth + confirmation + bounded params are mandatory, not optional. A leaked Telegram token could flatten the account; enforce least-privilege and rotation (FND-003).
- Manual breaker reset must always pass through RECOVERY (AMS-004) — never allow a direct CIRCUIT_BROKEN→ACTIVE jump, even by override, without the documented review/validation.
- Keep the command parser dead-simple and well-tested; this is the operator's last-resort safety lever and must work under stress.
