-- =============================================================================
-- Scalable Brain - PostgreSQL + TimescaleDB Initialization
-- =============================================================================
-- This script creates the full ForexBrainDB schema for PostgreSQL.
-- Time-series tables are converted to TimescaleDB hypertables.
-- Dimension tables remain as regular PostgreSQL tables.
-- =============================================================================

-- Enable TimescaleDB extension (requires TimescaleDB to be installed)
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- =============================================================================
-- 1. DIMENSION TABLES
-- =============================================================================

CREATE TABLE IF NOT EXISTS Dim_Asset (
    Asset_ID INT PRIMARY KEY,
    Symbol VARCHAR(20) NOT NULL,
    Market_Type VARCHAR(50),
    Is_Active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS Dim_Strategy_Registry (
    Strategy_ID INT PRIMARY KEY,
    Strategy_Name VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS Dim_Strategy (
    Strategy_ID INT PRIMARY KEY,
    Strategy_Name VARCHAR(100) NOT NULL,
    Strategy_Type VARCHAR(50),
    Description TEXT,
    Is_Active BOOLEAN DEFAULT TRUE,
    Created_At TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS Dim_Strategy_Config (
    Config_ID SERIAL PRIMARY KEY,
    Strategy_ID INT NOT NULL REFERENCES Dim_Strategy(Strategy_ID),
    Config_Version VARCHAR(50) NOT NULL,
    Config_Hash VARCHAR(64) UNIQUE NOT NULL,
    Granularity VARCHAR(10),
    Indicator_Configs JSONB,
    Signal_Rules JSONB,
    Risk_Filters JSONB,
    Effective_From TIMESTAMPTZ,
    Effective_To TIMESTAMPTZ,
    Created_At TIMESTAMPTZ DEFAULT NOW(),
    Is_Active BOOLEAN DEFAULT TRUE,
    CONSTRAINT UQ_Strategy_Config_Version UNIQUE (Strategy_ID, Config_Version, Granularity)
);

CREATE TABLE IF NOT EXISTS Dim_Strategy_Asset_Mapping (
    Mapping_ID SERIAL PRIMARY KEY,
    Strategy_ID INT NOT NULL REFERENCES Dim_Strategy(Strategy_ID),
    Asset_ID INT NOT NULL REFERENCES Dim_Asset(Asset_ID),
    Granularity VARCHAR(10) NOT NULL,
    Config_ID INT REFERENCES Dim_Strategy_Config(Config_ID),
    Is_Active BOOLEAN DEFAULT TRUE,
    Created_At TIMESTAMPTZ DEFAULT NOW(),
    Updated_At TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (Strategy_ID, Asset_ID, Granularity)
);

CREATE TABLE IF NOT EXISTS Dim_Indicator_Library (
    Indicator_ID SERIAL PRIMARY KEY,
    Indicator_Key VARCHAR(50) NOT NULL UNIQUE,
    Display_Name VARCHAR(100),
    Category VARCHAR(50),
    Default_Params JSONB,
    Description TEXT
);

-- =============================================================================
-- 2. TIME-SERIES FACT TABLES (Hypertables)
-- =============================================================================

-- Fact_Market_Prices: OHLCV price data (high volume)
CREATE TABLE IF NOT EXISTS Fact_Market_Prices (
    Timestamp TIMESTAMPTZ NOT NULL,
    Asset_ID INT NOT NULL REFERENCES Dim_Asset(Asset_ID),
    Granularity VARCHAR(10) NOT NULL DEFAULT 'H1',
    "Open" NUMERIC(19, 6) NOT NULL,
    High NUMERIC(19, 6) NOT NULL,
    Low NUMERIC(19, 6) NOT NULL,
    "Close" NUMERIC(19, 6) NOT NULL,
    Bid_Open NUMERIC(19, 6),
    Bid_High NUMERIC(19, 6),
    Bid_Low NUMERIC(19, 6),
    Bid_Close NUMERIC(19, 6),
    Ask_Open NUMERIC(19, 6),
    Ask_High NUMERIC(19, 6),
    Ask_Low NUMERIC(19, 6),
    Ask_Close NUMERIC(19, 6),
    Volume INT NOT NULL,
    PRIMARY KEY (Timestamp, Asset_ID, Granularity)
);
SELECT create_hypertable('Fact_Market_Prices', 'timestamp', if_not_exists => TRUE);

-- Fact_Market_Prices_H4: Pre-aggregated H4 candles
CREATE TABLE IF NOT EXISTS Fact_Market_Prices_H4 (
    Timestamp TIMESTAMPTZ NOT NULL,
    Asset_ID INT NOT NULL REFERENCES Dim_Asset(Asset_ID),
    "Open" NUMERIC(19, 6) NOT NULL,
    High NUMERIC(19, 6) NOT NULL,
    Low NUMERIC(19, 6) NOT NULL,
    "Close" NUMERIC(19, 6) NOT NULL,
    Volume INT NOT NULL,
    PRIMARY KEY (Timestamp, Asset_ID)
);
SELECT create_hypertable('Fact_Market_Prices_H4', 'timestamp', if_not_exists => TRUE);

-- Fact_Market_Prices_D1: Pre-aggregated D1 candles
CREATE TABLE IF NOT EXISTS Fact_Market_Prices_D1 (
    Timestamp TIMESTAMPTZ NOT NULL,
    Asset_ID INT NOT NULL REFERENCES Dim_Asset(Asset_ID),
    "Open" NUMERIC(19, 6) NOT NULL,
    High NUMERIC(19, 6) NOT NULL,
    Low NUMERIC(19, 6) NOT NULL,
    "Close" NUMERIC(19, 6) NOT NULL,
    Volume INT NOT NULL,
    PRIMARY KEY (Timestamp, Asset_ID)
);
SELECT create_hypertable('Fact_Market_Prices_D1', 'timestamp', if_not_exists => TRUE);

-- Fact_Market_Regime: Legacy regime table (kept for compatibility)
CREATE TABLE IF NOT EXISTS Fact_Market_Regime (
    Timestamp TIMESTAMPTZ NOT NULL,
    Asset_ID INT NOT NULL REFERENCES Dim_Asset(Asset_ID),
    Regime_Label VARCHAR(50),
    ATR_Value DOUBLE PRECISION,
    ADX_Value DOUBLE PRECISION,
    PRIMARY KEY (Timestamp, Asset_ID)
);
SELECT create_hypertable('Fact_Market_Regime', 'timestamp', if_not_exists => TRUE);

-- Fact_Market_Regime_V2: Enhanced regime detection
CREATE TABLE IF NOT EXISTS Fact_Market_Regime_V2 (
    Timestamp TIMESTAMPTZ NOT NULL,
    Asset_ID INT NOT NULL REFERENCES Dim_Asset(Asset_ID),
    Granularity VARCHAR(10) NOT NULL,
    Regime_Label VARCHAR(50),
    ATR_Value DOUBLE PRECISION,
    ADX_Value DOUBLE PRECISION,
    ATR_Percentile_20D DOUBLE PRECISION,
    Trend_Alignment_Score DOUBLE PRECISION,
    Volatility_Regime VARCHAR(50),
    Session_Volume_Z DOUBLE PRECISION,
    Regime_Model_Version VARCHAR(20),
    H4_Trend_Direction INT,
    D1_Trend_Direction INT,
    PRIMARY KEY (Timestamp, Asset_ID, Granularity)
);
SELECT create_hypertable('Fact_Market_Regime_V2', 'timestamp', if_not_exists => TRUE);

-- Fact_Signals: Trade signals generated by Layer 2
CREATE TABLE IF NOT EXISTS Fact_Signals (
    Timestamp TIMESTAMPTZ NOT NULL,
    Asset_ID INT NOT NULL REFERENCES Dim_Asset(Asset_ID),
    Granularity VARCHAR(10) NOT NULL,
    Strategy_ID INT NOT NULL REFERENCES Dim_Strategy_Registry(Strategy_ID),
    Signal_Value INT NOT NULL,
    Strategy_Version VARCHAR(50),
    Config_Hash VARCHAR(64),
    Signal_Reason TEXT,
    Rule_ID VARCHAR(100),
    Indicator_Snapshot JSONB,
    Confidence_Score NUMERIC(5,4),
    Batch_ID VARCHAR(50),
    Created_At TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (Timestamp, Asset_ID, Granularity, Strategy_ID)
);
SELECT create_hypertable('Fact_Signals', 'timestamp', if_not_exists => TRUE);

-- =============================================================================
-- 3. OPERATIONAL FACT TABLES (Regular tables - lower volume)
-- =============================================================================

CREATE TABLE IF NOT EXISTS Fact_Signal_Processing_Log (
    Log_ID SERIAL PRIMARY KEY,
    Asset_ID INT NOT NULL,
    Granularity VARCHAR(10) NOT NULL,
    Strategy_ID INT NOT NULL,
    Last_Processed_Timestamp TIMESTAMPTZ NOT NULL,
    Batch_ID VARCHAR(50),
    Records_Processed INT DEFAULT 0,
    Processed_At TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT UQ_Processing_Log UNIQUE (Asset_ID, Granularity, Strategy_ID)
);

CREATE INDEX IF NOT EXISTS IX_Processing_Log_Lookup 
    ON Fact_Signal_Processing_Log (Asset_ID, Granularity, Strategy_ID);
CREATE INDEX IF NOT EXISTS IX_Processing_Log_Batch 
    ON Fact_Signal_Processing_Log (Batch_ID);

CREATE TABLE IF NOT EXISTS Fact_Live_Trades (
    Trade_ID SERIAL PRIMARY KEY,
    Timestamp TIMESTAMPTZ NOT NULL,
    Asset_ID INT NOT NULL REFERENCES Dim_Asset(Asset_ID),
    Strategy_ID INT NOT NULL REFERENCES Dim_Strategy_Registry(Strategy_ID),
    Signal_Value INT,
    Entry_Price DOUBLE PRECISION,
    Stop_Loss DOUBLE PRECISION,
    Take_Profit DOUBLE PRECISION,
    Confidence_Score DOUBLE PRECISION,
    Is_Approved INT,
    Actual_Outcome INT,
    Created_At TIMESTAMPTZ DEFAULT NOW(),
    Updated_At TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT UQ_LiveTrades_Signal UNIQUE (Timestamp, Asset_ID, Strategy_ID, Signal_Value)
);

CREATE INDEX IF NOT EXISTS IX_LiveTrades_Timestamp ON Fact_Live_Trades(Timestamp DESC);
CREATE INDEX IF NOT EXISTS IX_LiveTrades_Asset ON Fact_Live_Trades(Asset_ID, Timestamp DESC);
CREATE INDEX IF NOT EXISTS IX_LiveTrades_Strategy ON Fact_Live_Trades(Strategy_ID, Timestamp DESC);
CREATE INDEX IF NOT EXISTS IX_LiveTrades_Approval ON Fact_Live_Trades(Is_Approved, Timestamp DESC);

CREATE TABLE IF NOT EXISTS Fact_Trade_Outcomes (
    Outcome_ID SERIAL PRIMARY KEY,
    Timestamp TIMESTAMPTZ NOT NULL,
    Asset_ID INT NOT NULL REFERENCES Dim_Asset(Asset_ID),
    Strategy_ID INT NOT NULL REFERENCES Dim_Strategy_Registry(Strategy_ID),
    Granularity VARCHAR(10),
    Trade_Horizon VARCHAR(10),
    Is_Winner INT,
    R_Multiple DOUBLE PRECISION,
    Holding_Bars INT,
    ATR_SL_Multiplier DOUBLE PRECISION,
    ATR_TP_Multiplier DOUBLE PRECISION,
    Entry_Signal_Type VARCHAR(50),
    Exit_Reason VARCHAR(50),
    Created_At TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS IX_TradeOutcomes_Lookup ON Fact_Trade_Outcomes(Timestamp, Asset_ID, Strategy_ID);

CREATE TABLE IF NOT EXISTS Fact_Execution_Log (
    Log_ID SERIAL PRIMARY KEY,
    Timestamp TIMESTAMPTZ NOT NULL,
    Trade_ID INT REFERENCES Fact_Live_Trades(Trade_ID),
    Asset_ID INT NOT NULL REFERENCES Dim_Asset(Asset_ID),
    Action VARCHAR(50) NOT NULL,
    Details JSONB,
    Created_At TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS Fact_Macro_Events (
    Event_ID SERIAL PRIMARY KEY,
    Timestamp TIMESTAMPTZ NOT NULL,
    Source VARCHAR(50),
    Title TEXT,
    Description TEXT,
    Sentiment_Score DOUBLE PRECISION,
    Created_At TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- 4. PERFORMANCE INDEXES ON HYPERTABLES
-- =============================================================================

-- Fact_Signals indexes
CREATE INDEX IF NOT EXISTS IX_Fact_Signals_Unique_Check
    ON Fact_Signals (Timestamp, Asset_ID, Granularity, Strategy_ID);
CREATE INDEX IF NOT EXISTS IX_Fact_Signals_Batch
    ON Fact_Signals (Batch_ID);
CREATE INDEX IF NOT EXISTS IX_Fact_Signals_Recent
    ON Fact_Signals (Timestamp DESC, Asset_ID, Granularity, Strategy_ID);

-- Fact_Market_Prices indexes
CREATE INDEX IF NOT EXISTS IX_MarketPrices_Asset_Time
    ON Fact_Market_Prices (Asset_ID, Timestamp DESC);

-- Fact_Market_Regime_V2 indexes
CREATE INDEX IF NOT EXISTS IX_RegimeV2_Asset_Time
    ON Fact_Market_Regime_V2 (Asset_ID, Timestamp DESC);
CREATE INDEX IF NOT EXISTS IX_RegimeV2_Label
    ON Fact_Market_Regime_V2 (Regime_Label, Timestamp DESC);

-- =============================================================================
-- 5. SEED DATA
-- =============================================================================

INSERT INTO Dim_Asset (Asset_ID, Symbol, Market_Type) VALUES
    (1, 'EUR_USD', 'Forex'),
    (2, 'GBP_USD', 'Forex'),
    (3, 'USD_JPY', 'Forex'),
    (4, 'AUD_USD', 'Forex'),
    (5, 'USD_CAD', 'Forex')
ON CONFLICT (Asset_ID) DO NOTHING;
