# FND-009 — Developer Onboarding, Runbooks & Documentation Index

- **Task ID**: FND-009
- **System**: Foundational & Cross-Cutting
- **Priority**: P2-Medium
- **Estimated Effort**: 2d
- **Prerequisites**: None
- **External Dependencies**:
  - A documentation home. Recommended: keep docs in-repo as Markdown (already the project's convention under `docs/`) plus an optional static site generator (MkDocs Material) if a browsable site is wanted. *Why:* a solo operator working part-time loses context between sessions; runbooks must be findable fast during an incident.
  - No paid service required; optional static-site hosting can reuse Computer 1 or object storage.

## Objective
Produce an onboarding guide, operational runbooks, and a documentation index so the solo operator (or a future collaborator / AI agent) can recover full context and safely operate the three-system architecture.

## Current State
Documentation is substantial but sprawling and current-architecture-centric: `CLAUDE.md`, `AGENTS.md`, `README.md`, `DATABASE_MIGRATION.md`, `DESIGN_SYSTEM_SPECIFICATION.md`, `UX_ARCHITECTURE.md`, plus `docs/design/`, `docs/reference/DOCUMENTATION_INDEX_2026_04_05.md`, and per-layer READMEs. None of it yet describes the three-system topology, the queues, the Decision Gate, or operational procedures (circuit-breaker reset, stage transitions, model rollback). There is no single "what to do when X breaks" reference.

## Target State
- A concise onboarding guide that orients a reader to the three-system architecture and how to bring each system up locally and in deployment.
- A set of incident/operational runbooks for the procedures the other foundational and AMS tasks reference.
- An updated documentation index that maps old (8-layer) docs to the new (3-system) structure and points to this roadmap.

## Technical Specification

### Onboarding guide (`docs/onboarding/README.md`)
- System map: System 1 (Brain/Computer 1), System 2 (Hand/Computer 2), System 3 (Guardian/Computer 3), the queues (FND-002), object storage (FND-001), and the DB (FND-004).
- "Cold start" per system: prerequisites, secrets needed (how to decrypt via FND-003), how to run, how to verify health (FND-005 dashboards).
- Glossary tying proposed-design terms (Decision Gate, regime, Quarter-Kelly, circuit breaker, graduated deployment) to code locations.

### Runbooks (`docs/runbooks/`) — at minimum
| Runbook | Trigger | Key steps |
|---------|---------|-----------|
| Circuit-breaker reset | CIRCUIT_BROKEN state | review cause in `AMS_Circuit_Breaker_Log`, mandatory notes, manual reset → RECOVERY, 1-week demo validation (AMS-006/014) |
| Stage transition | escalate/de-escalate deployment stage | criteria check, force-stage procedure, audit entry (AMS-012/014) |
| Model rollback | bad model published | repoint `latest.json` to prior version, consumers re-verify SHA256 (FND-001, MODEL-007, EXEC-001) |
| Queue recovery | queue stalled / broker restart | inspect depth/lag, drain or replay, confirm EXEC-008 un-pauses (FND-002) |
| Secret rotation | scheduled or exposure | rotate at provider → update encrypted store → roll services → verify (FND-003) |
| DR restore | host loss / DB corruption | per-scenario restore + broker reconciliation (FND-006) |
| Emergency flat-all / pause | operator intervention | manual PAUSE, close-all, audit logging (AMS-014) |
| VPN device revoke | lost/compromised host | revoke key, confirm access lost, alert (FND-008) |

- Each runbook: symptom → diagnosis → step-by-step action → verification → who/what to notify. Linked from FND-005 alerts.

### Documentation index update
- Refresh `docs/reference/DOCUMENTATION_INDEX_*` (or a new index) to include the `docs/implementation-roadmap/` tree and a mapping table: each old layer → new system + relevant task IDs.
- Note this roadmap supersedes ad-hoc planning; keep `CLAUDE.md`'s "implementation wins" doctrine.

## Testing & Validation
- **Cold-start test:** follow the onboarding guide on a clean environment for one system and reach a healthy state with no undocumented step (gaps are bugs to fix).
- **Runbook dry-run:** execute the circuit-breaker-reset and model-rollback runbooks on demo end-to-end; each step is accurate and sufficient.
- Link check: every FND-005 alert and every cross-task reference resolves to a real runbook/section.
- Freshness: each doc carries a "last updated / applies-to" header; the index has no dangling links.

## Rollback Plan
Documentation is non-runtime; there is nothing to roll back operationally. If a new doc proves inaccurate, revert it in git. The prior docs remain until superseded, so no operational knowledge is lost during the transition.

## Acceptance Criteria
- [ ] An onboarding guide exists covering all three systems' cold-start, secrets access, and health verification.
- [ ] Runbooks exist for circuit-breaker reset, stage transition, model rollback, queue recovery, secret rotation, DR restore, emergency flat/pause, and VPN revoke.
- [ ] A cold-start of at least one system succeeds following only the guide, with any gaps fixed.
- [ ] The documentation index maps every old layer to its new system + task IDs and has no dangling links.
- [ ] FND-005 alerts link to the relevant runbooks.

## Notes & Risks
- For a part-time solo operator, runbooks are the single highest-value safety doc — months may pass between incidents and context is lost; the circuit-breaker and DR runbooks are the priority.
- Docs drift; pair each significant behavior change with a doc update (existing `CLAUDE.md` doctrine) and keep this folder under the same CI repo (FND-007) so reviews catch staleness.
- Keep it lean — a few accurate runbooks beat an exhaustive wiki that's never updated.
