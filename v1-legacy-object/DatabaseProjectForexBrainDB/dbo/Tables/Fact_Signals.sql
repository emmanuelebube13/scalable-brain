CREATE TABLE [dbo].[Fact_Signals] (
    [Timestamp]    DATETIME NOT NULL,
    [Asset_ID]     INT      NOT NULL,
    [Strategy_ID]  INT      NOT NULL,
    [Signal_Value] INT      NULL,
    PRIMARY KEY CLUSTERED ([Timestamp] ASC, [Asset_ID] ASC, [Strategy_ID] ASC)
);


GO

