"""
=============================================================================
Author:       Emmanuel Mbachu
Date:         2026-03-21
Description:  ICE 3 - Data Download and Import Package.
              Self-healing ETL fetcher that syncs H1 candles from Oanda's 
              Practice API into the MS SQL Server Fact_Market_Prices table. 
              Resumes from the last stored timestamp per asset and paginates 
              in 5000-candle batches until present day.
=============================================================================
"""

import os
import pyodbc
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

# ── Configuration ────────────────────────────────────────────────────────────
load_dotenv()

CONN_STR = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={os.getenv('DB_SERVER', 'localhost')};"
    f"DATABASE=ForexBrainDB;"
    f"UID={os.getenv('DB_USER', 'sa')};"
    f"PWD={os.getenv('DB_PASS')}"
)

OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_URL = "https://api-fxpractice.oanda.com/v3/instruments/{instrument}/candles"
HEADERS = {
    "Authorization": f"Bearer {OANDA_API_KEY}",
    "Content-Type": "application/json",
}

ASSETS = {5: "EUR_USD", 6: "GBP_USD", 7: "USD_JPY"}
FALLBACK_START = "2008-01-01T00:00:00Z"
BATCH_SIZE = 5000


# ── Helpers ──────────────────────────────────────────────────────────────────
def get_last_timestamp(conn, asset_id):
    """Query the DB for the most recent candle timestamp for this asset."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT MAX(Timestamp) FROM Fact_Market_Prices WHERE Asset_ID = ?",
        asset_id,
    )
    row = cursor.fetchone()
    if row[0] is None:
        return FALLBACK_START
    # Format the DB datetime back to RFC3339 for the Oanda API
    return row[0].strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_candles(json_data):
    """Extract (timestamp, open, high, low, close, volume) from Oanda JSON."""
    rows = []
    for candle in json_data.get("candles", []):
        if not candle.get("complete", False):
            continue  # skip the in-progress candle
        mid = candle["mid"]
        ts = candle["time"][:19].replace("T", " ")  # "2008-01-02T05:00:00" -> SQL DATETIME
        rows.append((
            ts,
            float(mid["o"]),
            float(mid["h"]),
            float(mid["l"]),
            float(mid["c"]),
            int(candle["volume"]),
        ))
    return rows


def fetch_candles(instrument, start_time):
    """Fetch up to 5000 H1 candles from Oanda starting at start_time."""
    # Oanda expects the instrument with an underscore replaced by _
    oanda_instrument = instrument  # already EUR_USD format in Oanda v3
    url = OANDA_URL.format(instrument=oanda_instrument)
    params = {
        "granularity": "H1",
        "count": BATCH_SIZE,
        "from": start_time,
        "price": "M",  # mid prices
    }
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def insert_batch(conn, asset_id, rows):
    """
    Bulk insert into Fact_Market_Prices.
    Duplicates are silently skipped via row-level try/except fallback.
    """
    cursor = conn.cursor()
    cursor.fast_executemany = True

    # Removed 'Granularity' to match ICE 1 DDL schema
    insert_sql = """
        INSERT INTO Fact_Market_Prices ([Timestamp], Asset_ID, [Open], High, Low, [Close], Volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    params = [(ts, asset_id, o, h, l, c, v) for ts, o, h, l, c, v in rows]

    try:
        cursor.executemany(insert_sql, params)
        conn.commit()
        return len(params)
    except pyodbc.IntegrityError:
        # Batch had duplicates — fall back to row-by-row to skip only the dupes
        conn.rollback()
        inserted = 0
        for row in params:
            try:
                cursor.execute(insert_sql, row)
                conn.commit()
                inserted += 1
            except pyodbc.IntegrityError:
                conn.rollback()  # duplicate — skip silently
        return inserted


# ── Main Sync Loop ───────────────────────────────────────────────────────────
def sync_asset(conn, asset_id, symbol):
    """Paginate through Oanda history for one asset until caught up."""
    start_time = get_last_timestamp(conn, asset_id)
    total_inserted = 0
    batch_num = 0

    print(f"\n{'─' * 60}")
    print(f"  Syncing Asset {asset_id}: {symbol}")
    print(f"  Resuming from: {start_time}")
    print(f"{'─' * 60}")

    while True:
        batch_num += 1
        print(f"  [{symbol}] Batch {batch_num}: Fetching {BATCH_SIZE} H1 candles from {start_time} ...", end=" ")

        try:
            data = fetch_candles(symbol, start_time)
        except requests.exceptions.HTTPError as e:
            print(f"\n  [{symbol}] API error: {e}")
            break
        except requests.exceptions.RequestException as e:
            print(f"\n  [{symbol}] Network error: {e}")
            break

        rows = parse_candles(data)
        candle_count = len(rows)
        print(f"received {candle_count} complete candles.")

        if candle_count == 0:
            print(f"  [{symbol}] No new candles returned. Asset is fully synced.")
            break

        print(f"  [{symbol}] Inserting into Fact_Market_Prices ...", end=" ")
        inserted = insert_batch(conn, asset_id, rows)
        total_inserted += inserted
        print(f"{inserted} new rows written ({candle_count - inserted} duplicates skipped).")

        # Advance the cursor to the last candle's timestamp
        start_time = rows[-1][0].replace(" ", "T") + "Z"

        # If fewer than BATCH_SIZE returned, we've reached present day
        raw_candle_count = len(data.get("candles", []))
        if raw_candle_count < BATCH_SIZE:
            print(f"  [{symbol}] Reached present day ({raw_candle_count} < {BATCH_SIZE}).")
            break

    print(f"  [{symbol}] Sync complete. Total new rows: {total_inserted:,}")
    return total_inserted


def main():
    print("=" * 60)
    print(" OANDA HISTORICAL DATA SYNC")
    print(f" Target: ForexBrainDB.Fact_Market_Prices")
    print(f" Granularity: H1 | Batch size: {BATCH_SIZE}")
    print("=" * 60)

    conn = pyodbc.connect(CONN_STR)
    grand_total = 0

    for asset_id, symbol in ASSETS.items():
        grand_total += sync_asset(conn, asset_id, symbol)

    conn.close()

    print(f"\n{'=' * 60}")
    print(f" Sync finished. {grand_total:,} total new rows across all assets.")
    print("=" * 60)


if __name__ == "__main__":
    main()