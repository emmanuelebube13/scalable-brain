-- FND-004 Phase 1, Step 3 — Convert time-series tables to hypertables + indexing
-- =============================================================================
-- Idempotent. Safe to re-run. Run as the table owner `sa` (or any superuser):
--
--     PGPASSWORD=... psql -h localhost -p 5432 -U sa -d ForexBrainDB \
--         -f src/sql/timescaledb/02_hypertables_and_indexes.sql
--
-- Requires 01_enable_extension.sql to have been run first.
--
-- Scope (per FND-004): hypertable the price / regime / signal time-series tables
-- whose PRIMARY KEY already leads with `timestamp` (TimescaleDB requires the
-- partitioning column to be part of every UNIQUE/PK index). Surrogate-PK tables
-- (fact_trade_outcomes, fact_live_trades, fact_execution_log, fact_macro_events)
-- stay as plain tables and only receive supporting indexes.

\set ON_ERROR_STOP on
BEGIN;

-- 1. HYPERTABLES ----------------------------------------------------------------
-- 30-day chunks: ~20 years of data -> ~250 chunks; keeps the active working set
-- (recent months) in a small number of chunks. by_range is the current API.
-- migrate_data => true moves existing rows into chunks (fact_market_prices only;
-- the rest are empty so it is a no-op for them).

SELECT create_hypertable('fact_market_prices',    by_range('timestamp', INTERVAL '30 days'), migrate_data => true,  if_not_exists => true);
SELECT create_hypertable('fact_market_prices_h4', by_range('timestamp', INTERVAL '30 days'), migrate_data => true,  if_not_exists => true);
SELECT create_hypertable('fact_market_prices_d1', by_range('timestamp', INTERVAL '90 days'), migrate_data => true,  if_not_exists => true);
SELECT create_hypertable('fact_market_regime',    by_range('timestamp', INTERVAL '30 days'), migrate_data => true,  if_not_exists => true);
SELECT create_hypertable('fact_market_regime_v2', by_range('timestamp', INTERVAL '30 days'), migrate_data => true,  if_not_exists => true);
SELECT create_hypertable('fact_signals',          by_range('timestamp', INTERVAL '30 days'), migrate_data => true,  if_not_exists => true);

-- NOTE on space partitioning: the doc mentions "by asset+granularity". On a
-- single node, space (hash) partitioning is generally discouraged and there are
-- only 5 assets, so we satisfy asset/granularity access via composite indexes
-- below rather than a space dimension. Revisit if this ever goes multi-node.

-- 2. INDEXING STRATEGY (FND-004) -----------------------------------------------
-- Composite indexes on hot read paths. CREATE INDEX on a hypertable parent
-- propagates to all chunks automatically.

-- Fact_Signals(asset, granularity, signal_time)
CREATE INDEX IF NOT EXISTS ix_signals_asset_gran_time
    ON fact_signals (asset_id, granularity, "timestamp" DESC);

-- Fact_Market_Regime_V2(asset, granularity, ts)
CREATE INDEX IF NOT EXISTS ix_regimev2_asset_gran_time
    ON fact_market_regime_v2 (asset_id, granularity, "timestamp" DESC);

-- BRIN on the large append-only price time column (tiny, complements chunk
-- exclusion for wide range scans).
CREATE INDEX IF NOT EXISTS brin_market_prices_ts
    ON fact_market_prices USING brin ("timestamp");

-- Partial index for the Layer 6 auditor "unresolved outcome" query.
CREATE INDEX IF NOT EXISTS ix_livetrades_unresolved
    ON fact_live_trades ("timestamp" DESC)
    WHERE actual_outcome IS NULL;

-- Supporting lookups on surrogate-PK fact tables (plain tables).
CREATE INDEX IF NOT EXISTS ix_tradeoutcomes_asset_gran_time
    ON fact_trade_outcomes (asset_id, granularity, "timestamp" DESC);
CREATE INDEX IF NOT EXISTS ix_macro_events_ts
    ON fact_macro_events ("timestamp" DESC);

COMMIT;

-- 3. COMPRESSION (outside the txn; policies manage their own transactions) ------
-- Columnstore compression for the price history: segment by the columns we
-- filter on, order within segments by time. Compress chunks older than 90 days.
ALTER TABLE fact_market_prices SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'asset_id, granularity',
    timescaledb.compress_orderby   = '"timestamp" DESC'
);
SELECT add_compression_policy('fact_market_prices', INTERVAL '90 days', if_not_exists => true);

ALTER TABLE fact_signals SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'asset_id, granularity, strategy_id',
    timescaledb.compress_orderby   = '"timestamp" DESC'
);
SELECT add_compression_policy('fact_signals', INTERVAL '180 days', if_not_exists => true);
