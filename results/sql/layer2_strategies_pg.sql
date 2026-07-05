-- =============================================================================
-- Layer 2 Strategy Seed (PostgreSQL — translated from T-SQL)
-- Source: Layer 0 Strategy Qualification Engine
-- Generated: 2026-06-23T23:55:02
-- =============================================================================

DO $$
DECLARE
    v_strategy_id INT;
    v_config_id   INT;
BEGIN

    -- Deactivate currently active mappings first
    UPDATE dim_strategy_asset_mapping SET is_active = false WHERE is_active = true;
    UPDATE dim_strategy_config SET is_active = false WHERE is_active = true;
    UPDATE dim_strategy SET is_active = false WHERE is_active = true;

    -- =========================================================================
    -- Strategy: Range_Stochastic_Divergence
    -- =========================================================================

    -- UPSERT strategy
    INSERT INTO dim_strategy (strategy_id, strategy_name, strategy_type, description, is_active)
    VALUES (
        COALESCE(
            (SELECT strategy_id FROM dim_strategy WHERE strategy_name = 'Range_Stochastic_Divergence'),
            (SELECT COALESCE(MAX(strategy_id), 0) + 1 FROM dim_strategy)
        ),
        'Range_Stochastic_Divergence',
        'MEAN_REVERSION',
        'Stochastic divergence detection (14,3).',
        true
    )
    ON CONFLICT (strategy_id) DO UPDATE SET
        strategy_name = EXCLUDED.strategy_name,
        strategy_type = EXCLUDED.strategy_type,
        description = EXCLUDED.description,
        is_active = EXCLUDED.is_active;

    SELECT strategy_id INTO v_strategy_id FROM dim_strategy WHERE strategy_name = 'Range_Stochastic_Divergence';

    -- UPSERT config
    INSERT INTO dim_strategy_config (
        strategy_id, config_version, config_hash, granularity,
        indicator_configs, signal_rules, risk_filters,
        effective_from, is_active
    ) VALUES (
        v_strategy_id,
        '1.0.0',
        '652ea35709fd68ca9ecf37b84c1a514def9f9de373ff5d85ec3a035f89b448fd',
        'H4',
        '[{"indicator_key": "STOCH", "instance_name": "STOCH_14", "params": {"window": 14, "smooth_window": 3}, "output_column": "stoch"}]',
        '[{"rule_id": "LONG_STOCH_CROSS", "description": "Stochastic K crosses above 20 from oversold", "signal_value": 1, "conditions": [{"left": "STOCH_14.prev", "operator": "<=", "right": 20}, {"left": "STOCH_14", "operator": ">", "right": 20}], "logic": "AND"}, {"rule_id": "SHORT_STOCH_CROSS", "description": "Stochastic K crosses below 80 from overbought", "signal_value": -1, "conditions": [{"left": "STOCH_14.prev", "operator": ">=", "right": 80}, {"left": "STOCH_14", "operator": "<", "right": 80}], "logic": "AND"}]',
        '[{"note": "Divergence detection is NOT expressible in Layer 2 rule syntax. This config falls back to standard stochastic cross rules. Manual review required."}]',
        now() at time zone 'utc',
        true
    )
    ON CONFLICT (strategy_id, config_version, granularity) DO UPDATE SET
        config_hash = EXCLUDED.config_hash,
        indicator_configs = EXCLUDED.indicator_configs,
        signal_rules = EXCLUDED.signal_rules,
        risk_filters = EXCLUDED.risk_filters,
        effective_from = EXCLUDED.effective_from,
        effective_to = NULL,
        is_active = EXCLUDED.is_active;

    SELECT config_id INTO v_config_id FROM dim_strategy_config
        WHERE strategy_id = v_strategy_id AND config_version = '1.0.0' AND granularity = 'H4';

    -- UPSERT asset mappings (5 forex majors: EUR/USD=1, GBP/USD=2, USD/JPY=3, AUD/USD=4, USD/CAD=5)
    -- Asset 1: EUR_USD
    INSERT INTO dim_strategy_asset_mapping (strategy_id, asset_id, granularity, config_id, is_active)
    VALUES (v_strategy_id, 1, 'H4', v_config_id, true)
    ON CONFLICT (strategy_id, asset_id, granularity) DO UPDATE SET
        config_id = EXCLUDED.config_id,
        is_active = EXCLUDED.is_active;

    -- Asset 2: GBP_USD
    INSERT INTO dim_strategy_asset_mapping (strategy_id, asset_id, granularity, config_id, is_active)
    VALUES (v_strategy_id, 2, 'H4', v_config_id, true)
    ON CONFLICT (strategy_id, asset_id, granularity) DO UPDATE SET
        config_id = EXCLUDED.config_id,
        is_active = EXCLUDED.is_active;

    -- Asset 3: USD_JPY
    INSERT INTO dim_strategy_asset_mapping (strategy_id, asset_id, granularity, config_id, is_active)
    VALUES (v_strategy_id, 3, 'H4', v_config_id, true)
    ON CONFLICT (strategy_id, asset_id, granularity) DO UPDATE SET
        config_id = EXCLUDED.config_id,
        is_active = EXCLUDED.is_active;

    -- Asset 4: AUD_USD
    INSERT INTO dim_strategy_asset_mapping (strategy_id, asset_id, granularity, config_id, is_active)
    VALUES (v_strategy_id, 4, 'H4', v_config_id, true)
    ON CONFLICT (strategy_id, asset_id, granularity) DO UPDATE SET
        config_id = EXCLUDED.config_id,
        is_active = EXCLUDED.is_active;

    -- Asset 5: USD_CAD
    INSERT INTO dim_strategy_asset_mapping (strategy_id, asset_id, granularity, config_id, is_active)
    VALUES (v_strategy_id, 5, 'H4', v_config_id, true)
    ON CONFLICT (strategy_id, asset_id, granularity) DO UPDATE SET
        config_id = EXCLUDED.config_id,
        is_active = EXCLUDED.is_active;

    RAISE NOTICE 'Seeded Range_Stochastic_Divergence: strategy_id=%, config_id=%, 5 asset mappings', v_strategy_id, v_config_id;
END $$;

-- =============================================================================
-- END OF SEED SCRIPT
-- =============================================================================
