# FND-004 Phase 1 — Enable TimescaleDB on the live `ForexBrainDB`

This implements the storage half of the FND-004 decision (PostgreSQL + TimescaleDB
canonical). It does **not** touch application code (that is Phase 3, deferred).

## Verified current state (2026-06-22)

The canonical database is the **system PostgreSQL 16.14 cluster (`16/main`) on
`localhost:5432`**, database **`ForexBrainDB`** (the target of `.env`). It already
holds the data:

| Table | Rows |
|---|---|
| `fact_market_prices` | **4,670,963** (M15/M30/H1/H4/D1, 2006-01-01 → 2026-05-01) |
| `dim_asset` | 5 (EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD) |
| all downstream fact tables | 0 (derived; not generated yet) |

TimescaleDB 2.26.3 is **installed on the cluster** but **not enabled** on this DB
(only `plpgsql`), and tables are plain (not hypertables). The Docker
`timescale/timescaledb` container/volume and the SQL Server volumes are empty
duplicates, left in place for now (Phase 2 cleanup).

Two cluster-level prerequisites require `sudo`/superuser:
1. `timescaledb` is not in `shared_preload_libraries` → needs a config edit + restart.
2. `sa` is not a superuser → `CREATE EXTENSION` needs `postgres`.

## Run order

Run each from the repo root. The `!`-prefixed ones need your shell (sudo/superuser).

```bash
# Step 1 — preload the library + tune, then restart the cluster (ONE time)
!sudo timescaledb-tune --quiet --yes          # edits /etc/postgresql/16/main/postgresql.conf
!sudo systemctl restart postgresql

# Step 2 — enable the extension as the postgres superuser
!sudo -u postgres psql -d ForexBrainDB -f src/sql/timescaledb/01_enable_extension.sql

# Step 3 — convert hypertables + indexes + compression (as sa; idempotent)
PGPASSWORD='Emm5$manuel' psql -h localhost -p 5432 -U sa -d ForexBrainDB \
    -f src/sql/timescaledb/02_hypertables_and_indexes.sql

# Step 4 — verify
PGPASSWORD='Emm5$manuel' psql -h localhost -p 5432 -U sa -d ForexBrainDB \
    -f src/sql/timescaledb/03_verify.sql
```

## Acceptance checks

- `03_verify.sql` lists 6 hypertables and shows `fact_market_prices` chunk count > 0.
- **`fact_market_prices` row count is still 4,670,963** after migration (no data loss).
- Price coverage min/max unchanged (2006-01-01 → 2026-05-01).
- Compression policies registered for `fact_market_prices` and `fact_signals`.

## Rollback

Phase 1 is non-destructive to data (`migrate_data` moves rows into chunks within
`ForexBrainDB`; nothing is dropped). To undo the hypertable conversion if needed,
restore from the FND-006 backup taken before Step 3, or
`SELECT decompress_chunk(...)` + recreate as a plain table from a dump. Take a
`pg_dump` of `ForexBrainDB` before Step 1 as the safety net.

## Deferred (not in this phase)

- **Phase 2 — Consolidation:** drop the empty Docker `scalable-brain_postgres-data`
  volume + both SQL Server volumes; remove SQL Server from `docker-compose.yml`
  (it currently binds :5432, colliding with the system PG).
- **Phase 3 — Code de-coupling:** 16 `pyodbc` files, 12 `MERGE`, ~422 SQL-Server-isms
  → PostgreSQL driver + `INSERT … ON CONFLICT`, single canonical DSN from FND-003.
