from finbert import ScalableBrainFinBERT
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import numpy as np
from typing import List, Dict
import logging
from sqlalchemy import create_engine, Column, Integer, Float, DateTime, String
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

import os
import urllib.parse
from dotenv import load_dotenv


# ==================== IMPORT YOUR V5 FINBERT CLASS HERE ====================
# from scalable_brain_finbert import ScalableBrainFinBERT
# (Paste the full ScalableBrainFinBERT class from our previous message if not in a module)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Base = declarative_base()

class FactMacroEvents(Base):
    __tablename__ = 'Fact_Macro_Events'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False)
    asset_id = Column(Integer, nullable=False)          # FK to Dim_Asset (1 = EURUSD)
    event_title = Column(String(255))
    source = Column(String(100))
    standardized_surprise_score = Column(Float)
    finbert_sentiment = Column(Float)
    finbert_dispersion = Column(Float)
    hour_sin = Column(Float)
    hour_cos = Column(Float)
    dow_sin = Column(Float)
    dow_cos = Column(Float)
    dom_sin = Column(Float)
    dom_cos = Column(Float)

class MacroIngestionPipeline:
    """Institutional-grade async macro pipeline – all 5 bugs fixed"""

    def __init__(self, db_connection_string: str):
        self.engine = create_engine(
            db_connection_string,
            pool_size=10,
            max_overflow=20,
            pool_timeout=30,
            pool_pre_ping=True
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.finbert = ScalableBrainFinBERT

    @staticmethod
    def _cyclical_encode(dt: datetime) -> Dict[str, float]:
        hour = dt.hour
        dow = dt.weekday()
        dom = dt.day
        return {
            'hour_sin': np.sin(2 * np.pi * hour / 24),
            'hour_cos': np.cos(2 * np.pi * hour / 24),
            'dow_sin': np.sin(2 * np.pi * dow / 7),
            'dow_cos': np.cos(2 * np.pi * dow / 7),
            'dom_sin': np.sin(2 * np.pi * dom / 31),
            'dom_cos': np.cos(2 * np.pi * dom / 31)
        }

    @staticmethod
    def _compute_surprise_score(actual: float, consensus: float, previous: float) -> float:
        """Relative standardization (fixes scale corruption)"""
        if actual is None:
            return 0.0
        if consensus is not None and abs(consensus) > 0.0001:
            return (actual - consensus) / abs(consensus)
        elif previous is not None and abs(previous) > 0.0001:
            return (actual - previous) / abs(previous)
        return 0.0
    
    async def _fetch_rss(self, session: aiohttp.ClientSession, url: str) -> List[str]:
        """Async RSS fetch for ECB / Fed speeches (Crash-Proof Parsing)"""
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; ScalableBrain/1.0)'}
        try:
            async with session.get(url, headers=headers, timeout=15) as resp:
                if resp.status != 200:
                    logger.error(f"RSS fetch failed: {url}")
                    return []
                text = await resp.text()
        except Exception as e:
            logger.error(f"Network error fetching {url}: {e}")
            return []

        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            logger.error(f"Failed to parse XML from {url}")
            return []

        texts = []
        # Namespace-agnostic search (ignores complex XML formatting)
        for item in root.iter():
            if item.tag.endswith('item') or item.tag.endswith('entry'):
                title = ""
                summary = ""
                
                for child in item:
                    if child.tag.endswith('title') and child.text:
                        title = child.text.strip()
                    elif child.tag.endswith('description') and child.text:
                        summary = child.text.strip()
                    elif child.tag.endswith('summary') and child.text:
                        summary = child.text.strip()
                
                full_text = f"{title}. {summary}".strip()
                
                # Prevent adding empty ". " strings
                if full_text != "." and len(full_text) > 20:
                    texts.append(full_text)
                    
        return texts



    async def _fetch_forex_factory_xml(self, session: aiohttp.ClientSession) -> List[Dict]:
        """Reliable public XML feed – no Cloudflare, real timestamps"""
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/xml,application/xml'
        }
        async with session.get(url, headers=headers, timeout=15) as resp:
            if resp.status != 200:
                logger.error("Forex Factory XML fetch failed")
                return []
            text = await resp.text()
        
        root = ET.fromstring(text)
        events = []
        today = datetime.now(timezone.utc).date()
        
        for event in root.findall('event'):
            try:
                title = event.find('title').text.strip()
                currency = event.find('currency').text.strip()
                if currency not in ('EUR', 'USD'):  # Only EUR/USD relevant events
                    continue
                
                date_str = event.find('date').text.strip()
                time_str = event.find('time').text.strip() or "00:00"
                actual_str = event.find('actual').text
                forecast_str = event.find('forecast').text
                previous_str = event.find('previous').text
                
                # Build real timestamp
                dt = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                if ':' in time_str:
                    h, m = map(int, time_str.split(':'))
                    dt = dt.replace(hour=h, minute=m)
                
                events.append({
                    'timestamp': dt,
                    'event_title': title,
                    'actual': float(actual_str.replace('%', '').replace(',', '')) if actual_str and actual_str != '-' else None,
                    'forecast': float(forecast_str.replace('%', '').replace(',', '')) if forecast_str and forecast_str != '-' else None,
                    'previous': float(previous_str.replace('%', '').replace(',', '')) if previous_str and previous_str != '-' else None,
                    'source': 'ForexFactory'
                })
            except (ValueError, AttributeError, TypeError):
                continue
        return events

    async def run(self):
        """Main pipeline – CRON-ready"""
        async with aiohttp.ClientSession() as session:
            # 1. CENTRAL BANK SPEECHES (RSS)
            ecb_texts = await self._fetch_rss(session, "https://www.ecb.europa.eu/rss/press.xml")
            fed_texts = await self._fetch_rss(session, "https://www.federalreserve.gov/feeds/fed_speeches.xml")
            all_news_texts = ecb_texts + fed_texts
            
            # 2. FINBERT – ONE BATCH FOR ALL NEWS
            news_features = self.finbert.batch_features(all_news_texts) if all_news_texts else []
            
            # 3. MACRO CALENDAR (real timestamps + surprise)
            calendar_events = await self._fetch_forex_factory_xml(session)
            
            # 4. FINBERT – ONE SINGLE BATCH FOR ALL CALENDAR TITLES
            calendar_titles = [ev['event_title'] for ev in calendar_events]
            calendar_finbert = self.finbert.batch_features(calendar_titles) if calendar_titles else []
            
            # 5. BUILD RECORDS (context-managed DB)
            with self.Session() as session_db:
                try:
                    records = []
                    
                    # News records
                    for i, feat in enumerate(news_features):
                        cyclical = self._cyclical_encode(datetime.now(timezone.utc))
                        records.append(FactMacroEvents(
                            timestamp=datetime.now(timezone.utc),
                            asset_id=1,
                            event_title=all_news_texts[i][:200],
                            source='ECB/Fed',
                            standardized_surprise_score=0.0,
                            finbert_sentiment=feat['sentiment_score'],
                            finbert_dispersion=feat['dispersion'],
                            **cyclical
                        ))
                    
                    # Calendar records (with real surprise & real timestamp)
                    for i, ev in enumerate(calendar_events):
                        surprise = self._compute_surprise_score(ev['actual'], ev['forecast'], ev['previous'])
                        feat = calendar_finbert[i] if i < len(calendar_finbert) else {'sentiment_score': 0.0, 'dispersion': 0.0}
                        cyclical = self._cyclical_encode(ev['timestamp'])
                        records.append(FactMacroEvents(
                            timestamp=ev['timestamp'],
                            asset_id=1,
                            event_title=ev['event_title'],
                            source=ev['source'],
                            standardized_surprise_score=surprise,
                            finbert_sentiment=feat['sentiment_score'],
                            finbert_dispersion=feat['dispersion'],
                            **cyclical
                        ))
                    
                    if records:
                        session_db.bulk_save_objects(records)
                        session_db.commit()
                        logger.info(f"✅ Inserted {len(records)} macro events into Fact_Macro_Events")
                
                except Exception as e:
                    session_db.rollback()
                    logger.error(f"Database error: {e}")
                    raise
                # Auto-close guaranteed by context manager

# ==================== CRON USAGE ====================

if __name__ == "__main__":
    # Load variables from your .env file
    load_dotenv()
    
    # Grab the credentials
    db_user = os.getenv("DB_USER")
    raw_pass = os.getenv("DB_PASS")
    db_server = os.getenv("DB_SERVER")
    db_port = os.getenv("DB_PORT", "1433")
    db_name = os.getenv("DB_NAME")
    
    # Encode the password
    encoded_pass = urllib.parse.quote_plus(raw_pass)
    
    # Build the string
    CONN_STR = (
        f"postgresql+psycopg2://{db_user}:{encoded_pass}@{db_server}:{db_port}/{db_name}"
    )
    
    pipeline = MacroIngestionPipeline(CONN_STR)
    asyncio.run(pipeline.run())