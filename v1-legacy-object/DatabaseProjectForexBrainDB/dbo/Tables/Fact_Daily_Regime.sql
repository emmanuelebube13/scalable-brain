CREATE TABLE [dbo].[Fact_Daily_Regime] (
    [Regime_ID]          BIGINT          IDENTITY (1, 1) NOT NULL,
    [Asset_ID]           INT             NULL,
    [Date]               DATE            NOT NULL,
    [SMA_50]             DECIMAL (18, 5) NULL,
    [SMA_200]            DECIMAL (18, 5) NULL,
    [ATR_14]             DECIMAL (18, 5) NULL,
    [Regime_Type]        VARCHAR (20)    NOT NULL,
    [Is_High_Volatility] BIT             DEFAULT ((0)) NULL,
    PRIMARY KEY CLUSTERED ([Regime_ID] ASC),
    FOREIGN KEY ([Asset_ID]) REFERENCES [dbo].[Dim_Asset] ([Asset_ID]),
    CONSTRAINT [UQ_Asset_Date] UNIQUE NONCLUSTERED ([Asset_ID] ASC, [Date] ASC)
);


GO

