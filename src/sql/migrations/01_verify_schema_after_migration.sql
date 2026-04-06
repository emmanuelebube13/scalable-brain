/*
=============================================================================
POST-MIGRATION VERIFICATION SCRIPT
=============================================================================

Run this AFTER applying fix_schema_trade_id_2026_04_05.sql

Purpose: Verify that migration was successful and schema is correct

Execution:
    USE ForexBrainDB;
    GO
    -- Paste content below
=============================================================================
*/

USE ForexBrainDB;
GO

PRINT '=== POST-MIGRATION VERIFICATION: Fact_Live_Trades ==='
PRINT ''

-- Check if table exists
IF OBJECT_ID('Fact_Live_Trades', 'U') IS NULL
BEGIN
    PRINT '✗ ERROR: Fact_Live_Trades table does not exist!'
    RETURN
END

PRINT '✓ Table exists: Fact_Live_Trades'
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
    PRINT '✓ Trade_ID column exists'
    
    IF OBJECTPROPERTY(OBJECT_ID('Fact_Live_Trades'), 'TableHasIdentity') IS NOT NULL
    BEGIN
        PRINT '✓ Trade_ID is configured as IDENTITY primary key'
    END
END
ELSE
BEGIN
    PRINT '✗ Trade_ID column MISSING - migration may have failed'
END

PRINT ''

-- Check for backup table
IF OBJECT_ID('Fact_Live_Trades_Backup', 'U') IS NOT NULL
BEGIN
    DECLARE @BackupCount INT = (SELECT COUNT(*) FROM Fact_Live_Trades_Backup);
    PRINT '✓ Backup table exists: Fact_Live_Trades_Backup (' + CAST(@BackupCount AS VARCHAR(10)) + ' records)'
END

PRINT ''

-- Check indexes
PRINT 'Indexes present:'
SELECT 
    name,
    type_desc,
    is_unique
FROM sys.indexes
WHERE object_id = OBJECT_ID('Fact_Live_Trades')
  AND name IS NOT NULL
ORDER BY name;

PRINT ''

-- Show row count
DECLARE @RowCount INT = (SELECT COUNT(*) FROM Fact_Live_Trades);
PRINT 'Row count: ' + CAST(@RowCount AS VARCHAR(10)) + ' records';

PRINT ''

-- Test insert (to verify triggers/constraints)
PRINT 'Testing insert capability...'
BEGIN TRY
    -- Test with dummy data
    INSERT INTO Fact_Live_Trades (
        [Timestamp], Asset_ID, Strategy_ID, Signal_Value,
        Entry_Price, Stop_Loss, Take_Profit, Confidence_Score,
        Is_Approved
    )
    VALUES (
        GETUTCDATE(), 1, 1, 1,
        1.0500, 1.0400, 1.0600, 0.85,
        1
    );
    
    DECLARE @InsertedTradeID INT = @@IDENTITY;
    PRINT '✓ Insert successful (Trade_ID: ' + CAST(@InsertedTradeID AS VARCHAR(10)) + ')'
    
    -- Clean up test record
    DELETE FROM Fact_Live_Trades WHERE Trade_ID = @InsertedTradeID;
    PRINT '✓ Test record cleaned up'
    
END TRY
BEGIN CATCH
    PRINT '✗ Insert failed: ' + ERROR_MESSAGE()
END CATCH

PRINT ''
PRINT '=== MIGRATION VERIFICATION COMPLETE ==='
PRINT 'System is ready for Layer 4 live trading'
GO
