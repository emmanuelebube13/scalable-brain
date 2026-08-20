import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import pandas as pd
from sqlalchemy import text

from src.common.db import get_engine

logger = logging.getLogger("system1.signals.watcher")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STATE_FILE = os.path.join(REPO_ROOT, "results", "state", "watcher_state.json")

# Max allowable latency before a bar is considered "too old" to trade.
# Measured from the bar's timestamp (which is usually its open time).
# We allow roughly 2x the granularity window to account for the bar's duration + ingest lag.
#
# THESE MUST CLEAR THE WEEKEND. The FX market closes Friday 21:00 UTC and reopens Sunday
# 21:00 UTC, so on a Monday morning the newest *complete* bar is legitimately from Friday's
# close — about 3.5 days old for D1, and ~2.5 days for intraday frames. The original D1
# value of 48h was shorter than that gap, so every Monday run rejected perfectly good data
# as stale and emitted nothing. Verified against live data on 2026-08-17: the newest D1 bar
# was 85h old and correct.
#
# The job of these numbers is to catch a DEAD FEED, not a closed market. They are therefore
# sized as "longest legitimate gap + a holiday + ingest lag". Intraday frames keep tight
# thresholds because they are only ever evaluated while the market is open.
LATENCY_THRESHOLDS = {
    "H1": timedelta(hours=2, minutes=15),
    "H4": timedelta(hours=8, minutes=30),
    # Fri 21:00 -> Mon 21:00 is 72h; +24h for a Monday holiday, +12h ingest slack.
    "D1": timedelta(hours=108),
    "W1": timedelta(days=14),
}

def load_state() -> Dict[str, str]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Could not read watcher_state.json: %s", e)
    return {}

def save_state(state: Dict[str, str]):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    # atomic write
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)


class BarWatcher:
    """Watches fact_market_prices for newly closed bars."""
    
    def __init__(self, engine=None):
        self.engine = engine or get_engine()
        self.state = load_state()
        
    def get_new_closed_bars(self, granularity: str, commit: bool = True) -> pd.DataFrame:
        """Fetch newly closed bars for the given granularity across all active assets.
        
        Returns a DataFrame of the latest closed bars that haven't been emitted yet,
        joined with dim_asset to provide the 'instrument' symbol.
        """
        # We need the max complete bar for each asset_id where granularity matches
        # and timestamp > what we last saw.
        
        query = text("""
            WITH LatestBars AS (
                SELECT 
                    f.asset_id,
                    a.symbol as instrument,
                    f.timestamp,
                    f."Open",
                    f.high,
                    f.low,
                    f."Close",
                    f.volume,
                    ROW_NUMBER() OVER(PARTITION BY f.asset_id ORDER BY f.timestamp DESC) as rn
                FROM fact_market_prices f
                JOIN dim_asset a ON f.asset_id = a.asset_id
                WHERE f.granularity = :granularity
                  -- Completeness is enforced at INGEST, not here:
                  -- ingest_oanda_prices.py skips any candle whose OANDA payload has
                  -- complete=false, so presence in this table IS the guarantee. The
                  -- `complete` column itself is vestigial and NULL on 4.68M of 4.69M
                  -- rows — including EVERY D1 and H1 row. Filtering `complete = true`
                  -- therefore matched nothing and the producer could never emit a
                  -- signal, while logging only the indistinguishable "No signals
                  -- generated". NULL is accepted explicitly rather than by dropping
                  -- the predicate, so a future row that is genuinely flagged false is
                  -- still excluded.
                  AND COALESCE(f.complete, true) = true
                  AND a.is_active = true
            )
            SELECT * FROM LatestBars WHERE rn = 1
        """)
        
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"granularity": granularity})
            
        if df.empty:
            return df
            
        # Filter by state and lateness
        now = datetime.now(timezone.utc)
        max_age = LATENCY_THRESHOLDS.get(granularity, timedelta(days=1))
        
        valid_rows = []
        new_state = dict(self.state)
        
        for _, row in df.iterrows():
            inst = row["instrument"]
            ts = pd.to_datetime(row["timestamp"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
                
            state_key = f"{inst}_{granularity}"
            last_ts_str = self.state.get(state_key)
            
            if last_ts_str:
                last_ts = pd.to_datetime(last_ts_str)
                if ts <= last_ts:
                    continue # Already processed
                    
            # Check lateness
            age = now - ts
            if age > max_age:
                logger.warning(
                    "Ingest is behind for %s %s. Latest complete bar is %s (age %s, threshold %s). Skipping.",
                    inst, granularity, ts.isoformat(), age, max_age
                )
                continue
                
            # Valid new bar
            valid_rows.append(row)
            new_state[state_key] = ts.isoformat()
            
        # Advance the watermark ONLY when the caller intends to act on these bars.
        #
        # Reading used to persist state unconditionally, so a `--dry-run` silently
        # consumed the very bars the subsequent real run would have emitted — the
        # operator tests, sees the signal, runs for real, and gets "No signals
        # generated" with no indication why. A preview must not mutate state.
        if valid_rows and commit:
            self.state = new_state
            save_state(self.state)

        return pd.DataFrame(valid_rows)
