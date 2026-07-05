# Data Pipeline Agent

**Agent ID:** `data-pipeline-agent`
**File:** `docs/implementation-roadmap/system-1-model-building/tasks/agents/data-pipeline-agent.md`
**Role:** Multi-timeframe data ingestion and reproducible feature engineering.

---

## Assigned Tasks

| Task | Description | Priority | Est. Days | Prerequisites |
|------|-------------|----------|-----------|---------------|
| [MODEL-001](../01-multi-timeframe-data-ingestion.md) | Multi-Timeframe Data Ingestion | P0 | 4d | FND-004 |
| [MODEL-002](../02-feature-engineering-pipeline.md) | Feature Engineering Pipeline | P1 | 3d | MODEL-001 |

---

## Skills

Before starting, load these skill files:

- `skills/postgres-patterns.md` — DB connection via `src/common/db.py`, `INSERT … ON CONFLICT`, reserved words
- `skills/oanda-ingestion.md` — OANDA v20 API, paging, rate limits, granularity codes
- `skills/point-in-time-leakage.md` — No-look-ahead feature computation, trailing windows

---

## Communication With Other Agents

### Upstream (who this agent depends on)
- **None directly** — this is the entry point. Depends on:
  - FND-004: PostgreSQL 16 + TimescaleDB at `localhost:5432`, database `ForexBrainDB`, role `sa`
  - OANDA v20 practice API (`OANDA_API_KEY`, `OANDA_URL` from `.env`)
  - `pyarrow` package (verify in `requirements.txt`)

### Downstream (who depends on this agent's output)

| Consumer Agent | Consumes | Contract |
|----------------|----------|----------|
| `ml-regime-agent` | `Fact_Market_Prices` (D1/H4/W1) + `feature-store/{version}/` Parquet | `schema.json`, `lineage.json` |
| `attribution-vetting-agent` | `Fact_Market_Prices` (price data for backtests) | DB schema |
| `auditor-traceback-agent` | `results/state/ingest_progress.json`, DQ/Gap reports | Manifest schema |

---

## Input Contracts

### OANDA API
```
GET /v3/instruments/{instrument}/candles
  granularity: D | H4 | W
  count: 500
  from: ISO8601
  to: ISO8601 (optional)
```
- Only candles with `complete=true` are ingested.
- Apply exponential backoff on HTTP 429/5xx (base 1s, max 60s, jitter ±25%).
- Returned candles are ordered ascending by time.

### Database
- Connect via `src/common/db.py` `get_engine()` — never build a connection string or `create_engine` inline.
- `Fact_Market_Prices` is a TimescaleDB hypertable.
- Natural key: `(asset_id, granularity, bar_time_utc)`.
- Mixed-case reserved columns: `"Open"`, `"High"`, `"Low"`, `"Close"` (double-quoted).

---

## Output Contracts

### MODEL-001 Outputs

1. **`Fact_Market_Prices` rows** — D1, H4, W1 granularities, 2005-01-01 → present.
   - Columns: `asset_id`, `granularity`, `bar_time_utc`, `"Open"`, `"High"`, `"Low"`, `"Close"`, `volume`, `complete`, `source`, `ingest_run_id`, `ingested_at_utc`
   - Idempotent: re-running produces zero duplicate bars.

2. **`Fact_Market_Prices_Quarantine`** — Rows failing DQ checks.
   - Columns: same as above + `quarantine_reason_code`, `quarantined_at_utc`

3. **`results/state/ingest_progress.json`** — Resumable cursors.
   ```json
   {
     "instruments": {
       "EUR_USD": {
         "D1": {"last_bar_utc": "2026-06-22T21:00:00Z", "backsfill_complete": true},
         "H4": {"last_bar_utc": "2026-06-22T20:00:00Z", "backsfill_complete": true},
         "W1": {"last_bar_utc": "2026-06-15T00:00:00Z", "backsfill_complete": true}
       }
     }
   }
   ```

4. **`results/reports/ingest_manifest_{timestamp}.json`** — Per-run lineage.
   ```json
   {
     "ingest_run_id": "uuid",
     "instruments": ["EUR_USD", "..."],
     "granularities": ["D1", "H4", "W1"],
     "date_range": {"from": "2005-01-01", "to": "2026-06-22"},
     "rows_inserted": 12345,
     "rows_updated": 0,
     "rows_quarantined": 3,
     "start_cursor": {...},
     "end_cursor": {...}
   }
   ```

5. **`results/reports/dq_gap_report_{timestamp}.json`** — Per-run DQ/gap report.
   - Lists quarantine reason codes and counts, expected-bar gaps (weekend/holiday gaps logged as INFO, not errors).

### MODEL-002 Outputs

1. **Feature Store Parquet** — `feature-store/{feature_set_version}/`
   ```
   feature-store/1.0.0/
   ├── schema.json
   ├── lineage.json
   ├── granularity=D1/year=2026/part-0000.parquet
   ├── granularity=H4/year=2026/part-0000.parquet
   └── granularity=W1/year=2026/part-0000.parquet
   ```
   - Compression: Snappy.
   - Partitioned by granularity and year.
   - Columns per row: `asset_id`, `bar_time_utc`, `returns_1`, `atr_14`, `price_position_20`, `volatility_20`, `regime_feature_vector` (ATR14+ADX+volatility20+returns1)

2. **`feature-store/{version}/schema.json`** — Column names, dtypes, window params, formulae.

3. **`feature-store/{version}/lineage.json`** — Source `Ingest_Run_Id`s, price date range, code git SHA, build timestamp, row counts.

---

## Verification Gates (Self-Check Before Handoff)

### MODEL-001 Gates
- [ ] Double-run row count equality: run ingestion twice → identical `SELECT count(*) FROM Fact_Market_Prices WHERE ingest_run_id IN (run1, run2)`.
- [ ] No incomplete candles: `SELECT count(*) WHERE complete = false` → 0.
- [ ] DQ report emitted with at least OHLC sanity, monotonic, and duplicate checks.
- [ ] Resumable: kill at 50% progress, restart → completes without data loss. Row count = single-run count.
- [ ] Every row carries `ingest_run_id` lineage.
- [ ] Missing-expected-bar ratio < 0.5% (excluding weekends/holidays).

### MODEL-002 Gates
- [ ] Determinism: build twice → byte-identical Parquet partitions (`sha256sum` match).
- [ ] Look-ahead/leakage: inject future bar → only future rows change in feature output.
- [ ] `price_position_20` ∈ [0,1] for all non-null rows.
- [ ] First N-1 bars per instrument are null (warm-up, excluded from training).
- [ ] Parquet schema matches `schema.json` column-for-column.
- [ ] No divide-by-zero: constant-price windows handled without NaN in `price_position_20`.

---

## Failure Modes & Escalation

| Failure | Detection | Action | Escalate To |
|---------|-----------|--------|-------------|
| OANDA rate-limited (429) | HTTP response | Exponential backoff, checkpoint cursor, resume | Self (retry loop) |
| OANDA persistent 5xx | HTTP response after max retries | Log, pause ingestion for this instrument, raise alert | `auditor-traceback-agent` |
| DQ check failure (batch) | DQ predicate returns > 0 quarantined rows | Quarantine rows, log reason codes, continue next batch | Self (non-blocking) |
| DQ failure rate > 5% | Aggregate DQ report | Pause ingestion, investigate source data quality | `auditor-traceback-agent` (rework may be needed) |
| Parquet write failure | IOError | Retry with backoff, fail task if persistent | `auditor-traceback-agent` |
| Schema mismatch (feature store) | Column count/type assertion | Reject batch, log mismatch details | Self (fix code) |
| Constant-price window (edge case) | price_position_20 = NaN | Document, handle with default or exclude | Self (handled in code) |

---

## Notes

- Preserve legacy H1/H4 ingestion contract during MODEL-001 — D1/W1 are additive. Do not remove or alter the existing Saturday cron ingestion until all downstream tasks have migrated to D1/H4/W1.
- OANDA practice history depth varies by instrument (some may not reach 2005). Document per-instrument earliest available date in the ingest manifest.
- Feature store Snappy compression is chosen for read speed over zstd. Revisit if storage cost dominates later.
- Warm-up rows (first N-1 bars) must be null in the feature store and excluded by all downstream training — do NOT zero-fill them.
