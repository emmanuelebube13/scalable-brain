
-- =============================================================================
-- Extend Dim_Indicator_Library for Layer 0 strategies
-- =============================================================================
USE ForexBrainDB;
GO

MERGE [dbo].[Dim_Indicator_Library] AS target
USING (VALUES
    ('ATR', 'Average True Range',
     'Measures market volatility by decomposing the entire range of an asset price for that period.',
     'VOLATILITY', 'High,Low,Close',
     '{"window": 14}', 'atr',
     50, 'ta.volatility.AverageTrueRange', 1)
) AS source (
    [Indicator_Key], [Indicator_Name], [Description],
    [Category], [Required_Price_Fields], [Default_Parameters], [Output_Columns],
    [Warmup_Period_Min], [Python_Class], [Is_Active]
)
ON target.[Indicator_Key] = source.[Indicator_Key]
WHEN MATCHED THEN
    UPDATE SET
        [Indicator_Name] = source.[Indicator_Name],
        [Description] = source.[Description],
        [Category] = source.[Category],
        [Required_Price_Fields] = source.[Required_Price_Fields],
        [Default_Parameters] = source.[Default_Parameters],
        [Output_Columns] = source.[Output_Columns],
        [Warmup_Period_Min] = source.[Warmup_Period_Min],
        [Python_Class] = source.[Python_Class],
        [Is_Active] = source.[Is_Active]
WHEN NOT MATCHED BY TARGET THEN
    INSERT (
        [Indicator_Key], [Indicator_Name], [Description],
        [Category], [Required_Price_Fields], [Default_Parameters], [Output_Columns],
        [Warmup_Period_Min], [Python_Class], [Is_Active]
    )
    VALUES (
        source.[Indicator_Key], source.[Indicator_Name], source.[Description],
        source.[Category], source.[Required_Price_Fields], source.[Default_Parameters], source.[Output_Columns],
        source.[Warmup_Period_Min], source.[Python_Class], source.[Is_Active]
    );
GO

DECLARE @atr_id INT = (
    SELECT TOP (1) [Indicator_ID]
    FROM [dbo].[Dim_Indicator_Library]
    WHERE [Indicator_Key] = 'ATR'
);
PRINT 'Extended Dim_Indicator_Library with ATR (Indicator_ID = ' + COALESCE(CAST(@atr_id AS VARCHAR(20)), 'NULL') + ')';
GO

-- NOTE: The following custom indicators are used by Layer 0 but are NOT available
-- in the standard 'ta' library registry. They require custom Python implementation
-- in layer2_signals/signal_engine/indicators/registry.py before Layer 2 can execute them:
--   - detect_swing_points   (used by Support_Resistance family)
--   - volatility_contraction_index / squeeze logic (used by VCP_Breakout family)
-- =============================================================================
