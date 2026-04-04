import pyodbc
import os
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
import numpy as np
from numba import jit

# Load environment variables
SCRIPT_DIR = Path(__file__).resolve().parent
APP_ROOT = SCRIPT_DIR.parents[2]
WORKSPACE_ROOT = APP_ROOT.parent
load_dotenv(APP_ROOT / '.env')
load_dotenv(WORKSPACE_ROOT / '.env')

DB_SERVER = os.getenv('DB_SERVER')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')
DB_NAME = os.getenv('DB_NAME', 'ForexBrainDB')
DB_ODBC_DRIVER = os.getenv('DB_ODBC_DRIVER')
DEFAULT_TRADE_HORIZON = int(os.getenv('DEFAULT_TRADE_HORIZON', '120'))


def select_sqlserver_odbc_driver():
    available = set(pyodbc.drivers())
    candidates = []
    if DB_ODBC_DRIVER:
        candidates.append(DB_ODBC_DRIVER)
    candidates.extend([
        'ODBC Driver 18 for SQL Server',
        'ODBC Driver 17 for SQL Server',
    ])

    for candidate in candidates:
        if candidate in available:
            return candidate

    raise RuntimeError(
        "No supported SQL Server ODBC driver found. "
        f"Detected drivers: {sorted(available)}. "
        "Install ODBC Driver 18 for SQL Server or set DB_ODBC_DRIVER."
    )


SQLSERVER_ODBC_DRIVER = select_sqlserver_odbc_driver()

if not DB_SERVER or not DB_USER or not DB_PASS:
    raise RuntimeError("Missing DB_SERVER, DB_USER, or DB_PASS in environment.")

# Connect to SQL Server
conn = pyodbc.connect(
    f'DRIVER={{{SQLSERVER_ODBC_DRIVER}}};SERVER={DB_SERVER};DATABASE={DB_NAME};UID={DB_USER};PWD={DB_PASS};TrustServerCertificate=yes;'
)
cursor = conn.cursor()
cursor.fast_executemany = True


def table_columns(table_name):
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ?
        """,
        table_name,
    )
    return {row[0] for row in cursor.fetchall()}


def table_exists(table_name):
    cursor.execute(
        """
        SELECT CASE WHEN EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?
        ) THEN 1 ELSE 0 END
        """,
        table_name,
    )
    return bool(cursor.fetchone()[0])


def pick_column(columns, candidates):
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def pick_regime_table():
    if table_exists('Fact_Market_Regime_V2'):
        return 'Fact_Market_Regime_V2'
    if table_exists('Fact_Market_Regime'):
        return 'Fact_Market_Regime'
    raise RuntimeError('No regime fact table found. Expected Fact_Market_Regime_V2 or Fact_Market_Regime.')


regime_table = pick_regime_table()
regime_cols = table_columns(regime_table)
signal_cols = table_columns('Fact_Signals')
horizon_col = pick_column(signal_cols, ['Trade_Horizon', 'Horizon', 'Signal_Horizon'])

if 'Granularity' not in signal_cols:
    raise RuntimeError('Fact_Signals must include Granularity before generating outcomes.')
if 'Granularity' not in regime_cols:
    raise RuntimeError(f'{regime_table} must include Granularity before generating outcomes.')

# Drop and create Fact_Trade_Outcomes
drop_create_query = """
IF OBJECT_ID('Fact_Trade_Outcomes', 'U') IS NOT NULL
    DROP TABLE Fact_Trade_Outcomes;

CREATE TABLE Fact_Trade_Outcomes (
    Timestamp DATETIME,
    Asset_ID INT,
    Strategy_ID INT,
    Granularity VARCHAR(10) NOT NULL,
    Trade_Horizon INT NOT NULL,
    Signal_Value INT,
    Forward_Return FLOAT,
    Is_Winner INT,
    PRIMARY KEY (Timestamp, Asset_ID, Strategy_ID, Granularity, Trade_Horizon)
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

# Get unique Asset_IDs and granularities with active signals
cursor.execute("""
SELECT DISTINCT Asset_ID, Granularity 
FROM Fact_Signals 
WHERE Signal_Value IN (1, -1)
ORDER BY Asset_ID, Granularity
""")
asset_slices = [(row[0], row[1]) for row in cursor.fetchall()]

print("======================================================================")
print(" Generating Dynamic ATR-Based Trade Outcomes")
print("======================================================================")

# Numba-optimized function for calculating outcomes
@jit(nopython=True)
def calculate_outcomes(signal_indices, horizons, atrs, signals, closes, highs, lows):
    outcomes = np.zeros((len(signal_indices), 3))  # is_winner, forward_return, exit_found (dummy)
    for i in range(len(signal_indices)):
        idx = signal_indices[i]
        entry = closes[idx]
        atr = atrs[i]
        sig = signals[i]
        horizon = int(horizons[i])

        if horizon <= 0:
            horizon = 1
        
        if sig == 1:
            sl = entry - atr
            tp = entry + 3 * atr
        else:
            sl = entry + atr
            tp = entry - 3 * atr
        
        hit_tp = False
        hit_sl = False
        exit_price = 0.0
        
        max_steps = min(horizon, len(closes) - idx - 1)
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

insert_query = """
INSERT INTO Fact_Trade_Outcomes 
(Timestamp, Asset_ID, Strategy_ID, Granularity, Trade_Horizon, Signal_Value, Forward_Return, Is_Winner) 
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

for asset_id, granularity in asset_slices:
    symbol = asset_symbols.get(asset_id, f"Asset_{asset_id}")
    
    print(f"──────────────────────────────────────────────────")
    print(f"  Processing Asset {asset_id}: {symbol} @ {granularity}")
    print(f"──────────────────────────────────────────────────")
    
    # Fetch full prices for asset
    price_query = """
    SELECT Timestamp, High, Low, [Close]
    FROM Fact_Market_Prices
    WHERE Asset_ID = ? AND Granularity = ?
    ORDER BY Timestamp
    """
    df_prices = pd.read_sql(price_query, conn, params=[asset_id, granularity], parse_dates=['Timestamp'], index_col='Timestamp')
    
    if df_prices.empty:
        print(f"  No price data for {symbol} @ {granularity}. Skipping.")
        continue
    
    # Fetch signals and ATR
    signal_query = f"""
    SELECT fs.Timestamp, fs.Strategy_ID, fs.Signal_Value, fs.Granularity, fmr.ATR_Value{', fs.' + horizon_col if horizon_col else ''}
    FROM Fact_Signals fs
    INNER JOIN {regime_table} fmr
        ON fs.Timestamp = fmr.Timestamp
       AND fs.Asset_ID = fmr.Asset_ID
       AND fs.Granularity = fmr.Granularity
    WHERE fs.Asset_ID = ? AND fs.Granularity = ? AND fs.Signal_Value IN (1, -1)
    ORDER BY fs.Timestamp
    """
    df_signals = pd.read_sql(signal_query, conn, params=[asset_id, granularity], parse_dates=['Timestamp'])
    
    if df_signals.empty:
        print(f"  No signals for {symbol} @ {granularity}. Skipping.")
        continue

    price_index_map = {ts: idx for idx, ts in enumerate(df_prices.index)}
    signal_indices = []
    signal_rows = []
    for row in df_signals.itertuples(index=False):
        price_idx = price_index_map.get(row.Timestamp)
        if price_idx is None:
            continue
        signal_indices.append(price_idx)
        signal_rows.append(row)
    
    if len(signal_indices) == 0:
        continue
    
    # Extract arrays for numba
    closes = df_prices['Close'].values
    highs = df_prices['High'].values
    lows = df_prices['Low'].values
    atrs = np.array([float(row.ATR_Value) for row in signal_rows], dtype=np.float64)
    signals = np.array([int(row.Signal_Value) for row in signal_rows], dtype=np.int32)
    horizons = np.array([
        int(getattr(row, horizon_col)) if horizon_col and getattr(row, horizon_col) is not None else DEFAULT_TRADE_HORIZON
        for row in signal_rows
    ], dtype=np.int32)
    timestamps = [row.Timestamp.to_pydatetime() for row in signal_rows]
    strategy_ids = np.array([int(row.Strategy_ID) for row in signal_rows], dtype=np.int32)
    
    # Compute outcomes
    outcomes = calculate_outcomes(np.array(signal_indices, dtype=np.int32), horizons, atrs, signals, closes, highs, lows)
    
# Prepare insert data (FIXED: Cast NumPy types to native Python types)
    inserts = []
    for i in range(len(signal_indices)):
        ts = timestamps[i]
        strat_id = int(strategy_ids[i])     # Cast away numpy.int32
        sig = int(signals[i])               # Cast away numpy.int32
        fwd_ret = float(outcomes[i, 1])     # Cast away numpy float
        is_win = int(outcomes[i, 0])        # Already cast, but keeping for consistency
        inserts.append((ts, int(asset_id), strat_id, granularity, int(horizons[i]), sig, fwd_ret, is_win))
    
    total_rows = len(inserts)
    print(f"  [{symbol} @ {granularity}] Calculated {total_rows:,} outcomes.")
    
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
            print(f"  [{symbol} @ {granularity}] Inserted batch {batch_num} ({inserted:,}/{total_rows:,} rows)")
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
            print(f"  [{symbol} @ {granularity}] Inserted batch {batch_num} ({inserted:,}/{total_rows:,} rows) with fallback")
    
    print(f"  [{symbol} @ {granularity}] Processing complete. {inserted:,} rows inserted.")

# Final natural win rate
cursor.execute("SELECT AVG(CAST(Is_Winner AS FLOAT)) FROM Fact_Trade_Outcomes")
win_rate = cursor.fetchone()[0]
print("======================================================================")
print(f" Pipeline complete. Natural Win Rate: {win_rate:.2%}")
print("======================================================================")

# Clean up
cursor.close()
conn.close()
