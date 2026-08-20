-- Migration for Unified Strategy Registry (P0)

-- 1. Add new columns to dim_strategy
ALTER TABLE dim_strategy
ADD COLUMN IF NOT EXISTS strategy_key VARCHAR(255) UNIQUE,
ADD COLUMN IF NOT EXISTS universe VARCHAR(50) CHECK (universe IN ('legacy', 'v2_research', 'regime_aware_port')),
ADD COLUMN IF NOT EXISTS engine VARCHAR(50) CHECK (engine IN ('backtest_engine_v1', 'position_engine_v2')),
ADD COLUMN IF NOT EXISTS primary_granularity VARCHAR(10) CHECK (primary_granularity IN ('H1', 'H4', 'D1', 'W1')),
ADD COLUMN IF NOT EXISTS family VARCHAR(255),
ADD COLUMN IF NOT EXISTS registered_at_utc TIMESTAMP WITH TIME ZONE;

-- 2. Backfill legacy strategies
-- Legacy strategies already have an ID (1..10) and a strategy_name.
-- We backfill strategy_key with strategy_name.
UPDATE dim_strategy
SET strategy_key = strategy_name,
    universe = 'legacy',
    engine = 'backtest_engine_v1',
    -- Note: primary_granularity is H1 for most legacy, but we can leave it NULL or set it to 'H1' if required.
    -- For now we leave primary_granularity as NULL or we can assume H1 based on legacy usage. 
    -- The schema allows nullable except where specified.
    registered_at_utc = CURRENT_TIMESTAMP
WHERE strategy_id <= 10;
