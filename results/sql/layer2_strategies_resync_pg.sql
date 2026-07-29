-- =============================================================================
-- Layer 2 Strategy Seed — RE-SYNC (PostgreSQL)
-- Hand-translated from results/sql/layer2_strategies.sql (T-SQL, Generated 2026-07-04T14:15:09)
-- to match the CURRENT Layer 0 qualification output and the LIVE PostgreSQL schema
-- (dim_strategy_asset_mapping has no priority/effective_to columns).
--
-- Promotes 3 qualified strategies:
--   Range_Bollinger_H1  -> H1, GBP_USD only
--   Range_Bollinger_H4  -> H4, GBP_USD only
--   Range_Stochastic_Divergence -> H4, EUR/GBP/AUD/CAD (USD_JPY intentionally NOT qualified)
-- Assets: EUR_USD=1, GBP_USD=2, USD_JPY=3, AUD_USD=4, USD_CAD=5
-- =============================================================================

DO $$
DECLARE
    v_sid INT;
    v_cid INT;
BEGIN
    -- 1) Deactivate all currently-active Layer 2 records (clean slate before promotion)
    UPDATE dim_strategy_asset_mapping SET is_active = false WHERE is_active = true;
    UPDATE dim_strategy_config        SET is_active = false, effective_to = COALESCE(effective_to, now() at time zone 'utc') WHERE is_active = true;
    UPDATE dim_strategy               SET is_active = false WHERE is_active = true;

    -- =========================================================================
    -- Strategy: Range_Bollinger_H1  (H1, GBP_USD only)
    -- =========================================================================
    INSERT INTO dim_strategy (strategy_id, strategy_name, strategy_type, description, is_active)
    VALUES (
        COALESCE((SELECT strategy_id FROM dim_strategy WHERE strategy_name = 'Range_Bollinger_H1'),
                 (SELECT COALESCE(MAX(strategy_id),0)+1 FROM dim_strategy)),
        'Range_Bollinger_H1', 'RANGE',
        'H1 Bollinger Band mean reversion (10,2) with RSI(7).', true)
    ON CONFLICT (strategy_id) DO UPDATE SET
        strategy_name = EXCLUDED.strategy_name, strategy_type = EXCLUDED.strategy_type,
        description = EXCLUDED.description, is_active = EXCLUDED.is_active;
    SELECT strategy_id INTO v_sid FROM dim_strategy WHERE strategy_name = 'Range_Bollinger_H1';

    INSERT INTO dim_strategy_config (strategy_id, config_version, config_hash, granularity,
        indicator_configs, signal_rules, risk_filters, effective_from, effective_to, is_active)
    VALUES (v_sid, '1.0.0', '723439f88e08076d2d84df0d7f1e694b088db1acfd4ddf9c64094a824eee0adc', 'H1',
        '[{"indicator_key": "BB", "instance_name": "BB_10", "params": {"window": 10, "window_dev": 2}, "output_columns": ["bollinger_hband", "bollinger_lband"]}, {"indicator_key": "RSI", "instance_name": "RSI_7", "params": {"window": 7}, "output_column": "rsi"}]'::jsonb,
        '[{"rule_id": "LONG_BB_RSI", "description": "Price at lower Bollinger band with RSI oversold", "signal_value": 1, "conditions": [{"left": "Close", "operator": "<=", "right": "BB_10.lband"}, {"left": "RSI_7", "operator": "<", "right": 30}], "logic": "AND"}, {"rule_id": "SHORT_BB_RSI", "description": "Price at upper Bollinger band with RSI overbought", "signal_value": -1, "conditions": [{"left": "Close", "operator": ">=", "right": "BB_10.hband"}, {"left": "RSI_7", "operator": ">", "right": 70}], "logic": "AND"}]'::jsonb,
        '[{"note": "Layer 0 squeeze filter and cross-into-zone logic are not expressed in current Layer 2 rule syntax."}]'::jsonb,
        now() at time zone 'utc', NULL, true)
    ON CONFLICT (strategy_id, config_version, granularity) DO UPDATE SET
        config_hash = EXCLUDED.config_hash, indicator_configs = EXCLUDED.indicator_configs,
        signal_rules = EXCLUDED.signal_rules, risk_filters = EXCLUDED.risk_filters,
        effective_from = EXCLUDED.effective_from, effective_to = NULL, is_active = true;
    SELECT config_id INTO v_cid FROM dim_strategy_config
        WHERE strategy_id = v_sid AND config_version = '1.0.0' AND granularity = 'H1';

    INSERT INTO dim_strategy_asset_mapping (strategy_id, asset_id, granularity, config_id, is_active)
    VALUES (v_sid, 2, 'H1', v_cid, true)
    ON CONFLICT (strategy_id, asset_id, granularity) DO UPDATE SET
        config_id = EXCLUDED.config_id, is_active = true, updated_at = now() at time zone 'utc';

    -- =========================================================================
    -- Strategy: Range_Bollinger_H4  (H4, GBP_USD only)
    -- =========================================================================
    INSERT INTO dim_strategy (strategy_id, strategy_name, strategy_type, description, is_active)
    VALUES (
        COALESCE((SELECT strategy_id FROM dim_strategy WHERE strategy_name = 'Range_Bollinger_H4'),
                 (SELECT COALESCE(MAX(strategy_id),0)+1 FROM dim_strategy)),
        'Range_Bollinger_H4', 'RANGE',
        'H4 Bollinger Band mean reversion (20,2) with RSI(14).', true)
    ON CONFLICT (strategy_id) DO UPDATE SET
        strategy_name = EXCLUDED.strategy_name, strategy_type = EXCLUDED.strategy_type,
        description = EXCLUDED.description, is_active = EXCLUDED.is_active;
    SELECT strategy_id INTO v_sid FROM dim_strategy WHERE strategy_name = 'Range_Bollinger_H4';

    INSERT INTO dim_strategy_config (strategy_id, config_version, config_hash, granularity,
        indicator_configs, signal_rules, risk_filters, effective_from, effective_to, is_active)
    VALUES (v_sid, '1.0.0', '5c13014946893a0ace979657f795c588b1501d9f1d79a0be3fcf98e3e0cdda62', 'H4',
        '[{"indicator_key": "BB", "instance_name": "BB_20", "params": {"window": 20, "window_dev": 2}, "output_columns": ["bollinger_hband", "bollinger_lband"]}, {"indicator_key": "RSI", "instance_name": "RSI_14", "params": {"window": 14}, "output_column": "rsi"}]'::jsonb,
        '[{"rule_id": "LONG_BB_RSI", "description": "Price at lower Bollinger band with RSI oversold", "signal_value": 1, "conditions": [{"left": "Close", "operator": "<=", "right": "BB_20.lband"}, {"left": "RSI_14", "operator": "<", "right": 30}], "logic": "AND"}, {"rule_id": "SHORT_BB_RSI", "description": "Price at upper Bollinger band with RSI overbought", "signal_value": -1, "conditions": [{"left": "Close", "operator": ">=", "right": "BB_20.hband"}, {"left": "RSI_14", "operator": ">", "right": 70}], "logic": "AND"}]'::jsonb,
        '[{"note": "Layer 0 squeeze filter and cross-into-zone logic are not expressed in current Layer 2 rule syntax."}]'::jsonb,
        now() at time zone 'utc', NULL, true)
    ON CONFLICT (strategy_id, config_version, granularity) DO UPDATE SET
        config_hash = EXCLUDED.config_hash, indicator_configs = EXCLUDED.indicator_configs,
        signal_rules = EXCLUDED.signal_rules, risk_filters = EXCLUDED.risk_filters,
        effective_from = EXCLUDED.effective_from, effective_to = NULL, is_active = true;
    SELECT config_id INTO v_cid FROM dim_strategy_config
        WHERE strategy_id = v_sid AND config_version = '1.0.0' AND granularity = 'H4';

    INSERT INTO dim_strategy_asset_mapping (strategy_id, asset_id, granularity, config_id, is_active)
    VALUES (v_sid, 2, 'H4', v_cid, true)
    ON CONFLICT (strategy_id, asset_id, granularity) DO UPDATE SET
        config_id = EXCLUDED.config_id, is_active = true, updated_at = now() at time zone 'utc';

    -- =========================================================================
    -- Strategy: Range_Stochastic_Divergence  (H4, EUR/GBP/AUD/CAD -- NO USD_JPY)
    -- =========================================================================
    INSERT INTO dim_strategy (strategy_id, strategy_name, strategy_type, description, is_active)
    VALUES (
        COALESCE((SELECT strategy_id FROM dim_strategy WHERE strategy_name = 'Range_Stochastic_Divergence'),
                 (SELECT COALESCE(MAX(strategy_id),0)+1 FROM dim_strategy)),
        'Range_Stochastic_Divergence', 'MEAN_REVERSION',
        'Stochastic divergence detection (14,3).', true)
    ON CONFLICT (strategy_id) DO UPDATE SET
        strategy_name = EXCLUDED.strategy_name, strategy_type = EXCLUDED.strategy_type,
        description = EXCLUDED.description, is_active = EXCLUDED.is_active;
    SELECT strategy_id INTO v_sid FROM dim_strategy WHERE strategy_name = 'Range_Stochastic_Divergence';

    INSERT INTO dim_strategy_config (strategy_id, config_version, config_hash, granularity,
        indicator_configs, signal_rules, risk_filters, effective_from, effective_to, is_active)
    VALUES (v_sid, '1.0.0', '652ea35709fd68ca9ecf37b84c1a514def9f9de373ff5d85ec3a035f89b448fd', 'H4',
        '[{"indicator_key": "STOCH", "instance_name": "STOCH_14", "params": {"window": 14, "smooth_window": 3}, "output_column": "stoch"}]'::jsonb,
        '[{"rule_id": "LONG_STOCH_CROSS", "description": "Stochastic K crosses above 20 from oversold", "signal_value": 1, "conditions": [{"left": "STOCH_14.prev", "operator": "<=", "right": 20}, {"left": "STOCH_14", "operator": ">", "right": 20}], "logic": "AND"}, {"rule_id": "SHORT_STOCH_CROSS", "description": "Stochastic K crosses below 80 from overbought", "signal_value": -1, "conditions": [{"left": "STOCH_14.prev", "operator": ">=", "right": 80}, {"left": "STOCH_14", "operator": "<", "right": 80}], "logic": "AND"}]'::jsonb,
        '[{"note": "Divergence detection is NOT expressible in Layer 2 rule syntax. This config falls back to standard stochastic cross rules. Manual review required."}]'::jsonb,
        now() at time zone 'utc', NULL, true)
    ON CONFLICT (strategy_id, config_version, granularity) DO UPDATE SET
        config_hash = EXCLUDED.config_hash, indicator_configs = EXCLUDED.indicator_configs,
        signal_rules = EXCLUDED.signal_rules, risk_filters = EXCLUDED.risk_filters,
        effective_from = EXCLUDED.effective_from, effective_to = NULL, is_active = true;
    SELECT config_id INTO v_cid FROM dim_strategy_config
        WHERE strategy_id = v_sid AND config_version = '1.0.0' AND granularity = 'H4';

    -- Qualified assets only: 1=EUR_USD, 2=GBP_USD, 4=AUD_USD, 5=USD_CAD  (3=USD_JPY excluded)
    INSERT INTO dim_strategy_asset_mapping (strategy_id, asset_id, granularity, config_id, is_active)
    VALUES (v_sid, 1, 'H4', v_cid, true), (v_sid, 2, 'H4', v_cid, true),
           (v_sid, 4, 'H4', v_cid, true), (v_sid, 5, 'H4', v_cid, true)
    ON CONFLICT (strategy_id, asset_id, granularity) DO UPDATE SET
        config_id = EXCLUDED.config_id, is_active = true, updated_at = now() at time zone 'utc';

    RAISE NOTICE 'Re-sync complete: 3 strategies promoted, USD_JPY mapping left inactive.';
END $$;
