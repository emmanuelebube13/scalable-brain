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

# Dynamic ATR multiplier configuration (matching Layer 0 strategy defaults)
# Layer 0 Range_Stochastic uses 1.5 ATR for both SL and TP
SL_ATR_MULTIPLIER = float(os.getenv('SL_ATR_MULTIPLIER', '1.5'))
TP_ATR_MULTIPLIER = float(os.getenv('TP_ATR_MULTIPLIER', '1.5'))


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
    R_Multiple FLOAT,  -- Added: Risk-multiple of the trade outcome
    ATR_SL_Multiplier FLOAT,  -- Added: SL multiplier used for this outcome
    ATR_TP_Multiplier FLOAT,  -- Added: TP multiplier used for this outcome
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

# Numba-optimized function for calculating outcomes with dynamic ATR multipliers
@jit(nopython=True)
def calculate_outcomes(
    signal_indices, 
    horizons, 
    atrs, 
    signals, 
    closes, 
    highs, 
    lows,
    sl_atr_multiplier=1.5,  # Default SL: 1.5 ATR
    tp_atr_multiplier=1.5   # Default TP: 1.5 ATR (matching Layer 0 strategy config)
):
    """
    Calculate trade outcomes with dynamic ATR-based barriers.
    
    Args:
        signal_indices: Indices of signals in price arrays
        horizons: Maximum bars to hold each trade
        atrs: ATR values at signal time
        signals: Signal directions (1=long, -1=short)
        closes: Close prices
        highs: High prices
        lows: Low prices
        sl_atr_multiplier: Stop loss distance in ATR multiples (default 1.5)
        tp_atr_multiplier: Take profit distance in ATR multiples (default 1.5)
    
    Returns:
        outcomes: Array with columns [is_winner, forward_return, exit_price]
    """
    outcomes = np.zeros((len(signal_indices), 3))  # is_winner, forward_return, exit_price
    
    for i in range(len(signal_indices)):
        idx = signal_indices[i]
        entry = closes[idx]
        atr = atrs[i]
        sig = signals[i]
        horizon = int(horizons[i])

        if horizon <= 0:
            horizon = 1
        
        # Dynamic ATR-based barriers based on strategy configuration
        if sig == 1:  # Long position
            sl = entry - (sl_atr_multiplier * atr)
            tp = entry + (tp_atr_multiplier * atr)
        else:  # Short position
            sl = entry + (sl_atr_multiplier * atr)
            tp = entry - (tp_atr_multiplier * atr)
        
        hit_tp = False
        hit_sl = False
        exit_price = 0.0
        
        max_steps = min(horizon, len(closes) - idx - 1)
        for j in range(1, max_steps + 1):
            if sig == 1:  # Long: check if high hits TP or low hits SL
                if highs[idx + j] >= tp:
                    hit_tp = True
                    exit_price = tp
                    break
                if lows[idx + j] <= sl:
                    hit_sl = True
                    exit_price = sl
                    break
            else:  # Short: check if low hits TP or high hits SL
                if lows[idx + j] <= tp:
                    hit_tp = True
                    exit_price = tp
                    break
                if highs[idx + j] >= sl:
                    hit_sl = True
                    exit_price = sl
                    break
        
        if not (hit_tp or hit_sl):
            # Neither barrier hit - exit at horizon
            exit_price = closes[idx + max_steps] if max_steps > 0 else entry
        
        # Calculate forward return
        forward_return = (exit_price - entry) / entry * sig
        
        # Determine winner: 1 if TP hit, 0 if SL hit, otherwise based on P&L
        if hit_tp:
            is_winner = 1
        elif hit_sl:
            is_winner = 0
        else:
            # Time-based exit: winner if positive return
            is_winner = 1 if forward_return > 0 else 0
        
        outcomes[i, 0] = is_winner
        outcomes[i, 1] = forward_return
        outcomes[i, 2] = exit_price
    
    return outcomes

insert_query = """
INSERT INTO Fact_Trade_Outcomes 
(Timestamp, Asset_ID, Strategy_ID, Granularity, Trade_Horizon, Signal_Value, Forward_Return, Is_Winner, R_Multiple, ATR_SL_Multiplier, ATR_TP_Multiplier) 
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    
    # Compute outcomes with dynamic ATR multipliers
    print(f"  Using ATR multipliers: SL={SL_ATR_MULTIPLIER}x, TP={TP_ATR_MULTIPLIER}x")
    outcomes = calculate_outcomes(
        np.array(signal_indices, dtype=np.int32), 
        horizons, 
        atrs, 
        signals, 
        closes, 
        highs, 
        lows,
        sl_atr_multiplier=SL_ATR_MULTIPLIER,
        tp_atr_multiplier=TP_ATR_MULTIPLIER
    )
    
    # Prepare insert data with R_Multiple calculation
    inserts = []
    for i in range(len(signal_indices)):
        ts = timestamps[i]
        strat_id = int(strategy_ids[i])           # Cast away numpy.int32
        sig = int(signals[i])                     # Cast away numpy.int32
        fwd_ret = float(outcomes[i, 1])           # Forward return
        is_win = int(outcomes[i, 0])              # Winner flag
        exit_price = float(outcomes[i, 2])        # Exit price
        
        # Calculate R_Multiple: (exit - entry) / (entry - stop) for longs
        # This represents how many risk units (R) the trade made/lost
        entry = closes[signal_indices[i]]
        atr = atrs[i]
        sl_distance = SL_ATR_MULTIPLIER * atr
        
        if sl_distance > 0:
            price_diff = exit_price - entry
            if sig == -1:  # Short: invert the diff
                price_diff = -price_diff
            r_multiple = price_diff / sl_distance
        else:
            r_multiple = 0.0
        
        inserts.append((
            ts, 
            int(asset_id), 
            strat_id, 
            granularity, 
            int(horizons[i]), 
            sig, 
            fwd_ret, 
            is_win,
            float(r_multiple),
            float(SL_ATR_MULTIPLIER),
            float(TP_ATR_MULTIPLIER)
        ))
    
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

# Final natural win rate and expectancy statistics
cursor.execute("SELECT AVG(CAST(Is_Winner AS FLOAT)) FROM Fact_Trade_Outcomes")
win_rate = cursor.fetchone()[0]

cursor.execute("SELECT AVG(R_Multiple) FROM Fact_Trade_Outcomes WHERE R_Multiple IS NOT NULL")
avg_r_multiple = cursor.fetchone()[0]

cursor.execute("SELECT AVG(Forward_Return) FROM Fact_Trade_Outcomes WHERE Forward_Return IS NOT NULL")
avg_return = cursor.fetchone()[0]

print("======================================================================")
print(f" Pipeline complete.")
print(f"   Natural Win Rate: {win_rate:.2%}")
print(f"   Average R-Multiple: {avg_r_multiple:.3f}R")
print(f"   Average Forward Return: {avg_return:.4%}")
print(f"   SL/TP Multipliers Used: {SL_ATR_MULTIPLIER} / {TP_ATR_MULTIPLIER}")
print("======================================================================")

# Clean up
cursor.close()
conn.close()
