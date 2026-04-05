/*
=============================================================================
MIGRATION: Add Trade_ID Primary Key to Fact_Live_Trades
=============================================================================

Date:       2026-04-05
Purpose:    Fix critical database schema issues:
            1. Add Trade_ID as primary key for data integrity
            2. Improve indexing for better query performance
            3. Establish unique constraint on signal combinations

IMPORTANT NOTES:
- This script is idempotent (safe to run multiple times)
- Creates new table with corrected schema
- Preserves all existing data if present
- Adds proper constraints and indexes
- Original table is retained as backup if needed

Execution:
    USE ForexBrainDB;
    GO
    
    -- Review the script
    -- Then execute appropriate section below
=============================================================================
*/

USE ForexBrainDB;
GO

-- Check if migration has already been applied
IF OBJECTPROPERTY(OBJECT_ID('Fact_Live_Trades'), 'TableHasIdentity') IS NULL
BEGIN
    PRINT 'Migration: Adding Trade_ID primary key to Fact_Live_Trades...'
    
    -- Step 1: Backup existing data if table has records
    IF OBJECT_ID('Fact_Live_Trades_Backup', 'U') IS NULL
    BEGIN
        SELECT * INTO Fact_Live_Trades_Backup FROM Fact_Live_Trades;
        PRINT 'Created backup table: Fact_Live_Trades_Backup'
    END
    
    -- Step 2: Drop foreign key constraints if they exist
    IF OBJECT_ID('FK_LiveTrades_Asset', 'F') IS NOT NULL
    BEGIN
        ALTER TABLE Fact_Live_Trades DROP CONSTRAINT FK_LiveTrades_Asset;
        PRINT 'Dropped FK_LiveTrades_Asset constraint'
    END
    
    IF OBJECT_ID('FK_LiveTrades_Strategy', 'F') IS NOT NULL
    BEGIN
        ALTER TABLE Fact_Live_Trades DROP CONSTRAINT FK_LiveTrades_Strategy;
        PRINT 'Dropped FK_LiveTrades_Strategy constraint'
    END
    
    -- Step 3: Rename old table
    EXEC sp_rename 'Fact_Live_Trades', 'Fact_Live_Trades_Old';
    PRINT 'Renamed old table to Fact_Live_Trades_Old'
    
    -- Step 4: Create corrected table with Trade_ID as primary key
    CREATE TABLE Fact_Live_Trades (
        Trade_ID INT PRIMARY KEY IDENTITY(1,1),
        [Timestamp] DATETIME NOT NULL,
        Asset_ID INT NOT NULL,
        Strategy_ID INT NOT NULL,
        Signal_Value INT,
        Entry_Price FLOAT,
        Stop_Loss FLOAT,
        Take_Profit FLOAT,
        Confidence_Score FLOAT,
        Is_Approved INT,
        Actual_Outcome INT,
        
        -- NEW: Audit fields
        Created_At DATETIME DEFAULT GETUTCDATE(),
        Updated_At DATETIME DEFAULT GETUTCDATE(),
        
        -- Constraints
        CONSTRAINT FK_LiveTrades_Asset FOREIGN KEY (Asset_ID) 
            REFERENCES Dim_Asset(Asset_ID),
        CONSTRAINT FK_LiveTrades_Strategy FOREIGN KEY (Strategy_ID) 
            REFERENCES Dim_Strategy_Registry(Strategy_ID),
        
        -- Unique constraint on signal composition
        CONSTRAINT UQ_LiveTrades_Signal UNIQUE (
            [Timestamp], Asset_ID, Strategy_ID, Signal_Value
        )
    );
    
    PRINT 'Created new Fact_Live_Trades table with Trade_ID primary key'
    
    -- Step 5: Copy data from old table (if any records exist)
    IF (SELECT COUNT(*) FROM Fact_Live_Trades_Old) > 0
    BEGIN
        INSERT INTO Fact_Live_Trades (
            [Timestamp], Asset_ID, Strategy_ID, Signal_Value,
            Entry_Price, Stop_Loss, Take_Profit, Confidence_Score,
            Is_Approved, Actual_Outcome
        )
        SELECT
            [Timestamp], Asset_ID, Strategy_ID, Signal_Value,
            Entry_Price, Stop_Loss, Take_Profit, Confidence_Score,
            Is_Approved, Actual_Outcome
        FROM Fact_Live_Trades_Old
        ORDER BY [Timestamp], Asset_ID, Strategy_ID;
        
        DECLARE @RowCount INT = @@ROWCOUNT;
        PRINT 'Migrated ' + CAST(@RowCount AS VARCHAR(10)) + ' existing records'
    END
    
    -- Step 6: Create indexes for performance
    CREATE INDEX IX_LiveTrades_Timestamp 
        ON Fact_Live_Trades([Timestamp] DESC);
    
    CREATE INDEX IX_LiveTrades_Asset 
        ON Fact_Live_Trades(Asset_ID, [Timestamp] DESC);
    
    CREATE INDEX IX_LiveTrades_Strategy 
        ON Fact_Live_Trades(Strategy_ID, [Timestamp] DESC);
    
    CREATE INDEX IX_LiveTrades_Approval 
        ON Fact_Live_Trades(Is_Approved, [Timestamp] DESC);
    
    PRINT 'Created performance indexes'
    
    -- Step 7: Drop old table
    DROP TABLE Fact_Live_Trades_Old;
    PRINT 'Removed staging table: Fact_Live_Trades_Old'
    
    PRINT 'Migration completed successfully!'
END
ELSE
BEGIN
    PRINT 'Migration already applied: Fact_Live_Trades has Trade_ID identity column'
    
    -- Ensure indexes exist
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('Fact_Live_Trades') AND name = 'IX_LiveTrades_Timestamp')
    BEGIN
        CREATE INDEX IX_LiveTrades_Timestamp 
            ON Fact_Live_Trades([Timestamp] DESC);
        PRINT 'Added missing index: IX_LiveTrades_Timestamp'
    END
END

GO

-- Verify migration
PRINT ''
PRINT '=== MIGRATION VERIFICATION ==='
EXEC sp_columns 'Fact_Live_Trades';
GO

-- Show row count
DECLARE @RowCount INT = (SELECT COUNT(*) FROM Fact_Live_Trades);
PRINT 'Fact_Live_Trades contains ' + CAST(@RowCount AS VARCHAR(10)) + ' records'
GO
