"""MODEL-002 — Feature engineering pipeline (versioned Parquet feature store).

Reads multi-granularity prices from ``fact_market_prices`` and emits a canonical,
point-in-time (trailing-only) feature table per granularity, persisted as versioned,
Snappy-compressed Parquet with ``schema.json`` + ``lineage.json`` and an MLflow run.

Downstream (MODEL-003 regime, MODEL-006 gatekeeper) reads features from here instead
of recomputing them.
"""
