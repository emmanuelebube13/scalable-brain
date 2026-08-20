ALTER TABLE fact_trade_outcomes
ADD COLUMN IF NOT EXISTS leg_index INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS is_terminal_leg BOOLEAN DEFAULT true;

UPDATE fact_trade_outcomes SET leg_index = 0 WHERE leg_index IS NULL;
UPDATE fact_trade_outcomes SET is_terminal_leg = true WHERE is_terminal_leg IS NULL;

ALTER TABLE fact_trade_outcomes ALTER COLUMN leg_index SET NOT NULL;
ALTER TABLE fact_trade_outcomes ALTER COLUMN is_terminal_leg SET NOT NULL;

ALTER TABLE fact_trade_outcomes DROP CONSTRAINT IF EXISTS uq_trade_outcome_leg;
ALTER TABLE fact_trade_outcomes ADD CONSTRAINT uq_trade_outcome_leg UNIQUE ("timestamp", asset_id, strategy_id, granularity, leg_index);
