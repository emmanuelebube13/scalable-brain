-- Create the database if it doesn't already exist
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = N'ForexBrainDB')
BEGIN
    CREATE DATABASE ForexBrainDB;
    PRINT 'Database ForexBrainDB created successfully.';
END
ELSE
BEGIN
    PRINT 'Database ForexBrainDB already exists.';
END
GO