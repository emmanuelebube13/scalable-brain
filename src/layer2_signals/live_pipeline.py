import os
import pandas as pd
import urllib.parse
import numpy as np
import ta
import joblib
from dotenv import load_dotenv
from oandapyV20 import API
from oandapyV20.endpoints.instruments import InstrumentsCandles
from oandapyV20.exceptions import V20Error
import warnings
import logging
import smtplib
from email.mime.text import MIMEText
import sqlalchemy as sa

warnings.filterwarnings('ignore')

# Setup logging to file
logging.basicConfig(filename='live_pipeline.log', level=logging.INFO, 
                    format='%(asctime)s - %(message)s')

# ========================= CONFIG =========================
# Explicit path for CRON execution
load_dotenv('/home/eem/Documents/trading_system/.env')

# Read variables directly from the .env file
OANDA_TOKEN = os.getenv('OANDA_API_KEY')
OANDA_ENV = os.getenv('OANDA_ENV', 'live')  # Defaults to live if missing

SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASS = os.getenv('SMTP_PASS')
EMAIL_TO = os.getenv('EMAIL_TO', 'your@emaSil.com')  

DB_SERVER = os.getenv('DB_SERVER')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')
DB_NAME = 'ForexBrainDB'

# --- SYNCHRONIZED DB MAPPINGS ---
ASSETS = ['EUR_USD', 'GBP_USD', 'USD_JPY']
ASSET_ID_MAP = {'EUR_USD': 5, 'GBP_USD': 6, 'USD_JPY': 7}
ASSET_NAME_MAP = {5: 'EUR_USD', 6: 'GBP_USD', 7: 'USD_JPY'}

def get_strategy_id(asset_name, strategy_type):
    mapping = {
        'EUR_USD': {'Trend_EMA_ADX': 1017, 'Range_Bollinger': 1018},
        'GBP_USD': {'Trend_EMA_ADX': 1017, 'Range_Bollinger': 1021}, # Using 1017 as fallback for Trend
        'USD_JPY': {'Trend_EMA_ADX': 1017, 'Range_Bollinger': 1023}
    }
    return mapping[asset_name][strategy_type]

STRATEGY_NAME_MAP = {
    1017: 'Trend_EMA_ADX',
    1018: 'Range_Bollinger',
    1021: 'Range_Bollinger',
    1023: 'Range_Bollinger'
}

MODEL_PATH = 'models/best_ml_gatekeeper.pkl'
APPROVAL_THRESHOLD = 0.535
RR_RATIO_TARGET = 3  

# ========================= INITIALIZATION =========================
# Initialize the API using the correct variables
api = API(access_token=OANDA_TOKEN, environment=OANDA_ENV)
model = joblib.load(MODEL_PATH)

if hasattr(model, 'feature_names_in_'):
    EXPECTED_FEATURES = model.feature_names_in_.tolist()
else:
    raise ValueError("Model does not have feature_names_in_.")

params = urllib.parse.quote_plus(
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={DB_SERVER};"
    f"DATABASE={DB_NAME};"
    f"UID={DB_USER};"
    f"PWD={DB_PASS}"
)
engine = sa.create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

logging.info("Live Pipeline Started | Threshold: 0.535")
print("🚀 Live Pipeline Started | Check live_pipeline.log for details")

# ========================= FUNCTIONS =========================
def send_email(alert_text):
    if not SMTP_USER or not SMTP_PASS:
        logging.warning("SMTP creds missing; skipping email.")
        return
    msg = MIMEText(alert_text)
    msg['Subject'] = '💰 Scalable Brain Trade Alert'
    msg['From'] = SMTP_USER
    msg['To'] = EMAIL_TO
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        logging.info("Email alert sent.")
    except Exception as e:
        logging.error(f"Email send failed: {e}")

def fetch_candles(instrument: str, count: int = 200) -> pd.DataFrame:
    params = {"count": count, "granularity": "H1", "price": "M"}
    try:
        r = InstrumentsCandles(instrument=instrument, params=params)
        response = api.request(r)
        candles = response['candles']
        df = pd.DataFrame([{
            'Timestamp': pd.to_datetime(c['time']),
            'Open': float(c['mid']['o']),
            'High': float(c['mid']['h']),
            'Low': float(c['mid']['l']),
            'Close': float(c['mid']['c'])
        } for c in candles])
        print(f"   ✓ Fetched {len(df)} H1 candles for {instrument}")
        return df
    except Exception as e:
        print(f"   ❌ API error for {instrument}: {e}") # Added error context here
        return None

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    atr_ind = ta.volatility.AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close'], window=14)
    df['ATR_Value'] = atr_ind.average_true_range()
    
    adx_ind = ta.trend.ADXIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=14)
    df['ADX_Value'] = adx_ind.adx()
    
    df['Regime_Label'] = np.where(df['ADX_Value'] > 25, 'Trending', 'Ranging')
    df['EMA_10'] = ta.trend.ema_indicator(close=df['Close'], window=10)
    df['EMA_50'] = ta.trend.ema_indicator(close=df['Close'], window=50)
    
    bb_ind = ta.volatility.BollingerBands(close=df['Close'], window=20, window_dev=2)
    df['BB_Upper'] = bb_ind.bollinger_hband()
    df['BB_Lower'] = bb_ind.bollinger_lband()
    return df

def generate_signals(df: pd.DataFrame, asset_name: str) -> pd.DataFrame:
    latest = df.iloc[-1].copy()
    signals = []
    asset_id = ASSET_ID_MAP[asset_name]
    
    if (latest['EMA_10'] > latest['EMA_50'] and latest['ADX_Value'] > 25 and latest['Close'] > latest['EMA_50']):
        signals.append({'Strategy_ID': get_strategy_id(asset_name, 'Trend_EMA_ADX'), 'Signal_Value': 1, 'Asset_ID': asset_id})
    elif (latest['EMA_10'] < latest['EMA_50'] and latest['ADX_Value'] > 25 and latest['Close'] < latest['EMA_50']):
        signals.append({'Strategy_ID': get_strategy_id(asset_name, 'Trend_EMA_ADX'), 'Signal_Value': -1, 'Asset_ID': asset_id})
        
    if (latest['Regime_Label'] == 'Ranging' and latest['Close'] < latest['BB_Lower']):
        signals.append({'Strategy_ID': get_strategy_id(asset_name, 'Range_Bollinger'), 'Signal_Value': 1, 'Asset_ID': asset_id})
    elif (latest['Regime_Label'] == 'Ranging' and latest['Close'] > latest['BB_Upper']):
        signals.append({'Strategy_ID': get_strategy_id(asset_name, 'Range_Bollinger'), 'Signal_Value': -1, 'Asset_ID': asset_id})
        
    if signals:
        return pd.DataFrame(signals)
    return pd.DataFrame()

def run_gatekeeper(signal_row: pd.Series):
    input_df = pd.DataFrame([{
        'Regime_Label': signal_row['Regime_Label'],
        'ATR_Value': signal_row['ATR_Value'],
        'ADX_Value': signal_row['ADX_Value'],
        'Asset_ID': signal_row['Asset_ID'],
        'Strategy_ID': signal_row['Strategy_ID'],
        'Signal_Value': signal_row['Signal_Value']
    }])
    
    encoded = pd.get_dummies(input_df, columns=['Regime_Label', 'Asset_ID', 'Strategy_ID'], drop_first=True)
    encoded = encoded.reindex(columns=EXPECTED_FEATURES, fill_value=0)
    
    prob = model.predict_proba(encoded)[0][1]
    
    asset_name = ASSET_NAME_MAP[signal_row['Asset_ID']]
    strategy_name = STRATEGY_NAME_MAP.get(signal_row['Strategy_ID'], 'Unknown_Strategy')
    entry_price = signal_row['Close']
    atr = signal_row['ATR_Value']
    direction = signal_row['Signal_Value']
    
    sl = entry_price - (atr * direction)
    tp = entry_price + (atr * RR_RATIO_TARGET * direction)
    rr_ratio = abs(tp - entry_price) / abs(sl - entry_price)
    
    direction_str = "BUY" if direction == 1 else "SELL"
    alert = f"{asset_name} | {strategy_name} | {direction_str} @ {entry_price:.5f} | SL: {sl:.5f} | TP: {tp:.5f} | Conf: {prob*100:.2f}%"
    
# SQL LOGGING (Strict Formatting for Pre-Built Table)
    try:
        log_df = pd.DataFrame([{
            'Timestamp': signal_row['Timestamp'].strftime('%Y-%m-%d %H:%M:%S'), # Clean string format
            'Asset_ID': int(signal_row['Asset_ID']),
            'Strategy_ID': int(signal_row['Strategy_ID']),
            'Signal_Value': int(signal_row['Signal_Value']),
            'Entry_Price': float(entry_price),
            'Stop_Loss': float(sl),
            'Take_Profit': float(tp),
            'Confidence_Score': float(prob),
            'Is_Approved': int(1 if prob >= APPROVAL_THRESHOLD else 0)
        }])
        
        # if_exists='append' ensures it respects our manual SQL table
        log_df.to_sql('Fact_Live_Trades', engine, if_exists='append', index=False)
        print("   ✅ Successfully logged trade to SQL Server database.")
        logging.info("DB Logging SUCCESS")
        
    except Exception as e:
        print(f"   ❌ DB Logging failed: {e}")
        logging.error(f"DB Logging failed: {e}")

    # CONSOLE & EMAIL ALERTS
    if prob >= APPROVAL_THRESHOLD:
        full_alert = "\n" + "="*80 + f"\n[TRADE APPROVED] {alert}\n" + "="*80
        print(full_alert)
        logging.info(full_alert)
        send_email(full_alert)
    else:
        veto_alert = f"[TRADE VETOED] {alert} (< 53.5%)"
        print(veto_alert)
        logging.info(veto_alert)

# ====================== MAIN PIPELINE ======================
for asset in ASSETS:
    print(f"\n📡 Processing {asset}...")
    candles_df = fetch_candles(asset)
    if candles_df is None or len(candles_df) < 50:
        continue
    
    df = calculate_indicators(candles_df)
    latest_row = df.iloc[-1].copy()
    signals_df = generate_signals(df, asset)
    
    if not signals_df.empty:
        for _, sig in signals_df.iterrows():
            sig['Regime_Label'] = latest_row['Regime_Label']
            sig['ATR_Value'] = latest_row['ATR_Value']
            sig['ADX_Value'] = latest_row['ADX_Value']
            sig['Close'] = latest_row['Close']
            sig['Timestamp'] = latest_row['Timestamp']
            run_gatekeeper(sig)
    else:
        print(f"   No signal on latest closed candle for {asset}")

print("\n✅ Live Pipeline completed. Next CRON run in ~1 hour.")