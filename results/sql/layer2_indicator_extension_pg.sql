-- =============================================================================
-- Extend Dim_Indicator_Library (PostgreSQL — translated from T-SQL)
-- Generated from layer2_indicator_extension.sql
-- =============================================================================

INSERT INTO dim_indicator_library (indicator_key, display_name, description, category, default_params)
VALUES ('ATR', 'Average True Range',
        'Measures market volatility by decomposing the entire range of an asset price for that period.',
        'VOLATILITY', '{"window": 14}')
ON CONFLICT (indicator_key) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    default_params = EXCLUDED.default_params;

DO $$
DECLARE
    v_atr_id INT;
BEGIN
    SELECT indicator_id INTO v_atr_id FROM dim_indicator_library WHERE indicator_key = 'ATR';
    RAISE NOTICE 'Extended dim_indicator_library with ATR (indicator_id = %)', v_atr_id;
END $$;

-- NOTE: The following custom indicators are used by Layer 0 but are NOT available
-- in the standard 'ta' library registry:
--   - detect_swing_points   (used by Support_Resistance family)
--   - volatility_contraction_index / squeeze logic (used by VCP_Breakout family)
-- =============================================================================
