--
-- Migration: Add Signal Processing Tracking and Fix Deduplication
-- ================================================================
--
-- This migration:
-- 1. Creates Fact_Signal_Processing_Log table to track processing state
-- 2. Adds Granularity column to Fact_Signals primary key
-- 3. Adds unique constraint to prevent duplicate signals
-- 4. Adds validation columns for data integrity
--

-- ============================================================================
-- STEP 1: Create Processing Log Table
-- ============================================================================
-- Tracks the last processed timestamp for each asset/granularity/strategy

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Fact_Signal_Processing_Log')
BEGIN
    CREATE TABLE Fact_Signal_Processing_Log (
        Log_ID INT IDENTITY(1,1) PRIMARY KEY,
        Asset_ID INT NOT NULL,
        Granularity VARCHAR(10) NOT NULL,
        Strategy_ID INT NOT NULL,
        Last_Processed_Timestamp DATETIME NOT NULL,
        Batch_ID VARCHAR(50) NULL,
        Records_Processed INT DEFAULT 0,
        Processed_At DATETIME DEFAULT GETUTCDATE(),
        
        -- Unique constraint on the combination
        CONSTRAINT UQ_Processing_Log UNIQUE (Asset_ID, Granularity, Strategy_ID)
    );
    
    -- Index for faster lookups
    CREATE INDEX IX_Processing_Log_Lookup 
        ON Fact_Signal_Processing_Log (Asset_ID, Granularity, Strategy_ID);
    
    CREATE INDEX IX_Processing_Log_Batch 
        ON Fact_Signal_Processing_Log (Batch_ID);
    
    PRINT 'Created Fact_Signal_Processing_Log table';
END
ELSE
BEGIN
    PRINT 'Fact_Signal_Processing_Log table already exists';
END
GO

-- ============================================================================
-- STEP 2: Add Granularity to Fact_Signals if missing
-- ============================================================================

-- First, add the column if it doesn't exist
IF NOT EXISTS (
    SELECT * FROM sys.columns 
    WHERE object_id = OBJECT_ID('Fact_Signals') 
    AND name = 'Granularity'
)
BEGIN
    ALTER TABLE Fact_Signals
    ADD Granularity VARCHAR(10) NULL DEFAULT 'H1';
    
    PRINT 'Added Granularity column to Fact_Signals';
END
ELSE
BEGIN
    PRINT 'Granularity column already exists in Fact_Signals';
END
GO

-- Update existing records to have a default granularity
UPDATE Fact_Signals
SET Granularity = 'H1'
WHERE Granularity IS NULL;
GO

-- ============================================================================
-- STEP 3: Add additional columns to Fact_Signals for traceability
-- ============================================================================

-- Add Strategy_Version column
IF NOT EXISTS (
    SELECT * FROM sys.columns 
    WHERE object_id = OBJECT_ID('Fact_Signals') 
    AND name = 'Strategy_Version'
)
BEGIN
    ALTER TABLE Fact_Signals
    ADD Strategy_Version VARCHAR(50) NULL;
    
    PRINT 'Added Strategy_Version column to Fact_Signals';
END
GO

-- Add Config_Hash column
IF NOT EXISTS (
    SELECT * FROM sys.columns 
    WHERE object_id = OBJECT_ID('Fact_Signals') 
    AND name = 'Config_Hash'
)
BEGIN
    ALTER TABLE Fact_Signals
    ADD Config_Hash VARCHAR(64) NULL;
    
    PRINT 'Added Config_Hash column to Fact_Signals';
END
GO

-- Add Signal_Reason column
IF NOT EXISTS (
    SELECT * FROM sys.columns 
    WHERE object_id = OBJECT_ID('Fact_Signals') 
    AND name = 'Signal_Reason'
)
BEGIN
    ALTER TABLE Fact_Signals
    ADD Signal_Reason NVARCHAR(500) NULL;
    
    PRINT 'Added Signal_Reason column to Fact_Signals';
END
GO

-- Add Rule_ID column
IF NOT EXISTS (
    SELECT * FROM sys.columns 
    WHERE object_id = OBJECT_ID('Fact_Signals') 
    AND name = 'Rule_ID'
)
BEGIN
    ALTER TABLE Fact_Signals
    ADD Rule_ID VARCHAR(100) NULL;
    
    PRINT 'Added Rule_ID column to Fact_Signals';
END
GO

-- Add Indicator_Snapshot column
IF NOT EXISTS (
    SELECT * FROM sys.columns 
    WHERE object_id = OBJECT_ID('Fact_Signals') 
    AND name = 'Indicator_Snapshot'
)
BEGIN
    ALTER TABLE Fact_Signals
    ADD Indicator_Snapshot NVARCHAR(MAX) NULL;
    
    PRINT 'Added Indicator_Snapshot column to Fact_Signals';
END
GO

-- Add Confidence_Score column
IF NOT EXISTS (
    SELECT * FROM sys.columns 
    WHERE object_id = OBJECT_ID('Fact_Signals') 
    AND name = 'Confidence_Score'
)
BEGIN
    ALTER TABLE Fact_Signals
    ADD Confidence_Score DECIMAL(5,4) NULL;
    
    PRINT 'Added Confidence_Score column to Fact_Signals';
END
GO

-- Add Batch_ID column
IF NOT EXISTS (
    SELECT * FROM sys.columns 
    WHERE object_id = OBJECT_ID('Fact_Signals') 
    AND name = 'Batch_ID'
)
BEGIN
    ALTER TABLE Fact_Signals
    ADD Batch_ID VARCHAR(50) NULL;
    
    PRINT 'Added Batch_ID column to Fact_Signals';
END
GO

-- Add Created_At column
IF NOT EXISTS (
    SELECT * FROM sys.columns 
    WHERE object_id = OBJECT_ID('Fact_Signals') 
    AND name = 'Created_At'
)
BEGIN
    ALTER TABLE Fact_Signals
    ADD Created_At DATETIME DEFAULT GETUTCDATE();
    
    PRINT 'Added Created_At column to Fact_Signals';
END
GO

-- ============================================================================
-- STEP 4: Drop and recreate primary key to include Granularity
-- ============================================================================

-- Check if the old primary key exists (without Granularity)
IF EXISTS (
    SELECT * FROM sys.indexes 
    WHERE object_id = OBJECT_ID('Fact_Signals')
    AND name = 'PK__Fact_Sig__5E519FBC7F60ED59'  -- Common auto-generated name pattern
)
BEGIN
    -- Drop the old primary key
    ALTER TABLE Fact_Signals
    DROP CONSTRAINT PK__Fact_Sig__5E519FBC7F60ED59;
    
    PRINT 'Dropped old primary key';
END
ELSE IF EXISTS (
    SELECT * FROM sys.indexes 
    WHERE object_id = OBJECT_ID('Fact_Signals')
    AND is_primary_key = 1
)
BEGIN
    -- Find and drop any primary key
    DECLARE @pk_name NVARCHAR(256);
    SELECT @pk_name = name 
    FROM sys.indexes 
    WHERE object_id = OBJECT_ID('Fact_Signals') 
    AND is_primary_key = 1;
    
    IF @pk_name IS NOT NULL
    BEGIN
        EXEC('ALTER TABLE Fact_Signals DROP CONSTRAINT ' + @pk_name);
        PRINT 'Dropped existing primary key: ' + @pk_name;
    END
END
GO

-- Create new primary key with Granularity
IF NOT EXISTS (
    SELECT * FROM sys.indexes 
    WHERE object_id = OBJECT_ID('Fact_Signals')
    AND is_primary_key = 1
)
BEGIN
    ALTER TABLE Fact_Signals
    ADD CONSTRAINT PK_Fact_Signals PRIMARY KEY CLUSTERED (
        Timestamp ASC,
        Asset_ID ASC,
        Granularity ASC,
        Strategy_ID ASC
    );
    
    PRINT 'Created new primary key with Granularity';
END
ELSE
BEGIN
    PRINT 'Primary key already exists';
END
GO

-- ============================================================================
-- STEP 5: Create indexes for performance
-- ============================================================================

-- Index for deduplication checks
IF NOT EXISTS (
    SELECT * FROM sys.indexes 
    WHERE object_id = OBJECT_ID('Fact_Signals')
    AND name = 'IX_Fact_Signals_Unique_Check'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_Fact_Signals_Unique_Check
        ON Fact_Signals (Timestamp, Asset_ID, Granularity, Strategy_ID)
        INCLUDE (Signal_Value);
    
    PRINT 'Created IX_Fact_Signals_Unique_Check index';
END
GO

-- Index for batch lookups
IF NOT EXISTS (
    SELECT * FROM sys.indexes 
    WHERE object_id = OBJECT_ID('Fact_Signals')
    AND name = 'IX_Fact_Signals_Batch'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_Fact_Signals_Batch
        ON Fact_Signals (Batch_ID);
    
    PRINT 'Created IX_Fact_Signals_Batch index';
END
GO

-- Index for recent signals query
IF NOT EXISTS (
    SELECT * FROM sys.indexes 
    WHERE object_id = OBJECT_ID('Fact_Signals')
    AND name = 'IX_Fact_Signals_Recent'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_Fact_Signals_Recent
        ON Fact_Signals (Timestamp DESC, Asset_ID, Granularity, Strategy_ID);
    
    PRINT 'Created IX_Fact_Signals_Recent index';
END
GO

-- ============================================================================
-- STEP 6: Create validation function
-- ============================================================================

IF EXISTS (SELECT * FROM sys.objects WHERE name = 'fn_ValidateSignalUniqueness')
BEGIN
    DROP FUNCTION fn_ValidateSignalUniqueness;
END
GO

CREATE FUNCTION fn_ValidateSignalUniqueness(
    @Timestamp DATETIME,
    @Asset_ID INT,
    @Granularity VARCHAR(10),
    @Strategy_ID INT
)
RETURNS BIT
AS
BEGIN
    DECLARE @Exists BIT = 0;
    
    IF EXISTS (
        SELECT 1 FROM Fact_Signals
        WHERE Timestamp = @Timestamp
            AND Asset_ID = @Asset_ID
            AND Granularity = @Granularity
            AND Strategy_ID = @Strategy_ID
    )
    BEGIN
        SET @Exists = 1;
    END
    
    RETURN @Exists;
END
GO

PRINT 'Created fn_ValidateSignalUniqueness function';
GO

-- ============================================================================
-- STEP 7: Clean up duplicate signals if any exist
-- ============================================================================

-- This CTE finds and removes duplicate signals keeping only the most recent
WITH DuplicateSignals AS (
    SELECT 
        Timestamp,
        Asset_ID,
        Granularity,
        Strategy_ID,
        ROW_NUMBER() OVER (
            PARTITION BY Timestamp, Asset_ID, Granularity, Strategy_ID
            ORDER BY Created_At DESC
        ) AS RowNum
    FROM Fact_Signals
)
SELECT COUNT(*) AS DuplicateCount
INTO #TempDuplicateCount
FROM DuplicateSignals
WHERE RowNum > 1;

DECLARE @DupCount INT;
SELECT @DupCount = DuplicateCount FROM #TempDuplicateCount;

IF @DupCount > 0
BEGIN
    PRINT 'Found ' + CAST(@DupCount AS VARCHAR) + ' duplicate signals. Cleaning up...';
    
    -- Delete duplicates keeping only the most recent
    WITH DuplicateSignals AS (
        SELECT 
            Timestamp,
            Asset_ID,
            Granularity,
            Strategy_ID,
            Created_At,
            ROW_NUMBER() OVER (
                PARTITION BY Timestamp, Asset_ID, Granularity, Strategy_ID
                ORDER BY Created_At DESC
            ) AS RowNum
        FROM Fact_Signals
    )
    DELETE FROM Fact_Signals
    WHERE EXISTS (
        SELECT 1 FROM DuplicateSignals d
        WHERE d.RowNum > 1
            AND Fact_Signals.Timestamp = d.Timestamp
            AND Fact_Signals.Asset_ID = d.Asset_ID
            AND Fact_Signals.Granularity = d.Granularity
            AND Fact_Signals.Strategy_ID = d.Strategy_ID
            AND Fact_Signals.Created_At = d.Created_At
    );
    
    PRINT 'Duplicate signals cleaned up';
END
ELSE
BEGIN
    PRINT 'No duplicate signals found';
END

DROP TABLE #TempDuplicateCount;
GO

PRINT 'Migration completed successfully';
GO
