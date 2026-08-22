# ADR-001 / SYSTEM 1 — state

Resume file for `PROMPT-SYSTEM1.md` in this folder. Read that first.
Tick a box only after the step is verified AND committed.

## Blocking precondition

- [x] ADR-001 approved in writing by **System 2** — conditional APPROVE, 2026-08-22.
      Three pre-existing blockers must be fixed on their side first (Windows queue path,
      EXEC_SHADOW, stale SIGNAL_* config). Reply: `docs/comms/TO-SYSTEM2-2026-08-23-ADR001-reply.md`
- [ ] ADR-001 approved in writing by **System 3** (reply filed in `docs/comms/`)

Until both are ticked, only S2 (the queue fixture leak) may be worked.

## Checklist

- [ ] S1 — Scope the inference surface → `INFERENCE-SURFACE.md` *(no delegation)*
- [ ] S2 — Close the test-fixture leak into the production queue *(ungated)*
- [ ] S3 — Strategy code + pinned deps become a checksummed bundle artifact
- [ ] S4 — `publish_model_set` verifies it, fail-closed
- [ ] S0 — **ROTATE `system1-rw`** and issue System 2 a read-only identity *(urgent, ungated)*
- [ ] S4b — Resolve ADR-001 §3b: which regime model routes *(blocks S5 and System 2's scoring work)*
- [ ] S4c — Reconcile ADX/ATR to System 2's hand-rolled impl; drop `ta` from `regime/structural.py`
- [ ] S5 — Reference vector + `DETERMINISM.md` *(delegable; BLOCKED by S4b)*
- [ ] S6 — Publish bundle v2 + note to System 2
- [ ] S7 — `CUTOVER.md`, double-publishing structurally impossible *(no delegation)*
- [ ] S8 — Tidy: registry `regime_aware` imports, test counts, black/mypy
- [ ] S9 — `DELIVERABLE.md`

## Log

- 2026-08-22 — brief written (Claude). No code changed. ADR-001 is PROPOSED and unapproved;
  the precondition above is real, not ceremonial.
- 2026-08-22 — System 2 returned a verified Phase 1 review: conditional APPROVE. It caught
  a prohibition System 1 could not see (S1-NOTICE-2026-08-15 §4.3) — ADR amended with §3a
  to supersede it by name and scope. It also reported our `system1-rw` key world-readable
  (mode 0666) on their VM.
- 2026-08-22 — **NEW BLOCKER, found answering their check 05.** The map and gatekeeper were
  built on HMM causal labels; live routing uses CSRM structural labels. Different models.
  The gatekeeper needs 4 HMM posterior features the live path cannot produce, which is why
  `regime_probs` ships as uniform 0.25. Recorded as ADR-001 §3b. **S5 (reference vector) is
  blocked on this** — a vector pinning CSRM pins the wrong thing if routing moves to HMM.

## Blockers

_(none yet)_
