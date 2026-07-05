CREATE TABLE [dbo].[Dim_Model_Metadata] (
    [Model_ID]       INT          IDENTITY (1, 1) NOT NULL,
    [Algorithm_Type] VARCHAR (50) NULL,
    [Version_Number] VARCHAR (20) NULL,
    [Training_Date]  DATETIME     DEFAULT (getdate()) NULL,
    PRIMARY KEY CLUSTERED ([Model_ID] ASC)
);


GO

