# DONE — data-pipeline-agent — MODEL-002

**Completed:** 2026-06-24T01:35:00Z
**Task:** MODEL-002 — Feature Engineering Pipeline (versioned Parquet feature store)
**Audit gate:** AG-002 — **PASS (9/9)**

## What was produced
- **`feature-store/1.0.0/`** — versioned, Snappy-compressed, Hive-partitioned Parquet feature store:
  - `granularity={D1|H4|W1}/year=YYYY/part-0000.parquet` — 65 partitions, rows D1=29,243 · H4=164,563 · W1=5,340
  - `schema.json` — columns/dtypes, window params, formulae, `regime_feature_columns`, partition keys
  - `lineage.json` — source `ingest_run_id`s (3, from MODEL-001 W1 runs), price date ranges, git SHA, row counts, per-feature warm-up null counts, per-partition SHA256
- **MLflow run** registered (experiment `system1-feature-store`, sqlite backend `results/state/mlflow.db`).

## Features (trailing-only, no look-ahead)
`returns_1` (log), `atr_14`, `adx_14`, `price_position_20` ∈ [0,1], `volatility_20`. Regime-feature contract for MODEL-003 = `[atr_14, adx_14, volatility_20, returns_1]`. Reuses `src/layer0/indicators.py` ATR/ADX (causal EWM).

## Code (additive)
- New package `src/system1/features/`: `definitions.py` (feature math + warm-up), `feature_pipeline.py` (deterministic Parquet writer + schema/lineage + MLflow), `tests/test_features.py` (6 tests: returns/bounds/warmup/no-NaN/constant-price/leakage — all pass).

## Key decisions / fixes
- **Determinism**: explicit Arrow schema + stripped pandas metadata + sorted rows → byte-identical partitions across independent builds (verified: 65/65 SHA256 match).
- **`granularity`/`year` are partition keys only** (path), not in-file columns — avoids pyarrow path-vs-file column-type collision on read.
- **MLflow backend**: switched `.env` `MLFLOW_TRACKING_URI` from `file:` (rejected by MLflow 3.x) to `sqlite:///results/state/mlflow.db`.

## Downstream released
MODEL-003 (regime HMM) and MODEL-006 (gatekeeper) can now consume the feature store instead of recomputing indicators.
