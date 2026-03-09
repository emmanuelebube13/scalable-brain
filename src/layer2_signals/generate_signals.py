import pyodbc
import os
from dotenv import load_dotenv
import pandas as pd
import warnings
from ta.trend import EMAIndicator, ADXIndicator
from ta.volatility import BollingerBands, DonchianChannel
from ta.momentum import RSIIndicator, StochasticOscillator

# Suppress pandas SQL warning for clean terminal output
warnings.filterwarnings('ignore', category=UserWarning)

# Load environment variables
load_dotenv()
DB_SERVER = os.getenv('DB_SERVER')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')
DB_NAME = 'ForexBrainDB'

# Connect to SQL Server
conn = pyodbc.connect(f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={DB_SERVER};DATABASE={DB_NAME};UID={DB_USER};PWD={DB_PASS}')
cursor = conn.cursor()
cursor.fast_executemany = True

# Create Fact_Signals table if it doesn't exist
create_table_query = """
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Fact_Signals]') AND type in (N'U'))
BEGIN
    CREATE TABLE Fact_Signals (
        Timestamp DATETIME,
        Asset_ID INT,
        Strategy_ID INT,
        Signal_Value INT,
        PRIMARY KEY (Timestamp, Asset_ID, Strategy_ID)
    )
END
"""
cursor.execute(create_table_query)
conn.commit()

# Asset symbols for pretty printing
asset_symbols = {5: "EUR_USD", 6: "GBP_USD", 7: "USD_JPY"}

# Get unique Asset_IDs from our registry
cursor.execute("SELECT DISTINCT Asset_ID FROM Dim_Strategy_Registry")
assets = [row[0] for row in cursor.fetchall()]

print("======================================================================")
print(" LAYER 2: Signal Generation & Ingestion Pipeline")
print("======================================================================")

insert_query = "INSERT INTO Fact_Signals (Timestamp, Asset_ID, Strategy_ID, Signal_Value) VALUES (?, ?, ?, ?)"

for asset_id in assets:
    symbol = asset_symbols.get(asset_id, f"Asset_{asset_id}")
    
    print("──────────────────────────────────────────────────")
    print(f"  Processing Asset {asset_id}: {symbol}")
    print("──────────────────────────────────────────────────")
    
    # Get strategies for this asset (Removed the Is_Active check)
    cursor.execute("SELECT Strategy_ID, Strategy_Name FROM Dim_Strategy_Registry WHERE Asset_ID = ?", asset_id)
    strategies = cursor.fetchall()
    
    if not strategies:
        print(f"  No strategies for {symbol}. Skipping.")
        continue
    
    # Fetch historical data
    price_query = """
    SELECT Timestamp, [Open], High, Low, [Close], Volume 
    FROM Fact_Market_Prices 
    WHERE Asset_ID = ? AND Granularity = 'H1' 
    ORDER BY Timestamp
    """
    df = pd.read_sql(price_query, conn, params=[asset_id], parse_dates=['Timestamp'])
    
    if df.empty:
        print(f"  No price data for {symbol}. Skipping.")
        continue
    
    # Calculate all indicators
    df['ema50'] = EMAIndicator(df['Close'], window=50).ema_indicator()
    df['ema200'] = EMAIndicator(df['Close'], window=200).ema_indicator()
    df['adx14'] = ADXIndicator(df['High'], df['Low'], df['Close'], window=14).adx()
    bb = BollingerBands(df['Close'], window=20, window_dev=2)
    df['bb_lower'] = bb.bollinger_lband()
    df['bb_upper'] = bb.bollinger_hband()
    df['rsi14'] = RSIIndicator(df['Close'], window=14).rsi()
    donch = DonchianChannel(df['High'], df['Low'], df['Close'], window=20)
    df['donch_high'] = donch.donchian_channel_hband()
    df['donch_low'] = donch.donchian_channel_lband()
    stoch = StochasticOscillator(df['High'], df['Low'], df['Close'], window=14, smooth_window=3)
    df['stoch_k'] = stoch.stoch()
    df['stoch_k_prev'] = df['stoch_k'].shift(1)
    
    # Drop warm-up rows
    df.dropna(inplace=True)
    
    # Process each strategy
    for strat_id, strat_name in strategies:
        print(f"  [{symbol}] Generating signals for {strat_name} (Strategy_ID: {strat_id})")
        
        # Initialize signal column to 0
        df['signal'] = 0
        
        # FIX: Use startswith() to bypass the _EUR_USD suffix
        if strat_name.startswith('Trend_EMA_ADX'):
            df.loc[(df['ema50'] > df['ema200']) & (df['adx14'] > 25), 'signal'] = 1
            df.loc[(df['ema50'] < df['ema200']) & (df['adx14'] > 25), 'signal'] = -1
            
        elif strat_name.startswith('Range_Bollinger'):
            df.loc[(df['Low'] < df['bb_lower']) & (df['rsi14'] < 30), 'signal'] = 1
            df.loc[(df['High'] > df['bb_upper']) & (df['rsi14'] > 70), 'signal'] = -1
            
        elif strat_name.startswith('Trend_Donchian'):
            df.loc[df['Close'] >= df['donch_high'], 'signal'] = 1
            df.loc[df['Close'] <= df['donch_low'], 'signal'] = -1
            
        elif strat_name.startswith('Range_Stochastic'):
            df.loc[(df['stoch_k_prev'] <= 20) & (df['stoch_k'] > 20), 'signal'] = 1
            df.loc[(df['stoch_k_prev'] >= 80) & (df['stoch_k'] < 80), 'signal'] = -1
            
        else:
            print(f"  Unknown strategy logic for '{strat_name}'. Skipping.")
            continue
        
        # Prepare insert data
        inserts = [(row['Timestamp'], asset_id, strat_id, int(row['signal'])) for _, row in df.iterrows()]
        
        if not inserts:
            continue
            
        batch_size = 5000
        inserted = 0
        batch_num = 0
        
        for i in range(0, len(inserts), batch_size):
            batch_num += 1
            batch = inserts[i:i + batch_size]
            
            try:
                cursor.executemany(insert_query, batch)
                conn.commit()
                inserted += len(batch)
            except pyodbc.IntegrityError:
                inserted_this_batch = 0
                for single in batch:
                    try:
                        cursor.execute(insert_query, single)
                        conn.commit()
                        inserted_this_batch += 1
                    except pyodbc.IntegrityError:
                        pass
                inserted += inserted_this_batch
                
        print(f"  [{symbol}] ✔ Ingestion complete. {inserted:,} rows written to Fact_Signals.")

print("======================================================================")
print(" Pipeline complete. All signals ingested into Fact_Signals.")
print("======================================================================")

cursor.close()
conn.close()