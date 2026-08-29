# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Last updated: 2026-08-28 (governance pass — volatile state moved out to
`docs/critical/REPO_STATE.md`; agents, skills and folder-scoped `CLAUDE.md` files added).
Previous: 2026-08-28 (deep cleanup pass), 2026-08-23 (full rescan). Supersedes the 2026-07-08
version, which documented `src/system1/` as the module root — that prefix was dropped on
2026-08-20 (commit `4593d88`).

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

> ⚠️ **`docs/design/ADR-001-where-inference-runs.md` (PROPOSED, 2026-08-22).** System 1 currently
> *also* emits live scored signals (`src/signals/`, `src/queue_producer/`), which contradicts the
> ratified README design (System 2 runs inference from the bundle) and makes trading depend on this
> host. Treat the producer as **a bridge, not the destination** — do not build anything new that
> requires Computer 1 to be online.

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
| — | `regime/structural.py` | **CSRM structural labels — the label that actually routes live signals.** Computed on the fly from D1 closes (ADX + rolling ATR% z-score). `regime_causal` is NULL on the newest rows, so the live path must not use it |
| 004 | `attribution/attribute.py` + `metrics.py` + `discrimination.py` | Point-in-time join of trades to the **causal** regime at entry; per (strategy × regime × granularity) metrics on **OOS trades only** → `fact_strategy_regime_attribution` |
| 005 | `vetting/vet.py` + `gates.py` | Performance gates + softmax weights → `regime_strategy_map.json`, `strategy_weights.json` |
| — | `vetting/designate.py` | **Owner override**: put a gate-failing strategy in the map with a written reason. Refuses `INTEGRITY_DISQUALIFIED` ids. `selection_basis: "designated"` is carried all the way to the signal message |
| — | `vetting/rank_all.py` | Rank every registered strategy on pooled OOS — the selection report |
| 006 | `gatekeeper/train.py` + `thresholds.py` + `promote.py` + `score.py` | XGBoost gatekeeper on causal-regime features; expanding walk-forward; per-regime thresholds; bootstrap-significant OOS uplift |
| 007 | `serializer/serialize.py`, `publish_gatekeeper.py`, `publish_model_set.py` | Publish contract (below). `publish_model_set` is the **governed writer of the top-level `latest.json`** and the only place `--withdraw` exists |
| 008 | `queue_producer/producer.py` + `signals/{run,build,watcher}.py` | The **only online component**: watches for newly closed bars, builds + scores signals, publishes to `scored_signal_queue`. Slated for removal by ADR-001 |
| 009 | `scheduler/orchestrator.py` + `triggers.py` | Retrain orchestrator: trigger → single-flight lock → cooldown → gated pipeline → atomic promote. **Its cron is currently disabled (see Holds)** |
| — | `monitoring/` | `heartbeat.py` (daily freshness, exit 0/1/2 + `HEARTBEAT_ALERT` flag), `publish_health.py` (`telemetry/s1_health.json`), `model_card.py` (mirror/verify the card pinned in the live set), `holds.py`, `freshness.py` |
| — | `analytics/` | Read-only exports for the dashboard: `publish_analytics.py` (catalog, per-trade returns, frequency), `publish_strategy_stats.py` (`risk/strategy_stats/latest.json` for System 3), `publish_regime.py`, `assets.py` |
| — | `portfolio/` | Cross-sectional (multi-pair-at-once) research path: `bundle.py` aligns pairs onto one calendar, `run_momentum.py`, `evaluate.py` |
| — | `registry/` | `catalog.py` reads `dim_strategy`; `allocate.py` assigns strategy ids |
| — | `outcomes/persist_all.py` | Backtests registered strategies and writes `fact_trade_outcomes` (routes each strategy to its declared `primary_granularity`) |
| — | `validation/walk_forward.py` | Shared pure fold logic (min_train 36mo, step 6mo, OOS 6mo, anchored) used by 003/004/006 and the v2 harness |
| — | `layer0/` | Legacy name, **still load-bearing**: indicators, `core_engine/backtest_engine.py`, `position_engine.py`, `strategies/` (the ~47-strategy research sandbox + `v2_harness.py`) |
| — | `layer3_ml/` | A deliberate **tombstone** (`train_ml_gatekeeper.py` raises ImportError) plus guard tests. Do not "fix" it by restoring the module |

Legacy layers 1, 2, 4, 5, 6, 7 were retired and archived; `archieved/` is git-ignored wholesale.
The `archieved` typo is deliberate — `.gitignore` and prior task records reference it.

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
python -m pytest src -q --ignore=src/layer0/strategies/research/tests   # 586 tests, ~20 s
python -m pytest src/vetting -v                                          # one module
python -m pytest src/vetting/tests/test_gates.py::test_individual_gate_boundaries -q  # one test
black src/ && mypy src/
```

`conftest.py` at the root is what makes `import src...` resolve — do not delete it.

**There is a standing set of known-red tests** (2 collection errors, 19 stale-assertion
failures) and one known-broken module. They are enumerated with their causes in
`docs/critical/REPO_STATE.md` — read it before reporting a red as new, and **distinguish your
reds from those** before claiming "tests pass".

Fix stale tests to the current thresholds rather than reverting behavior; the gate change was deliberate.

### Scheduled operation

**The installed crontab is listed in `docs/critical/REPO_STATE.md`** — read it there rather
than from memory. What is durable:

- The **hourly** signal cadence exists because H4 bars close six times a day and the watcher's
  8h30m staleness threshold would discard five of six otherwise. It is `flock`-guarded
  (`results/state/hourly_signals.lock`) and self-limiting: outside market hours everything is
  stale, the watcher refuses, and the run is a no-op.
- **The retrain cron is NOT installed** — declared hold in `results/state/cron_holds.json` at
  Computer 2's request. Re-enable **only** when Computer 2 asks explicitly.
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
- **`results/state/regime_strategy_map.json` is the live map.** Read the file; the cell count
  evolves with each vetting run. Designated cells carry `designated_reason`, `ci_mean_r`,
  `pairs_passed_fraction` and `tail_dependence` — read those reasons before touching them.
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
| Orchestrator exits `no_trigger_or_cooldown` | Normal — no trigger fired, or within cooldown |
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
| `docs/proposed-fixes/system-1/` | `FIX-S1-001…015`. FIX-S1-016 (producer never emitted) has no doc here — it is written up in `docs/comms/to_system3/TO-SYSTEM3-2026-08-22-restore-signal-flow.md` and in code comments |
| `docs/design/ADR-001-where-inference-runs.md` | The inference-location decision (PROPOSED) |
| `docs/design/REGIME_STATE_AND_HOW_TO_RUN.md`, `REGIME_LABELS_EXPLAINED.md` | Which regime label is which, and why |
| `docs/design/STRATEGY_EXPERIMENT_STANDARD.md` | The contract every research experiment follows |
| `docs/comms/` | Correspondence with Computers 2 and 3. `README-START-HERE.md` indexes the work packages |
| `contracts/*.json` | Cross-machine message schemas, **read at runtime** — changing one is a cross-system change |
| `src/common/storage/README.md`, `src/serializer/{DETERMINISM,SIGNING}.md` | Publish, determinism and signing contracts |
| `docs/frontend/strategy-catalog.html` | All research strategies with OOS results. Generated by `shell/build_strategy_catalog.py` — re-run it, don't edit the HTML |
| `docs/database/SQL_TRANSLATION_RULES.md` | PostgreSQL rules and the FND-004 migration record |

---

*If this file conflicts with implementation behavior, implementation wins. Update this file in the
same change set that updates behavior.*
