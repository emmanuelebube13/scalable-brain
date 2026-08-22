# ADR-001 / SYSTEM 1 — state

Resume file for `PROMPT-SYSTEM1.md` in this folder. Read that first.
Tick a box only after the step is verified AND committed.

## Blocking precondition

- [x] ADR-001 approved in writing by **System 2** — conditional APPROVE, 2026-08-22.
      Three pre-existing blockers must be fixed on their side first (Windows queue path,
      EXEC_SHADOW, stale SIGNAL_* config). Reply: `docs/comms/TO-SYSTEM2-2026-08-23-ADR001-reply.md`
- [x] ADR-001 approved in writing by **System 3** — APPROVE, 2026-08-22, conditional on
      schema v2 landing first and Layer K + heartbeat being built on their side.
      Reply: `docs/comms/TO-SYSTEM3-2026-08-23-ADR001-reply.md`

**Both approvals are in.** The gate is now schema v2 (S3), not the reviews.

Read ADR-001 §3a/§3b/§3c and both reply documents before starting. The reviews changed the work.

## Checklist

- [ ] S0 — **ROTATE `system1-rw`**; System 2 gets a read-only identity *(URGENT, ungated)*
- [ ] S1 — Scope the inference surface → `INFERENCE-SURFACE.md` *(no delegation)*
- [ ] S2 — Close the test-fixture leak into the production queue *(ungated)*
- [ ] S3 — **Schema v2 reconciliation, signed off by both systems** *(BLOCKS EVERYTHING BELOW)*
- [ ] S3b — HMM is authoritative; CSRM stops routing; ADX/ATR reconciled to System 2; drop `ta`
- [ ] S4 — Strategy code + hash-locked deps become a checksummed bundle artifact
- [ ] S4b — `publish_model_set` verifies it, fail-closed
- [ ] S5 — Reference vector + `DETERMINISM.md` *(delegable; needs S3b)*
- [ ] S5b — Candle fingerprint + bid-as-mid repaired-range list *(delegable)*
- [ ] S6 — Manifest signing, then publish bundle v2 + note to System 2
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

Owned by other systems; do not build past them (see PROMPT §7a):

- System 2: `QUEUE_LOCAL_PATH` is a Windows path on a Linux host — link 3 severed since
  2026-07-27. Also `EXEC_SHADOW=true`, stale `SIGNAL_*` config, and a regime detector that
  caches its bundle in memory forever.
- System 3: Layer K (entry vs live market price) and the heartbeat topic contract.
- Both: schema v2 sign-off.
- 2026-08-22 — System 3 returned APPROVE. Its §4.4 regime note prompted a contract diff that
  found the headline blocker: `contracts/signal-message-contract.json` and System 3's
  `ScoredSignal.schema.json` are BOTH `additionalProperties: false` and disagree on nearly
  every field name (`instrument`/`pair`, `entry`/`proposed_entry`, `stop`/`proposed_sl`,
  `target`/`proposed_tp`, `atr` required and never sent, `regime_probs` unknown to them).
  **Every signal System 1 emits would be rejected.** The severed queue hid it. Schema v2 is
  a reconciliation, not an addition, and it now gates all downstream work.
- 2026-08-22 — §3b RESOLVED: HMM is authoritative. CSRM was only adopted because
  `regime_causal` is empty for the latest bar; System 2's live detector produces a real HMM
  posterior, so ADR-001 removes the reason CSRM existed. It becomes a diagnostic.
