# System 1 — Model Building ("The Brain")

## Overview

System 1 is the offline **intelligence factory** of the Scalable Brain platform. It runs on **Computer 1 (training cluster)** and is responsible for transforming raw market history and macro intelligence into validated, versioned, deployable decision artifacts. It comprises the current **Layers 0–3 plus the FinBERT NLP** auxiliary, reorganized into a self-contained training system.

System 1 does **not** place trades and does **not** talk to the broker for execution. Its only outputs are:

1. A **model artifact bundle** (`hmm_model.joblib`, `strategy_weights.json`, `regime_strategy_map.json`, `model_metadata.json`, `latest.json`) published to object storage with SHA256 checksums, pulled by **Computer 2 (System 2 — Execution Engine)**.
2. **Scored signals** published to the `Scored_Signal_Queue`, consumed by **System 3 — Account Management**.

This decoupling replaces today's direct, in-process coupling of Layer 3 → Layer 4.

### Pipeline at a glance

```
OANDA v20 (D1/H4/W1)  ──▶  MODEL-001 Multi-TF Ingestion  ──▶  Fact_Market_Prices (multi-granularity)
                                                                      │
                                                                      ▼
                                              MODEL-002 Feature Pipeline ──▶ Versioned Parquet feature store
                                                                      │
                                            ┌─────────────────────────┼───────────────────────────┐
                                            ▼                         ▼                             ▼
                                MODEL-003 HMM Regime Engine   MODEL-004 Per-Regime         MODEL-010 FinBERT
                                (4-state + K-Means fallback)  Strategy Attribution          Macro Features
                                            │                         │                             │
                                            ▼                         ▼                             │
                                MODEL-006 ML Gatekeeper        MODEL-005 Vetting Gate +              │
                                (+regime features,            regime_strategy_map.json +            │
                                 dynamic threshold) ◀─────────  strategy_weights.json               │
                                            │                         │                             │
                                            └──────────┬──────────────┘◀────────────────────────────┘
                                                       ▼
                                       MODEL-007 Model Serializer / Artifact Registry
                                                       │                       │
                                                       ▼                       ▼
                                       Object Storage (FND-001)        MODEL-008 Scored_Signal_Queue
                                       → Computer 2 pulls bundle       Producer → System 3 consumes
                                                       ▲
                                       MODEL-009 Retraining Scheduler (weekly + perf-triggered)
```

## Goals

- **G1 — Multi-timeframe, deep-history data foundation.** Ingest D1 (primary), H4 (entry), W1 (context) from OANDA with backfill to 2005, idempotently, with data-quality gates.
- **G2 — Reproducible, versioned features.** A feature pipeline persisted as versioned Parquet with explicit schema and lineage, suitable as a feature store.
- **G3 — Probabilistic regime detection.** Replace hard K-Means labels with a 4-state Gaussian HMM (Trending-Up, Trending-Down, Ranging, High-Vol) with state probabilities and persistence smoothing (min 3 bars), keeping K-Means as fallback.
- **G4 — Regime-aware strategy economics.** Per-regime attribution so each strategy's win-rate / PF / Sharpe is known per regime, feeding a stricter vetting gate and a regime→ranked-strategy map.
- **G5 — Smarter gatekeeping.** Regime-probability features and dynamic, regime-aware thresholds in the Layer 3 gatekeeper, validated by OOS uplift analysis.
- **G6 — Clean, auditable handoff.** Versioned, checksummed artifact bundles in object storage and a backpressure-aware scored-signal queue, fully decoupling training from execution.
- **G7 — Continuous learning.** Scheduled weekly retraining plus performance-triggered retraining with deployment gates.

## Success Criteria

| # | Criterion | Measurement |
|---|-----------|-------------|
| SC1 | Multi-timeframe history available from 2005→present for all configured instruments | Row counts per instrument/granularity; gap report < 0.5% missing expected bars |
| SC2 | Feature pipeline is deterministic and versioned | Re-running on identical inputs produces byte-identical Parquet (excluding timestamps); every feature set has a schema + lineage record |
| SC3 | HMM regime model validated and outperforms K-Means baseline | Log-likelihood convergence, regime persistence ≥ 3 bars, regime classification accuracy ≥ 70% on labeled holdout; K-Means fallback path proven |
| SC4 | Vetting gate enforces PF≥1.5, Sharpe≥0.8, MaxDD≤25%, WinRate≥40%, Recovery≥3.0, OOS≥60 months | Vetting report rejects strategies failing any gate; emitted map only contains passing strategies |
| SC5 | Gatekeeper shows positive OOS uplift | Approved-vs-rejected P&L differential statistically significant (p<0.05) on walk-forward folds |
| SC6 | Artifact bundle round-trips to object storage with verified checksums; Computer 2 can pull `latest.json` | Upload + re-download + SHA256 match; `latest.json` resolves to newest valid version |
| SC7 | Scored signals flow to queue with backpressure handling; no direct Layer 4 call remains | Queue depth bounded by max-queue-size; producer applies backpressure; integration test confirms no Layer 4 import |
| SC8 | Retraining runs on schedule and on triggers without manual intervention | Scheduler logs Sunday 00:00 UTC runs; trigger fires on rolling-14d Sharpe<0.3 / regime accuracy<70% / circuit-breaker |

## Scope Boundaries

- **In scope:** Layers 0–3, FinBERT NLP, multi-TF ingestion, feature store, HMM regime engine, vetting + maps, model serializer, scored-signal producer, retraining scheduler.
- **Out of scope (other systems):** Live execution / Layer 4 (System 2), broker order placement / Layer 7 (System 2), account/risk management and queue consumption (System 3), telemetry dashboard / Layer 5, post-trade auditor / Layer 6.
- **Preserved contracts:** Granularity labels (H1/H4 still flow where signals are produced; D1/H4/W1 added for ingestion/features), `Fact_Signals` schema, artifact-based handoff, deterministic decisioning.

## Cross-System Dependencies (Foundational)

| ID | What | Used by |
|----|------|---------|
| FND-001 | Object storage (artifact registry, encryption at rest) | MODEL-007 |
| FND-002 | Message queue infrastructure (`Scored_Signal_Queue`) | MODEL-008 |
| FND-004 | Database provisioning (`ForexBrainDB`, multi-granularity prices) | MODEL-001 |
| FND-007 | CI / automated test harness + experiment tracking baseline | All MODEL tasks (gates) |

## Task Index

| Task | Priority | Effort | Prereqs |
|------|----------|--------|---------|
| MODEL-001 Multi-timeframe data ingestion | P0-Critical | 4d | FND-004 |
| MODEL-002 Feature engineering pipeline | P1-High | 3d | MODEL-001 |
| MODEL-003 Regime engine HMM upgrade | P1-High | 5d | MODEL-002 |
| MODEL-004 Per-regime strategy attribution | P1-High | 3d | MODEL-003 |
| MODEL-005 Strategy vetting + regime map | P1-High | 3d | MODEL-004 |
| MODEL-006 ML gatekeeper regime features + dynamic threshold | P2-Medium | 4d | MODEL-003 |
| MODEL-007 Model serializer + artifact registry | P0-Critical | 3d | FND-001, MODEL-003, MODEL-005 |
| MODEL-008 Scored signal queue producer | P0-Critical | 2d | FND-002 |
| MODEL-009 Retraining scheduler | P2-Medium | 3d | MODEL-007 |
| MODEL-010 FinBERT macro feature integration | P3-Low | 3d | MODEL-006 |

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| OANDA practice API rate limits / gaps stall the 2005 backfill | High | High | Chunk requests at 500 candles, exponential backoff, resumable checkpoints, nightly gap-fill job, accept documented FX-market-closure gaps |
| Deep-history data quality issues (splits in CFDs, weekend bars, duplicate candles) corrupt features | Medium | High | Idempotent upserts, DQ checks (monotonic time, OHLC sanity, dup detection), quarantine table, lineage so bad batches can be reverted |
| HMM fails to converge or produces unstable/flickering regimes | Medium | High | Persistence smoothing (min 3 bars), fixed random seed + multiple inits, convergence/log-likelihood gates, automatic K-Means fallback retained |
| Per-regime attribution suffers small-sample bias (few trades per regime) | High | Medium | Minimum-sample thresholds per regime, Bayesian shrinkage to global stats, flag low-confidence cells, never promote on a regime with < N trades |
| Stricter vetting gate rejects nearly all strategies, starving the queue | Medium | High | Calibrate gates on historical data first, staged rollout (log-only mode), expose per-gate rejection reasons, allow temporary relaxation with audit trail |
| Artifact bundle/version drift between Computer 1 and Computer 2 | Medium | Critical | SHA256 checksums, `latest.json` pointer, immutable timestamped versions, schema/version field in `model_metadata.json`, Computer 2 validates before load |
| Queue backpressure / unbounded growth if System 3 lags | Medium | High | Max-queue-size with backpressure, dead-letter handling, monitoring/alerts on depth, idempotent message keys |
| Look-ahead bias / data leakage in features or labels | Medium | Critical | Strict point-in-time feature construction, walk-forward + OOS≥60mo validation, leakage unit tests, no future bars in rolling windows |
| Solo part-time bandwidth slips the schedule | High | Medium | Incremental tasks each leaving a working system, AI-agent assistance, P0/P1 sequencing, clear acceptance criteria per task |
| Secrets (OANDA key, object-storage creds) leaked in artifacts or logs | Low | Critical | Env-var-only secrets, encryption in transit/at rest, artifact scanning, never serialize credentials into metadata |
| Retraining produces a worse champion that auto-deploys | Medium | High | Deployment gates (must beat or match incumbent on OOS), shadow/canary before `latest.json` promotion, one-click rollback to previous version |
