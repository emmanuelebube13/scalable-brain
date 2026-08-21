import os
import json
import requests
from dotenv import load_dotenv
import pandas as pd
from datetime import datetime

# We are in scalable-brain/task/... so we need to load .env from the root
load_dotenv('../../../../.env')
import sys
sys.path.insert(0, '../../../../')

from src.common.db import get_engine

OANDA_API_KEY = os.environ.get("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.environ.get("OANDA_ACCOUNT_ID")
OANDA_URL = os.environ.get("OANDA_URL", "https://api-fxpractice.oanda.com")

def fetch_oanda_candle(ts=None):
    url = f"{OANDA_URL}/v3/instruments/EUR_USD/candles"
    headers = {
        "Authorization": f"Bearer {OANDA_API_KEY}",
        "Accept-Datetime-Format": "RFC3339"
    }
    params = {
        "granularity": "H1",
        "price": "MBA",
        "count": 1
    }
    if ts:
        params["from"] = ts
        params["to"] = ts
        del params["count"]
        
    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    data = resp.json()
    if data["candles"]:
        return data["candles"][0]
    return None

def main():
    engine = get_engine()
    
    # Let's get one H1 candle from DB that was written by System-1 (multi_timeframe_ingest)
    # wait, the brief said: for all of 2026, H1 rows have ingest_run_id populated on zero rows!
    # "H1 is not in the System-1 ingest's granularity list ... zero rows"
    # So System-1 hasn't written H1.
    # We should get a W1 row written by System-1, or D1/H4. Let's get a W1 row!
    
    query_sys1_w1 = """
    SELECT "timestamp"
    FROM fact_market_prices
    WHERE granularity = 'W1' AND asset_id = (SELECT asset_id FROM dim_asset WHERE symbol = 'EUR_USD')
    ORDER BY "timestamp" DESC LIMIT 1
    """
    df_w1 = pd.read_sql(query_sys1_w1, engine)
    
    if len(df_w1) > 0:
        ts = df_w1.iloc[0]["timestamp"].strftime("%Y-%m-%dT%H:%M:%SZ")
        print("Fetching W1 from OANDA for timestamp", ts)
        url = f"{OANDA_URL}/v3/instruments/EUR_USD/candles"
        headers = {
            "Authorization": f"Bearer {OANDA_API_KEY}",
            "Accept-Datetime-Format": "RFC3339"
        }
        params = {
            "granularity": "W",
            "price": "MBA",
            "from": ts,
            "count": 1
        }
        resp = requests.get(url, headers=headers, params=params)
        data = resp.json()
        if "candles" not in data:
            print("OANDA Response:", json.dumps(data, indent=2))
        if data.get("candles"):
            candle = data["candles"][0]
            print("\nOANDA W1 Candle:")
            print(json.dumps(candle, indent=2))
        else:
            print("OANDA W1 Error/Empty Response:", json.dumps(data, indent=2))
        
        query = """
        SELECT "timestamp", "Open", high, low, "Close", bid_close, ask_close, ingest_run_id
        FROM fact_market_prices 
        WHERE asset_id = (SELECT asset_id FROM dim_asset WHERE symbol = 'EUR_USD')
        AND granularity = 'W1'
        AND "timestamp" = %(ts)s
        """
        df_db = pd.read_sql(query, engine, params={"ts": df_w1.iloc[0]["timestamp"]})
        print("\nDB W1 Row:")
        print(df_db.to_string())

    # System-1 rows by granularity:
    query_count_sys1 = """
    SELECT granularity, COUNT(*) as count
    FROM fact_market_prices
    WHERE ingest_run_id IS NOT NULL
    GROUP BY granularity
    """
    df_count = pd.read_sql(query_count_sys1, engine)
    
    query_legacy_h1 = """
    SELECT "timestamp", "Open", high, low, "Close", bid_close, ask_close, ingest_run_id
    FROM fact_market_prices
    WHERE granularity = 'H1' AND asset_id = (SELECT asset_id FROM dim_asset WHERE symbol = 'EUR_USD')
    AND ingest_run_id IS NULL
    ORDER BY "timestamp" DESC LIMIT 1
    """
    df_h1 = pd.read_sql(query_legacy_h1, engine)
    if len(df_h1) > 0:
        ts_h1 = df_h1.iloc[0]["timestamp"].strftime("%Y-%m-%dT%H:%M:%SZ")
        print("\nFetching H1 from OANDA for timestamp", ts_h1)
        params_h1 = {
            "granularity": "H1",
            "price": "MBA",
            "from": ts_h1,
            "count": 1
        }
        resp_h1 = requests.get(f"{OANDA_URL}/v3/instruments/EUR_USD/candles", headers={"Authorization": f"Bearer {OANDA_API_KEY}"}, params=params_h1)
        data_h1 = resp_h1.json()
        if data_h1.get("candles"):
            print("OANDA H1 Candle:")
            print(json.dumps(data_h1["candles"][0], indent=2))
        else:
            print("OANDA H1 Error/Empty Response:", json.dumps(data_h1, indent=2))
        print("\nDB H1 Row (Legacy writer):")
        print(df_h1.to_string())

    # System-1 rows by granularity:
    print(df_count.to_string())
    
    # Null bid window 2026-05-03 to 2026-07-03
    query_null_bid = """
    SELECT granularity, COUNT(*) as count
    FROM fact_market_prices
    WHERE bid_close IS NULL
    AND "timestamp" >= '2026-05-03' AND "timestamp" < '2026-07-04'
    GROUP BY granularity
    """
    df_null = pd.read_sql(query_null_bid, engine)
    print("\nNull bid window rows (May-Jul 2026):")
    print(df_null.to_string())

if __name__ == "__main__":
    main()
