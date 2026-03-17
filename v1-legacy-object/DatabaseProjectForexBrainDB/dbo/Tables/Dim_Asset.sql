CREATE TABLE [dbo].[Dim_Asset] (
    [Asset_ID]    INT          IDENTITY (1, 1) NOT NULL,
    [Symbol]      VARCHAR (20) NOT NULL,
    [Market_Type] VARCHAR (20) NOT NULL,
    PRIMARY KEY CLUSTERED ([Asset_ID] ASC),
    UNIQUE NONCLUSTERED ([Symbol] ASC)
);


GO

