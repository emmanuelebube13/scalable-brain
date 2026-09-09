# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Last updated: 2026-09-06 (staleness pass — folded in the R1/R2/R4 remediation commits of
2026-09-05, retired the known-red list, corrected four dead paths, recorded ADR-001's approval).
Previous: 2026-08-28 (governance pass — volatile state moved out to
`docs/critical/REPO_STATE.md`), 2026-08-28 (deep cleanup), 2026-08-23 (full rescan). Supersedes
the 2026-07-08 version, which documented `src/system1/` as the module root — that prefix was
dropped on 2026-08-20 (commit `4593d88`).

**This file holds durable rules.** Anything that changes hourly — heartbeat status, the live
model set, signal counts, which tests are red — lives in `docs/critical/REPO_STATE.md` and is
refreshed by running commands, not by editing prose.

---

## START HERE

| Read | For |
|---|---|
| **`GOVERNANCE.md`** | How work is produced and accepted: the output standard, the agent roster, retention, comms |
| **`STRUCTURE.md`** | Where every file goes. Read before creating one |
| **`docs/critical/REPO_STATE.md`** | What is true right now — heartbeat, holds, live artifacts, known-red tests |
| **`task/OPEN.md`** | The open-items register |

### Agents and skills

Nine **read-only** review agents live in `.claude/agents/` — they report, they never write:
`auditor`, `devils-advocate`, `leakage-hunter`, `measurement-reviewer`, `forex-strategist`,
`release-guard`, `db-guardian`, `structure-warden`, `comms-liaison`.

Five procedures live in `.claude/skills/`: `publish-model-set`, `run-vetting`, `write-comms`,
`close-a-task`, `log-an-issue`. **Use the skill rather than reconstructing the procedure** —
each encodes an ordering that has been got wrong before.

Six folders carry their own `CLAUDE.md` with local constraints: `src/serializer/`,
`src/vetting/`, `src/common/`, `src/layer0/`, `docs/comms/`, `task/`.

---

## WHAT THIS REPO IS

**Scalable Brain** is a quantitative Forex platform split across three computers.
**This repo is System 1 — "The Brain"** (Computer 1): the offline model-building factory.
Its product is a versioned, checksummed **model set** published to GCS — never a direct order.

| System | Where | Role |
|---|---|---|
| **System 1 — The Brain** | **this repo, this machine** | ingest → features → regimes → attribution → vetting → gatekeeper → publish, plus a live signal bridge |
| System 2 — The Hand | user's other computer ("trading-1") | execution only: downloads the model set, fills on OANDA, manages positions, telemetry dashboard |
| System 3 — The Guardian | user's other computer | 10-layer risk gate (A–J), sizing, account state machine, circuit breakers |

Inviolable principles: preservation over profit; **no downstream recomputation** (S3 never
re-scores, S2 never re-sizes, S1 never knows if it's live); **default-safe** (missing/stale/error
⇒ REJECT); deterministic, idempotent, auditable.

- **Python 3.12**, venv at `/home/emmanuel/Documents/Scalable_Brain/.venv` (outside the repo; cron
  scripts hardcode this path — do not move it)
- **DB:** PostgreSQL 16 + TimescaleDB on host `localhost:5432`, database `ForexBrainDB`, role `sa`.
  SQL Server is gone; everything goes through `src/common/db.py`
- **Cloud:** GCS bucket `scalable-brain-artifacts` (`secrets/system1-rw.json`, git-ignored);
  **Pub/Sub is live** — `QUEUE_PROVIDER=pubsub`, project `scalable-brain`
- **Broker:** OANDA v20 REST, practice env — **price ingest only** in this repo

> ⚠️ **`docs/design/ADR-001-where-inference-runs.md` — APPROVED, not built.** System 2 gave a
> conditional APPROVE and System 3 an APPROVE, both 2026-08-22, both verified against running
> hosts (ADR §3c); Phase 2 build briefs are in `docs/comms/to_system2/`. **The ADR's own header
> still reads `Status: PROPOSED` and is stale — §3c is authoritative.**
>
> Approval changed nothing on disk yet. System 1 still *also* emits live scored signals
> (`src/signals/`, `src/queue_producer/`), which contradicts the ratified README design (System 2
> runs inference from the bundle) and makes trading depend on this host. Treat the producer as
> **a bridge, not the destination** — do not build anything new that requires Computer 1 online.
> The blocking finding from the reviews still stands: the System 1 and System 3 signal schemas are
> mutually incompatible (`instrument`/`pair`, `entry`/`proposed_entry`, …, both
> `additionalProperties: false`), so **every signal System 1 produces would be rejected**. Schema
> v2 reconciliation ships before any producer change; System 1 adopts System 3's names.

---

## MODULE MAP — `src/<module>/` (flat; there is no `src/system1/`)

Every module is a `python -m` entry point, separates pure math from I/O, and registers to MLflow
where relevant. Task specs are `MODEL-001…010` in
`docs/implementation-roadmap/system-1-model-building/tasks/`.

| # | Module | Role |
|---|---|---|
| 001 | `ingestion/multi_timeframe_ingest.py` + `dq.py` | OANDA D1/H4/H1/W1 MBA candle ingest with DQ gates → `fact_market_prices` |
| 002 | `features/feature_pipeline.py` | Versioned Parquet feature store; trailing-only features, byte-deterministic |
| 003 | `regime/hmm_regime.py` | 4-state Gaussian HMM (D1/H4/H1) with K-Means fallback; emits reporting **and causal** labels → `fact_market_regime_v2` |
| — | `regime/structural.py` | **CSRM structural labels — the label that actually routes live signals** (ADX + rolling ATR% z-score on D1 closes). `regime_causal` is NULL on the newest rows, so the live path must not use it |
| — | `regime/build_structural.py` | **R2: the ONE place structural labels are computed.** Full history from a fixed `ANCHOR_DATE` → `fact_regime_structural`. The labeller is *not* lookback-invariant (`ewm(adjust=False)` seeds off the first row), so three callers with three windows produced three answers for the same bar. **Never recompute labels in a consumer — read the table** |
| — | `regime/live.py` | `current_regimes()` reads the newest label per instrument from `fact_regime_structural` (reads, never recomputes); `record_live_labels()` appends what routed a signal to `fact_regime_structural_live`. The recorder is an observer with no vote in routing and must never be able to break the read |
| — | `regime/structural_schema.py` | Schema/guards for the two structural tables |
| 004 | `attribution/attribute.py` + `metrics.py` + `discrimination.py` | Point-in-time join of trades to the **causal** regime at entry; per (strategy × regime × granularity) metrics on **OOS trades only** → `fact_strategy_regime_attribution` |
| 005 | `vetting/vet.py` + `gates.py` | Performance gates + softmax weights → `regime_strategy_map.json`, `strategy_weights.json` |
| — | `vetting/designate.py` | **Owner override**: put a gate-failing strategy in the map with a written reason. Refuses `INTEGRITY_DISQUALIFIED` ids. `selection_basis: "designated"` is carried all the way to the signal message |
| — | `vetting/rank_all.py` | Rank every registered strategy on pooled OOS — the selection report |
| — | `vetting/map_contract.py` | **R1: the map's provenance contract, freeze switch and admissibility check.** A map states the label it was selected under (`source_label`); a map expires (`expires_at_utc` / `MAP_MAX_AGE_DAYS`); every defect means **no signals**, loudly. Exists because a map selected on the HMM's `regime_causal` was published and executed against the *structural* label (agreement 19–36%, kappa ~0) — every cell was a statement about conditions that never fired it. Failing **open** on a stale map is worse than the FIX-S1-016 stall |
| 006 | `gatekeeper/train.py` + `thresholds.py` + `promote.py` + `score.py` | XGBoost gatekeeper on causal-regime features; expanding walk-forward; per-regime thresholds; bootstrap-significant OOS uplift |
| 007 | `serializer/serialize.py`, `publish_gatekeeper.py`, `publish_model_set.py` | Publish contract (below). `publish_model_set` is the **governed writer of the top-level `latest.json`** and the only place `--withdraw` exists |
| 008 | `queue_producer/producer.py` + `signals/{run,build,watcher}.py` | The **only online component**: watches for newly closed bars, builds + scores signals, publishes to `scored_signal_queue`. Slated for removal by ADR-001 |
| 009 | `scheduler/orchestrator.py` + `triggers.py` | Retrain orchestrator: trigger → single-flight lock → cooldown → gated pipeline → atomic promote. Cron **is installed** (hourly poll; the Sunday-00:00-UTC window is the only scheduled trigger) |
| — | `monitoring/` | `heartbeat.py` (daily freshness, exit 0/1/2 + `HEARTBEAT_ALERT` flag), `publish_health.py` (`telemetry/s1_health.json`), `model_card.py` (mirror/verify the card pinned in the live set), `holds.py`, `freshness.py` |
| — | `monitoring/risk_off.py` | **R4.2: the risk-off flag the producer actually reads.** The heartbeat detected the 2026-08-24 regime stall correctly and loudly every day for 10 days and was ignored — because *nothing consumed* `HEARTBEAT_ALERT`. A detector with no consumer is not a control. Stale inputs now stop trading |
| — | `monitoring/job_runs.py` | **R4.3: a job's success is a written record, not an absence of errors.** Freshness alone cannot distinguish "ran and correctly wrote nothing" from "never ran at all". Cron scripts call `shell/_job_record.sh <name>` then `job_record_ok`, so a job's **absence** is detectable |
| — | `analytics/` | Read-only exports for the dashboard: `publish_analytics.py` (catalog, per-trade returns, frequency), `publish_strategy_stats.py` (`risk/strategy_stats/latest.json` for System 3), `publish_regime.py`, `assets.py` |
| — | `portfolio/` | Cross-sectional (multi-pair-at-once) research path: `bundle.py` aligns pairs onto one calendar, `run_momentum.py`, `evaluate.py` |
| — | `registry/` | `catalog.py` reads `dim_strategy`; `allocate.py` assigns strategy ids |
| — | `outcomes/persist_all.py` | Backtests registered strategies and writes `fact_trade_outcomes` (routes each strategy to its declared `primary_granularity`) |
| — | `validation/walk_forward.py` | Shared pure fold logic (min_train 36mo, step 6mo, OOS 6mo, anchored) used by 003/004/006 and the v2 harness |
| — | `layer0/` | Legacy name, **still load-bearing**: indicators, `core_engine/backtest_engine.py`, `strategies/position_engine.py`, `strategies/` (the ~47-strategy research sandbox + `v2_harness.py`) |
| — | `layer3_ml/` | A deliberate **tombstone** (`train_ml_gatekeeper.py` raises ImportError) plus guard tests. Do not "fix" it by restoring the module |

Legacy layers 1, 2, 4, 5, 6, 7 were retired and archived; `archieved/` is git-ignored wholesale.
The `archieved` typo is deliberate — `.gitignore` and prior task records reference it.

**Not part of the pipeline**, present but unwired — do not assume they run: `src/nlp/`
(`finbert.py`, `macro_scraper.py`), `src/sql/` (migration/diagnostic SQL and the SQL-Server
migration script), `src/research_notes_api.py` (a standalone Flask CRUD service).

---

## COMMANDS

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate
```

### Pipeline

```bash
python -m src.ingestion.multi_timeframe_ingest            # MODEL-001
python -m src.features.feature_pipeline --version 1.0.0   # MODEL-002
python -m src.regime.hmm_regime                           # MODEL-003 (minutes on H1)
python -m src.outcomes.persist_all                        # rebuild fact_trade_outcomes
python -m src.attribution.attribute                       # MODEL-004
python -m src.vetting.vet --live                          # MODEL-005 (omit --live ⇒ results/reports/proposed_*)
python -m src.vetting.rank_all                            # selection report, changes nothing
python -m src.vetting.designate --strategy KEY --reason "…" --by owner [--dry-run]
python -m src.gatekeeper.train --dry-run                  # MODEL-006 (dry-run ⇒ proposed_champion_*)
python -m src.serializer.serialize                        # MODEL-007 bundle
python -m src.serializer.publish_gatekeeper               # gated champion publish (--dry-run / --force)
python -m src.serializer.publish_model_set                # flip the top-level latest.json
python -m src.serializer.publish_model_set --withdraw --reason "…"   # CLI-only, never automated
python -m src.analytics.publish_analytics                 # (--dry-run stages locally)
python -m src.scheduler.orchestrator [--force]            # MODEL-009
python -m src.signals.run --once                          # the live signal bridge
python -m src.queue_producer.emit_drill [--publish]       # one rehearsal message (dry-run default)
python -m src.monitoring.heartbeat [--json]               # exit 0 fresh / 1 warn / 2 critical
python -m src.monitoring.publish_health
python -m src.monitoring.model_card --mirror | --verify
```

**Log-only / dry-run is the default for every promotion-capable stage.** The orchestrator is the
single governed writer of the champion bundle (FIX-S1-009) — never add a second promotion path.

### Tests

```bash
python -m pytest src -q --ignore=src/layer0/strategies/research/tests   # 747 tests, ~27 s
python -m pytest src/vetting -v                                          # one module
python -m pytest src/vetting/tests/test_gates.py::test_individual_gate_boundaries -q  # one test
black src/ && mypy src/
```

`conftest.py` at the root is what makes `import src...` resolve — do not delete it.

**The old known-red list is retired.** It recorded 2 collection errors and 19 stale-assertion
failures as of 2026-08-23; none reproduce. **Treat the suite as green and any red as yours** —
check `docs/critical/REPO_STATE.md` for anything newly declared before assuming otherwise.

Fix stale tests to the current thresholds rather than reverting behavior; the gate change was deliberate.

### Scheduled operation

**The installed crontab is listed in `docs/critical/REPO_STATE.md`** — read it there rather
than from memory. What is durable:

- The **hourly** signal cadence exists because H4 bars close six times a day and the watcher's
  8h30m staleness threshold would discard five of six otherwise. It is `flock`-guarded
  (`results/state/hourly_signals.lock`) and self-limiting: outside market hours everything is
  stale, the watcher refuses, and the run is a no-op.
- **The retrain cron IS installed** — re-enabled by owner decision 2026-09-03; the hold at
  Computer 2's request was removed and `results/state/cron_holds.json` now holds an empty list
  (backup: `results/state/crontab.backup-20260903.txt`). It polls **hourly** and no-ops unless a
  trigger fires; `MODEL_SET_AUTOPUBLISH` stays unset, so the top-level pointer System 2 reads is
  untouched by an automated run. **An hourly cron is not an hourly retrain** — a log full of
  `no_trigger_or_cooldown` is the design working.
- **A hold is not a fix.** It suppresses the heartbeat failure while preserving the underlying
  measurement, and it carries a reason, evidence and an expiry. When one expires, either fix
  the cause or renew it with a fresh reason — a silently renewed hold is an open issue in
  disguise.

---

## THE PUBLISH CONTRACT (do not reorder these steps)

1. upload to an **immutable versioned prefix** (`system1/<version>/`, `models/gatekeeper/<version>/`)
2. **SHA256 round-trip verify every object read back from the backend**
3. archive the superseded pointer to `previous.json`
4. **atomic pointer flip LAST** — a mismatch deletes the partial version and aborts with the pointer untouched

Two pointer levels, and they mean different things:

- `system1/latest.json`, `models/gatekeeper/latest.json` — the sub-pointers
- top-level `latest.json` — the **model-set manifest** System 2 downloads. It is a pure function of
  the two sub-pointers, so it can never invent a pairing. Only `publish_model_set` writes it.

Two `status` fields that must never be conflated (this cost weeks of silent non-emission, FIX-S1-016):

| Artifact | Field | Values | Meaning |
|---|---|---|---|
| model-set manifest | `status` | `published` / `withdrawn` | **is this model set live?** |
| `regime_strategy_map.json` | `status` | `proposed` / `published` | vetting's own field — **never a publication state** |

The local `model-artifacts/latest.json` is **not** authoritative; the backend copy is.

---

## CURRENT STATE

**Moved to `docs/critical/REPO_STATE.md`** — live model set, map cell counts, signal totals,
heartbeat, holds, known-red tests. Those change hourly; this file does not. Read the state
file, or re-run the commands it lists. Never cite a remembered value.

The durable parts stay here:

- **Vetting gates:** PF ≥ 1.5, Sharpe ≥ 0.8, MaxDD ≤ 25%, WinRate ≥ 40%, Recovery ≥ 3.0,
  **OOS ≥ 12 months** (lowered from 60 by owner decision 2026-08-21). There is **no
  minimum-trade-count gate** — `trade_count` is only a ranking tie-break, so a cell can pass
  everything on a small sample.
- **`results/state/regime_strategy_map.json` is the live map, and it is now under contract**
  (`vetting/map_contract.py`, R1). It is frozen, carries provenance, and **expires**. Three rules:
  a map states the `source_label` it was selected under and is inadmissible if that differs from
  the label the live path routes on; a map that outlives `expires_at_utc` must stop trading, not
  keep trading; every defect means **no signals**, never a permissive fallback. Read the file; the
  cell count evolves with each vetting run. Designated cells carry `designated_reason`, `ci_mean_r`,
  `pairs_passed_fraction` and `tail_dependence` — read those reasons before touching them.
- **Vetting may only qualify from ONE simulation engine.**
  `attribution.attribute.AUTHORITATIVE_ENGINE_FOR_VETTING` is deliberately `None`:
  `fact_trade_outcomes` holds `backtest_engine_v1` and `position_engine_v2`, whose `r_multiple` is
  not the same quantity (v2 moves stops and scales out; v1 does neither) over disjoint strategy
  populations, so there is no data-driven tie-break. **Until an owner sets it, the orchestrator
  aborts rather than silently averaging the two** — see `audit/reports/engine_validation_2/report.md` §B2.
  Pooling is available only as the explicit, logged `attribute.POOLED` opt-in, for read-only reporting.
- **`last_signal_emitted_at`** in `results/state/signal_emitter_state.json` is the
  load-bearing field. A green heartbeat with a null value there is the FIX-S1-016 failure mode.

### Standing findings — read before changing regime/attribution/vetting logic

- **Regimes do not discriminate.** `discrimination` reports `n_discriminating: 0 of 10`; among clean
  strategies max win-rate spread is 0.0567 against a 0.10 bar. Re-tested against honest labels; it stands.
- **FIX-S1-013** — strategy 10 `Range_Stochastic_Divergence` reads the future via `rolling(center=True)`
  and emits **zero** signals causally. Its attribution rows still show PF 1.92 because they derive from
  the look-ahead backtest, so regenerating the map would re-qualify it. It is barred by
  `INTEGRITY_DISQUALIFIED` in `vetting/vet.py`, checked **before** the performance gates and in a
  separate `integrity_fail` category — gates encode "could pass later by improving"; this cannot.
- **D1 HMM falls back to K-Means** (working as designed — don't claim HMM for D1).

---

## DATABASE

```bash
psql -h localhost -p 5432 -U sa -d ForexBrainDB -c "SELECT count(*) FROM fact_market_prices;"
```

Nothing to `docker-compose up` for normal operation (an optional throwaway dev DB exists on 5433
under the `dev` profile — never bind to host `:5432`).

| Table | Producer | Consumer |
|---|---|---|
| `fact_market_prices` | MODEL-001 | 002 / 003 |
| `fact_market_regime_v2` | MODEL-003 | 004 / 006 |
| `fact_regime_structural` | `regime/build_structural.py` | `regime/live.py` → the live routing path, analytics, gatekeeper. **The single source of structural labels** |
| `fact_regime_structural_live` | `regime/live.py` (`record_live_labels`) | audit only — what the regime was believed to be when a signal was placed |
| `fact_trade_outcomes` | `outcomes/persist_all.py` | 004 |
| `fact_strategy_regime_attribution` | MODEL-004 | 005 |
| `dim_strategy`, `dim_asset` | registry / seeds | everywhere |

### SQL rules

- Connect **only** via `src/common/db.py` (`get_engine()`, `get_psycopg2_connection()`,
  `bulk_upsert()`). SQLAlchemy 2.0 + psycopg2, UTC session. Never build a connection string inline.
- Case: only `"Open"`/`"Close"` are mixed-case (double-quote them); `"timestamp"` is reserved
  (quote it); everything else lowercase. Alias out to mixed-case when callers expect it.
- Idempotent writes: `INSERT … ON CONFLICT (<pk>)`. Parameterized SQL only.
- The schema has drifted from the original design — write schema-aware code, never assume an
  optional column exists. Reference: `docs/database/SQL_TRANSLATION_RULES.md`.

---

## AGENT RULES

### DO

- **Follow `GOVERNANCE.md`.** Claims carry their evidence inline; verification means running
  it, not reading a docstring; dry-run is the default for anything that promotes or publishes;
  state what you did **not** check; an adversarial pass by someone other than the author.
- Preserve walk-forward / causal-label discipline: fold-fit models, forward-only inference,
  OOS-only gate metrics.
- Keep the orchestrator the **only** champion promotion path, and `publish_model_set` the only
  writer of the top-level pointer.
- Use `src/common/{db,storage,queue}` abstractions.
- Keep granularity (H1/H4/D1/W1) explicit everywhere.
- Check `docs/proposed-fixes/system-1/` before "discovering" a bug — it may be known, fixed, or in flight.
- When a threshold appears in a message string, read it from the constant. A hardcoded "< 60mo" in a
  rejection reason sent a downstream agent on a real investigation into a gate that was working.

### DO NOT

- Start, edit, or "fix" `../system-2-execution-engine/` or `../system-3-account-management/` from this
  machine. They are deployed elsewhere; local copies are reference only.
- Add execution, sizing, order routing, or account state to this repo.
- Restore the `layer3_ml` tombstone, or add a second gatekeeper trainer/publisher.
- Call `--withdraw` from automation. It is CLI-only with a mandatory human `--reason`, deliberately.
- Rewrite a message already sent in `docs/comms/` — that folder is append-only in spirit.
- Put anything new at the repo root. `STRUCTURE.md` is the map and the root is closed to new files.
- Hand-edit a machine-written artifact (`results/`, `models/`, `model-artifacts/`,
  `feature-store/`, `mlruns/`). If the output is wrong, the run is wrong — editing the file
  hides the defect and the next run silently reverts your fix.
- Record volatile state in `CLAUDE.md`. It goes in `docs/critical/REPO_STATE.md`.
- Commit `.env`, `secrets/`, `configuration/`, or model binaries.

---

## TROUBLESHOOTING

| Symptom | Check |
|---|---|
| Producer logs "No signals generated" | Usually correct — watcher staleness (`LATENCY_THRESHOLDS` in `signals/watcher.py`) rejects bars outside market hours. D1 is 108 h **on purpose** so Monday's Friday-close bar is not rejected |
| `last_run_outcome: no_model_set` | The backend model-set manifest is `withdrawn` or unreadable (check GCS creds). Do **not** "fix" it by reading the local map — that conflation is FIX-S1-016 |
| PubSub 404 `scored-signals.heartbeat` | Known: the topic was never created. See `shell/provision_pubsub.sh` |
| Orchestrator exits `no_trigger_or_cooldown` | Normal — no trigger fired, or within cooldown. The hourly cron logs this for nearly every hour of the week by design; only Sunday 00:00 UTC carries a scheduled trigger |
| Retrain aborts: "attribution engine_version is unset" | Working as designed, and it is an **owner decision, not a bug**. Set `attribute.AUTHORITATIVE_ENGINE_FOR_VETTING` to one of `VALID_ENGINES`. Note the Sunday window only matches at hour 0, so unblocking mid-week needs `orchestrator --force` |
| Producer emits nothing, map-related outcome | `map_contract.routing_refusals` — the map expired, or its `source_label` disagrees with the label being routed on. **Fail-closed is deliberate; do not add a fallback.** Re-run vetting to mint a fresh map |
| "single-flight lock" error | A run is in progress, or a stale `results/state/retrain.lock` after a crash |
| Retrain ran but didn't promote | Deployment gates: `regime_accuracy_ok` (≥0.70), `non_empty_map`, `oos_uplift_ok`, `beats_incumbent` — read the `retrain_log_*.json` |
| Publish aborts on checksum mismatch | Working as designed: partial version deleted, pointer untouched. Retry |
| Heartbeat red but the cause is known | Declare it in `results/state/cron_holds.json` with a reason, evidence and an expiry — don't silence the check |
| Reserved-word / case SQL errors | Double-quote `"Open"`, `"Close"`, `"timestamp"`; everything else lowercase |

---

## DOCUMENTATION MAP

| Path | Content |
|---|---|
| `GOVERNANCE.md` | **How work is produced and accepted** — the output standard, the agent roster, data classes, retention |
| `STRUCTURE.md` | **The folder map** — read before creating a file anywhere |
| `docs/critical/REPO_STATE.md` | **What is true right now** — heartbeat, holds, live artifacts, known-red tests |
| `.claude/agents/`, `.claude/skills/` | Nine read-only review agents; five procedures |
| `task/OPEN.md` | The open-items register. Update in place; do not start a competing list |
| `task/<YYYY>-<Month>-week<N>/` | Active work. Finished weeks **stay put** — other docs cite them as evidence |
| `issues/<Month>-Week-<N>/<date>.md` | Problems noticed in passing, one file per day |
| `docs/proposed-fixes/system-1/` | `FIX-S1-001…018`, plus `EngineValidation2.md` and `auditfixsep5.md`. **FIX-S1-016 is absent by design** (producer never emitted) — it is written up in `docs/comms/to_system3/TO-SYSTEM3-2026-08-22-restore-signal-flow.md` and in code comments |
| `audit/reports/engine_validation_2/report.md` | Why the two simulation engines cannot be pooled (§B2 is the unset-engine decision) |
| `docs/design/ADR-001-where-inference-runs.md` | The inference-location decision — **approved 2026-08-22 by both systems (§3c); its own header still says PROPOSED and is wrong** |
| `docs/design/REGIME_STATE_AND_HOW_TO_RUN.md`, `REGIME_LABELS_EXPLAINED.md` | Which regime label is which, and why |
| `docs/design/STRATEGY_EXPERIMENT_STANDARD.md` | The contract every research experiment follows |
| `docs/comms/` | Correspondence with Computers 2 and 3. `README.md` indexes the work packages; `to_system2/`, `to_system3/`, `replies/`, `handoffs/`, `notices/`, `technical_docs/` |
| `contracts/*.json` | Cross-machine message schemas, **read at runtime** — changing one is a cross-system change |
| `src/common/storage/README.md`, `src/serializer/{DETERMINISM,SIGNING}.md` | Publish, determinism and signing contracts |
| `docs/frontendEducation/strategy-catalog.html` | All research strategies with OOS results. Generated by `shell/build_strategy_catalog.py` — re-run it, don't edit the HTML. ⚠️ **The script's `OUT` still writes to `docs/frontend/`, which no longer exists**; the committed page is the `frontendEducation/` copy, so a re-run lands in a new folder rather than updating it |
| `docs/database/SQL_TRANSLATION_RULES.md` | PostgreSQL rules and the FND-004 migration record |

---

*If this file conflicts with implementation behavior, implementation wins. Update this file in the
same change set that updates behavior.*
