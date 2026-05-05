/*
Layer 0 bypass migration:
- Maps every active strategy to every active asset
- Disables qualification gating by forcing Is_Active/Is_Qualified flags where present

Run against ForexBrainDB when you want all strategy x asset combinations enabled.
*/

SET XACT_ABORT ON;
BEGIN TRANSACTION;

-- 1) Ensure strategy reference table is active
IF COL_LENGTH('Dim_Strategy', 'Is_Active') IS NOT NULL
BEGIN
    UPDATE Dim_Strategy
    SET Is_Active = 1
    WHERE ISNULL(Is_Active, 0) <> 1;
END;

IF COL_LENGTH('Dim_Strategy_Registry', 'Is_Active') IS NOT NULL
BEGIN
    UPDATE Dim_Strategy_Registry
    SET Is_Active = 1
    WHERE ISNULL(Is_Active, 0) <> 1;
END;

-- 2) Cross-map all active assets with all active strategies
;WITH strategy_source AS (
    SELECT DISTINCT Strategy_ID
    FROM Dim_Strategy
    WHERE ISNULL(Is_Active, 1) = 1
),
asset_source AS (
    SELECT DISTINCT Asset_ID
    FROM Dim_Asset
    WHERE ISNULL(Is_Active, 1) = 1
),
mapping_source AS (
    SELECT s.Strategy_ID, a.Asset_ID
    FROM strategy_source s
    CROSS JOIN asset_source a
)
MERGE Dim_Strategy_Asset_Mapping AS target
USING mapping_source AS src
ON target.Strategy_ID = src.Strategy_ID AND target.Asset_ID = src.Asset_ID
WHEN MATCHED THEN
    UPDATE SET
        Is_Active = 1,
        Is_Qualified = 1,
        Updated_At = GETUTCDATE()
WHEN NOT MATCHED BY TARGET THEN
    INSERT (Strategy_ID, Asset_ID, Is_Active, Is_Qualified, Created_At, Updated_At)
    VALUES (
        src.Strategy_ID,
        src.Asset_ID,
        1,
        1,
        GETUTCDATE(),
        GETUTCDATE()
    );

-- 3) Optional: remove historical inactive rows that are no longer represented
UPDATE Dim_Strategy_Asset_Mapping
SET Is_Active = 1
WHERE ISNULL(Is_Active, 0) <> 1;

UPDATE Dim_Strategy_Asset_Mapping
SET Is_Qualified = 1
WHERE ISNULL(Is_Qualified, 0) <> 1;

COMMIT TRANSACTION;

SELECT
    COUNT(*) AS total_mappings,
    SUM(CASE WHEN ISNULL(Is_Active, 0) = 1 THEN 1 ELSE 0 END) AS active_mappings,
    SUM(CASE WHEN ISNULL(Is_Qualified, 0) = 1 THEN 1 ELSE 0 END) AS qualified_mappings
FROM Dim_Strategy_Asset_Mapping;
