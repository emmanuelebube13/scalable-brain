# MODEL-001 — Multi-Timeframe Data Ingestion

**Task ID:** MODEL-001
**System:** System 1 — Model Building
**Priority:** P0-Critical
**Estimated Effort:** 4d
**Prerequisites:** FND-004
**External Dependencies:**
- **OANDA v20 practice API** (`oandapyV20`, `OANDA_API_KEY`, `OANDA_URL=https://api-fxpractice.oanda.com`) — the source of D1/H4/W1 candle history; only task that calls OANDA.
- **`ForexBrainDB` (PostgreSQL 16 + TimescaleDB, FND-004)** — destination for multi-granularity prices; must accept the granularity extension to `Fact_Market_Prices`. Connect via `src/common/db.py`. *(DB = PostgreSQL 16 + TimescaleDB; any historical SQL-Server mention is obsolete.)*

## Objective
Build a multi-timeframe OANDA ingestion engine (D1 primary, H4 entry, W1 context; 500 candles/request; historical backfill 2005→present) with idempotent upserts and data-quality checks.

## Current State
- Prices land in `Fact_Market_Prices` (a TimescaleDB hypertable), consumed by Layers 1/2/6.
- **A proven ingester already exists: `src/layer0/ingest_oanda_prices.py`** — it pulls **H1/H4/D1** mid candles (complete only), is window-paginated, idempotent via `INSERT … ON CONFLICT (timestamp, asset_id, granularity)`, resumable from `MAX("timestamp")` per (asset, granularity), with exponential backoff + jitter on 429/5xx. **It has already been run; H1/H4/D1 are filled to the latest bar.** MODEL-001 **extends** this script — it does not rewrite it and does not re-backfill what is present.
- **Gaps to close:** no **W1** granularity; default start is 2006-01-01 (attempt earlier where OANDA depth allows, document per-instrument earliest); no formal **data-quality gate / quarantine table**, no **lineage columns** (`source`, `ingest_run_id`, `ingested_at_utc`, `complete`), and no per-run **gap/DQ report**.

## Target State
A resumable ingestion engine that, per configured instrument, pulls **D1 (primary), H4 (entry), W1 (context)** candles from OANDA in **500-candle pages**, backfills from **2005-01-01 → present**, then runs incrementally. Writes are idempotent (no duplicate bars on re-run). Every batch passes data-quality checks before commit; failing rows are quarantined, not silently dropped. Lineage (source, ingest run, granularity, page cursor) is recorded for traceability.

## Technical Specification

**Granularities & roles:** `D1` (primary modeling/regime), `H4` (entry timing), `W1` (macro context). OANDA granularity codes: `D`, `H4`, `W`. Existing H1/H4 contracts are preserved; D1/W1 are additive.

**Schema (additive, `Fact_Market_Prices`):**
- Ensure a `Granularity` column exists/extends to accept `D1`, `H4`, `W1` (alongside legacy `H1`/`H4`).
- Natural key for upsert: (`Instrument`/`Asset_Id`, `Granularity`, `Bar_Time_UTC`).
- Columns: `"Open"`, `high`, `low`, `"Close"` (double-quote the mixed-case reserved words `"Open"`/`"Close"`; other columns are lowercase), `volume`, `complete` (OANDA `complete` flag — only ingest complete candles), `source`='OANDA', `ingest_run_id`, `ingested_at_utc`.

**Paging / backfill:** request `count=500` with `from`/`to` or `from`+`count` cursors. Walk forward from 2005-01-01 UTC. Persist a **resumable cursor** per (instrument, granularity) in a small state table or `results/state/ingest_progress.json` so an interrupted backfill resumes. Apply exponential backoff on HTTP 429/5xx; honor rate limits.

**Idempotent upsert:** `INSERT … ON CONFLICT (asset_id, granularity, "timestamp") DO UPDATE` into `Fact_Market_Prices` on the natural key (update OHLCV/complete if the bar was previously incomplete, insert otherwise) — reuse the proven `psycopg2.extras.execute_values` + `ON CONFLICT … DO UPDATE … RETURNING (xmax = 0)` pattern already in `src/layer0/ingest_oanda_prices.py`.

**Data-quality checks (pre-commit, per batch):**
- Monotonic, gap-aware bar times (no out-of-order timestamps within a page).
- OHLC sanity: `Low ≤ Open,Close ≤ High`, no non-positive prices.
- Duplicate detection on natural key.
- Expected-bar coverage vs. FX trading calendar; flag gaps (weekend/holiday gaps are expected and logged, not errors).
- `Complete=true` only — skip the in-progress current candle.
Rows failing checks go to a `Fact_Market_Prices_Quarantine` table with a reason code; a per-run **gap/DQ report** is emitted (JSON + log).

**Lineage:** each row carries `Ingest_Run_Id`; a run manifest records instruments, granularities, date range, page count, rows inserted/updated/quarantined, and start/end cursors. Manifest registered with MLflow (or written to `results/state/`).

**Config / env:** instrument list + per-instrument earliest-history override (document instruments whose OANDA history starts after 2005), `OANDA_*` env vars, batch size 500, backoff params.

**Pseudo-code (clarifying only):**
```
for instrument in instruments:
  for g in [D1, H4, W1]:
    cursor = load_cursor(instrument, g) or 2005-01-01
    while cursor < now:
      page = oanda.candles(instrument, g, from=cursor, count=500)  # backoff on 429/5xx
      page = [c for c in page if c.complete]
      ok, quarantined = run_dq_checks(page)
      upsert(Fact_Market_Prices, ok)               # INSERT … ON CONFLICT DO UPDATE
      write_quarantine(quarantined)
      cursor = advance(page); save_cursor(...)
    emit_gap_report(instrument, g)
```

## Testing & Validation
- **Unit:** paging math, cursor advance/resume, DQ predicates (OHLC sanity, dup, ordering), backoff on simulated 429.
- **Integration:** small instrument over a bounded date range against OANDA practice; verify row counts per granularity and resume-after-kill produces no duplicates (idempotency test = run twice, assert identical row count).
- **DQ/edge cases:** weekend gaps (expected, logged not failed), DST boundaries, instrument with history starting after 2005, partial/incomplete final candle excluded, OANDA returning fewer than 500 on tail page.
- **Coverage report:** missing-expected-bar ratio < 0.5% (excluding documented market closures).

## Rollback Plan
Ingestion is additive and idempotent. To roll back: stop the engine, delete rows by `Ingest_Run_Id` (or by `Granularity in (D1,W1)` for the new granularities), drop the quarantine table; legacy H1/H4 ingestion and Layers 1/2/6 continue unaffected. No schema column is dropped destructively without dependency check.

## Acceptance Criteria
- [ ] D1/H4/W1 candles backfilled 2005→present for all configured instruments (with per-instrument earliest-date exceptions documented).
- [ ] Re-running ingestion produces zero duplicate bars (idempotency proven by double-run row-count equality).
- [ ] DQ checks run pre-commit; failing rows are quarantined with reason codes and a gap/DQ report is emitted per run.
- [ ] Resumable cursors allow an interrupted backfill to continue without data loss or duplication.
- [ ] Every row carries `Ingest_Run_Id` lineage and a run manifest is recorded.

## Notes & Risks
- OANDA practice history depth varies by instrument; some may not reach 2005 — document and accept.
- Rate limits are the main throughput constraint on the one-time backfill; backoff + checkpointing make it safe to run over multiple sessions.
- Preserve the existing H1/H4 contract; do not retire legacy ingestion until downstream tasks consume D1/H4/W1.
