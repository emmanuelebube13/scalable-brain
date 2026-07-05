# AMS-013 — Weekend/Holiday Manager

- **Task ID**: AMS-013
- **System**: System 3 — Account Management
- **Priority**: P2-Medium
- **Estimated Effort**: 2d
- **Prerequisites**: AMS-008
- **External Dependencies**:
  - **Holiday calendar** — a curated list of major market holidays (Christmas, New Year, Good Friday, July 4, etc.). *Why:* thin-liquidity sessions must be blocked or reduced.
  - **`Fact_Macro_Events` (read by Gate Layer I)** — complements the static calendar for scheduled high-impact events. *Why:* event-window avoidance.
  - **Flat-all/close channel (EXEC-004 / Layer 4)** — to enforce the Friday close protocol. *Why:* System 3 decides the close window; Layer 4 executes.

## Objective
Implement the weekend/holiday manager (Friday close protocol, Sunday open gap-assessment window, holiday calendar) feeding Gate Layer I.

## Current State
**New.** No weekend/holiday handling exists; AMS-008's Layer I currently carries built-in Friday/Sunday defaults. This task provides the authoritative calendar + protocols those rules consult.

## Target State
A small, low-footprint module that exposes, for any UTC timestamp, whether trading is **blocked**, **reduced**, or **allowed** due to weekend/holiday/session windows, and runs the Friday close protocol. Gate Layer I (AMS-008) calls it instead of using hardcoded times; values come from `risk_config.json.trade_parameters` (`friday_close_hour_utc=18`, `sunday_open_hour_utc=22`) plus the holiday calendar.

## Technical Specification

### Windows (all UTC)
- **Friday close protocol**: no new entries after **18:00 UTC** Friday (`FRIDAY_CLOSE`). Optionally close all open positions by a configurable hour (proposed design notes Friday 20:00 UTC) if `allow_over_weekend=false` — request flat-all via Layer 4.
- **Sunday open gap-assessment**: first **4 hours after the 22:00 UTC Sunday open** → block new entries (`SUNDAY_GAP_WINDOW`); the proposed design also allows a reduced-size (50%) variant for the window — expose both block/reduce per config.
- **Holiday calendar**: a static, versioned list (with per-holiday block/reduce flag); on a listed date → block (or reduce) new entries.
- **Macro-event proximity**: defer to Gate Layer I's ±2h `Fact_Macro_Events` rule (this module surfaces the calendar; Layer I owns the event-window decision).

### Interface (pseudo-code)
```
class CalendarManager:
    def session_state(ts_utc) -> {ALLOWED | REDUCED | BLOCKED, reason}
    def is_friday_close(ts_utc) -> bool
    def sunday_gap_window(ts_utc) -> {block|reduce|none}
    def is_holiday(date_utc) -> {block|reduce|none}
    def friday_close_protocol() -> close_all_request?   # scheduled task
```
Gate Layer I calls `session_state(now)`; BLOCKED → REJECT, REDUCED → reduce-size flag, ALLOWED → pass.

### Friday close protocol (scheduled)
- At `friday_close_hour_utc`, stop approving new entries. If `allow_over_weekend=false`, at the configured close hour request a flat-all of open positions via the Layer 4 close channel (same contract as AMS-006); log + notify (AMS-011).

### Footprint
- Pure date/time logic + a small in-memory calendar; no heavy dependency. Calendar is data, loaded from config/object storage and refreshable without a redeploy.

## Testing & Validation
- Unit: Friday 17:59 allowed, 18:00 blocked; Sunday 22:00–01:59 blocked/reduced per config, 02:00 allowed.
- Holiday: a listed date blocks (or reduces); a normal date allows.
- Friday close protocol: at the close hour, new entries stop and (when `allow_over_weekend=false`) a flat-all request is issued and acked by Layer 4.
- DST/UTC: all logic is UTC — no DST drift; boundary times exact.
- Integration: Gate Layer I uses this module's verdicts (replacing hardcoded defaults) with identical results for the default times.

## Rollback Plan
Additive and self-contained. Rollback = Gate Layer I falls back to its built-in Friday/Sunday defaults (from AMS-008) and the Friday flat-all is disabled via flag; weekday gating is unaffected. No state is mutated except the audit log of any flat-all.

## Acceptance Criteria
- [ ] Returns ALLOWED/REDUCED/BLOCKED with reasons for any UTC timestamp, driven by `risk_config.json` + the holiday calendar.
- [ ] Friday-close (18:00) and Sunday-open (22:00 + 4h) windows are enforced and consumed by Gate Layer I.
- [ ] The Friday close protocol issues a flat-all (when `allow_over_weekend=false`) that Layer 4 acks; logged + notified.
- [ ] All time logic is UTC with exact boundaries; the calendar is refreshable without redeploy.
- [ ] Footprint stays tiny on Computer 3.

## Notes & Risks
- Weekend gap risk is the rationale; if the Friday flat-all fails to execute, positions ride the gap — verify the close ack and alert loudly on failure (CRITICAL).
- The holiday calendar must be maintained yearly; a stale calendar silently allows trading on a thin holiday — surface its `last_updated`/coverage in health.
- Keep the reduce-vs-block choice per window configurable; over-blocking starves an already part-time strategy of opportunities.
