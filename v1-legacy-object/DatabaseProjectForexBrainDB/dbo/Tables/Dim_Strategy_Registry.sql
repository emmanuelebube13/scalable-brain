CREATE TABLE [dbo].[Dim_Strategy_Registry] (
    [Strategy_ID]       INT           IDENTITY (1, 1) NOT NULL,
    [Strategy_Name]     VARCHAR (100) NOT NULL,
    [Logic_Description] VARCHAR (MAX) NULL,
    [Asset_ID]          INT           NULL,
    [Is_Active]         BIT           DEFAULT ((1)) NOT NULL,
    PRIMARY KEY CLUSTERED ([Strategy_ID] ASC),
    UNIQUE NONCLUSTERED ([Strategy_Name] ASC)
);


GO

