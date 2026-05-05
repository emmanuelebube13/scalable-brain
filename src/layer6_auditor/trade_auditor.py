import os
import time
from datetime import datetime, timedelta, timezone
import psycopg2
from dotenv import load_dotenv
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments

load_dotenv()

# ================= CONFIG =================
OANDA_API_KEY = os.getenv("OANDA_API_KEY")
SQL_PASSWORD = os.getenv("DB_PASS")
if not OANDA_API_KEY or not SQL_PASSWORD:
    raise ValueError("Missing OANDA_API_KEY or DB_PASS in .env file")

DB_NAME = "ForexBrainDB"
BASE_URL = os.getenv("OANDA_URL", "https://api-fxpractice.oanda.com")  # Default to demo URL if not set
# Initialize official Oanda API client (Bypasses Cloudflare automatically)
oanda_env = "practice" if "fxpractice" in BASE_URL else "live"
api = API(access_token=OANDA_API_KEY, environment=oanda_env)


# Robust requests session


def get_db_connection():
    conn_str = (
        f"host=localhost "
        f"dbname={DB_NAME} "
        f"user=sa "
        f"password={SQL_PASSWORD} "
        f"port=5432"
    )
    return psycopg2.connect(conn_str)


def normalize_oanda_instrument(symbol: str) -> str:
    """Robust converter: EURUSD → EUR_USD, XAUUSD → XAU_USD, SPX500USD → SPX500_USD, US30 → US30_USD, etc."""
    s = str(symbol).strip().upper().replace("/", "_").replace(" ", "_")

    # Already perfect (exactly one underscore)
    if s.count("_") == 1:
        return s

    # Major forex pairs
    if "_" not in s and len(s) == 6:
        return s[:3] + "_" + s[3:]

    # Metals / indices / crypto ending in USD
    if s.endswith("USD") and len(s) > 6:
        return s[:-3] + "_USD"

    # Common indices without USD suffix (US30, NAS100, JP225, etc.)
    if "_" not in s and any(char.isdigit() for char in s):
        return s + "_USD"

    return s  # fallback


def determine_outcome_m1_chunked(instrument: str, entry_time: datetime, entry: float, sl: float, tp: float, is_long: bool):
    """M1 chunked auditor using official oandapyV20 to bypass Cloudflare."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    current_start = entry_time
    if hasattr(current_start, 'tzinfo') and current_start.tzinfo is not None:
        current_start = current_start.replace(tzinfo=None)

    while current_start < now:
        current_end = min(current_start + timedelta(days=3), now)

        # Format for oandapyV20
        params = {
            "granularity": "M1",
            "price": "M",
            "from": current_start.strftime('%Y-%m-%dT%H:%M:%S.000000Z'),
            "to": current_end.strftime('%Y-%m-%dT%H:%M:%S.000000Z')
        }

        try:
            r = instruments.InstrumentsCandles(instrument=instrument, params=params)
            response = api.request(r)
            candles = response.get("candles", [])
            
            for c in candles:
                if not c.get("complete"):
                    continue
                high = float(c["mid"]["h"])
                low = float(c["mid"]["l"])
                candle_time = c["time"][:19].replace("T", " ")

                if is_long:
                    if low <= sl:
                        print(f" → LOSS | SL hit at {candle_time} (Low: {low})")
                        return 0
                    elif high >= tp:
                        print(f" → WIN | TP hit at {candle_time} (High: {high})")
                        return 1
                else:
                    if high >= sl:
                        print(f" → LOSS | SL hit at {candle_time} (High: {high})")
                        return 0
                    elif low <= tp:
                        print(f" → WIN | TP hit at {candle_time} (Low: {low})")
                        return 1

        except Exception as e:
            print(f" → OANDA API Error during chunk {current_start}: {e}")
            return None

        current_start = current_end
        time.sleep(0.5) # Be gentle on rate limits

    print(" → PENDING | Trade is still active as of right now.")
    return None


def main():
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    print(f"[{now_utc}] 🔥 Scalable Brain M1 Auditor STARTED\n")

    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT f."Timestamp", f.Asset_ID, f.Strategy_ID,
               f.Entry_Price, f.Stop_Loss, f.Take_Profit, d.Symbol
        FROM Fact_Live_Trades f
        JOIN Dim_Asset d ON f.Asset_ID = d.Asset_ID
        WHERE f.Actual_Outcome IS NULL
          AND f."Timestamp" <= NOW() - INTERVAL '1 hour'
        ORDER BY f."Timestamp" ASC
    """

    cursor.execute(query)
    rows = cursor.fetchall()
    print(f"Found {len(rows)} unresolved active trades.\n")

    updated_count = 0
    for row in rows:
        ts, asset_id, strategy_id, entry, sl, tp, raw_symbol = row
        instrument = normalize_oanda_instrument(raw_symbol)

        print(f"Analyzing {instrument} | Entry: {ts} | Price: {entry:.5f}")

        is_long = float(tp) > float(entry)
        try:
            outcome = determine_outcome_m1_chunked(
                instrument=instrument,
                entry_time=ts,
                entry=float(entry),
                sl=float(sl),
                tp=float(tp),
                is_long=is_long
            )

            if outcome is not None:
                update_sql = """
                    UPDATE Fact_Live_Trades
                    SET Actual_Outcome = %s
                    WHERE "Timestamp" = %s
                      AND Asset_ID = %s
                      AND Strategy_ID = %s
                      AND Entry_Price = %s
                """
                cursor.execute(update_sql, (outcome, ts, asset_id, strategy_id, float(entry)))
                updated_count += 1
                print(f" ✓ Database Updated: Outcome = {'WIN' if outcome == 1 else 'LOSS'}\n")
        except Exception as e:
            print(f" ❌ ERROR on this trade: {e}\n")
            continue

    cursor.close()
    conn.close()

    finish_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    print(f"[{finish_utc}] Auditor FINISHED. Updated {updated_count} trade records.")


if __name__ == "__main__":
    main()