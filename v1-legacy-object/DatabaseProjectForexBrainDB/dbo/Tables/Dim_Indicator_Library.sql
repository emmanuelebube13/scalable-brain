CREATE TABLE [dbo].[Dim_Indicator_Library] (
    [Indicator_ID]   INT          IDENTITY (1, 1) NOT NULL,
    [Indicator_Name] VARCHAR (50) NOT NULL,
    [Category]       VARCHAR (50) NULL,
    PRIMARY KEY CLUSTERED ([Indicator_ID] ASC)
);


GO

