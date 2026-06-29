"""MODEL-001 — Multi-timeframe data ingestion extensions.

Adds, on top of the proven ``src/layer0/ingest_oanda_prices.py`` engine:
  * W1 (weekly) granularity for macro context (D1/H4 already supported),
  * lineage columns on ``fact_market_prices`` (source / ingest_run_id / ingested_at_utc / complete),
  * a ``fact_market_prices_quarantine`` table for rows failing data-quality checks,
  * per-batch data-quality checks + FX-calendar-aware gap detection,
  * per-run ingest manifest + DQ/gap report + resumable cursor state.

These modules REUSE the layer-0 primitives (OANDA client, paged fetch with backoff,
RFC3339 parsing) rather than reimplementing them.
"""
