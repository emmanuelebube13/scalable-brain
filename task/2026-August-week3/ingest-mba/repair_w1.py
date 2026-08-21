import logging
from datetime import datetime, timezone
import pandas as pd
from oandapyV20 import API

from src.common.db import get_engine
from src.layer0.ingest_data.ingest_oanda_prices import fetch_candles_with_retry
from src.ingestion.multi_timeframe_ingest import _normalize_candle, upsert_bars_with_lineage, create_oanda_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    engine = get_engine()
    from src.layer0.ingest_data.ingest_oanda_prices import read_env
    env = read_env()
    client = create_oanda_client(env)
    
    # 1. Fetch all assets mapped in dim_asset
    assets_df = pd.read_sql("SELECT asset_id, symbol FROM dim_asset", engine)
    
    with engine.begin() as conn:
        for _, row in assets_df.iterrows():
            asset_id = row['asset_id']
            symbol = row['symbol']
            
            logger.info(f"Repairing W1 for {symbol} (asset_id={asset_id})")
            
            # W1 covers all history, OANDA has 5000 limit, let's just use from 2005
            start_date = datetime(2005, 1, 1, tzinfo=timezone.utc)
            candles = fetch_candles_with_retry(
                client, 
                instrument=symbol, 
                granularity="W1", 
                from_ts=start_date, to_ts=datetime.now(timezone.utc),
                price="MBA"
            )
            
            bars = []
            for c in candles[0]:
                bar = _normalize_candle(c, asset_id, "W1")
                if bar is not None:
                    bars.append(bar)
                    
            if bars:
                ins, upd = upsert_bars_with_lineage(conn.connection, bars, run_id="11111111-1111-1111-1111-111111111111")
                logger.info(f"W1 for {symbol}: {len(bars)} fetched. {ins} inserted, {upd} updated.")
            
            # Now repair D1 and H4 for 2026-05-03 to 2026-07-03
            start_repair = datetime(2026, 5, 3, tzinfo=timezone.utc)
            end_repair = datetime(2026, 7, 5, tzinfo=timezone.utc)
            
            for gran in ["D1", "H4", "H1"]:
                logger.info(f"Repairing {gran} for {symbol} (asset_id={asset_id}) in window {start_repair.date()} to {end_repair.date()}")
                candles = fetch_candles_with_retry(
                    client,
                    instrument=symbol,
                    granularity=gran,
                    from_ts=start_repair,
                    to_ts=end_repair,
                    price="MBA"
                )
                
                bars = []
                for c in candles[0]:
                    bar = _normalize_candle(c, asset_id, gran)
                    if bar is not None:
                        bars.append(bar)
                        
                if bars:
                    ins, upd = upsert_bars_with_lineage(conn.connection, bars, run_id="22222222-2222-2222-2222-222222222222")
                    logger.info(f"{gran} for {symbol}: {len(bars)} fetched. {ins} inserted, {upd} updated.")
                    
    # Verify NULL count
    null_count_df = pd.read_sql("SELECT COUNT(*) as c FROM fact_market_prices WHERE bid_close IS NULL", engine)
    logger.info(f"NULL count for bid_close: {null_count_df['c'].iloc[0]}")

if __name__ == "__main__":
    main()
