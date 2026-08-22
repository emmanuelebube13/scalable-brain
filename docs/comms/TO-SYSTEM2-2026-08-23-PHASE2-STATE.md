# SYSTEM 2 — ADR-001 Phase 2 state

Resume file for `TO-SYSTEM2-2026-08-23-PHASE2-BUILD.md`. Read that first.
Tick a box only after the step is verified AND committed.

## Checklist

- [ ] P0 — Your own blockers: queue path, startup assertion, `SIGNAL_*` purge *(no delegation)*
- [ ] P1 — Sync + verify signature, checksums, status; `last_good` fallback
- [ ] P2 — Force detector reload on bundle swap *(invalidates P4 if skipped)*
- [ ] P3 — Install code bundle in a separate venv; add D1; lookback past 252 bars
- [ ] P4 — Determinism gate: replay in-memory, real `reference_vector_ok`, fingerprint
- [ ] P5 — HMM routing, gatekeeper scoring on the 12-feature contract, emit schema v2
- [ ] P6 — Cutover: observability first, drill, single coordinated change *(no delegation)*

## Log

- 2026-08-23 — brief written by System 1. Nothing started. Both approvals are in; the gate
  is now P0, which is entirely on System 2's side.

## Blockers

Owned by System 1 — tell us if any of these is wrong or missing:

- Hash-locked dependencies: the bundle ships `==` pins, not `--hash=sha256:` locks. Known
  gap, not yet done.
- `reference_vector_ok` is `false` on every System 1 signal today because no replay exists
  on our side. If System 3 rejects on it before you take over, signals die there — agree
  with System 3 whether it enforces that field during the bridge period.

## Open question for System 3

Does System 3 reject on `reference_vector_ok == false`? If yes, nothing flows until P4 is
done. If it only logs for now, the bridge can keep running while Phase 2 is built.
