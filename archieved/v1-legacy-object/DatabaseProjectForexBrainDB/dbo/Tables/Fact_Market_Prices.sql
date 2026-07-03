CREATE TABLE [dbo].[Fact_Market_Prices] (
    [Price_ID]    BIGINT          IDENTITY (1, 1) NOT NULL,
    [Asset_ID]    INT             NULL,
    [Timestamp]   DATETIME        NOT NULL,
    [Open]        DECIMAL (18, 5) NOT NULL,
    [High]        DECIMAL (18, 5) NOT NULL,
    [Low]         DECIMAL (18, 5) NOT NULL,
    [Close]       DECIMAL (18, 5) NOT NULL,
    [Volume]      BIGINT          NULL,
    [Granularity] VARCHAR (10)    NOT NULL,
    PRIMARY KEY CLUSTERED ([Price_ID] ASC),
    FOREIGN KEY ([Asset_ID]) REFERENCES [dbo].[Dim_Asset] ([Asset_ID]),
    CONSTRAINT [UQ_Asset_Time_Granularity] UNIQUE NONCLUSTERED ([Asset_ID] ASC, [Timestamp] ASC, [Granularity] ASC)
);


GO

