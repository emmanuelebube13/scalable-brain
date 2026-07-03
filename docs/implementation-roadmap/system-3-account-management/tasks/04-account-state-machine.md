# AMS-004 — Account State Machine

- **Task ID**: AMS-004
- **System**: System 3 — Account Management
- **Priority**: P0-Critical
- **Estimated Effort**: 3d
- **Prerequisites**: AMS-002
- **External Dependencies**:
  - **DB (AMS-001)** — read/write `AMS_Account_State`, `risk_state`. *Why:* the state machine is persisted truth that survives restarts.

## Objective
Implement the Account State Manager and full state machine (modes × sub-states) with documented auto-transitions and persistence to `AMS_Account_State`.

## Current State
**New.** No notion of account "mode" or "sub-state" exists; Layer 4/7 trade in one fixed (demo) mode with constant risk. Balances/drawdown/counters are not tracked centrally.

## Target State
A single in-memory `AccountStateManager`, loaded from `AMS_Account_State` at startup and persisted on every change, that owns the current **mode** (DEMO/MICRO_LIVE/SMALL_LIVE/FULL_LIVE) and **sub-state** (ACTIVE/CAUTION/PAUSED/CIRCUIT_BROKEN/RECOVERY). It exposes read accessors to the gate (AMS-003/005/008), accepts transition triggers from the post-trade processor (AMS-007), circuit breakers (AMS-006), and human overrides (AMS-014), and refuses illegal transitions. Every transition is persisted and logged.

## Technical Specification

### Modes (capital stages) and their risk caps
| Mode | Account | Max risk/trade | Stage multiplier |
|------|---------|----------------|------------------|
| DEMO | Practice | full logic, no real money | 0.5 |
| MICRO_LIVE | Live $1K–$5K | 1.0% | 0.5 |
| SMALL_LIVE | Live $5K–$10K | 1.5% | 0.75 |
| FULL_LIVE | Live $10K+ | 2.0% | 1.0 |

### Sub-states (apply to any mode)
| Sub-state | Meaning | Effect on gate |
|-----------|---------|----------------|
| ACTIVE | Normal | full size |
| CAUTION | DD building / losses building | −50% size |
| PAUSED | Manual halt | reject new trades; manage existing |
| CIRCUIT_BROKEN | Auto hard stop | reject all; positions flat |
| RECOVERY | Post-circuit | ≤0.5% risk, demo validation 1 week, highest-confidence only |

### Auto-transitions (documented, enforced)
| From | To | Trigger |
|------|----|---------|
| any | PAUSED | Manual command (AMS-014) |
| PAUSED | ACTIVE | Manual command (AMS-014) |
| ACTIVE | CAUTION | drawdown > 10% **OR** 3 consecutive losses |
| CAUTION | ACTIVE | drawdown recovers < 8% **AND** a win on the next trade |
| any | CIRCUIT_BROKEN | drawdown ≥ 20% **OR** daily loss ≥ 3% **OR** 5 consecutive losses |
| CIRCUIT_BROKEN | RECOVERY | manual review completed (AMS-014, mandatory notes) |
| RECOVERY | DEMO | start 1-week demo validation |
| RECOVERY | previous stage | after 1 profitable week on demo |

Notes: drawdown uses `peak_equity` (monotonic). Mode (capital stage) escalation/de-escalation is owned by AMS-012; AMS-004 only persists the mode the deployment manager / override sets and enforces its risk cap. The hysteresis (10% in / 8% out) prevents flapping.

### Persistence & restart
- Load `AMS_Account_State` row into memory at startup; if absent, seed DEMO/ACTIVE.
- Every transition writes the new mode/sub_state/`circuit_break_reason`/`last_updated` and updates the derived `risk_state` multipliers (drawdown, consecutive-loss, stage).
- All mutations are atomic (single-row update) and idempotent on replay.

### Interface (pseudo-code)
```
class AccountStateManager:
    def snapshot() -> AccountState            # for gate reads (in-memory, O(1))
    def apply_metrics(drawdown_pct, consecutive_losses, daily_pnl, ...)
        # evaluate auto-transitions, persist, log; returns transition or None
    def set_sub_state(target, reason, actor)   # validated; illegal -> raise
    def set_mode(target, actor)                # used by AMS-012/014
    def recovery_multipliers() -> dict          # drawdown/consec/stage factors
```
Illegal transitions (e.g. CIRCUIT_BROKEN → ACTIVE without RECOVERY) raise and are logged; the state does not change.

## Testing & Validation
- Unit: every documented transition fires on its exact trigger; every undocumented transition is rejected.
- Hysteresis: DD 11% → CAUTION; recovery to 9% stays CAUTION; 7% + a win → ACTIVE (no flap at the boundary).
- CIRCUIT_BROKEN paths: DD ≥ 20%, daily loss ≥ 3%, and 5 consecutive losses each independently force CIRCUIT_BROKEN with the right `circuit_break_reason`.
- Restart: kill mid-CAUTION; on restart the manager reloads CAUTION from the DB (no reset).
- Concurrency: a fill-driven transition and a manual override don't corrupt the single row (atomic update).

## Rollback Plan
The state machine is **passive** until other tasks call it; on its own it only persists state. Rollback = pin mode to DEMO/ACTIVE and disable auto-transitions (flag). Because state is a single persisted row, reverting is a config change, not a data migration. No existing layer depends on it yet.

## Acceptance Criteria
- [ ] In-memory manager loads from and persists to `AMS_Account_State`; survives restart with no state loss.
- [ ] All documented auto-transitions fire on their exact triggers; illegal transitions are rejected and logged.
- [ ] Hysteresis (CAUTION in at >10% DD, out at <8% DD + win) prevents flapping.
- [ ] `risk_state` multipliers (drawdown/consecutive-loss/stage) are derived and exposed to the gate.
- [ ] Reads are O(1) in-memory (no DB round-trip per gate decision).

## Notes & Risks
- The state machine is the **single source of truth** for risk posture; AMS-005/006/007/008/012/014 must mutate it only through this manager, never via direct SQL, to keep transitions valid and logged.
- Keep "mode" (capital stage) and "sub-state" (risk posture) strictly orthogonal to avoid a combinatorial mess.
- Drawdown definition must match AMS-007's calculation exactly; centralize it.
