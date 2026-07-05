CREATE TABLE [dbo].[Fact_Live_Trades] (
    [Timestamp]        DATETIME   NULL,
    [Asset_ID]         BIGINT     NULL,
    [Strategy_ID]      BIGINT     NULL,
    [Signal_Value]     BIGINT     NULL,
    [Entry_Price]      FLOAT (53) NULL,
    [Stop_Loss]        FLOAT (53) NULL,
    [Take_Profit]      FLOAT (53) NULL,
    [Confidence_Score] FLOAT (53) NULL,
    [Is_Approved]      INT        NULL
);


GO

