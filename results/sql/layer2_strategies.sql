-- =============================================================================
-- AUTO-GENERATED Layer 2 Strategy Seed Script
-- Generated: 2026-04-04T09:46:59.283357
-- Source: Layer 0 Strategy Qualification Engine
-- =============================================================================
USE ForexBrainDB;
GO

-- Deactivate currently active Layer 2 strategy records before promoting new ones
UPDATE [dbo].[Dim_Strategy_Asset_Mapping]
SET Is_Active = 0,
    Effective_To = COALESCE(Effective_To, GETUTCDATE())
WHERE Is_Active = 1;

UPDATE [dbo].[Dim_Strategy_Config]
SET Is_Active = 0,
    Effective_To = COALESCE(Effective_To, GETUTCDATE())
WHERE Is_Active = 1;

UPDATE [dbo].[Dim_Strategy]
SET Is_Active = 0,
    Modified_Date = GETUTCDATE()
WHERE Is_Active = 1;


-- Strategy: Range_Stochastic_Divergence
MERGE [dbo].[Dim_Strategy] AS target
USING (VALUES ('Range_Stochastic_Divergence', 'Range_Stochastic_Divergence', 'Stochastic divergence detection (14,3).', 'MEAN_REVERSION', 1))
    AS source (Strategy_Key, Strategy_Name, [Description], Strategy_Type, Is_Active)
ON target.Strategy_Key = source.Strategy_Key
WHEN MATCHED THEN
    UPDATE SET
        Strategy_Name = source.Strategy_Name,
        [Description] = source.[Description],
        Strategy_Type = source.Strategy_Type,
        Is_Active = source.Is_Active,
        Modified_Date = GETUTCDATE()
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_Key, Strategy_Name, [Description], Strategy_Type, Is_Active)
    VALUES (source.Strategy_Key, source.Strategy_Name, source.[Description], source.Strategy_Type, source.Is_Active);
DECLARE @sid_Range_Stochastic_Divergence INT = (SELECT Strategy_ID FROM [dbo].[Dim_Strategy] WHERE Strategy_Key = 'Range_Stochastic_Divergence');


MERGE [dbo].[Dim_Strategy_Config] AS target
USING (VALUES (@sid_Range_Stochastic_Divergence, '1.0.0', '652ea35709fd68ca9ecf37b84c1a514def9f9de373ff5d85ec3a035f89b448fd', 'H4', '[{"indicator_key": "STOCH", "instance_name": "STOCH_14", "params": {"window": 14, "smooth_window": 3}, "output_column": "stoch"}]', '[{"rule_id": "LONG_STOCH_CROSS", "description": "Stochastic K crosses above 20 from oversold", "signal_value": 1, "conditions": [{"left": "STOCH_14.prev", "operator": "<=", "right": 20}, {"left": "STOCH_14", "operator": ">", "right": 20}], "logic": "AND"}, {"rule_id": "SHORT_STOCH_CROSS", "description": "Stochastic K crosses below 80 from overbought", "signal_value": -1, "conditions": [{"left": "STOCH_14.prev", "operator": ">=", "right": 80}, {"left": "STOCH_14", "operator": "<", "right": 80}], "logic": "AND"}]', '[{"note": "Divergence detection is NOT expressible in Layer 2 rule syntax. This config falls back to standard stochastic cross rules. Manual review required."}]', GETUTCDATE(), NULL, 1))
    AS source (Strategy_ID, Config_Version, Config_Hash, Granularity, Indicator_Configs, Signal_Rules, Risk_Filters, Effective_From, Effective_To, Is_Active)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Config_Version = source.Config_Version
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_Hash = source.Config_Hash,
        Granularity = source.Granularity,
        Indicator_Configs = source.Indicator_Configs,
        Signal_Rules = source.Signal_Rules,
        Risk_Filters = source.Risk_Filters,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Config_Version, Config_Hash, Granularity, Indicator_Configs, Signal_Rules, Risk_Filters, Effective_From, Effective_To, Is_Active)
    VALUES (source.Strategy_ID, source.Config_Version, source.Config_Hash, source.Granularity, source.Indicator_Configs, source.Signal_Rules, source.Risk_Filters, source.Effective_From, source.Effective_To, source.Is_Active);
DECLARE @cid_Range_Stochastic_Divergence INT = (SELECT Config_ID FROM [dbo].[Dim_Strategy_Config]
    WHERE Strategy_ID = @sid_Range_Stochastic_Divergence AND Config_Version = '1.0.0' AND Granularity = 'H4');


MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Stochastic_Divergence, 1, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Stochastic_Divergence), @cid_Range_Stochastic_Divergence, 100, GETUTCDATE(), NULL, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active);


MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Stochastic_Divergence, 2, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Stochastic_Divergence), @cid_Range_Stochastic_Divergence, 100, GETUTCDATE(), NULL, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active);


MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Stochastic_Divergence, 3, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Stochastic_Divergence), @cid_Range_Stochastic_Divergence, 100, GETUTCDATE(), NULL, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active);


MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Stochastic_Divergence, 4, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Stochastic_Divergence), @cid_Range_Stochastic_Divergence, 100, GETUTCDATE(), NULL, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active);


MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Stochastic_Divergence, 5, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Stochastic_Divergence), @cid_Range_Stochastic_Divergence, 100, GETUTCDATE(), NULL, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active);


-- =============================================================================
-- END OF SEED SCRIPT
-- =============================================================================
GO
