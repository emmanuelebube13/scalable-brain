# PROGRESS LEDGER — System 1 (Model Building)

> **Human-readable mirror of `progress_ledger.json`.** The JSON is authoritative for machines;
> this file is the at-a-glance view. **Both must be updated together** by the `ledger-keeper-agent`
> after every state change. If they disagree, trust the JSON and fix this file.

**Last updated:** 2026-06-25T00:05:00Z  ·  **Overall:** `all_required_tasks_done` · **90% complete** (9/10 MODEL tasks)

> ✅ **All required tasks (MODEL-001…009) COMPLETE.** MODEL-006 gatekeeper now done (AG-006 9/9): regime-aware dynamic thresholds + significant OOS uplift (+0.0319, p=0.0001). Only **MODEL-010** (P3 optional FinBERT macro) remains — defer unless requested.
**DB:** PostgreSQL 16 + TimescaleDB (FND-004) — ✅ verified · **Storage:** local default (GCS later) — ✅ ready · **Queue:** local default (broker later) — ✅ ready · **MLflow:** 3.14.0 (file store)

---

## How to read / update this ledger

- **Statuses:** `not_started → in_progress → in_review → rework → done` (plus `blocked`).
- A task is **`done`** only when its spec **Acceptance Criteria** AND its **audit gate (AG-0XX)** are green.
- After any change: append an `events[]` entry in the JSON, update the task snapshot + `next_action`,
  update this table, and regenerate `STAKEHOLDER_UPDATE.docx`.
- **Never "randomly continue."** If unsure where things stand, re-run the last audit gate first.

---

## Task status

| Task | Owner | Pri | Prereqs | Status | Gate | Next action |
|------|-------|-----|---------|--------|------|-------------|
| MODEL-001 Ingestion (+W1/DQ/lineage) | data-pipeline | P0 | FND-004 | ✅ **done** (AG-001 9/9) | AG-001 | W1 backfilled (5 majors × 1068 wk bars); lineage+quarantine live; OANDA D1/W1 code bug fixed |
| MODEL-002 Feature store | data-pipeline | P1 | 001 | ✅ **done** (AG-002 9/9) | AG-002 | `feature-store/1.0.0` (65 parts, deterministic, leakage-free, MLflow) |
| MODEL-003 Regime HMM | ml-regime | P1 | 002 | ✅ **done** (AG-003 12/12) | AG-003 | 4-state HMM on D1/H4/H1 (all HMM); 841,596 regime rows; `hmm_model.joblib` |
| MODEL-004 Attribution | attribution-vetting | P1 | 003 | ✅ **done** (AG-004 7/7) | AG-004 | 80 cells; 66,743 trades tagged point-in-time; shrinkage |
| MODEL-005 Vetting + maps | attribution-vetting | P1 | 004 | ✅ **done** (AG-005 12/12) | AG-005 | Non-empty regime map (3 qualifiers) + weights; Trending-Up starved |
| MODEL-006 Gatekeeper + dyn-threshold | ml-regime | P2 | 003 | ✅ **done** (AG-006 9/9) | AG-006 | XGBoost on 134,520 trades; per-regime dynamic thresholds; OOS uplift +0.0319 (p=0.0001); approval 29.6%; champion triad + SHA256 |
| MODEL-007 Serializer/registry | serializer-infra | P0 | FND-001,003,005 | ✅ **done** (AG-007 9/9) | AG-007 | Bundle + atomic `latest.json` + retention via StorageBackend |
| MODEL-008 Queue producer | queue-nlp | P0 | FND-002 | ✅ **done** (AG-008 9/9) | AG-008 | Producer + QueueBackend/StorageBackend infra; zero Layer-4 imports |
| MODEL-009 Retraining scheduler | serializer-infra | P2 | 007 | ✅ **done** (AG-009 10/10) | AG-009 | Weekly + perf-triggered; gated atomic promote; single-flight lock |
| MODEL-010 FinBERT macro (optional) | queue-nlp | P3 | 006 | not_started | AG-010 | UNBLOCKED; P3 optional — keep only if no OOS-uplift loss vs +0.0319 baseline; needs `fact_macro_events`. Defer unless requested |

**Critical path:** 001 → 002 → 003 → 004 → 005 → 007 → 009  ·  **Parallel:** 006 (after 003) ✅, 008 (early)

---

## Data baseline (fill in Phase 0)

_Recorded 2026-06-23T21:30:00Z — matches expectation (H1/H4/D1 present & current; W1 absent)._

| Granularity | Rows | First bar | Last bar | Notes |
|-------------|------|-----------|----------|-------|
| D1 | 29,243 | 2005-12-31 22:00Z | 2026-04-30 21:00Z | present, **primary** (modeling/regime) |
| H1 | 648,195 | 2006-01-01 16:00Z | 2026-06-23 21:00Z | present (legacy Layer 2/3), current |
| H4 | 164,563 | 2006-01-01 14:00Z | 2026-06-23 17:00Z | present (entry timing), current |
| M15 | 2,553,691 | 2006-01-01 16:45Z | 2026-05-01 20:45Z | present (legacy intraday; not in canonical modeling set) |
| M30 | 1,280,826 | 2006-01-01 16:30Z | 2026-05-01 20:30Z | present (legacy intraday; not in canonical modeling set) |
| W1 | 5,340 | 2005-12-30 22:00Z | 2026-06-12 21:00Z | ✅ **added by MODEL-001** (1,068 wk bars × 5 majors; macro context) |

---

## Open rework directives
_None._  (Auditor writes them to `results/state/rework/{agent}_{ts}.md`; list them here when open.)

## Blocked agents
_None._  (Auditor writes `results/state/blocked/{agent}.md`; list them here when active.)

## Background jobs
_None running._  (Long jobs — W1 backfill, HMM EM, XGB/LGBM tournaments, FinBERT batch, OOS walk-forward —
are launched detached; record handle/log/ETA in the JSON `background_jobs[]` and mirror here.)

---

## Event log (most recent first)
- **2026-06-25T00:05:00Z** — `ml-regime-agent` — **MODEL-006 DONE · AG-006 9/9 · ALL REQUIRED TASKS COMPLETE.**
  Resumed prior session's gatekeeper; artifacts were **stale** vs committed `train.py` (manifest
  `n_folds=3` vs code `N_FOLDS=5`). Trust-but-verify: re-ran upstream **AG-003** on live DB → still
  green (all HMM, 4 states populated, `prob_*`=1.0 every row, argmax==`regime_raw` 0 violations,
  D1/H4/H1 present). Re-ran `python -m src.system1.gatekeeper.train` (detached, ~7min) so committed
  code reproduces artifacts. XGBoost on **134,520** backtest trades (win 0.384), point-in-time regime
  join (`merge_asof` backward, **0/134,520** look-ahead). Regime-aware dynamic thresholds
  (HV 0.55 / Rng 0.60 / TrDn 0.45 / TrUp 0.50 / fallback 0.60) within turnover band [0.05, 0.60].
  5-fold walk-forward **OOS uplift = +0.031902, p = 0.0001** (20k bootstrap), significant; OOS
  approval 29.6% → promotion gate passes. Champion triad + SHA256 + legacy fallback preserved.
  MLflow run `8d63aa5b…`. **Next:** MODEL-010 (P3 optional) or stop.
- **2026-06-24T04:45:00Z** — `serializer-infra-agent` — **MODEL-009 DONE · AG-009 10/10 · CRITICAL PATH
  COMPLETE.** Retrain scheduler: weekly (Sun 00:00 UTC) + perf triggers (14d Sharpe<0.3, regime
  acc<70%, circuit-breaker) + cooldown + single-flight lock + deployment gates (must beat incumbent)
  + gated atomic promote via MODEL-007 + lineage/MLflow. `shell/cron_system1_retrain.sh`. 8 tests.
- **2026-06-24T04:30:00Z** — `serializer-infra-agent` — **MODEL-007 DONE · AG-007 9/9.** Bundle
  (hmm_model.joblib + weights + map + metadata + checksums) → immutable `model-artifacts/{version}/`
  via StorageBackend; atomic `latest.json` after SHA256 round-trip; retention 5; refuses
  missing/mismatch/empty-map/secrets.
- **2026-06-24T04:15:00Z** — `attribution-vetting-agent` — **MODEL-005 DONE · AG-005 12/12.** Strict
  per-regime gates → non-empty `regime_strategy_map.json` (3 qualifiers; Trending-Up starved) +
  `strategy_weights.json`. Re-ran trades at 10y (134,520) to clear OOS≥60mo. 6 tests.
- **2026-06-24T04:05:00Z** — `data+attribution-vetting-agent` — **Trade-data RESOLVED + MODEL-004 DONE ·
  AG-004 PASS 7/7.** Built `src/layer0/persist_trade_outcomes.py` (reuses Layer 0 backtest engine) →
  **66,743 trades** in `fact_trade_outcomes` + `dim_strategy`/`dim_strategy_registry` seeded (fixed FK:
  outcomes→`dim_strategy_registry`). MODEL-004: `src/system1/attribution/` (6 tests) — point-in-time
  regime tag (`merge_asof` bar≤entry), **80 cells** (strategy×regime×granularity), win/PF/Sharpe +
  Bayesian shrinkage (N_min=20) + low-confidence; `fact_strategy_regime_attribution` + parquet +
  report + MLflow. 0 UNKNOWN regime; reconciliation OK. **Next:** MODEL-005.
- **2026-06-24T03:45:00Z** — `orchestrator+queue-nlp-agent` — **MODEL-008 DONE · AG-008 PASS 9/9 + BLOCKER.**
  Built pluggable infra `src/common/queue/` (QueueBackend + LocalDurableBackend: durable JSONL,
  idempotency, bounded depth+backpressure, DLQ, fsync confirm) and `src/common/storage/`
  (StorageBackend + LocalFSBackend: immutable versions, atomic pointer, sha256 round-trip + GCS
  stub) = FND-002/FND-001 satisfied locally. MODEL-008 producer (`src/system1/queue_producer/`):
  schema-validated messages, deterministic idempotency keys, never-drop backpressure, DLQ, confirms,
  metrics; **zero Layer-4 imports** (decoupling verified). 7 tests pass.
  ⛔ **BLOCKER:** trade-data tables empty → MODEL-004/005/006/007/009 paused (need Layer 0→2). Built
  unblocked work per user decision and paused.
- **2026-06-24T03:02:00Z** — `ml-regime-agent` — **MODEL-003 DONE · AG-003 PASS 12/12.** 4-state
  Gaussian HMM (Trending-Up/Down, Ranging, High-Vol) on D1/H4/H1 — all HMM (converged); K-Means
  fallback retained + proven. Wrote `fact_market_regime_v2` additive cols (regime_model/raw/smoothed,
  prob_*, model_version) for 841,596 rows; serialized `models/hmm_model.joblib` (reproduces DB
  exactly); MLflow logged. HMM input adds derived point-in-time `trend_20` (weighted) so it learns
  **direction**. `regime_raw`=argmax(posterior); 3-bar causal smoothing (no <3-bar segments). Stability
  acc D1=0.886/H4=0.970/H1=0.860; flicker smoothed<raw<KMeans. **Next:** MODEL-004 + MODEL-006 (parallel).
- **2026-06-24T01:35:00Z** — `data-pipeline-agent` — **MODEL-002 DONE · AG-002 PASS 9/9.** Built
  versioned Parquet feature store `feature-store/1.0.0` (65 Hive partitions D1/H4/W1×year; rows
  29,243 / 164,563 / 5,340; Snappy) + `schema.json` + `lineage.json` + MLflow run. Trailing-only,
  leakage-free features (`returns_1`, `atr_14`, `adx_14`, `price_position_20`∈[0,1], `volatility_20`).
  **Determinism proven** — independent rebuild → 65/65 partitions byte-identical (SHA256). New
  `src/system1/features/` (6 passing tests) reusing layer-0 ATR/ADX. MLflow moved `file:`→`sqlite`
  (MLflow 3.x rejects file store). **Next:** MODEL-003.
- **2026-06-24T00:21:00Z** — `data-pipeline-agent` — **MODEL-001 DONE · AG-001 PASS 9/9.** Added **W1**
  granularity: backfilled 5 forex majors (1,068 weekly bars each, 2005-12-30→2026-06-12; 5,340 rows,
  0 quarantined, 100% coverage). Additive lineage cols + `fact_market_prices_quarantine` (idempotent
  migration). New `src/system1/ingestion/` package (schema/dq/reports/orchestrator + 7 passing unit
  tests) reusing layer-0 OANDA primitives. **Fixed latent bug:** `D1`/`W1` codes were sent verbatim to
  OANDA (HTTP 400) → added `to_oanda_granularity()` map (`D1→D`, `W1→W`), repairing the broken daily
  path. Idempotency + resumability proven. Legacy H1/H4/D1 + Saturday cron untouched. **Next:** MODEL-002.
- **2026-06-23T21:30:00Z** — `orchestrator` — **Phase 0 bootstrap COMPLETE.** DB connectivity
  verified via `src/common/db.py`; OANDA practice creds present; venv confirmed; Storage/Queue
  resolved to local defaults with roots created; `.env` pinned (`STORAGE_PROVIDER=local`,
  `QUEUE_PROVIDER=local`, `MLFLOW_TRACKING_URI=file:results/state/mlruns`). Installed
  `hmmlearn==0.3.3` + `mlflow==3.14.0` (`requirements.txt` pinned); mlflow downgraded
  pandas 3.0.2→2.3.3 & protobuf 7→6 — **verified non-breaking** via import smoke test
  (`src.common.db`, `layer1_regime`, `layer3_ml`, full ML stack all OK). Data baseline recorded
  (see table). **Next:** start MODEL-001 (data-pipeline-agent).
- **2026-06-23T00:00:00Z** — `bootstrap` — scaffolding created; SQL-Server references scrubbed
  (System-1 docs + `AGENTS.md` + `ingest_oanda_prices.py`); `requirements.txt` gains `python-docx`.
  No MODEL task started. **Next:** orchestrator runs Phase 0.
