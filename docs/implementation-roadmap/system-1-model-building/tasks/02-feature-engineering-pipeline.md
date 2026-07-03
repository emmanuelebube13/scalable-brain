# MODEL-002 — Feature Engineering Pipeline

**Task ID:** MODEL-002
**System:** System 1 — Model Building
**Priority:** P1-High
**Estimated Effort:** 3d
**Prerequisites:** MODEL-001
**External Dependencies:**
- **`ForexBrainDB` (PostgreSQL 16 + TimescaleDB, FND-004)** — source of multi-granularity `Fact_Market_Prices`; read via `src/common/db.py`. *(DB = PostgreSQL 16 + TimescaleDB; any historical SQL-Server mention is obsolete.)*
- **`pyarrow`** — Parquet read/write with compression for the feature store.
- **Object storage / shared volume** (FND-001) — persistence target for versioned feature sets (or local scratch initially).
- **MLflow** (experiment tracking) — records feature-set version + lineage.

## Objective
Build a reproducible feature pipeline (returns(1), ATR(14), price_position(20), volatility(20), regime features) persisted as versioned Parquet with schema + lineage.

## Current State
- Indicators are computed ad hoc inside layers: `src/layer0/indicators.py` (ATR/ADX/RSI/Bollinger), Layer 1 derives ATR+ADX features inline in `Fact_market_regime_v2.py`, Layer 2 computes indicators in `signal_engine/indicators/`.
- No shared, versioned **feature store**; features are recomputed per layer with no single schema, no lineage, and no point-in-time guarantee.

## Target State
A single reproducible pipeline that reads multi-granularity prices and emits a **canonical feature table per granularity**, persisted as **versioned, compressed Parquet** (the feature store) with an explicit schema and a lineage record. Downstream tasks (MODEL-003 regime, MODEL-006 gatekeeper) read features from here instead of recomputing. Deterministic: identical inputs → identical features.

## Technical Specification

**Feature definitions (point-in-time, no look-ahead):**
- `returns_1` = log (or simple) return of `"Close"` over 1 bar: `Close_t / Close_{t-1} - 1` (the column is the double-quoted mixed-case `"Close"`).
- `atr_14` = Average True Range over 14 bars (reuse the ATR definition in `src/layer0/indicators.py`).
- `price_position_20` = position of `Close` within the 20-bar high/low channel: `(Close - min(Low,20)) / (max(High,20) - min(Low,20))`, in [0,1].
- `volatility_20` = rolling standard deviation of `returns_1` over 20 bars.
- `regime_features` = the feature vector the HMM/K-Means consumes (e.g., ATR(14), ADX, `volatility_20`, `returns_1`), assembled here so MODEL-003 consumes a stable contract.
- All rolling windows are **trailing-only**; the first `N-1` bars are null/warm-up and excluded from downstream training.

**Storage format:** Parquet, **Snappy compression** (fast, good ratio for analytics; `zstd` acceptable for cold archives). Partitioned by `granularity` and `year` (and optionally `instrument`) for efficient reads. Path convention: `feature-store/{feature_set_version}/granularity={D1|H4|W1}/year=YYYY/part-*.parquet`.

**Versioning & schema evolution:** each build is tagged with `feature_set_version` (semver or content hash). A sidecar `schema.json` per version lists column names, dtypes, window params, and the feature definition formulae. **Schema evolution** is additive — new features bump the minor version; breaking changes (renamed/removed columns) bump major and write to a new path so old consumers are unaffected.

**Lineage:** a `lineage.json` per version records source (`Ingest_Run_Id`s / price date range), code version/git SHA, build timestamp, row counts per granularity, and any nulls/warm-up rows dropped. Logged to MLflow as a dataset/run.

**Data flow (text):** read prices per granularity from `Fact_Market_Prices` → compute trailing features per instrument/granularity → validate schema + DQ → write partitioned Parquet under a new `feature_set_version` → write `schema.json` + `lineage.json` → register in MLflow → (optionally) upload to object storage.

**Determinism:** fixed column order, fixed null handling, no wall-clock-dependent values inside feature columns; re-running on identical inputs yields byte-identical data partitions (timestamps live only in lineage metadata).

## Testing & Validation
- **Unit:** each feature against hand-computed fixtures (returns, ATR(14), price_position(20), volatility(20)); null/warm-up handling for first N-1 bars; bounds (`price_position_20` ∈ [0,1]).
- **Leakage test:** assert no feature at bar t uses data from t+1…; shuffle/future-bar injection test must change only future rows.
- **Determinism test:** build twice → identical Parquet partitions (excluding lineage timestamps).
- **Schema test:** Parquet schema matches `schema.json`; additive evolution does not break a prior-version reader.
- **Edge cases:** instruments with short history, gaps from MODEL-001 quarantine, constant-price windows (avoid divide-by-zero in `price_position_20`).

## Rollback Plan
Feature sets are immutable per version. Roll back by repointing downstream consumers to the previous `feature_set_version`; delete the bad version's Parquet/metadata. No source tables are mutated, so rollback is non-destructive.

## Acceptance Criteria
- [ ] `returns_1`, `atr_14`, `price_position_20`, `volatility_20`, and the assembled regime-feature vector are produced per granularity with documented trailing-window definitions.
- [ ] Output persisted as versioned, compressed Parquet with `schema.json` + `lineage.json` per version.
- [ ] Pipeline is deterministic (double-build produces identical partitions) and passes the look-ahead/leakage test.
- [ ] Feature-set version is registered in MLflow with source lineage.
- [ ] Schema evolution is additive and does not break prior-version consumers.

## Notes & Risks
- Single source of feature truth reduces drift between training (MODEL-003/006) and any reuse, but downstream layers must migrate to read it rather than recompute — coordinate so Layer 2's runtime indicators stay consistent.
- Snappy chosen for read speed; revisit if storage cost dominates.
- Warm-up rows must be excluded consistently from all downstream training to avoid biased early samples.
