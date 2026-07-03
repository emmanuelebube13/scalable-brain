# FND-004 — Database Strategy & Consolidation Decision

- **Task ID**: FND-004
- **System**: Foundational & Cross-Cutting
- **Priority**: P0-Critical
- **Estimated Effort**: 3d
- **Prerequisites**: None
- **External Dependencies**:
  - **PostgreSQL 16 + TimescaleDB** extension (recommended canonical store). *Why:* the AMS design (System 3) is written against PostgreSQL, the project already runs a PostgreSQL instance for research notes, and TimescaleDB hypertables fit the heavy time-series tables (`Fact_Market_Prices`, equity curve, tick/price history) far better than row-store SQL Server for this workload.
  - The existing **SQL Server 2022** container (current `ForexBrainDB`) remains available for migration source/parallel-run. *Why:* Layers 1–4 currently depend on it; cutover must be non-destructive.
  - Migration tooling (e.g. `pgloader` or scripted ETL) and DDL for the chosen target.

## Objective
Decide and document the canonical datastore strategy that reconciles the current SQL Server `ForexBrainDB` with the AMS design's PostgreSQL assumption, choosing PostgreSQL + TimescaleDB and defining a non-destructive migration path.

## Current State
- **Primary DB:** SQL Server 2022 (Docker, `docker-compose.yml`), database `ForexBrainDB`, accessed via `pyodbc`/SQLAlchemy with ODBC driver 17/18. Hosts all `Fact_*`/`Dim_*` tables (`Fact_Market_Prices`, `Fact_Market_Regime_V2`, `Fact_Signals` (915K+ rows), `Fact_Live_Trades`, `Fact_Execution_Log`, `Fact_Macro_Events`, dimensions).
- **Secondary DB:** PostgreSQL — used only for research notes (`src/research_notes_api.py`, Flask).
- The `.env` is internally inconsistent (`DB_DRIVER=PostgreSQL`, `DB_PORT=5432` while the engine is SQL Server) — a latent configuration hazard.
- SQL Server-specific constraints leak into code: `[Close]` reserved-word escaping, ODBC driver auto-detection, `MERGE` upsert pattern, schema-aware `Is_Active` handling.

## Target State
A documented decision (this file is the decision record) selecting **PostgreSQL 16 + TimescaleDB** as the single canonical operational store, with:
- All runtime `Fact_*`/`Dim_*` tables migrated or dual-written, time-series tables as TimescaleDB hypertables.
- AMS tables (AMS-001) created natively in this DB — no cross-engine bridge needed.
- A defined indexing strategy, connection-config standard (one DSN convention, secrets via FND-003), and a migration sequence that lets each layer cut over independently without downtime.

## Technical Specification

### Decision & rationale
- **Chosen:** PostgreSQL + TimescaleDB. Rationale: aligns System 3 with its design DB; consolidates the two existing engines into one; TimescaleDB compression + continuous aggregates suit prices/equity history; eliminates SQL Server licensing/ODBC friction; better fit for a Linux solo-ops footprint and the lightweight Computer 3.
- **Rejected alternatives:** (a) stay on SQL Server and run AMS on it — works, but fights the AMS design and keeps ODBC/licensing friction; (b) dual-engine permanently — doubles ops/backup surface for no benefit.

### Schema portability work
- Translate SQL Server DDL → PostgreSQL: `MERGE` upserts → `INSERT ... ON CONFLICT ... DO UPDATE`; `[Close]` bracket-escaping → standard quoted identifiers (or rename to `close_price` during migration); `DECIMAL`/`DATETIME2` → `numeric`/`timestamptz`; identity columns → `GENERATED ... AS IDENTITY`/`SERIAL`.
- Designate hypertables: `Fact_Market_Prices` (partition by time, by `asset`+`granularity`), AMS `equity_curve`, any high-frequency price/PnL series.

### Indexing strategy
- Composite indexes on the hot read paths: `Fact_Signals(asset, granularity, signal_time)`, `Fact_Market_Regime_V2(asset, granularity, ts)`, `Fact_Live_Trades(status, opened_at)`, AMS `AMS_Decision_Log(timestamp)`, `AMS_Account_State(account_id)`.
- BRIN indexes on large append-only time columns; partial indexes for "unresolved outcome" auditor queries.

### Migration sequence (non-destructive)
1. Stand up PostgreSQL+TimescaleDB (extend existing PG or new instance); create schema via portable DDL.
2. Bulk-load historical tables (pgloader/ETL) from SQL Server; verify row counts + checksums.
3. **Parallel run:** dual-write new rows to both engines for a validation window; reconcile.
4. Cut over read paths layer-by-layer behind a `DB_BACKEND` flag (Layer 1 → 2 → 3 → 4 → 5/6), validating each.
5. Decommission SQL Server only after all layers + AMS read/write PostgreSQL cleanly.
- Fix the `.env`/connection-config inconsistency as part of step 1 (one canonical DSN convention).

## Testing & Validation
- Row-count and aggregate-checksum parity between SQL Server and PostgreSQL for every migrated table.
- Each layer runs end-to-end against PostgreSQL in dry-run and produces identical artifacts to the SQL Server run (signals, regime labels, gatekeeper decisions) on a fixed input window.
- Reserved-word/upsert regression: confirm former `[Close]`/`MERGE` paths behave identically under PostgreSQL.
- Hypertable performance: a representative price-range query meets its latency budget vs the SQL Server baseline.
- Dual-write reconciliation shows zero divergence over the validation window before cutover.

## Rollback Plan
Because cutover is per-layer behind `DB_BACKEND` and SQL Server is kept running through the parallel-run window, rollback is flipping a layer's flag back to SQL Server. No data loss: SQL Server remains the source of truth until each layer is validated on PostgreSQL. SQL Server is decommissioned only after a clean validation window, with a final backup retained per FND-006.

## Acceptance Criteria
- [ ] Decision record (this file) ratified: PostgreSQL + TimescaleDB as canonical, with rationale and rejected options.
- [ ] Portable DDL exists for all `Fact_*`/`Dim_*` + AMS tables; time-series tables defined as hypertables with the indexing strategy applied.
- [ ] Historical data migrated with verified row-count/checksum parity.
- [ ] Each layer validated against PostgreSQL behind `DB_BACKEND`, producing identical artifacts to the SQL Server baseline.
- [ ] `.env`/connection-config inconsistency resolved to one canonical DSN convention sourced from FND-003.

## Notes & Risks
- This is the single highest-leverage foundational decision: AMS-001 and MODEL-001 both block on it. Ratify early.
- Migration risk concentrates in the 915K-row `Fact_Signals` and any code with SQL Server-specific SQL; the per-layer flag + parallel run is the mitigation.
- TimescaleDB adds an extension dependency; if rejected, plain PostgreSQL partitioning is the fallback (slightly more manual).
- Trade-off: consolidation is real upfront effort, but the long-term ops/backup/secrets surface shrinks from two engines to one — worth it for a solo operator.
