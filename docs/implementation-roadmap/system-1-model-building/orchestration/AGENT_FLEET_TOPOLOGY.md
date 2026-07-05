# AGENT FLEET TOPOLOGY — System 1

Organizational model for implementing System 1. Mirrors real team structure: a program manager,
domain managers, ephemeral specialists, plus governance (structure), bookkeeping (ledger), and an
independent QA/audit function. **No agent calls another directly — they hand off through immutable
artifacts at contracted paths** (see `tasks/agents/README.md`).

---

## Org chart

```
                          ┌──────────────────────────────────────────┐
                          │ TIER 0 — Orchestrator / Program Manager   │
                          │ sequences DAG, deploys managers, owns gate │
                          │ enforcement + the living ledger            │
                          └───────────────┬───────────────────────────┘
            ┌─────────────────────────────┼───────────────────────────────────┐
            ▼                             ▼                                     ▼
  ┌───────────────────┐        ┌────────────────────────┐          ┌────────────────────────┐
  │ GOVERNANCE         │        │ TIER 1 — Domain managers│          │ CROSS-CUTTING QA        │
  │ structure-coherency│        │ (one per agent file)    │          │ auditor-traceback-agent │
  │ ledger-keeper      │        │                         │          │ (rework + block author) │
  └───────────────────┘        └───────────┬────────────┘          └────────────────────────┘
                                            │ each manager spawns short-lived
                                            ▼
                                 ┌────────────────────────────┐
                                 │ TIER 2 — ephemeral sub-agents│
                                 │ implementer + test-author    │
                                 │ (one per file/module, dispose)│
                                 └────────────────────────────┘
```

---

## Roles & ownership

| Role | Agent (file) | Owns | Notes |
|------|--------------|------|-------|
| Program Manager | _Tier-0 (this orchestration prompt)_ | DAG sequencing, gate enforcement, ledger | Deploys all others |
| Data pipeline | `tasks/agents/data-pipeline-agent.md` | MODEL-001, MODEL-002 | Extends `ingest_oanda_prices.py`; builds feature store |
| ML & regime | `tasks/agents/ml-regime-agent.md` | MODEL-003, MODEL-006 | HMM + gatekeeper; K-Means fallback retained |
| Attribution & vetting | `tasks/agents/attribution-vetting-agent.md` | MODEL-004, MODEL-005 | Per-regime metrics + maps; log-only first |
| Serializer & infra | `tasks/agents/serializer-infra-agent.md` | MODEL-007, MODEL-009 | Bundle/registry via `StorageBackend`; retrain |
| Queue & NLP | `tasks/agents/queue-nlp-agent.md` | MODEL-008, MODEL-010 | Queue producer via `QueueBackend`; FinBERT |
| Auditor / traceback | `tasks/agents/auditor-traceback-agent.md` | AG-001…AG-010, AG-CROSS | Only role with rework + blocking authority |
| **Structure-coherency** | _new governance role_ | `FOLDER_STRUCTURE.md`, naming, granularity contract | Approves every new path; prevents drift/dupes |
| **Ledger-keeper** | _new bookkeeping role_ | `progress_ledger.json`, `PROGRESS_LEDGER.md`, `.docx` | Updates living docs after every state change |

> The two governance roles can be run as dedicated sub-agents, or — in a no-sub-agent runtime —
> performed by the single executing LLM as explicit steps. Either way their **outputs are files**
> (the structure doc and the ledger), so the work is always auditable.

---

## Handoff artifacts (who produces what for whom)

| Producer | Artifact (path) | Consumer(s) |
|----------|-----------------|-------------|
| data-pipeline | `Fact_Market_Prices` (+W1/lineage), `results/state/ingest_progress.json`, `feature-store/{version}/` | ml-regime, attribution-vetting |
| ml-regime | `Fact_Market_Regime_V2` (+probs), `models/hmm_model.joblib`, `models/champion_manifest.json` | attribution-vetting, queue-nlp, serializer-infra |
| attribution-vetting | `results/state/regime_strategy_map.json`, `results/state/strategy_weights.json` | serializer-infra |
| serializer-infra | `model-artifacts/{version}/` bundle + `latest.json` (via `StorageBackend`) | System 2 / Computer 2 |
| queue-nlp | `Scored_Signal_Queue` messages (via `QueueBackend`), `results/state/macro_veto.json` | System 3 |
| auditor | `results/state/audit_log.{json,md}`, `rework/*.md`, `blocked/*.md` | all + human |
| ledger-keeper | `orchestration/progress_ledger.json` + `.md` + `STAKEHOLDER_UPDATE.docx` | humans + any resuming LLM |

---

## Control rules (from `tasks/agents/README.md`, enforced here)

1. **Startup checklist** — every manager: read fleet README → read own agent file → load skills →
   check `results/state/rework/{agent}_*.md` and `results/state/blocked/{agent}.md` → read upstream
   manifests → verify upstream checksums/schema → execute → self-verify → write
   `DONE_{agent}_{ts}.md` → wait for auditor.
2. **Rework loop** — auditor issues `rework/{agent}_{ts}.md`; manager fixes, re-runs, deletes the
   file to request re-validation. **Max 3 iterations**, then `blocked/BLOCKED_{agent}_{ts}.md` +
   human escalation.
3. **Blocking chain** — a consumer must not start while its upstream has an open rework/blocked file.
4. **Provenance (AG-CROSS)** — every output must trace back to the OANDA call through the artifact
   chain; version fields (`feature_set_version`, `regime_model_version`, `bundle_version`) must align.

---

## Pluggable infrastructure (storage & queue)

Managers code against interfaces, **not** vendors (full spec: `STORAGE_AND_QUEUE_ABSTRACTION.md`):

- **`StorageBackend`** — `LocalFSBackend` (default) reproduces immutable versions + `latest.json` +
  SHA256 + encryption-flag semantics on disk under `model-artifacts/`. `GCSBackend` attaches later
  via `STORAGE_PROVIDER=gcs` with no code change (serializer-infra-agent / MODEL-007/009).
- **`QueueBackend`** — `LocalDurableBackend` (default) provides bounded depth + ack + DLQ under
  `results/state/queue/`. A real broker attaches later via `QUEUE_PROVIDER=...` (queue-nlp-agent /
  MODEL-008).

This is what lets FND-001 and FND-002 be "satisfied" today so MODEL-007/008 are fully buildable and
testable before any cloud infrastructure exists.
