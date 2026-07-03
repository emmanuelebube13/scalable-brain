-- FND-004 Phase 1 — Verification
-- ================================
-- Run after 02. Confirms hypertables exist, data survived migration, chunks were
-- created, and policies are registered.
--
--     PGPASSWORD=... psql -h localhost -p 5432 -U sa -d ForexBrainDB \
--         -f src/sql/timescaledb/03_verify.sql

\echo '=== Hypertables ==='
SELECT hypertable_name, num_dimensions
FROM timescaledb_information.hypertables
ORDER BY hypertable_name;

\echo '=== Chunk counts per hypertable ==='
SELECT hypertable_name, count(*) AS chunks
FROM timescaledb_information.chunks
GROUP BY hypertable_name
ORDER BY hypertable_name;

\echo '=== Row counts (must match pre-migration baseline) ==='
SELECT 'fact_market_prices' AS t, count(*) FROM fact_market_prices
UNION ALL SELECT 'fact_signals', count(*) FROM fact_signals
UNION ALL SELECT 'fact_market_regime_v2', count(*) FROM fact_market_regime_v2;

\echo '=== Price coverage by granularity (sanity) ==='
SELECT granularity, count(*), min("timestamp"), max("timestamp")
FROM fact_market_prices
GROUP BY granularity
ORDER BY granularity;

\echo '=== Compression policies ==='
SELECT hypertable_name, config
FROM timescaledb_information.jobs
WHERE proc_name = 'policy_compression'
ORDER BY hypertable_name;
