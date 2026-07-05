# CONTINUATION PROMPT — Resume System 1 With Identical Quality

> **For any LLM picking up this work** (Claude Opus 4.8, DeepSeek, Kimi, or another capable coding
> agent), possibly in a **different harness** than the one that started it. This prompt is
> **tool-agnostic and filesystem-driven**. It assumes only that you can: read/write files in the
> repo, run shell commands, and run Python. It does **not** assume any Claude-Code-specific tool
> (no `Agent`, `Task`, `TaskCreate`, `ScheduleWakeup`, etc.). If you *have* a sub-agent facility,
> use the org model; if you do **not**, do exactly the same work **single-threaded**.

Repo root: `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`
Everything below is relative to `docs/implementation-roadmap/system-1-model-building/`.

---

## Step 1 — Establish ground truth (do this before anything else)

1. Read `orchestration/progress_ledger.json` (authoritative) and `orchestration/PROGRESS_LEDGER.md`.
2. Read the **tail of `events[]`** and the **per-task `status` + `next_action`** snapshots.
3. Read `orchestration/MASTER_ORCHESTRATION_PROMPT.md` (the full mission, non-negotiables, DAG, gates).
4. Identify the **first task that is not `done`**. That is where you resume.
5. **Trust, but verify.** Before continuing a task, **re-run the last passed audit gate** for its
   most recent upstream dependency (gate checks are in `tasks/agents/auditor-traceback-agent.md`,
   sections `AG-001`…`AG-010`, `AG-CROSS`). If a gate that the ledger says "passed" now fails, the
   ledger is stale — fix the ledger and resolve the regression before moving on. **Never assume.**

---

## Step 2 — Load the context for the task you're resuming

For task `MODEL-0XX`:
1. Read its spec: `tasks/0X-*.md` (Objective, Target State, Technical Spec, Testing & Validation,
   Acceptance Criteria, Rollback).
2. Read its owning agent file in `tasks/agents/` (Input/Output Contracts, exact artifact paths,
   self-verification gates, failure modes).
3. **Load every skill** listed in that agent's `## Skills` section from `tasks/skills/`. This is
   mandatory — the skills encode the patterns (PostgreSQL `INSERT … ON CONFLICT`, HMM
   state→label determinism, point-in-time joins, vetting gates, storage atomic-pointer, queue
   decoupling, financial metrics). Do not write code before loading them.
4. Read `orchestration/FOLDER_STRUCTURE.md` to know where new files go, and
   `orchestration/STORAGE_AND_QUEUE_ABSTRACTION.md` for the pluggable storage/queue interfaces.

---

## Step 3 — The non-negotiables (identical to the master prompt)

- **PostgreSQL only.** Connect via `src/common/db.py`. No SQL Server / ODBC (any such wording is
  obsolete). Double-quote only `"Open"`/`"Close"`/`"timestamp"`. Idempotent writes via
  `INSERT … ON CONFLICT`.
- **Reuse, don't rebuild.** Extend `src/layer0/ingest_oanda_prices.py`,
  `src/layer1_regime/Fact_market_regime_v2.py`, `src/layer3_ml/…`, `src/nlp/…`. Additive, non-breaking.
- **Storage/queue are pluggable with local defaults.** Build against `StorageBackend` /
  `QueueBackend`; a GCS adapter and a real broker attach **later by config only** — do not hardcode
  a cloud SDK.
- **Granularity contract:** D1 primary, H4 entry, W1 macro context, H1/H4 preserved for Layer 2/3.
- **Secrets from `.env` only**; never serialize a credential anywhere; scan bundles before publishing.
- **Data is already ingested** (H1/H4/D1 current). MODEL-001 only **adds W1 + DQ/lineage**; it does
  **not** re-backfill.

---

## Step 4 — Execute the task (same loop every time)

1. Build the change (extend existing code; keep it additive and deterministic).
2. Run the spec's **self-verification gates** and the owning agent's `## Verification Gates`.
3. Run long jobs **detached / in the background** (W1 backfill, HMM EM, XGB/LGBM tournaments,
   FinBERT batch, OOS walk-forward). Record each as a `background_jobs[]` entry in the ledger
   (command, log path, start time, expected duration) and poll it later — do not block on it.
4. Write a completion marker: `results/state/DONE_{agent}_{UTC-timestamp}.md` describing what was
   produced and where.
5. **Run the matching audit gate** (`AG-0XX`) yourself, acting as the auditor: execute every check
   in that gate against the produced artifacts.
   - **Pass:** delete any rework file, update the ledger (set task `done`, append an event, set the
     next task's `next_action`), regenerate `STAKEHOLDER_UPDATE.docx`, release downstream.
   - **Fail:** write `results/state/rework/{agent}_{UTC}.md` (failed check, expected vs actual, root
     cause, remediation), fix, re-run. **Max 3 iterations**, then write
     `results/state/blocked/{agent}.md` and **stop to alert the human** (do not loop forever).

---

## Step 5 — Hand off cleanly (so the next LLM can resume from you)

Before you stop (planned or out of budget):
1. Make sure `progress_ledger.json` reflects reality: correct `status`, a precise `next_action`
   (an exact command or named sub-step), and any running `background_jobs[]`.
2. Mirror it into `PROGRESS_LEDGER.md` and regenerate the stakeholder `.docx`.
3. Ensure all artifacts are at their **contracted paths** so the provenance chain
   (`latest.json → bundle → model_metadata → regime_model_version → hmm_model.joblib →
   feature_set_version → lineage.json → ingest_run_id → Fact_Market_Prices → OANDA`) is walkable.
4. Leave nothing implicit. If a fact lives only in your head, it is lost — write it to the ledger.

---

## If you have NO sub-agent / parallel tooling

Run the DAG single-threaded in this order, gating each step:
`001 → 002 → 003 → (004 → 005) → 006 → 007 → (008 any time) → 009 → 010(optional)`.
You personally play every role: implementer, test-author, structure-coherency (obey
`FOLDER_STRUCTURE.md`), ledger-keeper (update the living docs), and auditor (run AG-0XX). The
quality bar and the gates are identical — only the concurrency changes.

---

## Definition of done
Same as the master prompt §9: all 10 acceptance sets + all audit gates green, bundle round-trips via
the (local) storage backend with verified checksums, queue contract validated with no Layer-4 import,
non-empty regime map, significant OOS uplift, ledger at 100%, granularity contract consistent across
all docs, storage/queue still on local defaults (GCS/broker = config-only attach).
