import os
import pyodbc
import pandas as pd
from ta.trend import EMAIndicator, ADXIndicator
from ta.volatility import AverageTrueRange
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
CONN_STR = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={os.getenv('DB_SERVER')};UID={os.getenv('DB_USER')};PWD={os.getenv('DB_PASS')};DATABASE=ForexBrainDB;TrustServerCertificate=yes"

def get_asset_map():
    """Returns a dictionary: {'EUR_USD': 5, 'GBP_USD': 6, ...}"""
    conn = pyodbc.connect(CONN_STR)
    df = pd.read_sql("SELECT Symbol, Asset_ID FROM Dim_Asset", conn)
    conn.close()
    return dict(zip(df['Symbol'], df['Asset_ID']))

def get_market_data(asset_id):
    conn = pyodbc.connect(CONN_STR)
    query = f"""
        SELECT TOP 5000 Timestamp, [Close], [High], [Low] 
        FROM Fact_Market_Prices 
        WHERE Asset_ID = {asset_id} AND Granularity = 'H1'
        ORDER BY Timestamp ASC
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def get_regime_map(asset_id):
    conn = pyodbc.connect(CONN_STR)
    query = "SELECT Date, Regime_Type FROM Fact_Daily_Regime WHERE Asset_ID = ?"
    df = pd.read_sql(query, conn, params=[asset_id])
    conn.close()
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    return dict(zip(df['Date'], df['Regime_Type']))

def run_trend_strategy(symbol, asset_id):
    print(f"\n📈 Analyzing {symbol} (ID: {asset_id})...")
    
    # 1. Get Data
    df = get_market_data(asset_id)
    if df.empty:
        print(f"   ⚠️ No H1 data found for {symbol}. Did you run ingest_h1.py?")
        return

    regime_map = get_regime_map(asset_id)
    if not regime_map:
        print(f"   ⚠️ No Regime data found for {symbol}. Did you run detect_regime.py?")
        
    # 2. Calculate Indicators
    df['EMA_50'] = EMAIndicator(close=df['Close'], window=50).ema_indicator()
    df['EMA_200'] = EMAIndicator(close=df['Close'], window=200).ema_indicator()
    
    adx_ind = ADXIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=14)
    df['ADX'] = adx_ind.adx()
    
    atr_ind = AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close'], window=14)
    df['ATR'] = atr_ind.average_true_range()
    
    # 3. Generate Signals
    signals = []
    
    for i in range(200, len(df)):
        current_time = df.iloc[i]['Timestamp']
        current_date = current_time.date()
        
        # GATEKEEPER: Check Daily Regime
        daily_regime = regime_map.get(current_date, "UNKNOWN")
        
        price = df.iloc[i]['Close']
        ema_50 = df.iloc[i]['EMA_50']
        ema_200 = df.iloc[i]['EMA_200']
        prev_ema_50 = df.iloc[i-1]['EMA_50']
        prev_ema_200 = df.iloc[i-1]['EMA_200']
        adx = df.iloc[i]['ADX']
        atr = df.iloc[i]['ATR']
        
        # BUY LOGIC
        if daily_regime == 'BULLISH_TREND':
            # Golden Cross + Strong Trend
            if (ema_50 > ema_200) and (prev_ema_50 <= prev_ema_200) and (adx > 25):
                stop_loss = price - (atr * 3)
                signals.append((asset_id, current_time, 'BUY', price, stop_loss))
        
        # SELL LOGIC
        elif daily_regime == 'BEARISH_TREND':
            # Death Cross + Strong Trend
            if (ema_50 < ema_200) and (prev_ema_50 >= prev_ema_200) and (adx > 25):
                stop_loss = price + (atr * 3)
                signals.append((asset_id, current_time, 'SELL', price, stop_loss))

    # 4. Save to Database
    if signals:
        print(f"   🚀 FOUND {len(signals)} TRADES! Saving to DB...")
        save_signals_to_db(signals)
    else:
        print("   😴 No trades found. Market conditions did not align.")

def save_signals_to_db(signals):
    conn = pyodbc.connect(CONN_STR)
    cursor = conn.cursor()
    
    query = """
    INSERT INTO Fact_Signals (Asset_ID, Timestamp, Signal_Type, Entry_Price, Stop_Loss, Take_Profit, Signal_Strength)
    VALUES (?, ?, ?, ?, ?, 0, 1.0)
    """
    
    cursor.executemany(query, signals)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    # AUTOMATICALLY FIND ASSETS
    assets = get_asset_map()
    
    # Run for EUR_USD and GBP_USD specifically
    targets = ['EUR_USD', 'GBP_USD']
    
    for symbol in targets:
        if symbol in assets:
            run_trend_strategy(symbol, assets[symbol])
        else:
            print(f"❌ Could not find ID for {symbol}")
