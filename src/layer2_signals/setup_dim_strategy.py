import pyodbc
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DB_SERVER = os.getenv('DB_SERVER')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')
DB_NAME = 'ForexBrainDB'

# Connect to SQL Server
conn = pyodbc.connect(f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={DB_SERVER};DATABASE={DB_NAME};UID={DB_USER};PWD={DB_PASS}')
cursor = conn.cursor()

# Create table if not exists
create_table_query = """
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Dim_Strategy_Registry]') AND type in (N'U'))
BEGIN
    CREATE TABLE Dim_Strategy_Registry (
        Strategy_ID INT PRIMARY KEY,
        Strategy_Name VARCHAR(50) NOT NULL,
        Asset_ID INT NOT NULL,
        Is_Active BIT NOT NULL
    )
END
"""
cursor.execute(create_table_query)
conn.commit()

# Add Is_Active column if missing
cursor.execute("""
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
               WHERE TABLE_NAME = 'Dim_Strategy_Registry' AND COLUMN_NAME = 'Is_Active')
BEGIN
    ALTER TABLE Dim_Strategy_Registry
    ADD Is_Active BIT NOT NULL DEFAULT 1
END
""")
conn.commit()

# Sample data: Strategies for assets 5,6,7 (repeat for each asset)
strategies = [
    # For Asset 5 (EUR_USD)
    (1, 'Trend_EMA_ADX', 5, 1),
    (2, 'Range_Bollinger', 5, 1),
    (3, 'Trend_Donchian', 5, 1),
    (4, 'Range_Stochastic', 5, 1),
    # For Asset 6 (GBP_USD)
    (5, 'Trend_EMA_ADX', 6, 1),
    (6, 'Range_Bollinger', 6, 1),
    (7, 'Trend_Donchian', 6, 1),
    (8, 'Range_Stochastic', 6, 1),
    # For Asset 7 (USD_JPY)
    (9, 'Trend_EMA_ADX', 7, 1),
    (10, 'Range_Bollinger', 7, 1),
    (11, 'Trend_Donchian', 7, 1),
    (12, 'Range_Stochastic', 7, 1)
]

# Insert data (with try-except for duplicates)
insert_query = """
INSERT INTO Dim_Strategy_Registry (Strategy_ID, Strategy_Name, Asset_ID, Is_Active) VALUES (?, ?, ?, ?)
"""
for strat in strategies:
    try:
        cursor.execute(insert_query, strat)
        conn.commit()
    except pyodbc.IntegrityError:
        print(f"Skipping duplicate Strategy_ID {strat[0]}")
        conn.rollback()

print("Dim_Strategy_Registry setup complete.")

# Clean up
cursor.close()
conn.close()