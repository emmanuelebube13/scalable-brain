CREATE TABLE [dbo].[Dim_Market_Regime] (
    [Regime_ID]        INT          IDENTITY (1, 1) NOT NULL,
    [Regime_Name]      VARCHAR (50) NOT NULL,
    [Volatility_Index] VARCHAR (50) NULL,
    PRIMARY KEY CLUSTERED ([Regime_ID] ASC)
);


GO

