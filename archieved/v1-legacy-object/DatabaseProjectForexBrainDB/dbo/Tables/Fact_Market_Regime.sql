CREATE TABLE [dbo].[Fact_Market_Regime] (
    [Timestamp]    DATETIME     NOT NULL,
    [Asset_ID]     INT          NOT NULL,
    [Regime_Label] VARCHAR (50) NOT NULL,
    [ATR_Value]    FLOAT (53)   NOT NULL,
    [ADX_Value]    FLOAT (53)   NOT NULL,
    PRIMARY KEY CLUSTERED ([Timestamp] ASC, [Asset_ID] ASC)
);


GO

