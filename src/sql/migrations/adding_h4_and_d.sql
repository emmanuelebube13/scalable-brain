-- =============================================
-- Additive-only: Create ONLY the new H4 and D1 tables
-- Exact schema match to your existing Fact_Market_Prices
-- (existing Fact_Market_Prices table is left 100% untouched)
-- =============================================

CREATE TABLE Fact_Market_Prices_H4 (
    Timestamp   DATETIME    NOT NULL,
    Asset_ID    INT         NOT NULL,
    [Open]      FLOAT       NOT NULL,
    High        FLOAT       NOT NULL,
    Low         FLOAT       NOT NULL,
    [Close]     FLOAT       NOT NULL,
    Volume      INT         NOT NULL,
    CONSTRAINT PK_Fact_Market_Prices_H4 
        PRIMARY KEY CLUSTERED (Timestamp, Asset_ID)
);
GO

CREATE TABLE Fact_Market_Prices_D1 (
    Timestamp   DATETIME    NOT NULL,
    Asset_ID    INT         NOT NULL,
    [Open]      FLOAT       NOT NULL,
    High        FLOAT       NOT NULL,
    Low         FLOAT       NOT NULL,
    [Close]     FLOAT       NOT NULL,
    Volume      INT         NOT NULL,
    CONSTRAINT PK_Fact_Market_Prices_D1 
        PRIMARY KEY CLUSTERED (Timestamp, Asset_ID)
);
GO

PRINT '✅ Fact_Market_Prices_H4 and Fact_Market_Prices_D1 created successfully.';
PRINT '   Existing Fact_Market_Prices (H1) remains untouched.';