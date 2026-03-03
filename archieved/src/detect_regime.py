import os
import pyodbc
import pandas as pd
# We changed this library:
from ta.trend import SMAIndicator, ADXIndicator
from ta.volatility import AverageTrueRange
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
SERVER = os.getenv("DB_SERVER", "localhost")
USER = os.getenv("DB_USER", "sa")
PASS = os.getenv("DB_PASS")
DB_NAME = "ForexBrainDB"
DRIVER = "ODBC Driver 17 for SQL Server"

CONN_STR = f"DRIVER={{{DRIVER}}};SERVER={SERVER};UID={USER};PWD={PASS};DATABASE={DB_NAME};TrustServerCertificate=yes"

def get_daily_data(asset_id):
    """Fetch raw D1 candles from the Warehouse."""
    conn = pyodbc.connect(CONN_STR)
    query = f"""
        SELECT Timestamp, [Close], High, Low 
        FROM Fact_Market_Prices 
        WHERE Asset_ID = {asset_id} AND Granularity = 'D'
        ORDER BY Timestamp ASC
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def calculate_metrics(df):
    """The MATH Layer: Calculates Indicators using 'ta' library."""
    # Ensure columns are lowercase for consistency
    df.rename(columns={'Timestamp': 'date', 'Close': 'close', 'High': 'high', 'Low': 'low'}, inplace=True)
    df.set_index('date', inplace=True)
    
    # 1. Simple Moving Averages
    # We use the class-based approach from 'ta' library
    df['SMA_50'] = SMAIndicator(close=df['close'], window=50).sma_indicator()
    df['SMA_200'] = SMAIndicator(close=df['close'], window=200).sma_indicator()
    
    # 2. ATR (Volatility)
    atr_indicator = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
    df['ATR_14'] = atr_indicator.average_true_range()
    
    # 3. ADX (Trend Strength)
    adx_indicator = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14)
    df['ADX'] = adx_indicator.adx()
    
    return df.dropna()

def define_regime(row):
    """The LOGIC Layer: Classifies the Market."""
    price = row['close']
    sma50 = row['SMA_50']
    sma200 = row['SMA_200']
    adx = row['ADX']
    
    if price > sma50 and sma50 > sma200:
        return "BULLISH_TREND"
    elif price < sma50 and sma50 < sma200:
        return "BEARISH_TREND"
    elif adx < 20:
        return "SIDEWAYS_QUIET"
    else:
        return "SIDEWAYS_CHOPPY"

def process_regimes():
    conn = pyodbc.connect(CONN_STR)
    cursor = conn.cursor()
    
    # Get all assets
    cursor.execute("SELECT Asset_ID, Symbol FROM Dim_Asset")
    assets = cursor.fetchall()
    
    for asset_id, symbol in assets:
        print(f"🧠 Analyzing Regime for {symbol}...")
        
        # 1. Get Data
        df = get_daily_data(asset_id)
        if df.empty:
            print(f"   ⚠️ No Daily data found for {symbol}. Skipping.")
            continue
            
        # 2. Calculate Math
        try:
            df = calculate_metrics(df)
        except Exception as e:
            print(f"   ❌ Math Error on {symbol}: {e}")
            continue
        
        # 3. Apply Logic
        df['Regime'] = df.apply(define_regime, axis=1)
        
        # 4. Save to DB
        print(f"   💾 Saving {len(df)} days of analysis...")
        
        batch_data = []
        for date_idx, row in df.iterrows():
            # Volatility Flag: If ATR is > 1.5% of price, it's Volatile
            is_volatile = 1 if (row['ATR_14'] / row['close']) > 0.015 else 0
            
            batch_data.append((
                asset_id, date_idx, row['Regime'], 
                row['SMA_50'], row['SMA_200'], row['ATR_14'], is_volatile
            ))

        # Refresh Data for this Asset
        cursor.execute("DELETE FROM Fact_Daily_Regime WHERE Asset_ID = ?", asset_id)
        
        insert_query = """
        INSERT INTO Fact_Daily_Regime (Asset_ID, Date, Regime_Type, SMA_50, SMA_200, ATR_14, Is_High_Volatility)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        
        cursor.executemany(insert_query, batch_data)
        conn.commit()
        
    print("✅ Regime Analysis Complete.")
    conn.close()

if __name__ == "__main__":
    process_regimes()
