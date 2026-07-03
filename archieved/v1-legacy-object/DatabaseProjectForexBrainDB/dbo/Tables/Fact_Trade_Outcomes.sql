CREATE TABLE [dbo].[Fact_Trade_Outcomes] (
    [Timestamp]      DATETIME   NOT NULL,
    [Asset_ID]       INT        NOT NULL,
    [Strategy_ID]    INT        NOT NULL,
    [Signal_Value]   INT        NULL,
    [Forward_Return] FLOAT (53) NULL,
    [Is_Winner]      INT        NULL,
    PRIMARY KEY CLUSTERED ([Timestamp] ASC, [Asset_ID] ASC, [Strategy_ID] ASC)
);


GO

