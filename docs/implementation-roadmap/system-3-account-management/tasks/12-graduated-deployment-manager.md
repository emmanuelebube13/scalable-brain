# AMS-012 — Graduated Deployment Manager

- **Task ID**: AMS-012
- **System**: System 3 — Account Management
- **Priority**: P2-Medium
- **Estimated Effort**: 3d
- **Prerequisites**: AMS-009
- **External Dependencies**:
  - **DB (AMS-001)** — read `daily_summary`/`strategy_performance`/`equity_curve`; drive AMS-004 mode changes. *Why:* escalation/de-escalation criteria are evaluated from live performance.
  - **Notification (AMS-011)** — stage-change alerts. *Why:* capital-stage changes are high-significance and require operator awareness/confirmation.

## Objective
Implement the graduated deployment manager (Paper→Micro→Small→Full) with stage-transition criteria and auto escalation/de-escalation.

## Current State
**New.** There is no concept of capital stages; the system runs one (demo) mode at fixed risk. AMS-004 holds the modes; this task decides *when* to move between them.

## Target State
A periodic evaluator that reads live performance and recommends/executes stage transitions through AMS-004's `set_mode`, applying the stage's risk cap and multiplier. Escalation is **gated and conservative** (recommend → require operator confirmation via AMS-011/AMS-014 before moving to a higher-capital live stage); de-escalation (to safer/smaller) is automatic.

## Technical Specification

### Stages (proposed design §7.5)
| Stage | Account | Risk/trade | Stage multiplier | Criteria to advance |
|-------|---------|-----------|------------------|---------------------|
| Paper (DEMO) | Demo $100K | 2% | 0.5 | 2+ weeks profitable, no circuit breaks |
| Micro Live | $1K–$5K | 1% | 0.5 | profitable month, max DD < 10% |
| Small Live | $5K–$10K | 1.5% | 0.75 | 2 consecutive profitable months |
| Full Live | $10K+ | 2% | 1.0 | 3 consecutive profitable months, max DD < 15% |

### Escalation (gated, conservative)
- Evaluate on a periodic cadence (e.g. weekly) from `daily_summary`/`equity_curve`.
- All advance criteria for the next stage met → emit a **recommendation** + notify; require explicit operator confirmation (AMS-014 `force_stage_change` or a confirm command) before `set_mode` to a higher live stage. Never auto-escalate into more real capital.
- Within-stage size ramp (proposed design §7.5): after N profitable days, allow +25% size up to the stage cap (a `risk_state` ramp factor), bounded by the mode cap.

### De-escalation (automatic)
- After M consecutive losses → −50% size (already via Gate Layer E; the manager may also drop a stage if sustained).
- Max DD breaching the lower stage's threshold, a circuit break, or a losing month → automatically **de-escalate** to the next safer stage (and into RECOVERY/DEMO if a circuit broke), via AMS-004; notify.
- A circuit-breaker RECOVERY exit returns to the *previous* stage only after the AMS-004 1-week demo validation passes.

### Interface (pseudo-code)
```
evaluate_stage():
    perf = read_rolling_performance()
    if meets_advance(current_stage, perf):
        recommend_escalation(next_stage); notify(HIGH)   # await confirm
    if meets_deescalate(current_stage, perf) or circuit_broke():
        AMS004.set_mode(safer_stage); notify(HIGH)         # automatic
    update ramp_factor in risk_state
```

### Persistence
- Current stage = `AMS_Account_State.mode`. Stage-change events recorded (audit) with the criteria snapshot that justified them; escalations record the confirming actor.

## Testing & Validation
- Unit: each advance criterion gates correctly (e.g. 1 profitable month + DD 9% advances Micro→Small only with 2 consecutive months met for the right step; boundary at DD=10%/15%).
- Escalation requires confirmation: criteria met → recommendation only; mode does not change until confirmed.
- De-escalation is automatic: a losing month / DD breach / circuit break drops the stage and applies the safer cap without confirmation.
- Ramp factor: N profitable days raises size 25% but never above the stage cap.
- RECOVERY interplay: post-circuit, mode goes to RECOVERY/DEMO and only returns to the prior stage after the 1-week demo validation.

## Rollback Plan
Flag-gated; off, the system stays pinned to DEMO (AMS-004 default) and the manager only logs recommendations. Because escalation already requires manual confirmation, the dangerous direction (more capital) is never automatic. Rollback = disable auto de-escalation too (not recommended) or pin the mode; no data migration.

## Acceptance Criteria
- [ ] Evaluates Paper→Micro→Small→Full criteria from live performance on a periodic cadence.
- [ ] Escalation to a higher-capital stage is recommend-only and requires operator confirmation; de-escalation is automatic.
- [ ] Within-stage ramp respects the stage cap; stage maps to `AMS_Account_State.mode` with the correct risk cap/multiplier.
- [ ] Circuit-break/RECOVERY interplay returns to a prior stage only after AMS-004's 1-week demo validation.
- [ ] Every stage change is audited with the justifying criteria snapshot; changes are notified.

## Notes & Risks
- The asymmetry (auto down, manual up) is the whole point: easy to get safer, deliberate to risk more capital. Do not "simplify" it to symmetric auto-transitions.
- "Profitable month" definitions (calendar vs rolling) must be explicit and config-driven, matched to AMS-009's metrics.
- Solo operator may be slow to confirm escalations — that is acceptable; capital growth target ($70k by Dec 2027) must not pressure auto-escalation into real money.
