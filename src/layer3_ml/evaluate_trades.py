import pyodbc
from dotenv import load_dotenv
import os
import pandas as pd

load_dotenv()

DB_SERVER = os.getenv('DB_SERVER')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')

conn_str = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={DB_SERVER};DATABASE=ForexBrainDB;UID={DB_USER};PWD={DB_PASS}'
conn = pyodbc.connect(conn_str)
cursor = conn.cursor()
cursor.fast_executemany = True

# Drop the table if it exists
cursor.execute("IF OBJECT_ID('Fact_Trade_Outcomes', 'U') IS NOT NULL DROP TABLE Fact_Trade_Outcomes")
conn.commit()

# Create the table
create_table_query = """
CREATE TABLE Fact_Trade_Outcomes (
    Timestamp DATETIME,
    Asset_ID INT,
    Strategy_ID INT,
    Signal_Value INT,
    Forward_Return FLOAT,
    Is_Winner INT,
    PRIMARY KEY (Timestamp, Asset_ID, Strategy_ID)
)
"""
cursor.execute(create_table_query)
conn.commit()

# Get unique Asset_IDs from signals
assets_query = "SELECT DISTINCT Asset_ID FROM Fact_Signals WHERE Signal_Value IN (1, -1)"
assets_df = pd.read_sql(assets_query, conn)
assets = assets_df['Asset_ID'].tolist()

for asset in assets:
    print(f"Processing Asset_ID: {asset}")

    # Fetch prices for the asset
    prices_query = f"""
    SELECT Timestamp, [Close]
    FROM Fact_Market_Prices
    WHERE Asset_ID = {asset}
    ORDER BY Timestamp
    """
    prices = pd.read_sql(prices_query, conn)
    prices['Close_T24'] = prices['Close'].shift(-24)

    # Fetch signals for the asset
    signals_query = f"""
    SELECT Timestamp, Strategy_ID, Signal_Value
    FROM Fact_Signals
    WHERE Asset_ID = {asset} AND Signal_Value IN (1, -1)
    ORDER BY Timestamp
    """
    signals = pd.read_sql(signals_query, conn)

    # Merge signals with prices
    df = pd.merge(signals, prices[['Timestamp', 'Close', 'Close_T24']], on='Timestamp', how='left')
    df['Asset_ID'] = asset

    # Drop rows without current or future close prices
    df = df.dropna(subset=['Close', 'Close_T24'])

    # Calculate Forward_Return
    df['Forward_Return'] = (df['Close_T24'] - df['Close']) / df['Close']

    # Calculate Is_Winner
    df['Is_Winner'] = 0
    buy_win = (df['Signal_Value'] == 1) & (df['Forward_Return'] > 0)
    sell_win = (df['Signal_Value'] == -1) & (df['Forward_Return'] < 0)
    df.loc[buy_win, 'Is_Winner'] = 1
    df.loc[sell_win, 'Is_Winner'] = 1

    # Calculate and print win rate
    win_rate = df['Is_Winner'].mean() * 100 if not df.empty else 0
    print(f"Asset_ID {asset} Win Rate: {win_rate:.2f}%")

    # Prepare data for insertion
    insert_data = df[['Timestamp', 'Asset_ID', 'Strategy_ID', 'Signal_Value', 'Forward_Return', 'Is_Winner']].values.tolist()

    if insert_data:
        insert_query = """
        INSERT INTO Fact_Trade_Outcomes (Timestamp, Asset_ID, Strategy_ID, Signal_Value, Forward_Return, Is_Winner)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        try:
            cursor.executemany(insert_query, insert_data)
            conn.commit()
            print(f"Batch insert successful for Asset_ID {asset}")
        except pyodbc.IntegrityError as e:
            print(f"IntegrityError for Asset_ID {asset}: {e}")
            conn.rollback()
            for row in insert_data:
                try:
                    cursor.execute(insert_query, row)
                    conn.commit()
                except pyodbc.IntegrityError:
                    print(f"Skipping duplicate row for Asset_ID {asset}: {row}")
        except Exception as e:
            print(f"Error inserting for Asset_ID {asset}: {e}")

cursor.close()
conn.close()