-- =============================================================================
-- AUTO-GENERATED Layer 2 Strategy Seed Script (BYPASS MODE)
-- Generated: 2026-04-06T19:45:14.683980
-- Source: Layer 0 Strategy Qualification Engine (BYPASS MODE)
-- NOTE: All strategies are mapped to all assets without backtest qualification
-- REGIME FILTERING: Range-based regimes -> Range strategies, Trending regimes -> Trend strategies
-- =============================================================================
USE ForexBrainDB;
GO

-- Regime-Based Strategy Classification:
--   RANGING: Range_Bollinger_H1, Range_Bollinger_H4, Range_Bollinger_Aggressive, Range_Stochastic_Divergence
--   TRENDING: Trend_EMA_ADX_H1, Trend_EMA_ADX_H4, Trend_EMA_ADX_MultiTF, Trend_Donchian_H1, Trend_Donchian_H4, Trend_Donchian_VCP

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

-- Strategy: Trend_EMA_ADX_H1 (Regime: TRENDING)
MERGE [dbo].[Dim_Strategy] AS target
USING (VALUES ('Trend_EMA_ADX_H1', 'Trend_EMA_ADX_H1', 'H1 EMA crossover (10/20) with ADX filter. [REGIME:TRENDING]', 'TREND', 1))
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
DECLARE @sid_Trend_EMA_ADX_H1 INT = (SELECT Strategy_ID FROM [dbo].[Dim_Strategy] WHERE Strategy_Key = 'Trend_EMA_ADX_H1');
MERGE [dbo].[Dim_Strategy_Config] AS target
USING (VALUES (@sid_Trend_EMA_ADX_H1, '1.0.0', '1f49f636eaecb5dbc6c848cecceb8625b3d37f351ff92c401d3bd58cf74b214a', 'H1', '[{"indicator_key": "EMA", "instance_name": "EMA_10", "params": {"window": 10}, "output_column": "ema_indicator"}, {"indicator_key": "EMA", "instance_name": "EMA_20", "params": {"window": 20}, "output_column": "ema_indicator"}, {"indicator_key": "ADX", "instance_name": "ADX_14", "params": {"window": 14}, "output_column": "adx"}]', '[{"rule_id": "LONG_EMA_ADX", "description": "EMA10 crosses above EMA20 with ADX > 25", "signal_value": 1, "conditions": [{"left": "EMA_10", "operator": "cross_above", "right": "EMA_20"}, {"left": "ADX_14", "operator": ">", "right": 25}], "logic": "AND"}, {"rule_id": "SHORT_EMA_ADX", "description": "EMA10 crosses below EMA20 with ADX > 25", "signal_value": -1, "conditions": [{"left": "EMA_10", "operator": "cross_below", "right": "EMA_20"}, {"left": "ADX_14", "operator": ">", "right": 25}], "logic": "AND"}]', NULL, GETUTCDATE(), NULL, 1))
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
DECLARE @cid_Trend_EMA_ADX_H1 INT = (SELECT Config_ID FROM [dbo].[Dim_Strategy_Config]
    WHERE Strategy_ID = @sid_Trend_EMA_ADX_H1 AND Config_Version = '1.0.0' AND Granularity = 'H1');
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_EMA_ADX_H1, 5, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_EMA_ADX_H1), @cid_Trend_EMA_ADX_H1, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_EMA_ADX_H1, 3, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_EMA_ADX_H1), @cid_Trend_EMA_ADX_H1, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_EMA_ADX_H1, 2, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_EMA_ADX_H1), @cid_Trend_EMA_ADX_H1, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_EMA_ADX_H1, 1, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_EMA_ADX_H1), @cid_Trend_EMA_ADX_H1, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_EMA_ADX_H1, 4, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_EMA_ADX_H1), @cid_Trend_EMA_ADX_H1, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);

-- Strategy: Trend_EMA_ADX_H4 (Regime: TRENDING)
MERGE [dbo].[Dim_Strategy] AS target
USING (VALUES ('Trend_EMA_ADX_H4', 'Trend_EMA_ADX_H4', 'H4 EMA crossover (20/50) with ADX filter. [REGIME:TRENDING]', 'TREND', 1))
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
DECLARE @sid_Trend_EMA_ADX_H4 INT = (SELECT Strategy_ID FROM [dbo].[Dim_Strategy] WHERE Strategy_Key = 'Trend_EMA_ADX_H4');
MERGE [dbo].[Dim_Strategy_Config] AS target
USING (VALUES (@sid_Trend_EMA_ADX_H4, '1.0.0', 'bcb4315f2bd6c95e0f262654bb8b87d2d406dc8008a5d2f6424d81643befe624', 'H4', '[{"indicator_key": "EMA", "instance_name": "EMA_20", "params": {"window": 20}, "output_column": "ema_indicator"}, {"indicator_key": "EMA", "instance_name": "EMA_50", "params": {"window": 50}, "output_column": "ema_indicator"}, {"indicator_key": "ADX", "instance_name": "ADX_14", "params": {"window": 14}, "output_column": "adx"}]', '[{"rule_id": "LONG_EMA_ADX", "description": "EMA20 crosses above EMA50 with ADX > 25", "signal_value": 1, "conditions": [{"left": "EMA_20", "operator": "cross_above", "right": "EMA_50"}, {"left": "ADX_14", "operator": ">", "right": 25}], "logic": "AND"}, {"rule_id": "SHORT_EMA_ADX", "description": "EMA20 crosses below EMA50 with ADX > 25", "signal_value": -1, "conditions": [{"left": "EMA_20", "operator": "cross_below", "right": "EMA_50"}, {"left": "ADX_14", "operator": ">", "right": 25}], "logic": "AND"}]', NULL, GETUTCDATE(), NULL, 1))
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
DECLARE @cid_Trend_EMA_ADX_H4 INT = (SELECT Config_ID FROM [dbo].[Dim_Strategy_Config]
    WHERE Strategy_ID = @sid_Trend_EMA_ADX_H4 AND Config_Version = '1.0.0' AND Granularity = 'H4');
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_EMA_ADX_H4, 5, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_EMA_ADX_H4), @cid_Trend_EMA_ADX_H4, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_EMA_ADX_H4, 3, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_EMA_ADX_H4), @cid_Trend_EMA_ADX_H4, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_EMA_ADX_H4, 2, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_EMA_ADX_H4), @cid_Trend_EMA_ADX_H4, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_EMA_ADX_H4, 1, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_EMA_ADX_H4), @cid_Trend_EMA_ADX_H4, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_EMA_ADX_H4, 4, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_EMA_ADX_H4), @cid_Trend_EMA_ADX_H4, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);

-- Strategy: Trend_EMA_ADX_MultiTF (Regime: TRENDING)
MERGE [dbo].[Dim_Strategy] AS target
USING (VALUES ('Trend_EMA_ADX_MultiTF', 'Trend_EMA_ADX_MultiTF', 'Multi-timeframe EMA crossover (H4 primary / H1 confirmation) with ADX filter. [REGIME:TRENDING]', 'TREND', 1))
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
DECLARE @sid_Trend_EMA_ADX_MultiTF INT = (SELECT Strategy_ID FROM [dbo].[Dim_Strategy] WHERE Strategy_Key = 'Trend_EMA_ADX_MultiTF');
MERGE [dbo].[Dim_Strategy_Config] AS target
USING (VALUES (@sid_Trend_EMA_ADX_MultiTF, '1.0.0', '02b764944f1e1efd67c4e25aa7f918936413de4cf635e223d1390cfeaa098548', 'H4', '[{"indicator_key": "EMA", "instance_name": "EMA_20", "params": {"window": 20}, "output_column": "ema_indicator"}, {"indicator_key": "EMA", "instance_name": "EMA_50", "params": {"window": 50}, "output_column": "ema_indicator"}, {"indicator_key": "ADX", "instance_name": "ADX_14", "params": {"window": 14}, "output_column": "adx"}]', '[{"rule_id": "LONG_EMA_ADX", "description": "EMA20 crosses above EMA50 with ADX > 25", "signal_value": 1, "conditions": [{"left": "EMA_20", "operator": "cross_above", "right": "EMA_50"}, {"left": "ADX_14", "operator": ">", "right": 25}], "logic": "AND"}, {"rule_id": "SHORT_EMA_ADX", "description": "EMA20 crosses below EMA50 with ADX > 25", "signal_value": -1, "conditions": [{"left": "EMA_20", "operator": "cross_below", "right": "EMA_50"}, {"left": "ADX_14", "operator": ">", "right": 25}], "logic": "AND"}]', '[{"note": "MultiTF variant: H1 confirmation and D1 macro alignment are enforced in Layer 0. Layer 2 runs H4 rules; combine with H1 config for full confluence."}]', GETUTCDATE(), NULL, 1))
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
DECLARE @cid_Trend_EMA_ADX_MultiTF INT = (SELECT Config_ID FROM [dbo].[Dim_Strategy_Config]
    WHERE Strategy_ID = @sid_Trend_EMA_ADX_MultiTF AND Config_Version = '1.0.0' AND Granularity = 'H4');
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_EMA_ADX_MultiTF, 5, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_EMA_ADX_MultiTF), @cid_Trend_EMA_ADX_MultiTF, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_EMA_ADX_MultiTF, 3, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_EMA_ADX_MultiTF), @cid_Trend_EMA_ADX_MultiTF, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_EMA_ADX_MultiTF, 2, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_EMA_ADX_MultiTF), @cid_Trend_EMA_ADX_MultiTF, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_EMA_ADX_MultiTF, 1, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_EMA_ADX_MultiTF), @cid_Trend_EMA_ADX_MultiTF, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_EMA_ADX_MultiTF, 4, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_EMA_ADX_MultiTF), @cid_Trend_EMA_ADX_MultiTF, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);

-- Strategy: Trend_Donchian_H1 (Regime: TRENDING)
MERGE [dbo].[Dim_Strategy] AS target
USING (VALUES ('Trend_Donchian_H1', 'Trend_Donchian_H1', 'H1 Donchian Channel breakout (10) with ADX filter. [REGIME:TRENDING]', 'BREAKOUT', 1))
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
DECLARE @sid_Trend_Donchian_H1 INT = (SELECT Strategy_ID FROM [dbo].[Dim_Strategy] WHERE Strategy_Key = 'Trend_Donchian_H1');
MERGE [dbo].[Dim_Strategy_Config] AS target
USING (VALUES (@sid_Trend_Donchian_H1, '1.0.0', 'd4d581f429865162811af4f1da612bd95c20f00d20a2487d42606beb45fba060', 'H1', '[{"indicator_key": "DONCHIAN", "instance_name": "DONCHIAN_10", "params": {"window": 10}, "output_columns": ["donchian_channel_hband", "donchian_channel_lband"]}, {"indicator_key": "ADX", "instance_name": "ADX_14", "params": {"window": 14}, "output_column": "adx"}]', '[{"rule_id": "LONG_DONCHIAN_ADX", "description": "Close breaks above Donchian high band with ADX > 25", "signal_value": 1, "conditions": [{"left": "Close", "operator": ">=", "right": "DONCHIAN_10.hband"}, {"left": "ADX_14", "operator": ">", "right": 25}], "logic": "AND"}, {"rule_id": "SHORT_DONCHIAN_ADX", "description": "Close breaks below Donchian low band with ADX > 25", "signal_value": -1, "conditions": [{"left": "Close", "operator": "<=", "right": "DONCHIAN_10.lband"}, {"left": "ADX_14", "operator": ">", "right": 25}], "logic": "AND"}]', '[{"note": "Layer 0 uses a 1-bar shifted band to avoid look-ahead. Current Layer 2 evaluator does not support arbitrary shifts; verify execution logic."}]', GETUTCDATE(), NULL, 1))
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
DECLARE @cid_Trend_Donchian_H1 INT = (SELECT Config_ID FROM [dbo].[Dim_Strategy_Config]
    WHERE Strategy_ID = @sid_Trend_Donchian_H1 AND Config_Version = '1.0.0' AND Granularity = 'H1');
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_Donchian_H1, 5, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_Donchian_H1), @cid_Trend_Donchian_H1, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_Donchian_H1, 3, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_Donchian_H1), @cid_Trend_Donchian_H1, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_Donchian_H1, 2, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_Donchian_H1), @cid_Trend_Donchian_H1, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_Donchian_H1, 1, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_Donchian_H1), @cid_Trend_Donchian_H1, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_Donchian_H1, 4, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_Donchian_H1), @cid_Trend_Donchian_H1, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);

-- Strategy: Trend_Donchian_H4 (Regime: TRENDING)
MERGE [dbo].[Dim_Strategy] AS target
USING (VALUES ('Trend_Donchian_H4', 'Trend_Donchian_H4', 'H4 Donchian Channel breakout (20) with ADX filter. [REGIME:TRENDING]', 'BREAKOUT', 1))
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
DECLARE @sid_Trend_Donchian_H4 INT = (SELECT Strategy_ID FROM [dbo].[Dim_Strategy] WHERE Strategy_Key = 'Trend_Donchian_H4');
MERGE [dbo].[Dim_Strategy_Config] AS target
USING (VALUES (@sid_Trend_Donchian_H4, '1.0.0', '84957f55ecd54f05648d5920aed57c32b74614a1f42c32d5abc7ec6c7c1cb322', 'H4', '[{"indicator_key": "DONCHIAN", "instance_name": "DONCHIAN_20", "params": {"window": 20}, "output_columns": ["donchian_channel_hband", "donchian_channel_lband"]}, {"indicator_key": "ADX", "instance_name": "ADX_14", "params": {"window": 14}, "output_column": "adx"}]', '[{"rule_id": "LONG_DONCHIAN_ADX", "description": "Close breaks above Donchian high band with ADX > 25", "signal_value": 1, "conditions": [{"left": "Close", "operator": ">=", "right": "DONCHIAN_20.hband"}, {"left": "ADX_14", "operator": ">", "right": 25}], "logic": "AND"}, {"rule_id": "SHORT_DONCHIAN_ADX", "description": "Close breaks below Donchian low band with ADX > 25", "signal_value": -1, "conditions": [{"left": "Close", "operator": "<=", "right": "DONCHIAN_20.lband"}, {"left": "ADX_14", "operator": ">", "right": 25}], "logic": "AND"}]', '[{"note": "Layer 0 uses a 1-bar shifted band to avoid look-ahead. Current Layer 2 evaluator does not support arbitrary shifts; verify execution logic."}]', GETUTCDATE(), NULL, 1))
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
DECLARE @cid_Trend_Donchian_H4 INT = (SELECT Config_ID FROM [dbo].[Dim_Strategy_Config]
    WHERE Strategy_ID = @sid_Trend_Donchian_H4 AND Config_Version = '1.0.0' AND Granularity = 'H4');
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_Donchian_H4, 5, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_Donchian_H4), @cid_Trend_Donchian_H4, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_Donchian_H4, 3, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_Donchian_H4), @cid_Trend_Donchian_H4, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_Donchian_H4, 2, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_Donchian_H4), @cid_Trend_Donchian_H4, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_Donchian_H4, 1, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_Donchian_H4), @cid_Trend_Donchian_H4, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_Donchian_H4, 4, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_Donchian_H4), @cid_Trend_Donchian_H4, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);

-- Strategy: Trend_Donchian_VCP (Regime: TRENDING)
MERGE [dbo].[Dim_Strategy] AS target
USING (VALUES ('Trend_Donchian_VCP', 'Trend_Donchian_VCP', 'Donchian VCP breakout (20) with squeeze filter. [REGIME:TRENDING]', 'BREAKOUT', 1))
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
DECLARE @sid_Trend_Donchian_VCP INT = (SELECT Strategy_ID FROM [dbo].[Dim_Strategy] WHERE Strategy_Key = 'Trend_Donchian_VCP');
MERGE [dbo].[Dim_Strategy_Config] AS target
USING (VALUES (@sid_Trend_Donchian_VCP, '1.0.0', 'fbc30d26e9e1d935096a613c5cebb86ae8a66c31e6bc8cae5db114d192ad2c31', 'H4', '[{"indicator_key": "DONCHIAN", "instance_name": "DONCHIAN_20", "params": {"window": 20}, "output_columns": ["donchian_channel_hband", "donchian_channel_lband"]}, {"indicator_key": "ADX", "instance_name": "ADX_14", "params": {"window": 14}, "output_column": "adx"}]', '[{"rule_id": "LONG_DONCHIAN_ADX", "description": "Close breaks above Donchian high band with ADX > 25", "signal_value": 1, "conditions": [{"left": "Close", "operator": ">=", "right": "DONCHIAN_20.hband"}, {"left": "ADX_14", "operator": ">", "right": 25}], "logic": "AND"}, {"rule_id": "SHORT_DONCHIAN_ADX", "description": "Close breaks below Donchian low band with ADX > 25", "signal_value": -1, "conditions": [{"left": "Close", "operator": "<=", "right": "DONCHIAN_20.lband"}, {"left": "ADX_14", "operator": ">", "right": 25}], "logic": "AND"}]', '[{"note": "VCP squeeze filter is NOT expressible in Layer 2 rule syntax. Review before production: implement custom indicator or use Layer 3 ML gatekeeper."}]', GETUTCDATE(), NULL, 1))
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
DECLARE @cid_Trend_Donchian_VCP INT = (SELECT Config_ID FROM [dbo].[Dim_Strategy_Config]
    WHERE Strategy_ID = @sid_Trend_Donchian_VCP AND Config_Version = '1.0.0' AND Granularity = 'H4');
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_Donchian_VCP, 5, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_Donchian_VCP), @cid_Trend_Donchian_VCP, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_Donchian_VCP, 3, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_Donchian_VCP), @cid_Trend_Donchian_VCP, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_Donchian_VCP, 2, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_Donchian_VCP), @cid_Trend_Donchian_VCP, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_Donchian_VCP, 1, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_Donchian_VCP), @cid_Trend_Donchian_VCP, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Trend_Donchian_VCP, 4, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Trend_Donchian_VCP), @cid_Trend_Donchian_VCP, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);

-- Strategy: Range_Bollinger_H1 (Regime: RANGING)
MERGE [dbo].[Dim_Strategy] AS target
USING (VALUES ('Range_Bollinger_H1', 'Range_Bollinger_H1', 'H1 Bollinger Band mean reversion (10,2) with RSI(7). [REGIME:RANGING]', 'RANGE', 1))
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
DECLARE @sid_Range_Bollinger_H1 INT = (SELECT Strategy_ID FROM [dbo].[Dim_Strategy] WHERE Strategy_Key = 'Range_Bollinger_H1');
MERGE [dbo].[Dim_Strategy_Config] AS target
USING (VALUES (@sid_Range_Bollinger_H1, '1.0.0', '723439f88e08076d2d84df0d7f1e694b088db1acfd4ddf9c64094a824eee0adc', 'H1', '[{"indicator_key": "BB", "instance_name": "BB_10", "params": {"window": 10, "window_dev": 2}, "output_columns": ["bollinger_hband", "bollinger_lband"]}, {"indicator_key": "RSI", "instance_name": "RSI_7", "params": {"window": 7}, "output_column": "rsi"}]', '[{"rule_id": "LONG_BB_RSI", "description": "Price at lower Bollinger band with RSI oversold", "signal_value": 1, "conditions": [{"left": "Close", "operator": "<=", "right": "BB_10.lband"}, {"left": "RSI_7", "operator": "<", "right": 30}], "logic": "AND"}, {"rule_id": "SHORT_BB_RSI", "description": "Price at upper Bollinger band with RSI overbought", "signal_value": -1, "conditions": [{"left": "Close", "operator": ">=", "right": "BB_10.hband"}, {"left": "RSI_7", "operator": ">", "right": 70}], "logic": "AND"}]', '[{"note": "Layer 0 squeeze filter and cross-into-zone logic are not expressed in current Layer 2 rule syntax."}]', GETUTCDATE(), NULL, 1))
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
DECLARE @cid_Range_Bollinger_H1 INT = (SELECT Config_ID FROM [dbo].[Dim_Strategy_Config]
    WHERE Strategy_ID = @sid_Range_Bollinger_H1 AND Config_Version = '1.0.0' AND Granularity = 'H1');
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Bollinger_H1, 5, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Bollinger_H1), @cid_Range_Bollinger_H1, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Bollinger_H1, 3, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Bollinger_H1), @cid_Range_Bollinger_H1, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Bollinger_H1, 2, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Bollinger_H1), @cid_Range_Bollinger_H1, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Bollinger_H1, 1, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Bollinger_H1), @cid_Range_Bollinger_H1, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Bollinger_H1, 4, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Bollinger_H1), @cid_Range_Bollinger_H1, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);

-- Strategy: Range_Bollinger_H4 (Regime: RANGING)
MERGE [dbo].[Dim_Strategy] AS target
USING (VALUES ('Range_Bollinger_H4', 'Range_Bollinger_H4', 'H4 Bollinger Band mean reversion (20,2) with RSI(14). [REGIME:RANGING]', 'RANGE', 1))
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
DECLARE @sid_Range_Bollinger_H4 INT = (SELECT Strategy_ID FROM [dbo].[Dim_Strategy] WHERE Strategy_Key = 'Range_Bollinger_H4');
MERGE [dbo].[Dim_Strategy_Config] AS target
USING (VALUES (@sid_Range_Bollinger_H4, '1.0.0', '5c13014946893a0ace979657f795c588b1501d9f1d79a0be3fcf98e3e0cdda62', 'H4', '[{"indicator_key": "BB", "instance_name": "BB_20", "params": {"window": 20, "window_dev": 2}, "output_columns": ["bollinger_hband", "bollinger_lband"]}, {"indicator_key": "RSI", "instance_name": "RSI_14", "params": {"window": 14}, "output_column": "rsi"}]', '[{"rule_id": "LONG_BB_RSI", "description": "Price at lower Bollinger band with RSI oversold", "signal_value": 1, "conditions": [{"left": "Close", "operator": "<=", "right": "BB_20.lband"}, {"left": "RSI_14", "operator": "<", "right": 30}], "logic": "AND"}, {"rule_id": "SHORT_BB_RSI", "description": "Price at upper Bollinger band with RSI overbought", "signal_value": -1, "conditions": [{"left": "Close", "operator": ">=", "right": "BB_20.hband"}, {"left": "RSI_14", "operator": ">", "right": 70}], "logic": "AND"}]', '[{"note": "Layer 0 squeeze filter and cross-into-zone logic are not expressed in current Layer 2 rule syntax."}]', GETUTCDATE(), NULL, 1))
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
DECLARE @cid_Range_Bollinger_H4 INT = (SELECT Config_ID FROM [dbo].[Dim_Strategy_Config]
    WHERE Strategy_ID = @sid_Range_Bollinger_H4 AND Config_Version = '1.0.0' AND Granularity = 'H4');
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Bollinger_H4, 5, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Bollinger_H4), @cid_Range_Bollinger_H4, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Bollinger_H4, 3, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Bollinger_H4), @cid_Range_Bollinger_H4, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Bollinger_H4, 2, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Bollinger_H4), @cid_Range_Bollinger_H4, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Bollinger_H4, 1, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Bollinger_H4), @cid_Range_Bollinger_H4, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Bollinger_H4, 4, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Bollinger_H4), @cid_Range_Bollinger_H4, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);

-- Strategy: Range_Bollinger_Aggressive (Regime: RANGING)
MERGE [dbo].[Dim_Strategy] AS target
USING (VALUES ('Range_Bollinger_Aggressive', 'Range_Bollinger_Aggressive', 'Aggressive Bollinger Band (20,1.5) without RSI requirement. [REGIME:RANGING]', 'RANGE', 1))
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
DECLARE @sid_Range_Bollinger_Aggressive INT = (SELECT Strategy_ID FROM [dbo].[Dim_Strategy] WHERE Strategy_Key = 'Range_Bollinger_Aggressive');
MERGE [dbo].[Dim_Strategy_Config] AS target
USING (VALUES (@sid_Range_Bollinger_Aggressive, '1.0.0', '446016d3ac1086f4086580c8c0a4e297593ad8e0df25d6b801974dcec46b3570', 'H4', '[{"indicator_key": "BB", "instance_name": "BB_20", "params": {"window": 20, "window_dev": 1.5}, "output_columns": ["bollinger_hband", "bollinger_lband"]}]', '[{"rule_id": "LONG_BB", "description": "Price at lower Bollinger band (aggressive)", "signal_value": 1, "conditions": [{"left": "Close", "operator": "<=", "right": "BB_20.lband"}], "logic": "AND"}, {"rule_id": "SHORT_BB", "description": "Price at upper Bollinger band (aggressive)", "signal_value": -1, "conditions": [{"left": "Close", "operator": ">=", "right": "BB_20.hband"}], "logic": "AND"}]', '[{"note": "Aggressive variant: no RSI filter. Tighter stops (1.0 ATR)."}]', GETUTCDATE(), NULL, 1))
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
DECLARE @cid_Range_Bollinger_Aggressive INT = (SELECT Config_ID FROM [dbo].[Dim_Strategy_Config]
    WHERE Strategy_ID = @sid_Range_Bollinger_Aggressive AND Config_Version = '1.0.0' AND Granularity = 'H4');
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Bollinger_Aggressive, 5, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Bollinger_Aggressive), @cid_Range_Bollinger_Aggressive, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Bollinger_Aggressive, 3, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Bollinger_Aggressive), @cid_Range_Bollinger_Aggressive, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Bollinger_Aggressive, 2, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Bollinger_Aggressive), @cid_Range_Bollinger_Aggressive, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Bollinger_Aggressive, 1, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Bollinger_Aggressive), @cid_Range_Bollinger_Aggressive, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Bollinger_Aggressive, 4, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Bollinger_Aggressive), @cid_Range_Bollinger_Aggressive, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);

-- Strategy: Range_Stochastic_Divergence (Regime: RANGING)
MERGE [dbo].[Dim_Strategy] AS target
USING (VALUES ('Range_Stochastic_Divergence', 'Range_Stochastic_Divergence', 'Stochastic divergence detection (14,3). [REGIME:RANGING]', 'MEAN_REVERSION', 1))
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
USING (VALUES (@sid_Range_Stochastic_Divergence, 5, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Stochastic_Divergence), @cid_Range_Stochastic_Divergence, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Stochastic_Divergence, 3, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Stochastic_Divergence), @cid_Range_Stochastic_Divergence, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Stochastic_Divergence, 2, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Stochastic_Divergence), @cid_Range_Stochastic_Divergence, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Stochastic_Divergence, 1, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Stochastic_Divergence), @cid_Range_Stochastic_Divergence, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);
MERGE [dbo].[Dim_Strategy_Asset_Mapping] AS target
USING (VALUES (@sid_Range_Stochastic_Divergence, 4, (SELECT Granularity FROM [dbo].[Dim_Strategy_Config] WHERE Config_ID = @cid_Range_Stochastic_Divergence), @cid_Range_Stochastic_Divergence, 100, GETUTCDATE(), NULL, 1, 1))
    AS source (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
ON target.Strategy_ID = source.Strategy_ID
   AND target.Asset_ID = source.Asset_ID
   AND target.Granularity = source.Granularity
WHEN MATCHED THEN
    UPDATE SET
        Config_ID = source.Config_ID,
        Priority = source.Priority,
        Effective_From = source.Effective_From,
        Effective_To = source.Effective_To,
        Is_Active = source.Is_Active,
        Is_Qualified = source.Is_Qualified
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active, Is_Qualified)
    VALUES (source.Strategy_ID, source.Asset_ID, source.Granularity, source.Config_ID, source.Priority, source.Effective_From, source.Effective_To, source.Is_Active, source.Is_Qualified);

-- ============================================================================
-- END OF BYPASS MODE SEED SCRIPT
-- ============================================================================
GO
