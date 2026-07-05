-- FND-004 Phase 1, Step 2 — Enable the TimescaleDB extension
-- =============================================================
-- RUN AS A SUPERUSER (the `sa` role is NOT a superuser on this cluster):
--
--     sudo -u postgres psql -d ForexBrainDB -f src/sql/timescaledb/01_enable_extension.sql
--
-- Prerequisite (Step 1, done once): `timescaledb` must be in
-- shared_preload_libraries and the cluster restarted. See README.md.
-- CREATE EXTENSION will FAIL with a clear hint if the library was not preloaded.

\echo 'Enabling timescaledb extension on' :DBNAME

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Optional analytical hyperfunctions (percentile_agg, time-weighted avg, etc.).
-- Comment out if the toolkit package is unwanted.
CREATE EXTENSION IF NOT EXISTS timescaledb_toolkit;

-- Let the table owner (`sa`) build hypertables/indexes in step 02 without
-- needing superuser again.
GRANT ALL ON SCHEMA public TO sa;

\echo 'Installed extensions:'
SELECT extname, extversion FROM pg_extension WHERE extname LIKE 'timescaledb%';
