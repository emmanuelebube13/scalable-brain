# ADR-001 / SYSTEM 1 — state

Resume file for `PROMPT-SYSTEM1.md` in this folder. Read that first.
Tick a box only after the step is verified AND committed.

## Blocking precondition

- [ ] ADR-001 approved in writing by **System 2** (reply filed in `docs/comms/`)
- [ ] ADR-001 approved in writing by **System 3** (reply filed in `docs/comms/`)

Until both are ticked, only S2 (the queue fixture leak) may be worked.

## Checklist

- [ ] S1 — Scope the inference surface → `INFERENCE-SURFACE.md` *(no delegation)*
- [ ] S2 — Close the test-fixture leak into the production queue *(ungated)*
- [ ] S3 — Strategy code + pinned deps become a checksummed bundle artifact
- [ ] S4 — `publish_model_set` verifies it, fail-closed
- [ ] S5 — Reference vector + `DETERMINISM.md` *(delegable)*
- [ ] S6 — Publish bundle v2 + note to System 2
- [ ] S7 — `CUTOVER.md`, double-publishing structurally impossible *(no delegation)*
- [ ] S8 — Tidy: registry `regime_aware` imports, test counts, black/mypy
- [ ] S9 — `DELIVERABLE.md`

## Log

- 2026-08-22 — brief written (Claude). No code changed. ADR-001 is PROPOSED and unapproved;
  the precondition above is real, not ceremonial.

## Blockers

_(none yet)_
