# System 1 — Audit Log

### AG-009 — Retraining Scheduler Integrity — **PASS**
- **Target:** serializer-infra-agent / MODEL-009 · **Run:** 2026-06-24T04:45Z · **10/10**
- scheduled Sun-00-UTC ✓ · perf triggers independent ✓ · cooldown ✓ · single-flight lock ✓ · degraded not promoted ✓ · passing promoted atomically (MODEL-007) ✓ · interrupted→incumbent unchanged ✓ · missing-metrics fail-safe ✓ · run lineage logged ✓ · MLflow lineage ✓

### AG-007 — Bundle Integrity & Atomic Publication — **PASS**
- **Target:** serializer-infra-agent / MODEL-007 · **Run:** 2026-06-24T04:30Z · **9/9**
- round-trip SHA256 ✓ · atomic pointer unchanged on interrupted upload ✓ · all artifacts present ✓ · metadata==checksums ✓ · encryption (local N/A, skipped-with-note) ✓ · TLS (local N/A) ✓ · no secrets ✓ · retention keeps 5 ✓ · empty-map blocks promotion ✓

### AG-005 — Vetting Gate Correctness — **PASS**
- **Target:** attribution-vetting-agent / MODEL-005 · **Run:** 2026-06-24T04:15Z · **12/12**
- boundary accept/reject (6 gates) ✓ · low-conf rejected ✓ · map+weights schemas ✓ · weights sum=1 ✓ · dense ranks ✓ · rank-1=max composite ✓ · empty regimes listed ✓ · rejection_summary matches ✓ · OOS≥60 ✓ · legacy vetting untouched ✓ · lineage ✓

### AG-004 — Per-Regime Attribution — **PASS**
- **Target:** attribution-vetting-agent / MODEL-004 · **Run at:** 2026-06-24T04:05Z · **Result:** 7/7
- 66,743 trades (real, from `persist_trade_outcomes.py`) tagged point-in-time to regime; 80 cells.
- Checks: reconciliation (20 groups) ✓ · no future regime (0/66,743) ✓ · low_confidence iff <20 trades ✓ · no zero-trade cells ✓ · shrunk∈[cell,global] ✓ · none dropped ✓ · lineage ✓

### AG-008 — Queue Message Contract & Decoupling — **PASS**
- **Target:** queue-nlp-agent / MODEL-008 (scored-signal queue producer, local QueueBackend)
- **Run at:** 2026-06-24T03:45Z · **Result:** 9/9 checks passed
- Checks: 100-msg schema-valid ✓ · idempotent re-publish→1 ✓ · backpressure caps depth≤max (no drop) ✓ · DLQ routing+reason+metric ✓ · **decoupling: 0 Layer-4 imports in src/system1 + src/layer3_ml** ✓ · H1/H4 preserved ✓ · message_id deterministic ✓ · publisher confirm (fsync, not fire-and-forget) ✓ · metrics logged ✓
- **Note:** runs against `LocalDurableBackend` (broker attaches by config). Built `src/common/queue/` + `src/common/storage/` (FND-002/FND-001). Producer is source-agnostic; live DB feed activates once MODEL-006 scores exist.

### AG-003 — HMM Quality & Probabilities — **PASS**
- **Target:** ml-regime-agent / MODEL-003 (4-state Gaussian HMM, K-Means fallback retained)
- **Run at:** 2026-06-24T03:02Z · **Result:** 12/12 checks passed
- Models: D1/H4/H1 all HMM (converged); rows 29,108 / 164,428 / 648,060; `models/hmm_model.joblib`.
- Checks: reproducibility ✓ · 4 states>1% ✓ · converged ✓ · non-degenerate cov ✓ · prob sum=1 (0 bad/841,596) ✓ · argmax==raw (0 mismatch) ✓ · no <3-bar segments ✓ · flicker sm 0.0158<raw 0.0161<kmeans 0.1755 ✓ · stability acc D1=0.886/H4=0.970/H1=0.860 ✓ · fallback→KMeans ✓ · joblib round-trip exact ✓ · D1/H4/H1 present ✓
- **Note:** accuracy = out-of-sample regime stability (no human-labeled ground truth exists). `regime_raw`=argmax(posterior); 3-bar causal smoothing.

### AG-002 — Feature Determinism & Schema — **PASS**
- **Target:** data-pipeline-agent / MODEL-002 (versioned Parquet feature store `feature-store/1.0.0/`)
- **Run at:** 2026-06-24T01:35Z · **Result:** 9/9 checks passed

| # | Check | Result | Detail |
|---|-------|--------|--------|
| 1 | Determinism (byte-identical partitions, SHA256) | PASS | 65/65 partitions identical across 2 independent builds |
| 2 | `schema.json` matches Parquet schema | PASS | column sets equal |
| 3 | `lineage.json` rows == Parquet rows | PASS | D1=29,243 H4=164,563 W1=5,340 |
| 4 | `price_position_20` ∈ [0,1] (100% non-null) | PASS | 0 violations |
| 5 | No look-ahead leakage | PASS | future-shock test: only ≥shock rows change |
| 6 | Warm-up rows null (first N-1) | PASS | atr_14 first 13 null per instrument |
| 7 | No NaN in `returns_1` beyond first-bar warmup | PASS | 0 instruments with extra NaN |
| 8 | `regime_feature_columns` present | PASS | [atr_14, adx_14, volatility_20, returns_1] |
| 9 | Registered in MLflow | PASS | experiment `system1-feature-store` (sqlite) |

**Notes:** `granularity`/`year` are partition keys (path) not in-file columns. MLflow switched to sqlite backend (`file:` store rejected by MLflow 3.x).

### AG-001 — Ingestion Data Quality — **PASS**
- **Target:** data-pipeline-agent / MODEL-001 (multi-timeframe ingestion: +W1, DQ/quarantine, lineage, gap report)
- **Run at:** 2026-06-24T00:21Z
- **Result:** 9/9 checks passed
- **Artifacts:** `fact_market_prices` (+W1, +lineage cols), `fact_market_prices_quarantine`, `results/reports/ingest_manifest_*.json`, `results/reports/dq_gap_report_*.json`, `results/state/ingest_progress.json`

| # | Check | Result | Detail |
|---|-------|--------|--------|
| 1 | Idempotency (double-run row count unchanged) | PASS | W1 total = 5,340; re-run did 0 inserts/0 updates |
| 2 | DQ/gap report exists | PASS | `results/reports/dq_gap_report_*.json` present |
| 3 | Quarantine rate < 5% | PASS | 0 quarantined / 5,340 = 0.00% |
| 4 | No incomplete candles (`complete=false`) | PASS | count = 0 |
| 5 | Ingest manifest has required fields | PASS | all required keys present |
| 6 | Resumable cursor (kill→restart = same count) | PASS | deleted 60 W1 bars → restart re-fetched 60 → 1,068 |
| 7 | Coverage ≥ 99.5% (W1, ex-weekends/holidays) | PASS | max missing ratio 0.0 → 100% |
| 8 | `ingest_run_id` on every new row | PASS | 0 W1 rows missing run_id |
| 9 | Per-instrument earliest-date exceptions documented | PASS | `history_start_override` recorded per series (all reach 2005) |

**Notes:**
- W1 backfilled for all 5 forex majors (EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD): 1,068 weekly bars each, 2005-12-30 → 2026-06-12.
- **Latent bug fixed:** legacy `D1`/`W1` codes were sent verbatim to OANDA which rejects them (400). Added `to_oanda_granularity()` map (`D1→D`, `W1→W`) at the API boundary in `src/layer0/ingest_oanda_prices.py` — fixes the previously-broken daily path and enables weekly.
- Legacy H1/H4/D1 ingestion path and the Saturday cron remain unchanged (W1 additive; default granularity list untouched).
