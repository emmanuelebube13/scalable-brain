# CLAUDE.md

This file provides comprehensive guidance to Claude Code for working in this repository.

Last updated: 2026-07-08 (full rescan; supersedes the 2026-06-20 version, which documented
the legacy 8-layer monolith as the runtime — that is no longer accurate)
Repository root: `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`

---

## PROJECT OVERVIEW

**Scalable Brain** is an institutional-grade quantitative trading platform for automated
Forex trading, reorganized from a single-host 8-layer monolith into **three independently
deployable systems across three computers**, connected by cloud object storage (GCS) and
message queues (Pub/Sub). Philosophy: *"No strategy touches live capital until it proves a
mathematical edge. Every decision is deterministic, idempotent, auditable."*

**This repository is System 1 — "The Brain"** (Computer 1, this machine): the offline
model-building factory. Its outputs are a versioned, checksummed model bundle published to
object storage and scored signals published to a queue — **never a direct order**.

| System | Host | Role | Status (2026-07-08) |
|--------|------|------|---------------------|
| **System 1 — The Brain** | **Computer 1 (this repo)** | Ingest → features → regimes → attribution → vetting → gatekeeper → publish | **Operational.** Last gated retrain 2026-07-01 → promoted bundle `2026-07-01T12-56-32Z`; hourly orchestrator cron + Saturday ingest cron active |
| System 2 — The Hand | The user's **other computer** | Execution-only: consumes approved orders, fills on OANDA, manages positions | Engineering complete (152/152 tests); ops provisioning + practice drill + D-004 pending. Local copy at `../system-2-execution-engine/` is **reference only — do not run or edit it here** |
| System 3 — The Guardian | The user's **other computer** | 10-layer risk gate (A–J), account state machine, circuit breakers, sizing | Built on the other machine; this tree holds only docs/specs at `../system-3-account-management/` |

**Inviolable principles** (from README): preservation over profit; no downstream
recomputation (S3 never re-scores, S2 never re-sizes, S1 never knows if it's live);
default-safe posture (missing/stale/error ⇒ REJECT); deterministic and auditable.

- **Language:** Python 3.12 (venv: `/home/emmanuel/Documents/Scalable_Brain/.venv`)
- **DB:** PostgreSQL 16 + TimescaleDB 2.26.3, host cluster `localhost:5432`, database
  `ForexBrainDB`, role `sa`. FND-004 migration **complete** — all code is
  PostgreSQL-native via `src/common/db.py`. SQL Server is gone.
- **ML:** XGBoost gatekeeper, Gaussian HMM regimes (hmmlearn) with K-Means fallback,
  scikit-learn preprocessing, MLflow experiment tracking, Optuna
- **NLP:** FinBERT (auxiliary; MODEL-010 integration planned)
- **Broker (data ingest only, in this repo):** OANDA v20 REST, practice environment
- **Cloud:** GCS bucket `scalable-brain-artifacts` (service-account key
  `secrets/system1-rw.json`, git-ignored); Pub/Sub planned for queues (see Known Gaps)
- **Dev tools:** pytest, black, mypy

---

## SYSTEM 1 RUNTIME — `src/system1/` (THE code that matters)

The active pipeline is a clean rewrite organized as tasks **MODEL-001 … MODEL-010**
(specs in `docs/implementation-roadmap/system-1-model-building/tasks/`). It reuses some
`layer0` primitives (indicators, backtest engine) but is otherwise self-contained.
**The legacy `src/layer*` tree is NOT the runtime anymore** (see Legacy section).

Data flows top-to-bottom; every module is a `python -m` entry point, separates pure math
from I/O, and registers to MLflow:

| # | Module | Role | Key output |
|---|--------|------|-----------|
| 001 | `ingestion/multi_timeframe_ingest.py` + `dq.py` | OANDA multi-timeframe price ingest with data-quality gates | `fact_market_prices` |
| 002 | `features/feature_pipeline.py` + `definitions.py` | Versioned Parquet feature store; all features trailing-only (no look-ahead), deterministic | `feature-store/{version}/…` |
| 003 | `regime/hmm_regime.py` + `mapping.py` | 4-state Gaussian HMM regimes (D1/H4/H1) → {Trending-Up, Trending-Down, Ranging, High-Vol}; K-Means fallback below the ≥0.70 accuracy gate; emits reporting label AND **causal walk-forward label** | `fact_market_regime_v2`, `models/hmm_model.joblib` |
| 004 | `attribution/attribute.py` + `metrics.py` + `discrimination.py` | Point-in-time join of trades to **causal** regime at entry; per (strategy × regime × granularity) metrics on **OOS trades only**, Bayesian shrinkage for thin cells | `fact_strategy_regime_attribution` |
| 005 | `vetting/vet.py` + `gates.py` | Strict gates (PF≥1.5, Sharpe≥0.8, MaxDD≤25%, WinRate≥40%, Recovery≥3.0, OOS≥60mo); emits regime→strategy map + weights | `regime_strategy_map.json`, `strategy_weights.json` |
| 006 | `gatekeeper/train.py` + `thresholds.py` + `promote.py` | XGBoost signal gatekeeper on causal-regime features; expanding-window walk-forward; per-regime thresholds; bootstrap-significant OOS uplift | `champion_model.pkl` + manifest |
| 007 | `serializer/serialize.py` + `publish_gatekeeper.py` | Serialize + publish bundle to storage backend: SHA256 round-trip verify, secret scan, **atomic `latest.json` pointer flip only after verify**, beats-incumbent gate, immutable versioned prefixes, retention | published bundle in GCS/local |
| 008 | `queue_producer/producer.py` | Scored signals → `Scored_Signal_Queue`; schema-validated, idempotent, backpressure + DLQ | queue messages |
| 009 | `scheduler/orchestrator.py` + `triggers.py` | **Retrain orchestrator**: triggers (Sunday 00:00 UTC / low Sharpe / circuit breaker) → single-flight lock → cooldown → gated pipeline → atomic promote only if it clears gates AND beats the incumbent (incumbent read from the **storage backend**, FIX-S1-007) | `results/state/retrain_log_*.json`, `retrain_state.json` |
| — | `validation/walk_forward.py` | Shared pure walk-forward folds (min_train=36mo, step=6mo, OOS=6mo, anchored) used by 003/004/006 | — |
| — | `analytics/publish_analytics.py` (S1-EXPORT-002) | Read-only strategy analytics bundle for downstream telemetry/simulation: strategy catalog, OOS per-trade r-multiple series per qualified (strategy×regime×gran×pair) cell, frequency stats + regime occupancy; same immutable-prefix + SHA256-verify + pointer-flip-last contract; refreshed by the orchestrator after each promote (failure never affects the promote) | `system1/analytics/<version>/` + `latest.json` in GCS |

### Run commands (from repo root, venv active)

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate

python -m src.system1.features.feature_pipeline --version 1.0.0   # MODEL-002
python -m src.system1.regime.hmm_regime                           # MODEL-003 (multi-minute on H1)
python -m src.system1.attribution.attribute                       # MODEL-004
python -m src.system1.vetting.vet --live                          # MODEL-005 (omit --live = log-only proposal)
python -m src.system1.gatekeeper.train --dry-run                  # MODEL-006 (dry-run = proposed_champion_*)
python -m src.system1.serializer.serialize                        # MODEL-007
python -m src.system1.serializer.publish_gatekeeper               # MODEL-007 (gated champion publish; --dry-run / --force)
python -m src.system1.analytics.publish_analytics                 # S1-EXPORT-002 analytics bundle (--dry-run = stage locally only)
python -m src.system1.scheduler.orchestrator                      # MODEL-009 evaluate triggers (no-ops if none)
python -m src.system1.scheduler.orchestrator --force              # force a full gated retrain + promote
```

**Safety design:** log-only/dry-run is the *default* for promotion-capable stages. `vet`
writes `results/reports/proposed_*` unless `--live`; `gatekeeper.train --dry-run` never
touches the live champion. **The orchestrator is the single governed writer of the
champion bundle (FIX-S1-009)** — never add a second promotion path.                                                                                                                                                                                                                                                                               

### Scheduled operation (crontab, verified active 2026-07-08)

```
0 * * * *  shell/cron_system1_retrain.sh        # hourly trigger evaluation (no-op unless a trigger fires; single-flight + cooldown)
0 0 * * 6  shell/cron_oanda_ingest_saturday.sh  # weekly OANDA price ingest
# The legacy */30 layer-4 cron was DISABLED 2026-07-08 (broken since FIX-S1-009; execution belongs to System 2)
```

Retrain state lives in `results/state/retrain_state.json`; each evaluation appends
`results/state/retrain_log_*.json`. Logs: `logs/system1_retrain.log`,
`logs/cron_system1_retrain.log`.

### Storage & queue abstraction — `src/common/storage/`, `src/common/queue/`

Backends are env-selected (`.env`):

- `STORAGE_PROVIDER=gcs|localfs`, `GCS_BUCKET=scalable-brain-artifacts`,
  `STORAGE_LOCAL_ROOT=model-artifacts`,
  `GOOGLE_APPLICATION_CREDENTIALS=secrets/system1-rw.json`
- `QUEUE_PROVIDER=local|pubsub`, `QUEUE_LOCAL_ROOT=results/state/queue`,
  `SCORED_SIGNAL_QUEUE`, `DLQ_NAME`, `MAX_QUEUE_SIZE`,
  `BACKPRESSURE_TIMEOUT_MS`, `BACKPRESSURE_MAX_RETRIES`

Publish contract (see `src/common/storage/README.md`): immutable versioned prefixes,
SHA256 verify **before** the atomic pointer flip, superseded pointer archived to
`previous.json`, old versions never overwritten (retention trims oldest).

> ⚠️ `QUEUE_PROVIDER` is currently **`local`** — scored signals land in
> `results/state/queue/` on this machine, which System 3 (other computer) cannot read.
> Switching to Pub/Sub is a July 2026 goal (`docs/goals/JULY_2026_GOALS.md`).

---

## CURRENT MODEL STATE (as of 2026-07-08)

- Last gated retrain: **2026-07-01 → `promoted`**, bundle `2026-07-01T12-56-32Z`
  (per `results/state/retrain_state.json`). All 4 deployment gates passed:
  `regime_accuracy_ok`, `non_empty_map`, `oos_uplift_ok`, `beats_incumbent`.
  The live pointer is in the **storage backend** (GCS); the local
  `model-artifacts/latest.json` may lag it.
- Live map: of 10 strategies × 4 regimes = 80 cells, **4 qualified — all
  `Range_Stochastic_Divergence` (id 10)**, essentially all weight on H1.
  High-Vol regime has **no coverage** (starvation).
- Data (2026-07-01 counts): `fact_market_prices` 4,682,503 · `fact_market_regime_v2`
  842,241 (H1/H4 = HMM, **D1 fell back to K-Means**) · `fact_trade_outcomes` 134,520 ·
  `fact_strategy_regime_attribution` 640.

### Open findings (from `archieved/SYSTEM1_ANALYSIS_2026-07-01.md` — read it before touching vetting/regime code)

- **A — weight starvation (likely real bug):** `gates.normalized_weights` shift-by-floor
  drives the lowest-scoring qualifier in a regime to ≈0 weight regardless of merit
  (Ranging H4: Sharpe 1.74, PF 3.06 → weight 8e-8). Softmax/rank weighting proposed.
- **B — regimes are cosmetic:** discrimination run reports `n_discriminating: 0` of 10
  strategies (max win-rate spread 0.075 < 0.10 bar). The regime→strategy mapping is not
  a proven edge.
- **C — concentration risk:** entire live model = one strategy at one granularity.
- **D — D1 HMM fell back to K-Means** (fallback working as designed; don't claim HMM for D1).

### Fix history — `docs/proposed-fixes/system-1/`

FIX-S1-001…009 are remediated with guarding tests (metrics sanity bounds, true-OOS gate,
causal regime labels, weight-collision post-condition, fail-closed uplift gate, incumbent
read via backend, single governed champion writer). **FIX-S1-008** (gatekeeper leakage /
pipeline unification gates) is implemented in the working tree but **uncommitted** as of
2026-07-08 — commit it before anything else.

---

## LEGACY 8-LAYER MONOLITH — `src/layer*` (being retired)

The old CLAUDE.md documented these as the runtime. Current truth:

| Layer | Path | Status |
|-------|------|--------|
| 0 — Strategy qualification | `src/layer0/` | **Partially reused** by System 1: `indicators.py`, `backtest_engine.py`, `persist_trade_outcomes.py` (produced the 134,520 outcomes: spread 1.0 pip, slippage 0.5 pip entry-only, commission 0). `layer2_config_adapter.py` still emits SQL-Server T-SQL — known gap |
| 1 — K-Means regimes | ~~`src/layer1_regime/`~~ | **ARCHIVED 2026-07-29 (T7)** → `archieved/v1-cleanup-2026-W31/src/layer1_regime/`. Superseded by `src/system1/regime/` |
| 2 — Signal engine | ~~`src/layer2_signals/`~~ | **ARCHIVED 2026-07-29 (T7)**. `fact_signals` was not part of the System-1 retrain path |
| 3 — ML gatekeeper | `src/layer3_ml/` | Root `train_ml_gatekeeper.py` is a **tombstone that raises ImportError** (FIX-S1-009). `training/train_ml_gatekeeper.py` (legacy tournament trainer) remains but champion promotion is governed exclusively by the System-1 orchestrator |
| 4 — Live executor | ~~`src/layer4_executor/`~~ | **Retired → System 2.** Copy archived to `archieved/layer4_executor/`; its cron disabled 2026-07-08 (had been failing every run since FIX-S1-009) |
| 5 — Telemetry + dashboard | ~~`src/layer5/`~~ | **Retired → System 2** (telemetry is System 2's surface). Copy in `archieved/layer5/` |
| 6 — Trade auditor | ~~`src/layer6_auditor/`~~ | **Retired → System 3** (post-trade processing). Copy in `archieved/layer6_auditor/` |
| 7 — OANDA executor | ~~`src/layer7/`~~ | **Retired → System 2** (broker adapter). Copy in `archieved/layer7/` |
| NLP | `src/nlp/` | Auxiliary FinBERT macro intelligence; MODEL-010 integration planned |

**As of 2026-07-29 (T7) the legacy layer trees 1, 2, 4, 5, 6 and 7 have been moved out of `src/` into `archieved/v1-cleanup-2026-W31/`** (zip + SHA256 manifest alongside it). `src/layer0/` (partially reused) and `src/layer3_ml/` (tombstone + FIX-S1-008 guard tests) remain in place. Reversal is `git revert 9920b5b..040dd31`.

Do not build new functionality on the legacy layers. Do not "fix" the layer-3 tombstone
by restoring the retired module.

---

## DATABASE

**`ForexBrainDB`** — PostgreSQL 16 + TimescaleDB 2.26.3, host system cluster on
`localhost:5432`, role `sa`. Time-series fact tables are hypertables with compression.
Nothing to `docker-compose up` for normal operation (an optional throwaway dev DB exists
on port 5433 under the `dev` profile — never bind to host `:5432`).

```bash
psql -h localhost -p 5432 -U sa -d ForexBrainDB -c "SELECT count(*) FROM fact_market_prices;"
```

### Tables in the System-1 path

| Table | Producer | Consumer |
|-------|----------|----------|
| `fact_market_prices` | MODEL-001 ingest (+ Saturday cron) | 002/003 |
| `fact_market_regime_v2` | MODEL-003 | 004/006 |
| `fact_trade_outcomes` | `layer0/persist_trade_outcomes.py` | 004 |
| `fact_strategy_regime_attribution` | MODEL-004 | 005 |
| Feature store (Parquet, not DB) | MODEL-002 | 003/006 |
| `results/state/strategy_regime_attribution.parquet` | MODEL-004 | analysis |

Legacy tables (`fact_signals`, `fact_live_trades`, `fact_execution_log`,
`fact_macro_events`, `Dim_*`) still exist; `fact_live_trades` writing now belongs to
System 2.

### SQL rules (unchanged, still critical)

- Connect **only** via `src/common/db.py` (`get_engine()`; SQLAlchemy 2.0 +
  `postgresql+psycopg2`, UTC session). Never build a connection string inline.
- Column case: only `"Open"`/`"Close"` are mixed-case (double-quote them);
  `"timestamp"` is reserved (quote it); everything else lowercase. Alias outputs to
  mixed-case (`asset_id AS "Asset_ID"`) when callers expect it.
- Idempotent writes: `INSERT … ON CONFLICT (<pk>)`. Parameterized SQL only (SQLAlchemy
  `:named` / psycopg2 `%s`).
- Schema has drifted from the original design — write schema-aware code; never assume
  optional columns exist. Reference: `docs/database/SQL_TRANSLATION_RULES.md`.

---

## ENVIRONMENT

```bash
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate
pip install -r requirements.txt
```

Key `.env` variables (git-ignored; never commit values):

```
DB_SERVER=localhost  DB_PORT=5432  DB_NAME=ForexBrainDB  DB_USER=sa  DB_PASS=…
OANDA_API_KEY=…  OANDA_ACCOUNT_ID=101-002-38449021-001  OANDA_ENV=practice
OANDA_URL=https://api-fxpractice.oanda.com
STORAGE_PROVIDER=gcs  GCS_BUCKET=scalable-brain-artifacts  STORAGE_LOCAL_ROOT=model-artifacts
GOOGLE_APPLICATION_CREDENTIALS=…/secrets/system1-rw.json
QUEUE_PROVIDER=local  QUEUE_LOCAL_ROOT=results/state/queue
LAYER3_APPROVAL_THRESHOLD=0.20   # legacy
```

---

## TESTING

```bash
# System 1 — the suite that matters (125+ tests across all 10 modules; ~8 s)
pytest src/system1 -v

# New leakage/gate-teeth tests (FIX-S1-008, currently uncommitted)
pytest src/layer3_ml/tests/ -v

# Layer 0 primitives still in use
pytest src/layer0/tests/ -v

black src/ && mypy src/
```

Notable guard tests: `attribution/tests/test_no_smoothed_leak.py` (causal vs leaked
labels), `validation/tests/test_walk_forward.py` (fold boundaries),
`serializer/tests/test_serialize.py` (checksum-mismatch abort).

---

## CODING CONVENTIONS

- Type hints everywhere (mypy); docstrings on public functions
- Parameterized SQL only; no hardcoded secrets (env via `.env`; keys live in `secrets/`, git-ignored)
- Logging: `%(asctime)s | %(levelname)-8s | %(name)s | %(message)s`, rotating handlers (10 MB × 14)
- SHA256 for artifact integrity; dry-run/log-only defaults on promotion-capable stages
- Pure math separated from I/O for testability; deterministic outputs (byte-identical feature partitions)
- Naming: fact tables `fact_*`, dims `dim_*`; System-1 modules `src/system1/<module>/`;
  legacy folder typo `archieved` retained deliberately

---

## AGENT RULES

### DO

- Treat `src/system1/` as the runtime; read `archieved/SYSTEM1_ANALYSIS_2026-07-01.md` before
  changing regime/attribution/vetting/gatekeeper logic
- Preserve the walk-forward/causal-label discipline (FIX-S1-005): fold-fit models,
  forward-only inference, OOS-only gate metrics
- Keep the orchestrator as the **only** champion promotion path (FIX-S1-009)
- Keep publish ordering: upload → SHA256 verify → only then pointer flip (MODEL-007)
- Use `src/common/db.py`, `src/common/storage`, `src/common/queue` abstractions
- Pair schema/SQL changes with doc updates; keep granularity (H1/H4/D1) explicit
- Check `docs/proposed-fixes/` before "discovering" a bug — it may be known, fixed, or in flight

### DO NOT

- Start, edit, or "fix" `../system-2-execution-engine/` or `../system-3-account-management/`
  from this machine — they are deployed on the user's other computer; local copies are reference
- Re-enable the legacy layer-4 cron or add execution/broker logic to this repo (System 2's job)
- Restore `src/layer3_ml/train_ml_gatekeeper.py` (tombstone is intentional) or add a second
  gatekeeper trainer/publisher
- Recompute downstream concerns here: no sizing, no order routing, no account state
- Commit `.env`, anything in `secrets/`, or model binaries; never log credentials
- Remove compatibility symlinks/dirs (`archieved` typo) blindly
- Assume optional DB columns exist; assume the local `model-artifacts/latest.json` is the
  live pointer (the backend copy is authoritative)

---

## TROUBLESHOOTING

| Symptom | Check |
|---------|-------|
| Orchestrator exits `no_trigger_or_cooldown` | Normal — not Sunday-00UTC window, metrics healthy, or within cooldown |
| Orchestrator "single-flight lock" error | A run is in progress (or stale `results/state/retrain.lock` after a crash) |
| Retrain ran but didn't promote | Deployment gates: `regime_accuracy_ok` (≥0.70), `non_empty_map`, `oos_uplift_ok` (bootstrap-significant, ≥ `MIN_UPLIFT`), `beats_incumbent` — see the `retrain_log_*.json` |
| Publish aborts with checksum mismatch | Working as designed — partial version deleted, pointer untouched; retry |
| DB connection issues | Host PostgreSQL on `:5432` running; `.env` creds; `src/common/db.py` `test_connection()` |
| Reserved-word/case SQL errors | Double-quote `"Open"`/`"Close"`/`"timestamp"`; everything else lowercase |
| GCS publish fails | `GOOGLE_APPLICATION_CREDENTIALS` path valid; bucket `scalable-brain-artifacts` reachable |
| Scored signals "not arriving" downstream | `QUEUE_PROVIDER=local` — they're in `results/state/queue/`, not Pub/Sub (known gap) |

---

## KNOWN GAPS / CURRENT FOCUS (July 2026)

Full plan: **`docs/goals/JULY_2026_GOALS.md`** (per-system goals, weekly milestones).

1. **Commit FIX-S1-008** working-tree changes (orchestrator, serializer,
   `publish_gatekeeper.py`, leakage + gate-teeth tests) — currently the only copy.
2. **Wire Pub/Sub**: `QUEUE_PROVIDER=local` dead-ends scored signals locally; the three
   topics (`Scored_Signal_Queue`, `AMS_Outbound_Queue`, `AMS_Inbound_Queue`) need creating.
3. Findings A–D above (weight starvation is the most actionable).
4. `src/layer0/layer2_config_adapter.py` still emits T-SQL — reconcile or retire.
5. End-to-end practice drill across all three computers; D-004 evidence package
   (go-live is a human decision, targeted August).
6. FinBERT/`fact_macro_events` (MODEL-010) not yet a gate/feature.

---

## DOCUMENTATION MAP

| File | Content |
|------|---------|
| `archieved/SYSTEM1_ANALYSIS_2026-07-01.md` | **Best current deep-dive**: module-by-module, live results, findings A–D, due-diligence Q&A |
| `docs/goals/JULY_2026_GOALS.md` | July 2026 goals, per system, weekly milestones |
| `docs/implementation-roadmap/system-1-model-building/` | MODEL-001…010 task specs |
| `docs/proposed-fixes/system-1/` | FIX-S1-001…009 + verification report |
| `docs/database/SQL_TRANSLATION_RULES.md`, `CODE_MIGRATION_PHASE3.md` | PostgreSQL rules, FND-004 migration record |
| `docs/proposedchanges/SCALABLE_BRAIN_REVIEW_AND_SYSTEM3_DESIGN.md` | System 3 design |
| `../system-2-execution-engine/RUNBOOK.md`, `ARCHITECTURE.md` | System 2 ops + design (reference copy) |
| `../system-3-account-management/docs/` + `tasks/01–20` | System 3 architecture + task specs |
| `docs/design/RESEARCH_STRATEGY_ENGINE.md` | T6 research sandbox: contract, registry, research→staged→qualified pipeline + strategy author's guide |
| `task/2026-W31/deliverables/` | Week 2026-W31 reports, charts and the T7 archive manifest |
| `README.md` | Three-system topology narrative |

---

*If this file conflicts with implementation behavior, implementation wins. Update this
file in the same change set that updates behavior.*
