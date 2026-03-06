import os
import pyodbc
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
CONN_STR = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={os.getenv('DB_SERVER')};UID={os.getenv('DB_USER')};PWD={os.getenv('DB_PASS')};DATABASE=ForexBrainDB;TrustServerCertificate=yes"

def fetch_raw_data(asset_id):
    print(f"📥 Fetching raw H1 data for Asset ID: {asset_id}...")
    conn = pyodbc.connect(CONN_STR)
    query = f"""
        SELECT Timestamp, [Open], [High], [Low], [Close], Volume 
        FROM Fact_Market_Prices 
        WHERE Asset_ID = {asset_id} AND Granularity = 'H1'
        ORDER BY Timestamp ASC
    """
    df = pd.read_sql(query, conn)
    conn.close()
    
    # Ensure Timestamp is a datetime object for our new Temporal logic
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    return df

def generate_features(df):
    print("⚙️ Engineering Technical Features (RSI, EMAs, ADX, ATR)...")
    
    # --- 1. CORE TECHNICALS ---
    df['EMA_50'] = EMAIndicator(close=df['Close'], window=50).ema_indicator()
    df['EMA_200'] = EMAIndicator(close=df['Close'], window=200).ema_indicator()
    df['RSI'] = RSIIndicator(close=df['Close'], window=14).rsi()
    df['ADX'] = ADXIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=14).adx()
    df['ATR'] = AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close'], window=14).average_true_range()
    
    # --- 2. TEMPORAL AWARENESS (Market Sessions) ---
    print("🌍 Injecting Temporal Awareness (London/NY Sessions)...")
    # Assuming Oanda data is in UTC. 
    # London Open: ~08:00 UTC | NY Open: ~13:00 UTC | London Close: ~16:00 UTC
    df['Hour_UTC'] = df['Timestamp'].dt.hour
    
    df['Is_London_Session'] = np.where((df['Hour_UTC'] >= 8) & (df['Hour_UTC'] < 16), 1, 0)
    df['Is_NY_Session'] = np.where((df['Hour_UTC'] >= 13) & (df['Hour_UTC'] < 21), 1, 0)
    
    # The most volatile/liquid time of day
    df['Is_London_NY_Overlap'] = np.where((df['Is_London_Session'] == 1) & (df['Is_NY_Session'] == 1), 1, 0)
    
    # Clean up the hour column as we now have the one-hot encoded sessions
    df = df.drop(columns=['Hour_UTC'])

    # --- 3. MULTI-TIMEFRAME (MTF) ALIGNMENT ---
    print("🔭 Injecting Multi-Timeframe Alignment (H4 Trend)...")
    # We set the index to Timestamp to allow for easy resampling
    df_temp = df.set_index('Timestamp').copy()
    
    # Resample H1 data to H4 (taking the last close of every 4-hour block)
    df_h4 = df_temp['Close'].resample('4h').last().to_frame(name='H4_Close')
    
    # Calculate the 50 EMA on the new H4 timeframe
    df_h4['H4_EMA_50'] = EMAIndicator(close=df_h4['H4_Close'], window=50).ema_indicator()
    
    # Determine the H4 Trend (1 = Bullish, 0 = Bearish)
    df_h4['H4_Trend_Bullish'] = np.where(df_h4['H4_Close'] > df_h4['H4_EMA_50'], 1, 0)
    
    # Map the H4 Trend back to the original H1 dataframe
    # We use 'ffill' (forward fill) so the H1 candles know what the *last closed* H4 trend was
    df = df.merge(df_h4[['H4_Trend_Bullish']], left_on='Timestamp', right_index=True, how='left')
    df['H4_Trend_Bullish'] = df['H4_Trend_Bullish'].ffill()

    # --- 4. THE GROUND TRUTH (1:2 Risk/Reward Setup) ---
    print("🎯 Calculating the Ground Truth (Dynamic ATR R:R Strategy)...")
    lookahead = 24  
    
    df['Future_Max'] = df['High'].rolling(lookahead).max().shift(-lookahead)
    df['Future_Min'] = df['Low'].rolling(lookahead).min().shift(-lookahead)
    
    df['Take_Profit_Buy'] = df['Close'] + (2.0 * df['ATR'])
    df['Stop_Loss_Buy'] = df['Close'] - (1.0 * df['ATR'])
    
    df['Take_Profit_Sell'] = df['Close'] - (2.0 * df['ATR'])
    df['Stop_Loss_Sell'] = df['Close'] + (1.0 * df['ATR'])
    
    buy_condition = (df['Future_Max'] >= df['Take_Profit_Buy']) & (df['Future_Min'] > df['Stop_Loss_Buy'])
    sell_condition = (df['Future_Min'] <= df['Take_Profit_Sell']) & (df['Future_Max'] < df['Stop_Loss_Sell'])
    
    df['Target_Class'] = np.select([buy_condition, sell_condition], [1, -1], default=0)
    
    # Clean up intermediate calculation columns
    cols_to_drop = ['Future_Max', 'Future_Min', 'Take_Profit_Buy', 'Stop_Loss_Buy', 'Take_Profit_Sell', 'Stop_Loss_Sell']
    df = df.drop(columns=cols_to_drop)
    df = df.dropna().copy()
    
    return df

def save_and_verify(df, asset_id):
    print("\n✅ DATASET GENERATION COMPLETE")
    print("-" * 30)
    print(f"Total Usable Rows: {len(df)}")
    
    buy_count = len(df[df['Target_Class'] == 1])
    sell_count = len(df[df['Target_Class'] == -1])
    hold_count = len(df[df['Target_Class'] == 0])
    
    print(f"📈 1:2 R/R Buy Setups (1):   {buy_count}")
    print(f"📉 1:2 R/R Sell Setups (-1): {sell_count}")
    print(f"⏸️ Invalid/Chop Setups (0):  {hold_count}")
    print("-" * 30)
    
    os.makedirs('data/processed', exist_ok=True)
    filepath = f'data/processed/asset_{asset_id}_ml_data.csv'
    df.to_csv(filepath, index=False)
    print(f"💾 Saved cleanly to: {filepath}")

if __name__ == "__main__":
    raw_df = fetch_raw_data(5)
    if not raw_df.empty:
        ml_dataset = generate_features(raw_df)
        save_and_verify(ml_dataset, 5)
