import pyodbc
import os
from dotenv import load_dotenv
import pandas as pd
import numpy as np
from numba import jit

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

# Drop and create Fact_Trade_Outcomes
drop_create_query = """
IF OBJECT_ID('Fact_Trade_Outcomes', 'U') IS NOT NULL
    DROP TABLE Fact_Trade_Outcomes;

CREATE TABLE Fact_Trade_Outcomes (
    Timestamp DATETIME,
    Asset_ID INT,
    Strategy_ID INT,
    Signal_Value INT,
    Forward_Return FLOAT,
    Is_Winner INT,
    PRIMARY KEY (Timestamp, Asset_ID, Strategy_ID)
);
"""
cursor.execute(drop_create_query)
conn.commit()

# Asset symbols for printing
asset_symbols = {
    5: "EUR_USD",
    6: "GBP_USD",
    7: "USD_JPY"
}

# Get unique Asset_IDs with active signals
cursor.execute("""
SELECT DISTINCT Asset_ID 
FROM Fact_Signals 
WHERE Signal_Value IN (1, -1)
""")
assets = [row[0] for row in cursor.fetchall()]

print("======================================================================")
print(" Generating Dynamic ATR-Based Trade Outcomes")
print("======================================================================")

# Numba-optimized function for calculating outcomes
@jit(nopython=True)
def calculate_outcomes(signal_indices, atrs, signals, closes, highs, lows):
    outcomes = np.zeros((len(signal_indices), 3))  # is_winner, forward_return, exit_found (dummy)
    for i in range(len(signal_indices)):
        idx = signal_indices[i]
        entry = closes[idx]
        atr = atrs[i]
        sig = signals[i]
        
        if sig == 1:
            sl = entry - atr
            tp = entry + 3 * atr
        else:
            sl = entry + atr
            tp = entry - 3 * atr
        
        hit_tp = False
        hit_sl = False
        exit_price = 0.0
        
        max_steps = min(120, len(closes) - idx - 1)
        for j in range(1, max_steps + 1):
            if sig == 1:
                if highs[idx + j] >= tp:
                    hit_tp = True
                    exit_price = tp
                    break
                if lows[idx + j] <= sl:
                    hit_sl = True
                    exit_price = sl
                    break
            else:
                if lows[idx + j] <= tp:
                    hit_tp = True
                    exit_price = tp
                    break
                if highs[idx + j] >= sl:
                    hit_sl = True
                    exit_price = sl
                    break
        
        if not (hit_tp or hit_sl):
            exit_price = closes[idx + max_steps] if max_steps > 0 else entry
        
        forward_return = (exit_price - entry) / entry * sig
        if hit_tp:
            is_winner = 1
        elif hit_sl:
            is_winner = 0
        else:
            is_winner = 1 if forward_return > 0 else 0
        
        outcomes[i, 0] = is_winner
        outcomes[i, 1] = forward_return
        # outcomes[i, 2] unused
    
    return outcomes

# Insert query
insert_query = """
INSERT INTO Fact_Trade_Outcomes 
(Timestamp, Asset_ID, Strategy_ID, Signal_Value, Forward_Return, Is_Winner) 
VALUES (?, ?, ?, ?, ?, ?)
"""

for asset_id in assets:
    symbol = asset_symbols.get(asset_id, f"Asset_{asset_id}")
    
    print(f"──────────────────────────────────────────────────")
    print(f"  Processing Asset {asset_id}: {symbol}")
    print(f"──────────────────────────────────────────────────")
    
    # Fetch full prices for asset
    price_query = """
    SELECT Timestamp, High, Low, [Close]
    FROM Fact_Market_Prices
    WHERE Asset_ID = ?
    ORDER BY Timestamp
    """
    df_prices = pd.read_sql(price_query, conn, params=[asset_id], parse_dates=['Timestamp'], index_col='Timestamp')
    
    if df_prices.empty:
        print(f"  No price data for {symbol}. Skipping.")
        continue
    
    # Fetch signals and ATR
    signal_query = """
    SELECT fs.Timestamp, fs.Strategy_ID, fs.Signal_Value, fmr.ATR_Value
    FROM Fact_Signals fs
    INNER JOIN Fact_Market_Regime fmr ON fs.Timestamp = fmr.Timestamp AND fs.Asset_ID = fmr.Asset_ID
    WHERE fs.Asset_ID = ? AND fs.Signal_Value IN (1, -1)
    ORDER BY fs.Timestamp
    """
    df_signals = pd.read_sql(signal_query, conn, params=[asset_id], parse_dates=['Timestamp'], index_col='Timestamp')
    
    if df_signals.empty:
        print(f"  No signals for {symbol}. Skipping.")
        continue
    
    # Align signals with prices (assuming timestamps match)
    df_combined = df_prices.join(df_signals, how='left')
    
    # Get signal rows
    signal_mask = df_combined['Signal_Value'].notna()
    signal_indices = np.where(signal_mask)[0]
    
    if len(signal_indices) == 0:
        continue
    
    # Extract arrays for numba
    closes = df_combined['Close'].values
    highs = df_combined['High'].values
    lows = df_combined['Low'].values
    atrs = df_combined.loc[signal_mask, 'ATR_Value'].values
    signals = df_combined.loc[signal_mask, 'Signal_Value'].values.astype(np.int32)
    timestamps = df_combined.index[signal_mask]
    strategy_ids = df_combined.loc[signal_mask, 'Strategy_ID'].values.astype(np.int32)
    
    # Compute outcomes
    outcomes = calculate_outcomes(signal_indices, atrs, signals, closes, highs, lows)
    
# Prepare insert data (FIXED: Cast NumPy types to native Python types)
    inserts = []
    for i in range(len(signal_indices)):
        ts = timestamps[i].to_pydatetime()  # Cast to native Python datetime
        strat_id = int(strategy_ids[i])     # Cast away numpy.int32
        sig = int(signals[i])               # Cast away numpy.int32
        fwd_ret = float(outcomes[i, 1])     # Cast away numpy float
        is_win = int(outcomes[i, 0])        # Already cast, but keeping for consistency
        inserts.append((ts, int(asset_id), strat_id, sig, fwd_ret, is_win))
    
    total_rows = len(inserts)
    print(f"  [{symbol}] Calculated {total_rows:,} outcomes.")
    
    batch_size = 5000
    inserted = 0
    batch_num = 0
    
    for i in range(0, total_rows, batch_size):
        batch_num += 1
        batch = inserts[i:i + batch_size]
        
        try:
            cursor.executemany(insert_query, batch)
            conn.commit()
            inserted += len(batch)
            print(f"  [{symbol}] Inserted batch {batch_num} ({inserted:,}/{total_rows:,} rows)")
        except pyodbc.IntegrityError:
            conn.rollback()
            inserted_this_batch = 0
            for single in batch:
                try:
                    cursor.execute(insert_query, single)
                    conn.commit()
                    inserted_this_batch += 1
                except pyodbc.IntegrityError:
                    pass  # Skip duplicate
            inserted += inserted_this_batch
            print(f"  [{symbol}] Inserted batch {batch_num} ({inserted:,}/{total_rows:,} rows) with fallback")
    
    print(f"  [{symbol}] Processing complete. {inserted:,} rows inserted.")

# Final natural win rate
cursor.execute("SELECT AVG(CAST(Is_Winner AS FLOAT)) FROM Fact_Trade_Outcomes")
win_rate = cursor.fetchone()[0]
print("======================================================================")
print(f" Pipeline complete. Natural Win Rate: {win_rate:.2%}")
print("======================================================================")

# Clean up
cursor.close()
conn.close()