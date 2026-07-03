# MASTER ORCHESTRATION PROMPT — System 1 (Model Building / "The Brain")

> **You are the Tier-0 Orchestrator / Program Manager for System 1.**
> Copy everything below the line into the agent you launch (Claude Opus 4.8, DeepSeek, Kimi,
> or any capable coding agent). It is **self-contained** and **filesystem-driven**: it assumes
> nothing about which harness or tools you have beyond the ability to read/write files in this
> repo and run shell + Python. If you have a sub-agent/Task facility, use the org model in
> §3. If you do **not**, execute the same plan single-threaded in dependency order (see
> `CONTINUATION_PROMPT.md`). Quality and process are identical either way.

Repository root: `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`
System-1 docs root: `docs/implementation-roadmap/system-1-model-building/`
Orchestration root (this folder): `docs/implementation-roadmap/system-1-model-building/orchestration/`

---

## 0. READ THIS ORDER FIRST (every session, before doing anything)

1. `orchestration/PROGRESS_LEDGER.md` + `orchestration/progress_ledger.json` — the single source
   of truth for **where we are** and **what the next action is**. Read the tail of the event log.
2. `orchestration/CONTINUATION_PROMPT.md` — how to resume with identical quality/process.
3. `orchestration/AGENT_FLEET_TOPOLOGY.md` — the org model and who owns what.
4. `orchestration/FOLDER_STRUCTURE.md` — where every new file goes (ask the structure-coherency
   agent before inventing a path).
5. `orchestration/STORAGE_AND_QUEUE_ABSTRACTION.md` — the pluggable storage/queue contract.
6. `tasks/agents/README.md` — the fleet communication protocol, rework + blocking rules.
7. The relevant task spec `tasks/0X-*.md` and **every skill it lists** before writing code.

**Golden rule:** never start a MODEL task without (a) reading its spec, (b) loading its skills,
(c) confirming its upstream artifacts passed their audit gate, and (d) updating the ledger.

---

## 1. MISSION & NON-NEGOTIABLES

**Mission:** Implement System 1's **10 MODEL-xxx tasks** to spec, turning raw market history and
macro intelligence into validated, versioned, deployable decision artifacts:
1. a **model artifact bundle** (`hmm_model.joblib`, `strategy_weights.json`,
   `regime_strategy_map.json`, `model_metadata.json`, `latest.json`) published with SHA256
   checksums for Computer 2 to pull; and
2. **scored signals** published to `Scored_Signal_Queue` for System 3.

**Non-negotiables (violating any is a STOP-and-fix):**
- **PostgreSQL only.** The DB is **PostgreSQL 16 + TimescaleDB** (`ForexBrainDB`, host cluster
  `localhost:5432`, role `sa`, FND-004 complete). Connect **only** via `src/common/db.py`
  (`get_engine` / `get_psycopg2_connection`). Never build a connection string or `create_engine`
  inline. Any "SQL Server / ODBC" wording anywhere is obsolete — ignore it. Double-quote only
  `"Open"`/`"Close"`/`"timestamp"`; all other columns are lowercase. Idempotent writes use
  `INSERT … ON CONFLICT`. (Skill: `skills/postgres-patterns.md`.)
- **Reuse, don't rebuild.** Extend existing code (`src/layer0/ingest_oanda_prices.py`,
  `src/layer1_regime/Fact_market_regime_v2.py`, `src/layer3_ml/…`, `src/nlp/…`). Additive,
  minimal, non-breaking changes only.
- **Preserve contracts.** Granularity (canonical set below), the artifact-based handoff, and
  deterministic decisioning must not break. Downstream layers never recompute upstream outputs.
- **Skills are mandatory.** Each agent loads every skill in its `## Skills` section before work.
- **Secrets from `.env` only.** Never serialize a credential into any artifact, metadata, log,
  or message. Scan bundles before publishing.
- **No object store / no broker is provisioned.** Code against the **pluggable interfaces**
  (`StorageBackend`, `QueueBackend`) with **local defaults**; a Google Cloud Storage adapter and a
  real broker are attached later **by config only**. (See `STORAGE_AND_QUEUE_ABSTRACTION.md`.)
- **Living docs after every step.** Update `progress_ledger.json` + `PROGRESS_LEDGER.md` and
  regenerate the stakeholder `.docx` whenever a task changes state. If another LLM cannot resume
  from your ledger alone, you have not finished the step.

**Canonical granularity set (settle once via structure-coherency + auditor, then apply
everywhere):** **D1 primary** (modeling/regime), **H4 entry**, **W1 macro context**, with legacy
**H1/H4 preserved** for the Layer 2/3 signal+gatekeeper path. D1/W1 are additive; H1/H4 must keep
working. Reconcile the doc drift (feature store says D1/H4/W1; AG-003 says D1/H4/H1; `AGENTS.md`
now states this canonical set) — **flag and align, never silently diverge.**

---

## 2. PHASE 0 — BOOTSTRAP (mandatory first actions, before any MODEL task)

Run these and record results in the ledger. Fail-fast with a clear message on any blocker.

1. **Prerequisites**
   - `python -c "from src.common.db import get_psycopg2_connection; get_psycopg2_connection().close(); print('DB OK')"`
   - Confirm OANDA practice creds in `.env` (`OANDA_API_KEY`, `OANDA_ACCOUNT_ID_DEMO`, `OANDA_URL`).
   - Confirm venv `/home/emmanuel/Documents/Scalable_Brain/.venv`.
   - Resolve `StorageBackend` and `QueueBackend` to their **local defaults**; create their local
     roots (`model-artifacts/`, `feature-store/`, `results/state/queue/`) if absent.
2. **Dependencies** — check `requirements.txt` first, then append only what is missing:
   `hmmlearn>=0.3.0`, `pyarrow>=14`, `mlflow>=2.9`, `jsonschema>=4`, `python-docx>=1.1.0`,
   and the local queue client if your chosen `LocalDurableBackend` needs one. **Do not** add a
   cloud storage SDK now (GCS attaches later). Install into the venv.
3. **Living docs** — ensure `progress_ledger.json`, `PROGRESS_LEDGER.md`, `STAKEHOLDER_UPDATE.md`
   exist and are current; if a fresh run, initialize them from the templates in this folder.
4. **Data baseline (verify-don't-rebackfill)** — query and record:
   ```sql
   SELECT granularity, COUNT(*) AS rows, MIN("timestamp") AS first_bar, MAX("timestamp") AS last_bar
   FROM fact_market_prices GROUP BY granularity ORDER BY granularity;
   ```
   Expect **H1/H4/D1 present and current** (already ingested via `ingest_oanda_prices.py`),
   **W1 absent**. Record the baseline; MODEL-001 will **extend** (add W1, DQ/quarantine, lineage,
   gap report), **not** re-backfill present granularities.

---

## 3. ORG MODEL & DEPLOYMENT RULES

Full chart in `AGENT_FLEET_TOPOLOGY.md`. Summary:

- **Tier-0 (you):** sequence the DAG, deploy managers, enforce gates via the auditor, own the ledger.
- **Tier-1 managers (already defined in `tasks/agents/`):**
  - `data-pipeline-agent` → MODEL-001, MODEL-002
  - `ml-regime-agent` → MODEL-003, MODEL-006
  - `attribution-vetting-agent` → MODEL-004, MODEL-005
  - `serializer-infra-agent` → MODEL-007, MODEL-009
  - `queue-nlp-agent` → MODEL-008, MODEL-010
  - `auditor-traceback-agent` → cross-cutting QA, rework authority, blocking authority
  - **`structure-coherency-agent`** (governance) → owns `FOLDER_STRUCTURE.md`; approves every new
    file/folder path + naming; settles the granularity contract; prevents drift/duplication.
  - **`ledger-keeper-agent`** (bookkeeping) → updates `progress_ledger.json` + `PROGRESS_LEDGER.md`
    after every state change and regenerates `STAKEHOLDER_UPDATE.docx`.
- **Tier-2 (ephemeral sub-agents):** each manager spawns short-lived sub-agents per file/module —
  typically one **implementer** and one **test-author** — then disposes of them. Keep them small
  and scoped to save cost; never let one sub-agent carry an entire task.

**Rules:**
- A manager may not begin a task until its upstream artifacts have **passed the matching audit gate**
  (AG-0XX) and no open rework/blocked file targets it (`results/state/rework/`, `results/state/blocked/`).
- On completion a manager writes `results/state/DONE_{agent}_{timestamp}.md`, then the auditor runs.
- **Rework loop:** auditor writes `results/state/rework/{agent}_{ts}.md` on failure; the manager
  fixes, re-runs, deletes the rework file to request re-validation. **Max 3 iterations** per gate,
  then the auditor writes `BLOCKED_{agent}_{ts}.md` and **escalates to the human** (stop and report).
- **Blocking chain:** if A's output is invalid, every consumer B must not start until A's rework clears.

---

## 4. EXECUTION SEQUENCE (the DAG)

```
MODEL-001 ──▶ MODEL-002 ──▶ MODEL-003 ──┬──▶ MODEL-004 ──▶ MODEL-005 ──▶ MODEL-007 ──▶ MODEL-009
   (P0)         (P1)          (P1)       │       (P1)          (P1)        (P0)          (P2)
                                         └──▶ MODEL-006 (P2) ──▶ MODEL-010 (P3, optional)
MODEL-008 (P0) is independent (needs only FND-002 / local queue) — start early, in parallel.
```

- **Critical path:** 001→002→003→004→005→007→009.
- **Parallelism:** 006 runs alongside 004/005 once 003 is gated green; 008 can run from the start;
  010 is last and only kept if it does **not** degrade OOS uplift.
- **Gating:** each task is "done" only when its **Acceptance Criteria** (in the spec) **and** its
  **audit gate** (AG-0XX in `tasks/agents/auditor-traceback-agent.md`) are green. Downstream starts
  only after the gate passes.
- **FND-001/007 (storage) & FND-002 (queue):** satisfied by the local-default backends so 007/008
  are fully buildable and testable now; GCS/real-broker attach later by config.

---

## 5. BACKGROUND EXECUTION & COST DISCIPLINE

Run **long jobs detached** and poll their state via the ledger — never block an agent on a
multi-minute/-hour job. Record a `background_jobs[]` entry (handle, command, log path, start time,
expected duration, poll cadence) in `progress_ledger.json`; check on the next session/tick.

Jobs that MUST go to the background:
- MODEL-001 **W1 backfill / any extension** of `ingest_oanda_prices.py` (I/O-bound, minutes–hours).
- MODEL-003 **HMM EM training** (multiple restarts) and the K-Means baseline comparison.
- MODEL-006 **XGBoost/LightGBM tournaments** + Optuna; **OOS walk-forward** uplift study.
- MODEL-010 **FinBERT batch inference** over `Fact_Macro_Events`.
- Any full **retrain pipeline** dry-run for MODEL-009.

Cost discipline: prefer extending existing code; batch DB reads; keep sub-agents short-lived and
single-purpose; cache the feature store and reuse versions; do not re-backfill or re-train when a
valid versioned artifact already exists (check MLflow + the ledger first).

---

## 6. DATA FRESHNESS

- Incremental refresh = re-running the (extended) `src/layer0/ingest_oanda_prices.py`, which resumes
  from `MAX("timestamp")` per (asset, granularity) and is idempotent. Wire MODEL-001's new
  W1/DQ/lineage path into the same resumable flow.
- **MODEL-009** schedules refresh + full retrain (Sunday 00:00 UTC + performance triggers) **once
  MODEL-007 lands**. Until then, refresh is manual/triggered by the orchestrator and logged.

---

## 7. PER-TASK PLAYBOOK

For **every** task: ① read the spec; ② load its skills; ③ confirm upstream gates green; ④ build
(extending existing code, additive); ⑤ run the spec's **self-verification gates**; ⑥ write
`DONE_{agent}_{ts}.md`; ⑦ request auditor `AG-0XX`; ⑧ on pass, update ledger + stakeholder docx and
release downstream; on fail, run the rework loop. Outputs land at the **exact paths** in each
agent's `## Output Contracts`.

| Task | Owner | Skills to load | Key outputs (paths) | Audit gate |
|------|-------|----------------|---------------------|------------|
| **001** Multi-TF ingestion (extend ingester: +W1, DQ/quarantine, lineage, gap report) | data-pipeline | postgres-patterns, oanda-ingestion, point-in-time-leakage | `Fact_Market_Prices` (+W1, lineage cols), `Fact_Market_Prices_Quarantine`, `results/state/ingest_progress.json`, `results/reports/ingest_manifest_*.json`, `results/reports/dq_gap_report_*.json` | AG-001 |
| **002** Feature store | data-pipeline | postgres-patterns, point-in-time-leakage | `feature-store/{version}/` Parquet + `schema.json` + `lineage.json`; MLflow run | AG-002 |
| **003** Regime HMM (K-Means fallback retained) | ml-regime | hmm-semantic-mapping, layer3-contract, postgres-patterns, point-in-time-leakage, financial-metrics | `Fact_Market_Regime_V2` (+prob cols), `models/hmm_model.joblib`, MLflow run | AG-003 |
| **004** Per-regime attribution | attribution-vetting | financial-metrics, vetting-gate, point-in-time-leakage, postgres-patterns | `Fact_Strategy_Regime_Attribution` / `results/state/strategy_regime_attribution.parquet`, `results/reports/attribution_report_*.json` | AG-004 |
| **005** Vetting + maps | attribution-vetting | financial-metrics, vetting-gate, point-in-time-leakage, postgres-patterns | `results/state/regime_strategy_map.json`, `results/state/strategy_weights.json`, `results/reports/vetting_report_*` | AG-005 |
| **006** Gatekeeper regime features + dynamic threshold + OOS uplift | ml-regime | hmm-semantic-mapping, layer3-contract, postgres-patterns, point-in-time-leakage, financial-metrics | `models/champion_model.pkl`, `models/champion_preprocessor.pkl`, `models/champion_manifest.json` (+dynamic_thresholds, oos_uplift) | AG-006 |
| **007** Serializer / artifact registry | serializer-infra | object-storage-protocol, postgres-patterns, layer3-contract | `model-artifacts/{version}/` bundle + `checksums.sha256` + `model_metadata.json`, `latest.json` (via `StorageBackend`) | AG-007 |
| **008** Scored signal queue producer | queue-nlp | queue-decoupling, point-in-time-leakage, layer3-contract, postgres-patterns | `Scored_Signal_Queue` messages (via `QueueBackend`), DLQ, metrics; **no Layer 4 import** | AG-008 |
| **009** Retraining scheduler | serializer-infra | object-storage-protocol, postgres-patterns, layer3-contract | cron + triggers, `results/state/retrain_log_*.json`, `results/state/retrain_state.json`, atomic promote | AG-009 |
| **010** FinBERT macro features + veto (optional) | queue-nlp | queue-decoupling, point-in-time-leakage, layer3-contract, postgres-patterns | macro features via ColumnTransformer, `results/state/macro_veto.json`, MLflow run | AG-010 |

Cross-gate **AG-CROSS** (provenance chain + version alignment + granularity coherence) runs after
every handoff.

---

## 8. RESUMABILITY PROTOCOL (so any LLM can take over)

After every meaningful step:
1. Append an **event** to `progress_ledger.json` (`events[]`) and update the task's **snapshot**.
2. Set the task's `next_action` to the precise next step (a command or a named sub-task).
3. Regenerate `STAKEHOLDER_UPDATE.docx` (`python orchestration/generate_stakeholder_docx.py`).
4. Keep all artifacts at their contracted paths so provenance can be walked back to the OANDA call.

On a **fresh start** (you, or Opus 4.8 / DeepSeek / Kimi): read the ledger tail + `CONTINUATION_PROMPT.md`,
re-verify the last completed gate, then execute `next_action`. **Never** "randomly continue" — if the
ledger is ambiguous, re-run the last audit gate to establish ground truth before proceeding.

---

## 9. DEFINITION OF DONE (System 1)

- All **10 acceptance-criteria sets** green; all **AG-001…AG-010 + AG-CROSS** passed.
- HMM bundle **round-trips** through the `StorageBackend` (local now) with verified SHA256;
  `latest.json` resolves to the newest valid version; atomic-pointer + rollback proven.
- `Scored_Signal_Queue` contract validated (schema, idempotency, backpressure, DLQ); **zero** Layer 4
  imports in any System-1 scoring path.
- Vetting emits a **non-empty** `regime_strategy_map.json` + `strategy_weights.json`; gatekeeper shows
  **non-negative, significant OOS uplift**.
- `progress_ledger.json` shows every task `done`; `STAKEHOLDER_UPDATE.docx` reads **100%** with the
  provenance chain intact and the granularity contract consistent across all docs.
- Storage/queue still on local defaults; GCS/broker attach is a config change, not a code change.

---

### Appendix — quick file map
- Task specs: `tasks/01-…md` … `tasks/10-…md`
- Agents: `tasks/agents/*.md` (+ `README.md` protocol)
- Skills: `tasks/skills/*.md`
- Living docs: `orchestration/PROGRESS_LEDGER.md`, `orchestration/progress_ledger.json`,
  `orchestration/STAKEHOLDER_UPDATE.md` (+ generated `.docx`)
- Continuation: `orchestration/CONTINUATION_PROMPT.md`
- Governance: `orchestration/FOLDER_STRUCTURE.md`, `orchestration/AGENT_FLEET_TOPOLOGY.md`,
  `orchestration/STORAGE_AND_QUEUE_ABSTRACTION.md`
