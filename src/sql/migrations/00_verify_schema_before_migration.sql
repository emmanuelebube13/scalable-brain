/*
=============================================================================
PRE-MIGRATION VERIFICATION SCRIPT
=============================================================================

Run this BEFORE applying fix_schema_trade_id_2026_04_05.sql

Purpose: Check current Fact_Live_Trades schema to determine if migration needed

Execution:
    USE ForexBrainDB;
    GO
    -- Paste content below
=============================================================================
*/

USE ForexBrainDB;
GO

PRINT '=== SCHEMA VERIFICATION: Fact_Live_Trades ==='
PRINT ''

-- Check if table exists
IF OBJECT_ID('Fact_Live_Trades', 'U') IS NULL
BEGIN
    PRINT 'ERROR: Fact_Live_Trades table does not exist!'
    RETURN
END

PRINT 'Table exists: Fact_Live_Trades'
PRINT ''

-- List all columns
PRINT 'Current columns:'
SELECT 
    COLUMN_NAME,
    DATA_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'Fact_Live_Trades'
ORDER BY ORDINAL_POSITION;

PRINT ''

-- Check for Trade_ID column
IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS 
           WHERE TABLE_NAME = 'Fact_Live_Trades' AND COLUMN_NAME = 'Trade_ID')
BEGIN
    PRINT '✓ Trade_ID column EXISTS'
    
    -- Check if it's identity
    IF OBJECTPROPERTY(OBJECT_ID('Fact_Live_Trades'), 'TableHasIdentity') IS NOT NULL
    BEGIN
        PRINT '✓ Trade_ID is configured as IDENTITY'
        PRINT ''
        PRINT 'Migration status: ALREADY APPLIED'
    END
    ELSE
    BEGIN
        PRINT '⚠ Trade_ID exists but is NOT an identity column (review needed)'
    END
END
ELSE
BEGIN
    PRINT '✗ Trade_ID column MISSING'
    PRINT ''
    PRINT 'Migration status: REQUIRED - run fix_schema_trade_id_2026_04_05.sql'
END

PRINT ''

-- Show row count
DECLARE @RowCount INT = (SELECT COUNT(*) FROM Fact_Live_Trades);
PRINT 'Row count: ' + CAST(@RowCount AS VARCHAR(10)) + ' records';

PRINT ''
PRINT 'Next step: If Trade_ID is missing, execute fix_schema_trade_id_2026_04_05.sql'
GO
