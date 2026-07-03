# DONE — data-pipeline-agent — MODEL-001

**Completed:** 2026-06-24T00:21:00Z
**Task:** MODEL-001 — Multi-Timeframe Data Ingestion (extend ingester: +W1, DQ/quarantine, lineage, gap report)
**Audit gate:** AG-001 — **PASS (9/9)**

## What was produced
- **W1 (weekly) granularity** backfilled for all 5 forex majors (EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD): 1,068 weekly bars each (2005-12-30 → 2026-06-12), 5,340 rows total. 0 quarantined, 0 unexpected gaps.
- **Lineage columns** added to `fact_market_prices` (additive, idempotent): `complete`, `source`, `ingest_run_id`, `ingested_at_utc`.
- **`fact_market_prices_quarantine`** table created (DQ failures with reason codes; currently 0 rows).
- **Reports:** `results/reports/ingest_manifest_*.json`, `results/reports/dq_gap_report_*.json`.
- **Resumable cursor:** `results/state/ingest_progress.json`.

## Code (additive / non-breaking)
- New package `src/system1/ingestion/`: `schema.py` (migration), `dq.py` (DQ + gap detection), `reports.py` (manifest/report/cursor), `multi_timeframe_ingest.py` (orchestrator — **reuses** layer-0 OANDA primitives), `tests/test_dq.py` (7 unit tests, all pass).
- Minimal additive edits to `src/layer0/ingest_oanda_prices.py`: W1 interval + chunk size, `--granularity W1` CLI choice, and `to_oanda_granularity()` map (`D1→D`, `W1→W`) at the API boundary — **fixes a latent bug** where `D1`/`W1` were sent verbatim to OANDA (HTTP 400).

## Contracts preserved
- Legacy H1/H4/D1 ingestion path and the Saturday cron untouched (default granularity list unchanged; W1 is opt-in/additive).
- Natural key `(asset_id, granularity, "timestamp")`, idempotent `INSERT … ON CONFLICT DO UPDATE`.
- Connected only via `src/common/db.py`. No secrets serialized.

## Downstream released
MODEL-002 (feature engineering pipeline) is unblocked — D1/H4/W1 prices with lineage are available in `fact_market_prices`.
