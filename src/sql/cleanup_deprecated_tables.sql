/*
=============================================================================
Script:       cleanup_deprecated_tables.sql
Author:       Emmanuel Mbachu
Date:         2026-04-03
Description:  Remove deprecated and unused tables from ForexBrainDB.
              This script cleans up tables that have been replaced by newer
              implementations or are no longer referenced in the system.
              
TABLES TO BE DROPPED:
  1. Fact_Market_Regime        (deprecated, replaced by Fact_Market_Regime_V2)
  2. Fact_Daily_Regime         (deprecated, legacy daily regime classification)
  3. Dim_Strategy_Registry     (deprecated, replaced by Dim_Strategy + Config + Mapping)
  4. Dim_Model_Metadata        (unused, never referenced)

NOTE: Run this script only after verifying that:
  - No active code references these tables
  - Backups have been taken
  - All data has been migrated to replacement tables

=============================================================================
*/

USE ForexBrainDB;
GO

-- ================================================
-- 1. DROP Fact_Market_Regime (replaced by V2)
-- ================================================
IF OBJECT_ID('dbo.Fact_Market_Regime', 'U') IS NOT NULL
BEGIN
    PRINT '[CLEANUP] Dropping Fact_Market_Regime (deprecated)...';
    DROP TABLE dbo.Fact_Market_Regime;
    PRINT '✅ Fact_Market_Regime dropped successfully.';
END
ELSE
BEGIN
    PRINT '⚠️ Fact_Market_Regime not found (may already be dropped).';
END
GO

-- ================================================
-- 2. DROP Fact_Daily_Regime (legacy table)
-- ================================================
IF OBJECT_ID('dbo.Fact_Daily_Regime', 'U') IS NOT NULL
BEGIN
    PRINT '[CLEANUP] Dropping Fact_Daily_Regime (legacy)...';
    DROP TABLE dbo.Fact_Daily_Regime;
    PRINT '✅ Fact_Daily_Regime dropped successfully.';
END
ELSE
BEGIN
    PRINT '⚠️ Fact_Daily_Regime not found (may already be dropped).';
END
GO

-- ================================================
-- 3. DROP Dim_Strategy_Registry (replaced by new strategy tables)
-- ================================================
IF OBJECT_ID('dbo.Dim_Strategy_Registry', 'U') IS NOT NULL
BEGIN
    PRINT '[CLEANUP] Dropping Dim_Strategy_Registry (replaced by Dim_Strategy + Dim_Strategy_Config + Dim_Strategy_Asset_Mapping)...';
    DROP TABLE dbo.Dim_Strategy_Registry;
    PRINT '✅ Dim_Strategy_Registry dropped successfully.';
END
ELSE IF OBJECT_ID('dbo.Dim_Strategy_Registry_Deprecated', 'U') IS NOT NULL
BEGIN
    PRINT '[CLEANUP] Dim_Strategy_Registry already renamed to Dim_Strategy_Registry_Deprecated. Dropping...';
    DROP TABLE dbo.Dim_Strategy_Registry_Deprecated;
    PRINT '✅ Dim_Strategy_Registry_Deprecated dropped successfully.';
END
ELSE
BEGIN
    PRINT '⚠️ Dim_Strategy_Registry not found (may already be dropped).';
END
GO

-- ================================================
-- 4. DROP Dim_Model_Metadata (unused)
-- ================================================
IF OBJECT_ID('dbo.Dim_Model_Metadata', 'U') IS NOT NULL
BEGIN
    PRINT '[CLEANUP] Dropping Dim_Model_Metadata (unused)...';
    DROP TABLE dbo.Dim_Model_Metadata;
    PRINT '✅ Dim_Model_Metadata dropped successfully.';
END
ELSE
BEGIN
    PRINT '⚠️ Dim_Model_Metadata not found (may already be dropped).';
END
GO

-- ================================================
-- VERIFICATION
-- ================================================
PRINT '';
PRINT '========== CLEANUP VERIFICATION ==========';
PRINT 'Remaining active tables in ForexBrainDB:';
SELECT 
    TABLE_NAME,
    CASE 
        WHEN TABLE_NAME LIKE 'Dim_%' THEN 'DIMENSION'
        WHEN TABLE_NAME LIKE 'Fact_%' THEN 'FACT'
        ELSE 'OTHER'
    END AS TABLE_TYPE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'dbo'
ORDER BY TABLE_TYPE, TABLE_NAME;

PRINT '';
PRINT '✅ Cleanup script completed successfully!';
