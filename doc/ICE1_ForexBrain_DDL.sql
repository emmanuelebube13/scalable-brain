/*
=============================================================================
Author:       Emmanuel Mbachu
Date:         2026-03-21
Description:  Data Definition Language (DDL) script to initialize the 
              ForexBrainDB (Scalable Brain) database. This script creates
              all dimension and fact tables, defines primary and foreign 
              keys, and establishes relationships for the trading system.
=============================================================================
*/

-- CREATE DATABASE ForexBrainDB;
-- GO

USE ForexBrainDB;
-- GO

-- ==========================================
-- 1. DIMENSION TABLES (Lookup Data)
-- ==========================================

CREATE TABLE Dim_Asset (
    Asset_ID INT PRIMARY KEY,
    Symbol VARCHAR(20) NOT NULL
);

CREATE TABLE Dim_Strategy_Registry (
    Strategy_ID INT PRIMARY KEY,
    Strategy_Name VARCHAR(100) NOT NULL
);

-- ==========================================
-- 2. FACT TABLES (Transactional Data)
-- ==========================================

CREATE TABLE Fact_Live_Trades (
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
    CONSTRAINT FK_LiveTrades_Asset FOREIGN KEY (Asset_ID) REFERENCES Dim_Asset(Asset_ID),
    CONSTRAINT FK_LiveTrades_Strategy FOREIGN KEY (Strategy_ID) REFERENCES Dim_Strategy_Registry(Strategy_ID)
);

CREATE TABLE Fact_Market_Prices (
    [Timestamp] DATETIME NOT NULL,
    Asset_ID INT NOT NULL,
    [Open] FLOAT,
    High FLOAT,
    Low FLOAT,
    [Close] FLOAT,
    Volume INT,
    CONSTRAINT FK_MarketPrices_Asset FOREIGN KEY (Asset_ID) REFERENCES Dim_Asset(Asset_ID)
);

CREATE TABLE Fact_Market_Regime (
    [Timestamp] DATETIME NOT NULL,
    Asset_ID INT NOT NULL,
    Regime_Label VARCHAR(50),
    ATR_Value FLOAT,
    ADX_Value FLOAT,
    CONSTRAINT FK_MarketRegime_Asset FOREIGN KEY (Asset_ID) REFERENCES Dim_Asset(Asset_ID)
);