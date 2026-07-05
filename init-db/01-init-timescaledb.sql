-- ============================================================================
-- init-db/01-init-timescaledb.sql
-- ----------------------------------------------------------------------------
-- PostgreSQL init script for the OPTIONAL, DEV-ONLY TimescaleDB service defined
-- in docker-compose.yml (service `timescaledb-dev`, host port 5433).
--
-- This runs ONLY on first initialization of an empty dev volume, against the
-- POSTGRES_DB created by the container (`ForexBrainDB`). It is NOT applied to
-- the canonical store — the canonical `ForexBrainDB` is the HOST system
-- PostgreSQL 16 cluster on localhost:5432, which already has TimescaleDB enabled
-- (see src/sql/timescaledb/ for the Phase 1 SQL).
--
-- Replaces the obsolete SQL Server `01-create-database.sql` (removed in
-- FND-004 Phase 2). The `CREATE DATABASE` step is unnecessary here: the
-- container creates the database from POSTGRES_DB automatically.
-- ============================================================================

-- Enable TimescaleDB on the dev database so local tests mirror the prod
-- extension surface. Toolkit is optional and only loaded if available.
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS timescaledb_toolkit;
