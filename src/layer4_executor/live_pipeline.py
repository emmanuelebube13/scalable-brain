"""
Layer 4: Live Execution Pipeline (Refactored)
=============================================

A thin, deterministic execution layer that consumes upstream artifacts from
Layer 1, Layer 2, and Layer 3 without recomputing market state or strategy signals.

Architecture:
- Layer 0: Strategy qualification (offline)
- Layer 1: Market regime labels (Fact_Market_Regime_V2)
- Layer 2: Raw trade signals (Fact_Signals)
- Layer 3: ML gatekeeper training and artifact serving
- Layer 4: Risk checks, correlation checks, broker execution (THIS FILE)
- Layer 5-6: Telemetry and audit

Key Constraints:
- Never recomputes regime labels internally
- Never regenerates strategy signals internally
- Consumes granularity-aware records throughout
- Resolves stable Layer 3 model artifact contract
- Performs ATR-based risk calculations
- Performs correlation / portfolio exposure checks
- Writes rich live execution logs

Usage:
    python live_pipeline.py
    python live_pipeline.py --dry-run
    python live_pipeline.py --granularity H1
    python live_pipeline.py --skip-correlation-check
    python live_pipeline.py --all-signals  # Process all signals (batch mode)
"""

import os
import sys
import json
import hashlib
import logging
import argparse
import smtplib
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple, Any, Callable
from enum import Enum

import pandas as pd
import numpy as np
import joblib
import ta
import sqlalchemy as sa
import pyodbc
from dotenv import load_dotenv
from email.mime.text import MIMEText
from oandapyV20 import API
from oandapyV20.endpoints.instruments import InstrumentsCandles

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.layer7.oanda_executor import execute_trade

# Import feature engineering from Layer 3 training
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src' / 'layer3_ml'))
try:
    # Try new import structure (preferred)
    from layer3_ml import (
        align_features_for_inference,
        safe_comprehensive_feature_engineering,
        prepare_inference_dataframe,
        validate_inference_data,
        SUPPORTED_GATEKEEPER_GRANULARITIES,
    )
except ImportError:
    # Fallback to old import structure
    from train_ml_gatekeeper import (
        comprehensive_feature_engineering,
        SUPPORTED_GATEKEEPER_GRANULARITIES,
    )
    from feature_alignment import align_features_for_inference


# =============================================================================
# CONFIGURATION & CONSTANTS
# =============================================================================

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / '.env')

SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASS = os.getenv('SMTP_PASS')
EMAIL_TO = os.getenv('EMAIL_TO')

# Layer 3 Model Contract
_models_dir_env = Path(os.getenv('LAYER3_MODELS_DIR', 'models'))
LAYER3_MODELS_DIR = _models_dir_env if _models_dir_env.is_absolute() else (ROOT_DIR / _models_dir_env)
LAYER3_MANIFEST_PATH = LAYER3_MODELS_DIR / 'champion_manifest.json'
LAYER3_STABLE_ALIAS = LAYER3_MODELS_DIR / 'champion_model.pkl'
LAYER3_PREPROCESSOR_ALIAS = LAYER3_MODELS_DIR / 'champion_preprocessor.pkl'
LAYER3_LEGACY_MODEL_PATH = LAYER3_MODELS_DIR / 'best_ml_gatekeeper_sklearn.pkl'
LAYER3_LEGACY_PREPROCESSOR_PATH = LAYER3_MODELS_DIR / 'best_ml_gatekeeper_preprocessor.pkl'

# Supported granularities (must match Layer 3 training contract)
DEFAULT_GRANULARITY = 'H1'

# Risk Parameters
DEFAULT_RR_RATIO = 3.0
DEFAULT_ATR_MULTIPLIER_SL = 1.0
DEFAULT_ATR_MULTIPLIER_TP = 3.0
MAX_POSITIONS_PER_ASSET = 1
MAX_TOTAL_EXPOSURE_PCT = 0.25  # 25% of portfolio

# Correlation Gate Parameters
CORRELATION_LOOKBACK_BARS = 100
CORRELATION_THRESHOLD = 0.85
MAX_CORRELATED_POSITIONS = 2

# Database Schema Constants
REGIME_TABLE = 'Fact_Market_Regime_V2'
SIGNALS_TABLE = 'Fact_Signals'
LIVE_TRADES_TABLE = 'Fact_Live_Trades'
EXECUTION_LOG_TABLE = 'Fact_Execution_Log'


# =============================================================================
# DATA CLASSES & ENUMS
# =============================================================================

class TradeDecision(Enum):
    """Trade decision outcomes from the execution pipeline."""
    APPROVED = "approved"
    VETOED_MODEL = "vetoed_model"
    VETOED_CORRELATION = "vetoed_correlation"
    VETOED_EXPOSURE = "vetoed_exposure"
    VETOED_RISK = "vetoed_risk"
    SKIPPED_NO_REGIME = "skipped_no_regime"
    SKIPPED_NO_SIGNAL = "skipped_no_signal"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    SKIPPED_INVALID_ATR = "skipped_invalid_atr"
    ERROR = "error"


@dataclass
class SignalContext:
    """Upstream signal with all required contract fields."""
    timestamp: datetime
    asset_id: int
    strategy_id: int
    granularity: str
    signal_value: int  # 1 for buy, -1 for sell
    symbol: str
    
    # Optional fields from Layer 2
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RegimeContext:
    """Market regime context from Layer 1."""
    timestamp: datetime
    asset_id: int
    granularity: str
    regime_label: str
    atr_value: float
    adx_value: float
    session_volume_z: Optional[float] = None
    model_version: Optional[str] = None


@dataclass
class ModelArtifact:
    """Layer 3 model artifact with metadata."""
    model: Any
    preprocessor: Any
    threshold: float
    model_type: str
    feature_columns: List[str]
    run_id: str
    training_timestamp: str
    supported_granularities: List[str]
    artifact_hash: str


@dataclass
class RiskParameters:
    """ATR-based risk parameters for a trade."""
    entry_price: float
    stop_loss: float
    take_profit: float
    atr_value: float
    position_size: Optional[float] = None
    rr_ratio: float = DEFAULT_RR_RATIO


@dataclass
class CorrelationResult:
    """Result of correlation/exposure check."""
    passed: bool
    correlation_score: Optional[float] = None
    correlated_assets: List[str] = field(default_factory=list)
    exposure_pct: float = 0.0
    reason: str = ""


@dataclass
class ExecutionResult:
    """Complete execution result for audit logging."""
    # Identification
    trade_id: str
    timestamp: datetime
    asset_id: int
    strategy_id: int
    granularity: str
    symbol: str
    
    # Signal context
    signal_value: int
    regime_label: str
    
    # Model decision
    model_decision: TradeDecision
    confidence_score: Optional[float] = None
    model_threshold: Optional[float] = None
    
    # Risk parameters
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    atr_value: Optional[float] = None
    
    # Correlation gate
    correlation_result: Optional[CorrelationResult] = None
    
    # Broker execution
    broker_order_id: Optional[str] = None
    fill_price: Optional[float] = None
    fill_time: Optional[datetime] = None
    slippage_pips: Optional[float] = None
    
    # Audit
    veto_reason: str = ""
    execution_metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure structured logging for the execution pipeline."""
    log_dir = Path("logs")

    # Handle stale cleanup artifacts (e.g., broken symlink at ./logs) gracefully.
    if log_dir.is_symlink() and not log_dir.exists():
        fallback_dir = Path("runtime_logs")
        fallback_dir.mkdir(parents=True, exist_ok=True)
        log_dir = fallback_dir
    elif log_dir.exists() and not log_dir.is_dir():
        fallback_dir = Path("runtime_logs")
        fallback_dir.mkdir(parents=True, exist_ok=True)
        log_dir = fallback_dir
    else:
        log_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"layer4_execution_{timestamp}.log"
    
    logger = logging.getLogger("layer4")
    logger.setLevel(getattr(logging, log_level.upper()))
    logger.propagate = False
    
    if logger.handlers:
        logger.handlers.clear()
    
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    
    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)
    
    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger


logger = logging.getLogger("layer4")


# =============================================================================
# DATABASE CONNECTION
# =============================================================================

def create_db_engine() -> sa.engine.Engine:
    """Create SQLAlchemy engine with environment configuration."""
    db_server = os.getenv('DB_SERVER')
    db_user = os.getenv('DB_USER')
    db_pass = os.getenv('DB_PASS')
    db_name = os.getenv('DB_NAME', 'ForexBrainDB')
    db_driver = os.getenv('DB_DRIVER') or os.getenv('DB_ODBC_DRIVER')
    db_port = os.getenv('DB_PORT')
    db_timeout = os.getenv('DB_CONNECTION_TIMEOUT', '15')
    
    if not all([db_server, db_user, db_pass]):
        raise ValueError("Missing required database credentials in environment")

    # Select an installed SQL Server ODBC driver instead of assuming Driver 17.
    available_drivers = set(pyodbc.drivers())
    driver_candidates = []
    if db_driver:
        driver_candidates.append(db_driver)
    driver_candidates.extend([
        'ODBC Driver 18 for SQL Server',
        'ODBC Driver 17 for SQL Server',
    ])

    selected_driver = None
    for candidate in driver_candidates:
        if candidate in available_drivers:
            selected_driver = candidate
            break

    if selected_driver is None:
        raise RuntimeError(
            "No supported SQL Server ODBC driver found for Layer 4. "
            f"Installed drivers: {sorted(available_drivers)}"
        )

    server_spec = db_server
    if db_port and ',' not in db_server:
        server_spec = f"{db_server},{db_port}"
    
    params = (
        f"DRIVER={{{selected_driver}}};"
        f"SERVER={server_spec};"
        f"DATABASE={db_name};"
        f"UID={db_user};"
        f"PWD={db_pass};"
        "TrustServerCertificate=yes;"
        "Encrypt=yes;"
        f"Connection Timeout={db_timeout};"
    )
    
    import urllib.parse
    return sa.create_engine(f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(params)}")


def send_email(alert_text: str) -> None:
    """Send a trade alert email when SMTP credentials are configured."""
    if not SMTP_USER or not SMTP_PASS:
        logger.warning("SMTP creds missing; skipping email alert.")
        return

    if not EMAIL_TO:
        logger.warning("EMAIL_TO missing; skipping email alert.")
        return

    msg = MIMEText(alert_text)
    msg['Subject'] = 'Scalable Brain Trade Alert'
    msg['From'] = SMTP_USER
    msg['To'] = EMAIL_TO

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        logger.info("Email alert sent.")
    except Exception as exc:
        logger.error(f"Email send failed: {exc}")


# =============================================================================
# STAGE 1: LOAD LIVE SIGNAL CONTEXT WITH FULL FEATURES
# =============================================================================

def load_live_signals_with_features(
    engine: sa.engine.Engine,
    granularity: str,
    lookback_minutes: Optional[int] = None,
    lookback_bars: Optional[int] = None,
    max_signals: int = 1000
) -> pd.DataFrame:
    """
    Load approved signal candidates from Layer 2 with ALL features needed for ML.
    
    This joins Fact_Signals with Fact_Market_Regime_V2 and Fact_Trade_Outcomes
    to provide the complete feature set that the Layer 3 model was trained on.
    
    Args:
        engine: Database engine
        granularity: Time granularity (H1, H4)
        lookback_minutes: How far back to look for signals (None = all)
        lookback_bars: Alternative to minutes - look back N bars (None = all)
        max_signals: Maximum signals to load (safety limit)
        
    Returns:
        DataFrame with full feature columns matching training
    """
    if granularity not in SUPPORTED_GATEKEEPER_GRANULARITIES:
        raise ValueError(
            f"Granularity '{granularity}' not supported. "
            f"Supported: {SUPPORTED_GATEKEEPER_GRANULARITIES}"
        )
    
    # Build WHERE clause dynamically
    where_clauses = ["s.Granularity = :granularity"]
    params = {'granularity': granularity}
    
    if lookback_minutes is not None:
        cutoff_time = datetime.now() - timedelta(minutes=lookback_minutes)
        where_clauses.append("s.Timestamp >= :cutoff_time")
        params['cutoff_time'] = cutoff_time
    elif lookback_bars is not None:
        hours_back = lookback_bars if granularity == 'H1' else lookback_bars * 4
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        where_clauses.append("s.Timestamp >= :cutoff_time")
        params['cutoff_time'] = cutoff_time
    
    # Check for Is_Active column
    signal_cols = {c['name'] for c in sa.inspect(engine).get_columns(SIGNALS_TABLE)}
    if 'Is_Active' in signal_cols:
        where_clauses.append("s.Is_Active = 1")
    
    where_sql = " AND ".join(where_clauses)
    
    # Check which columns exist in Fact_Trade_Outcomes
    outcome_cols = {c['name'] for c in sa.inspect(engine).get_columns('Fact_Trade_Outcomes')}
    has_outcome_granularity = 'Granularity' in outcome_cols
    
    # Build outcome join condition
    outcome_join = """LEFT JOIN Fact_Trade_Outcomes t ON s.Asset_ID = t.Asset_ID 
        AND s.Strategy_ID = t.Strategy_ID 
        AND s.Timestamp = t.Timestamp"""
    if has_outcome_granularity:
        outcome_join += "\n        AND s.Granularity = t.Granularity"
    
    # Build outcome column selection dynamically
    outcome_select_cols = []
    if 'Is_Winner' in outcome_cols:
        outcome_select_cols.append("t.Is_Winner")
    if 'R_Multiple' in outcome_cols:
        outcome_select_cols.append("t.R_Multiple")
    if 'Holding_Bars' in outcome_cols:
        outcome_select_cols.append("t.Holding_Bars")
    
    outcome_select = ",\n        ".join(outcome_select_cols) if outcome_select_cols else ""
    
    # Check which columns exist in Fact_Market_Regime_V2
    regime_cols = {c['name'] for c in sa.inspect(engine).get_columns(REGIME_TABLE)}
    
    # Build dynamic regime column selection
    base_regime_cols = [
        "r.Regime_Label",
        "r.ATR_Value",
        "r.ADX_Value",
        "r.Session_Volume_Z",
        "r.Regime_Model_Version"
    ]
    
    # Optional regime columns - only add if they exist
    optional_regime_cols = [
        "ATR_Pct", "ATR_Z", "ADX_Delta", "Trend_Ratio", "Realized_Vol_Z",
        "Candle_Body", "Upper_Wick", "Lower_Wick", "Close_Position",
        "BB_Width", "BB_Width_Z", "Vol_Persistence",
        "H4_Trend_Direction", "D1_Trend_Direction",
        "Trend_Alignment_Score", "Volatility_Regime", "ATR_Percentile_20D"
    ]
    
    for col in optional_regime_cols:
        if col in regime_cols:
            base_regime_cols.append(f"r.{col}")
    
    regime_select = ",\n        ".join(base_regime_cols)
    
    # Add comma before outcome columns if there are any
    outcome_section = f",\n        {outcome_select}" if outcome_select else ""
    
    # COMPREHENSIVE query joining all three tables
    query = sa.text(f"""
    SELECT TOP {max_signals}
        -- Core identifiers
        s.Timestamp,
        s.Asset_ID,
        s.Strategy_ID,
        s.Granularity,
        s.Signal_Value,
        s.Signal_Reason,
        s.Rule_ID,
        s.Confidence_Score as Signal_Confidence,
        s.Strategy_Version,
        s.Indicator_Snapshot,
        a.Symbol,
        
        -- Regime features from Layer 1
        {regime_select}{outcome_section}
        
    FROM {SIGNALS_TABLE} s
    INNER JOIN Dim_Asset a ON s.Asset_ID = a.Asset_ID
    LEFT JOIN {REGIME_TABLE} r ON s.Asset_ID = r.Asset_ID 
        AND s.Granularity = r.Granularity 
        AND r.Timestamp = (
            SELECT MAX(Timestamp) FROM {REGIME_TABLE} 
            WHERE Asset_ID = s.Asset_ID 
            AND Granularity = s.Granularity 
            AND Timestamp <= s.Timestamp
        )
    {outcome_join}
    WHERE {where_sql}
      AND s.Signal_Value != 0
    ORDER BY s.Timestamp DESC
    """)
    
    try:
        df = pd.read_sql(query, engine, params=params)
        
        # Log signal distribution
        if not df.empty:
            buy_count = (df['Signal_Value'] == 1).sum()
            sell_count = (df['Signal_Value'] == -1).sum()
            logger.info(
                f"Loaded {len(df)} signals with full features from {SIGNALS_TABLE} for {granularity} "
                f"(Buy: {buy_count}, Sell: {sell_count})"
            )
            logger.info(f"Feature columns available: {len(df.columns)}")
        else:
            count_query = sa.text(f"SELECT COUNT(*) as total FROM {SIGNALS_TABLE}")
            total_count = pd.read_sql(count_query, engine).iloc[0]['total']
            logger.warning(
                f"No signals found for {granularity} with current filters. "
                f"Total signals in table: {total_count}"
            )
            
        return df
    except Exception as e:
        logger.error(f"Failed to load signals: {e}")
        raise


# Legacy function for backward compatibility
def load_live_signals(
    engine: sa.engine.Engine,
    granularity: str,
    lookback_minutes: Optional[int] = None,
    lookback_bars: Optional[int] = None,
    max_signals: int = 1000
) -> pd.DataFrame:
    """Legacy wrapper that calls the new comprehensive feature loader."""
    return load_live_signals_with_features(
        engine, granularity, lookback_minutes, lookback_bars, max_signals
    )


# =============================================================================
# STAGE 2: LOAD CURRENT REGIME
# =============================================================================

def load_current_regime(
    engine: sa.engine.Engine,
    asset_id: int,
    granularity: str,
    timestamp: datetime
) -> Optional[RegimeContext]:
    """
    Resolve current regime from Fact_Market_Regime_V2.
    
    Args:
        engine: Database engine
        asset_id: Asset identifier
        granularity: Time granularity
        timestamp: Signal timestamp for regime lookup
        
    Returns:
        RegimeContext if found, None otherwise
    """
    query = sa.text(f"""
    SELECT TOP 1
        Timestamp,
        Asset_ID,
        Granularity,
        Regime_Label,
        ATR_Value,
        ADX_Value,
        Session_Volume_Z,
        Regime_Model_Version
    FROM {REGIME_TABLE}
    WHERE Asset_ID = :asset_id
      AND Granularity = :granularity
      AND Timestamp <= :timestamp
    ORDER BY Timestamp DESC
    """)
    
    try:
        df = pd.read_sql(
            query,
            engine,
            params={
                'asset_id': asset_id,
                'granularity': granularity,
                'timestamp': timestamp
            }
        )
        
        if df.empty:
            logger.warning(
                f"No regime found for Asset_ID={asset_id}, "
                f"Granularity={granularity}, Timestamp<={timestamp}"
            )
            return None
        
        row = df.iloc[0]
        return RegimeContext(
            timestamp=row['Timestamp'],
            asset_id=row['Asset_ID'],
            granularity=row['Granularity'],
            regime_label=row['Regime_Label'],
            atr_value=row['ATR_Value'],
            adx_value=row['ADX_Value'],
            session_volume_z=row.get('Session_Volume_Z'),
            model_version=row.get('Regime_Model_Version')
        )
    except Exception as e:
        logger.error(f"Failed to load regime: {e}")
        return None


# =============================================================================
# STAGE 3: LOAD MODEL ARTIFACT
# =============================================================================

def load_model_manifest(manifest_path: Path) -> Optional[Dict[str, Any]]:
    """Load and validate the Layer 3 champion model manifest."""
    if not manifest_path.exists():
        logger.warning(f"Manifest not found at {manifest_path}")
        return None
    
    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        
        required_fields = [
            'model_type', 'artifact_path', 'preprocessor_path', 
            'threshold', 'feature_columns', 'run_id'
        ]
        
        missing = [f for f in required_fields if f not in manifest]
        if missing:
            logger.error(f"Manifest missing required fields: {missing}")
            return None
        
        return manifest
    except Exception as e:
        logger.error(f"Failed to load manifest: {e}")
        return None


def verify_artifact_hash(file_path: Path, expected_hash: str) -> bool:
    """Verify SHA256 hash of model artifact."""
    if not expected_hash:
        return True
    
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    
    actual_hash = sha256.hexdigest()
    return actual_hash == expected_hash


def compute_artifact_hash(file_path: Path) -> str:
    """Compute SHA256 hash for an artifact file."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def load_model_artifact(
    use_stable_alias: bool = True,
    manifest_path: Optional[Path] = None
) -> ModelArtifact:
    """
    Load the Layer 3 champion model artifact.
    
    Args:
        use_stable_alias: If True, use stable alias paths; else use manifest
        manifest_path: Optional override for manifest location
        
    Returns:
        ModelArtifact with all components
        
    Raises:
        FileNotFoundError: If artifact cannot be loaded
        ValueError: If artifact is corrupted or invalid
    """
    manifest = None
    
    if not use_stable_alias:
        manifest_path = manifest_path or LAYER3_MANIFEST_PATH
        manifest = load_model_manifest(manifest_path)
    
    if manifest:
        model_path = Path(manifest['artifact_path'])
        preprocessor_path = Path(manifest['preprocessor_path'])
        threshold = manifest['threshold']
        model_type = manifest['model_type']
        feature_columns = manifest['feature_columns']
        run_id = manifest['run_id']
        training_timestamp = manifest.get('training_timestamp', '')
        supported_granularities = manifest.get('supported_granularities', ['H1', 'H4'])
        expected_hash = manifest.get('artifact_hash', '')
    else:
        # Fallback to stable alias, then legacy Layer 3 artifact names.
        if LAYER3_STABLE_ALIAS.exists() and LAYER3_PREPROCESSOR_ALIAS.exists():
            model_path = LAYER3_STABLE_ALIAS
            preprocessor_path = LAYER3_PREPROCESSOR_ALIAS
            run_id = 'stable_alias'
        elif LAYER3_LEGACY_MODEL_PATH.exists() and LAYER3_LEGACY_PREPROCESSOR_PATH.exists():
            model_path = LAYER3_LEGACY_MODEL_PATH
            preprocessor_path = LAYER3_LEGACY_PREPROCESSOR_PATH
            run_id = 'legacy_alias'
            logger.warning(
                "Using legacy Layer 3 artifacts. Promote a champion model to align with current contract."
            )
        else:
            model_path = LAYER3_STABLE_ALIAS
            preprocessor_path = LAYER3_PREPROCESSOR_ALIAS
            run_id = 'stable_alias'

        threshold = float(os.getenv('LAYER3_APPROVAL_THRESHOLD', '0.82'))
        model_type = 'unknown'
        feature_columns = []
        training_timestamp = ''
        supported_granularities = ['H1', 'H4']
        expected_hash = ''
    
    # Validate paths exist
    if not model_path.exists():
        raise FileNotFoundError(f"Model artifact not found: {model_path}")
    if not preprocessor_path.exists():
        raise FileNotFoundError(f"Preprocessor not found: {preprocessor_path}")
    
    # Verify hash if available
    if expected_hash and not verify_artifact_hash(model_path, expected_hash):
        raise ValueError(f"Model artifact hash mismatch: {model_path}")
    
    # Load artifacts
    try:
        model = joblib.load(model_path)
        preprocessor = joblib.load(preprocessor_path)
        
        # Extract feature columns from model if not in manifest
        if not feature_columns and hasattr(model, 'feature_names_in_'):
            feature_columns = model.feature_names_in_.tolist()
        
        logger.info(f"Loaded model artifact: {model_type} (run_id={run_id})")
        logger.info(f"Model threshold: {threshold:.4f}")
        logger.info(f"Expected features: {len(feature_columns)}")
        
        return ModelArtifact(
            model=model,
            preprocessor=preprocessor,
            threshold=threshold,
            model_type=model_type,
            feature_columns=feature_columns,
            run_id=run_id,
            training_timestamp=training_timestamp,
            supported_granularities=supported_granularities,
            artifact_hash=expected_hash or compute_artifact_hash(model_path)
        )
    except Exception as e:
        logger.error(f"Failed to load model artifact: {e}")
        raise


# =============================================================================
# STAGE 4: COMPUTE ATR RISK PARAMETERS
# =============================================================================

def fetch_live_price(symbol: str, granularity: str = "H1", count: int = 50) -> Optional[pd.DataFrame]:
    """Fetch live price data from OANDA for ATR calculation."""
    try:
        api_key = os.getenv('OANDA_API_KEY')
        env = os.getenv('OANDA_ENV', 'practice')
        
        if not api_key:
            logger.warning("OANDA_API_KEY not set, cannot fetch live prices")
            return None
        
        api = API(access_token=api_key, environment=env)
        
        params = {
            "count": count,
            "granularity": granularity,
            "price": "M"
        }
        
        r = InstrumentsCandles(instrument=symbol, params=params)
        response = api.request(r)
        candles = response['candles']
        
        df = pd.DataFrame([{
            'Timestamp': pd.to_datetime(c['time']),
            'Open': float(c['mid']['o']),
            'High': float(c['mid']['h']),
            'Low': float(c['mid']['l']),
            'Close': float(c['mid']['c'])
        } for c in candles])
        
        return df
    except Exception as e:
        logger.warning(f"Failed to fetch live price for {symbol}: {e}")
        return None


def compute_atr_risk_parameters(
    signal: SignalContext,
    regime: RegimeContext,
    live_price_df: Optional[pd.DataFrame] = None,
    rr_ratio: float = DEFAULT_RR_RATIO,
    atr_multiplier_sl: float = DEFAULT_ATR_MULTIPLIER_SL,
    atr_multiplier_tp: float = DEFAULT_ATR_MULTIPLIER_TP
) -> Optional[RiskParameters]:
    """
    Compute ATR-based stop loss and take profit.
    
    Args:
        signal: Signal context with direction
        regime: Regime context with ATR value
        live_price_df: Optional live price data for validation
        rr_ratio: Risk/reward ratio target
        atr_multiplier_sl: ATR multiplier for stop loss
        atr_multiplier_tp: ATR multiplier for take profit
        
    Returns:
        RiskParameters if valid, None otherwise
    """
    # Validate ATR
    if not regime.atr_value or regime.atr_value <= 0:
        logger.warning(f"Invalid ATR value: {regime.atr_value}")
        return None
    
    # Get entry price
    if live_price_df is not None and not live_price_df.empty:
        entry_price = live_price_df['Close'].iloc[-1]
    else:
        logger.warning(f"Using fallback price for {signal.symbol}")
        return None
    
    direction = signal.signal_value
    atr = regime.atr_value
    
    # Calculate SL and TP
    sl_distance = atr * atr_multiplier_sl
    tp_distance = atr * atr_multiplier_tp
    
    if direction == 1:  # Buy
        stop_loss = entry_price - sl_distance
        take_profit = entry_price + tp_distance
    else:  # Sell
        stop_loss = entry_price + sl_distance
        take_profit = entry_price - tp_distance
    
    # Validate SL/TP are on correct side
    if direction == 1 and (stop_loss >= entry_price or take_profit <= entry_price):
        logger.error(f"Invalid SL/TP for BUY: entry={entry_price}, SL={stop_loss}, TP={take_profit}")
        return None
    if direction == -1 and (stop_loss <= entry_price or take_profit >= entry_price):
        logger.error(f"Invalid SL/TP for SELL: entry={entry_price}, SL={stop_loss}, TP={take_profit}")
        return None
    
    return RiskParameters(
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        atr_value=atr,
        rr_ratio=rr_ratio
    )


# =============================================================================
# STAGE 5: EVALUATE CORRELATION GATE (Layer 4.5)
# =============================================================================

def fetch_price_history(
    engine: sa.engine.Engine,
    asset_id: int,
    granularity: str,
    bars: int = CORRELATION_LOOKBACK_BARS
) -> Optional[pd.Series]:
    """Fetch price history for correlation calculation."""
    safe_bars = max(1, int(bars))
    query = sa.text(f"""
    SELECT TOP ({safe_bars}) Close
    FROM Fact_Market_Prices
    WHERE Asset_ID = :asset_id
      AND Granularity = :granularity
    ORDER BY Timestamp DESC
    """)
    
    try:
        df = pd.read_sql(
            query,
            engine,
            params={'asset_id': asset_id, 'granularity': granularity}
        )
        if len(df) < bars * 0.8:
            return None
        return df['Close'].iloc[::-1]
    except Exception as e:
        logger.warning(f"Failed to fetch price history: {e}")
        return None


def evaluate_correlation_gate(
    engine: sa.engine.Engine,
    signal: SignalContext,
    open_positions: List[Dict[str, Any]],
    correlation_threshold: float = CORRELATION_THRESHOLD
) -> CorrelationResult:
    """
    Evaluate portfolio exposure and correlation constraints.
    
    Args:
        engine: Database engine
        signal: New signal being evaluated
        open_positions: List of currently open positions
        correlation_threshold: Maximum allowed correlation
        
    Returns:
        CorrelationResult with pass/fail and details
    """
    # Check exposure limit
    total_exposure = len(open_positions)
    if total_exposure >= MAX_TOTAL_EXPOSURE_PCT * 10:
        return CorrelationResult(
            passed=False,
            exposure_pct=total_exposure / 10,
            reason=f"Maximum exposure reached: {total_exposure} positions"
        )
    
    # Check asset concentration
    asset_positions = [p for p in open_positions if p['asset_id'] == signal.asset_id]
    if len(asset_positions) >= MAX_POSITIONS_PER_ASSET:
        return CorrelationResult(
            passed=False,
            exposure_pct=total_exposure / 10,
            reason=f"Max positions for asset {signal.asset_id}: {len(asset_positions)}"
        )
    
    # Check correlation with existing positions
    correlated_assets = []
    max_correlation = 0.0
    
    new_asset_prices = fetch_price_history(engine, signal.asset_id, signal.granularity)
    if new_asset_prices is None:
        logger.warning(f"Cannot calculate correlation: no price history for Asset_ID={signal.asset_id}")
        return CorrelationResult(
            passed=True,
            correlation_score=None,
            reason="Correlation calculation skipped: insufficient price history"
        )
    
    for position in open_positions:
        existing_prices = fetch_price_history(
            engine, position['asset_id'], position.get('granularity', signal.granularity)
        )
        if existing_prices is None:
            continue
        
        min_len = min(len(new_asset_prices), len(existing_prices))
        if min_len < 20:
            continue
        
        correlation = np.corrcoef(
            new_asset_prices.iloc[-min_len:].pct_change().dropna(),
            existing_prices.iloc[-min_len:].pct_change().dropna()
        )[0, 1]
        
        if not np.isnan(correlation):
            max_correlation = max(max_correlation, abs(correlation))
            if abs(correlation) > correlation_threshold:
                correlated_assets.append(position['symbol'])
    
    if len(correlated_assets) >= MAX_CORRELATED_POSITIONS:
        return CorrelationResult(
            passed=False,
            correlation_score=max_correlation,
            correlated_assets=correlated_assets,
            exposure_pct=total_exposure / 10,
            reason=f"Too many correlated positions: {correlated_assets}"
        )
    
    return CorrelationResult(
        passed=True,
        correlation_score=max_correlation,
        correlated_assets=correlated_assets,
        exposure_pct=total_exposure / 10,
        reason="Correlation check passed"
    )


# =============================================================================
# STAGE 6: ML GATEKEEPER EVALUATION WITH FULL FEATURES
# =============================================================================

def prepare_features_for_inference(
    signal_row: pd.Series,
    artifact: ModelArtifact
) -> pd.DataFrame:
    """
    Prepare the complete feature vector for ML inference.
    
    This function:
    1. Converts signal data to DataFrame
    2. Applies comprehensive feature engineering (creates derived features)
    3. Aligns columns to match training schema
    4. Returns DataFrame ready for preprocessor.transform()
    
    The ColumnTransformer expects EXACTLY these columns in the same order.
    Missing columns are filled with NaN (preprocessor handles imputation).
    """
    logger.debug(f"prepare_features_for_inference: Starting with {len(signal_row)} fields")
    
    # Step 1: Convert Series to DataFrame
    df = pd.DataFrame([signal_row.to_dict()])
    
    # Step 2: Standardize common column names
    column_mapping = {
        'Confidence_Score': 'Signal_Confidence',
        'Signal_Reason': 'Signal_Reason',  # Keep as-is
    }
    df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})
    
    # Step 3: Ensure datetime columns
    if 'Timestamp' in df.columns:
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
    
    logger.debug(f"After standardization: {len(df.columns)} columns")
    
    # Step 4: Apply comprehensive feature engineering
    # This creates derived features, interactions, etc.
    try:
        df = safe_comprehensive_feature_engineering(df)
        logger.debug(f"After feature engineering: {len(df.columns)} columns")
    except Exception as e:
        logger.error(f"Feature engineering failed: {e}")
        # Continue anyway - alignment will add missing columns with NaN
        pass
    
    # Step 5: Align to expected columns
    # This ensures we have EXACTLY the columns the ColumnTransformer expects
    df = align_features_for_inference(df, artifact.feature_columns)
    
    logger.debug(
        f"After alignment: {len(df.columns)} columns (expected {len(artifact.feature_columns)})\n"
        f"  Sample columns: {list(df.columns)[:5]}..."
    )
    
    # Step 6: Validation check
    missing = set(artifact.feature_columns) - set(df.columns)
    if missing:
        logger.warning(f"Error: {len(missing)} columns still missing after alignment: {sorted(list(missing)[:5])}...")
        raise ValueError(f"Failed to provide {len(missing)} required columns")
    
    return df
    
    return df


def run_ml_gatekeeper(
    artifact: ModelArtifact,
    signal_row: pd.Series
) -> Tuple[TradeDecision, float]:
    """
    Run ML gatekeeper approval with comprehensive features.
    
    Args:
        artifact: Loaded model artifact
        signal_row: Signal data row with all available features
        
    Returns:
        Tuple of (decision, confidence_score)
    """
    granularity = signal_row.get('Granularity', 'H1')
    
    # Validate granularity is supported by model
    if artifact.supported_granularities and granularity not in artifact.supported_granularities:
        logger.warning(
            f"Granularity {granularity} not supported by model. "
            f"Supported: {artifact.supported_granularities}"
        )
        return TradeDecision.ERROR, 0.0
    
    try:
        # Prepare complete feature vector
        features_df = prepare_features_for_inference(signal_row, artifact)
        
        logger.debug(f"Feature matrix shape: {features_df.shape}")
        logger.debug(f"Feature columns: {list(features_df.columns)[:10]}...")
        
        # Apply preprocessing
        features = artifact.preprocessor.transform(features_df)
        
        # Predict
        if hasattr(artifact.model, 'predict_proba'):
            prob = artifact.model.predict_proba(features)[0][1]
        else:
            prob = float(artifact.model.predict(features)[0])
        
        # Apply threshold
        if prob >= artifact.threshold:
            return TradeDecision.APPROVED, prob
        else:
            return TradeDecision.VETOED_MODEL, prob
            
    except Exception as e:
        logger.error(f"ML gatekeeper evaluation failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return TradeDecision.ERROR, 0.0


# =============================================================================
# STAGE 7: BROKER EXECUTION
# =============================================================================

def prepare_broker_order(
    signal: SignalContext,
    risk: RiskParameters,
    symbol_map: Dict[int, str]
) -> Dict[str, Any]:
    """
    Prepare order parameters for broker execution.
    
    Args:
        signal: Signal context
        risk: Risk parameters
        symbol_map: Mapping of Asset_ID to broker symbol
        
    Returns:
        Order parameters dictionary
    """
    symbol = symbol_map.get(signal.asset_id, signal.symbol)
    
    # Determine precision based on symbol
    precision = 3 if 'JPY' in symbol else 5
    
    return {
        'instrument': symbol,
        'entry_price': round(risk.entry_price, precision),
        'sl_price': round(risk.stop_loss, precision),
        'tp_price': round(risk.take_profit, precision),
        'direction': signal.signal_value,
        'units': None
    }


def execute_broker_order(
    order_params: Dict[str, Any],
    dry_run: bool = False
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    Execute order through broker adapter.
    
    Args:
        order_params: Order parameters
        dry_run: If True, simulate execution without actual order
        
    Returns:
        Tuple of (success, order_id, execution_metadata)
    """
    if dry_run:
        logger.info(f"[DRY RUN] Would execute: {order_params}")
        return True, "DRY_RUN_001", {'simulated': True}
    
    try:
        result = execute_trade(
            instrument=order_params['instrument'],
            entry_price=order_params['entry_price'],
            sl_price=order_params['sl_price'],
            tp_price=order_params['tp_price'],
            direction=order_params['direction']
        )
        
        if result and result.get('success'):
            return (
                True,
                result.get('order_id'),
                {
                    'fill_price': result.get('fill_price'),
                    'fill_time': result.get('fill_time'),
                    'slippage_pips': result.get('slippage_pips')
                }
            )
        else:
            return False, None, {'error': result.get('error', 'Unknown')}
            
    except Exception as e:
        logger.error(f"Broker execution failed: {e}")
        return False, None, {'error': str(e)}


# =============================================================================
# STAGE 8: EXECUTION LOGGING
# =============================================================================

def write_pre_execution_log(
    engine: sa.engine.Engine,
    result: ExecutionResult
) -> bool:
    """Write pre-execution state to database."""
    query = f"""
    INSERT INTO {LIVE_TRADES_TABLE} (
        Trade_ID, Timestamp, Asset_ID, Strategy_ID, Granularity,
        Symbol, Signal_Value, Regime_Label, Model_Decision,
        Confidence_Score, Model_Threshold, Entry_Price, Stop_Loss,
        Take_Profit, ATR_Value, Correlation_Score, Correlation_Passed,
        Veto_Reason, Execution_Status, Created_At
    ) VALUES (
        :trade_id, :timestamp, :asset_id, :strategy_id, :granularity,
        :symbol, :signal_value, :regime_label, :model_decision,
        :confidence_score, :model_threshold, :entry_price, :stop_loss,
        :take_profit, :atr_value, :correlation_score, :correlation_passed,
        :veto_reason, 'PENDING', GETDATE()
    )
    """
    
    try:
        with engine.connect() as conn:
            conn.execute(
                sa.text(query),
                {
                    'trade_id': result.trade_id,
                    'timestamp': result.timestamp,
                    'asset_id': result.asset_id,
                    'strategy_id': result.strategy_id,
                    'granularity': result.granularity,
                    'symbol': result.symbol,
                    'signal_value': result.signal_value,
                    'regime_label': result.regime_label,
                    'model_decision': result.model_decision.value,
                    'confidence_score': result.confidence_score,
                    'model_threshold': result.model_threshold,
                    'entry_price': result.entry_price,
                    'stop_loss': result.stop_loss,
                    'take_profit': result.take_profit,
                    'atr_value': result.atr_value,
                    'correlation_score': result.correlation_result.correlation_score if result.correlation_result else None,
                    'correlation_passed': result.correlation_result.passed if result.correlation_result else None,
                    'veto_reason': result.veto_reason
                }
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to write pre-execution log: {e}")
        return False


def update_post_execution_log(
    engine: sa.engine.Engine,
    trade_id: str,
    broker_order_id: Optional[str],
    fill_price: Optional[float],
    fill_time: Optional[datetime],
    slippage_pips: Optional[float],
    final_status: str
) -> bool:
    """Update execution log with post-execution details."""
    query = f"""
    UPDATE {LIVE_TRADES_TABLE}
    SET Broker_Order_ID = :broker_order_id,
        Fill_Price = :fill_price,
        Fill_Time = :fill_time,
        Slippage_Pips = :slippage_pips,
        Execution_Status = :final_status,
        Updated_At = GETDATE()
    WHERE Trade_ID = :trade_id
    """
    
    try:
        with engine.connect() as conn:
            conn.execute(
                sa.text(query),
                {
                    'trade_id': trade_id,
                    'broker_order_id': broker_order_id,
                    'fill_price': fill_price,
                    'fill_time': fill_time,
                    'slippage_pips': slippage_pips,
                    'final_status': final_status
                }
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to update post-execution log: {e}")
        return False


def log_skipped_trade(
    engine: sa.engine.Engine,
    signal_row: pd.Series,
    reason: TradeDecision,
    details: str = ""
) -> None:
    """Log a skipped trade with reason."""
    trade_id = f"SKIPPED_{signal_row['Asset_ID']}_{signal_row['Strategy_ID']}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    query = f"""
    INSERT INTO {LIVE_TRADES_TABLE} (
        Trade_ID, Timestamp, Asset_ID, Strategy_ID, Granularity,
        Symbol, Signal_Value, Model_Decision, Veto_Reason, Execution_Status, Created_At
    ) VALUES (
        :trade_id, :timestamp, :asset_id, :strategy_id, :granularity,
        :symbol, :signal_value, :model_decision, :veto_reason, 'SKIPPED', GETDATE()
    )
    """
    
    try:
        with engine.connect() as conn:
            conn.execute(
                sa.text(query),
                {
                    'trade_id': trade_id,
                    'timestamp': signal_row['Timestamp'],
                    'asset_id': signal_row['Asset_ID'],
                    'strategy_id': signal_row['Strategy_ID'],
                    'granularity': signal_row['Granularity'],
                    'symbol': signal_row['Symbol'],
                    'signal_value': signal_row['Signal_Value'],
                    'model_decision': reason.value,
                    'veto_reason': details
                }
            )
            conn.commit()
        logger.info(f"Logged skipped trade: {reason.value} - {details}")
    except Exception as e:
        logger.error(f"Failed to log skipped trade: {e}")


# =============================================================================
# MAIN PIPELINE ORCHESTRATOR
# =============================================================================

class ExecutionPipeline:
    """Layer 4 execution pipeline orchestrator."""
    
    def __init__(
        self,
        engine: sa.engine.Engine,
        model_artifact: ModelArtifact,
        dry_run: bool = False,
        skip_correlation: bool = False
    ):
        self.engine = engine
        self.model_artifact = model_artifact
        self.dry_run = dry_run
        self.skip_correlation = skip_correlation
        self.open_positions: List[Dict[str, Any]] = []
        self.symbol_map: Dict[int, str] = {}
        
    def load_symbol_map(self) -> None:
        """Load Asset_ID to symbol mapping from database."""
        try:
            df = pd.read_sql("SELECT Asset_ID, Symbol FROM Dim_Asset", self.engine)
            self.symbol_map = dict(zip(df['Asset_ID'], df['Symbol']))
        except Exception as e:
            logger.error(f"Failed to load symbol map: {e}")
            raise
    
    def generate_trade_id(self, signal_row: pd.Series) -> str:
        """Generate unique trade ID."""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        return f"T{signal_row['Asset_ID']}_{signal_row['Strategy_ID']}_{timestamp}"
    
    def process_signal(self, signal_row: pd.Series) -> ExecutionResult:
        """
        Process a single signal through the full execution pipeline.
        """
        trade_id = self.generate_trade_id(signal_row)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing signal: {signal_row['Symbol']} | Strategy {signal_row['Strategy_ID']}")
        logger.info(f"Trade ID: {trade_id}")
        logger.info(f"{'='*60}")
        
        # Stage 1: Load regime (already included in signal_row from JOIN)
        logger.info("Stage 1: Checking regime context...")
        regime_label = signal_row.get('Regime_Label', 'UNKNOWN')
        atr_value = signal_row.get('ATR_Value', 0)
        
        if pd.isna(regime_label) or regime_label == 'UNKNOWN':
            logger.warning(f"No regime found, skipping trade")
            log_skipped_trade(
                self.engine, signal_row, TradeDecision.SKIPPED_NO_REGIME,
                "No matching regime in Fact_Market_Regime_V2"
            )
            return ExecutionResult(
                trade_id=trade_id,
                timestamp=signal_row['Timestamp'],
                asset_id=signal_row['Asset_ID'],
                strategy_id=signal_row['Strategy_ID'],
                granularity=signal_row['Granularity'],
                symbol=signal_row['Symbol'],
                signal_value=signal_row['Signal_Value'],
                regime_label="UNKNOWN",
                model_decision=TradeDecision.SKIPPED_NO_REGIME,
                veto_reason="No matching regime found"
            )
        
        logger.info(f"  Regime: {regime_label} | ATR: {atr_value:.5f}")
        
        # Stage 2: ML Gatekeeper with full features
        logger.info("Stage 2: Running ML gatekeeper with full features...")
        model_decision, confidence = run_ml_gatekeeper(
            self.model_artifact, signal_row
        )
        
        logger.info(f"  Decision: {model_decision.value} | Confidence: {confidence:.3f} | Threshold: {self.model_artifact.threshold:.3f}")
        
        if model_decision != TradeDecision.APPROVED:
            log_skipped_trade(
                self.engine, signal_row, model_decision,
                f"Confidence {confidence:.3f} below threshold {self.model_artifact.threshold}"
            )
            return ExecutionResult(
                trade_id=trade_id,
                timestamp=signal_row['Timestamp'],
                asset_id=signal_row['Asset_ID'],
                strategy_id=signal_row['Strategy_ID'],
                granularity=signal_row['Granularity'],
                symbol=signal_row['Symbol'],
                signal_value=signal_row['Signal_Value'],
                regime_label=regime_label,
                model_decision=model_decision,
                confidence_score=confidence,
                model_threshold=self.model_artifact.threshold,
                veto_reason=f"ML gatekeeper veto: confidence={confidence:.3f}"
            )
        
        # Stage 3: Compute risk parameters
        logger.info("Stage 3: Computing ATR risk parameters...")
        
        # Create SignalContext for risk calc
        signal = SignalContext(
            timestamp=signal_row['Timestamp'],
            asset_id=signal_row['Asset_ID'],
            strategy_id=signal_row['Strategy_ID'],
            granularity=signal_row['Granularity'],
            signal_value=signal_row['Signal_Value'],
            symbol=signal_row['Symbol']
        )
        
        # Create RegimeContext for risk calc
        regime = RegimeContext(
            timestamp=signal_row['Timestamp'],
            asset_id=signal_row['Asset_ID'],
            granularity=signal_row['Granularity'],
            regime_label=regime_label,
            atr_value=atr_value,
            adx_value=signal_row.get('ADX_Value', 0)
        )
        
        live_price = fetch_live_price(signal.symbol, signal.granularity)
        risk = compute_atr_risk_parameters(signal, regime, live_price)
        
        if risk is None:
            log_skipped_trade(
                self.engine, signal_row, TradeDecision.SKIPPED_INVALID_ATR,
                "Could not compute valid risk parameters"
            )
            return ExecutionResult(
                trade_id=trade_id,
                timestamp=signal_row['Timestamp'],
                asset_id=signal_row['Asset_ID'],
                strategy_id=signal_row['Strategy_ID'],
                granularity=signal_row['Granularity'],
                symbol=signal_row['Symbol'],
                signal_value=signal_row['Signal_Value'],
                regime_label=regime_label,
                model_decision=model_decision,
                confidence_score=confidence,
                model_threshold=self.model_artifact.threshold,
                veto_reason="Invalid ATR or risk parameters"
            )
        
        logger.info(f"  Entry: {risk.entry_price:.5f} | SL: {risk.stop_loss:.5f} | TP: {risk.take_profit:.5f}")
        
        # Stage 4: Correlation gate
        if not self.skip_correlation:
            logger.info("Stage 4: Evaluating correlation gate...")
            correlation_result = evaluate_correlation_gate(
                self.engine, signal, self.open_positions
            )
            logger.info(f"  Passed: {correlation_result.passed} | Score: {correlation_result.correlation_score}")
            
            if not correlation_result.passed:
                log_skipped_trade(
                    self.engine, signal_row, TradeDecision.VETOED_CORRELATION,
                    correlation_result.reason
                )
                return ExecutionResult(
                    trade_id=trade_id,
                    timestamp=signal_row['Timestamp'],
                    asset_id=signal_row['Asset_ID'],
                    strategy_id=signal_row['Strategy_ID'],
                    granularity=signal_row['Granularity'],
                    symbol=signal_row['Symbol'],
                    signal_value=signal_row['Signal_Value'],
                    regime_label=regime_label,
                    model_decision=model_decision,
                    confidence_score=confidence,
                    model_threshold=self.model_artifact.threshold,
                    entry_price=risk.entry_price,
                    stop_loss=risk.stop_loss,
                    take_profit=risk.take_profit,
                    atr_value=risk.atr_value,
                    correlation_result=correlation_result,
                    veto_reason=f"Correlation veto: {correlation_result.reason}"
                )
        else:
            correlation_result = CorrelationResult(passed=True, reason="Skipped")
        
        # Stage 5: Prepare execution result
        execution_result = ExecutionResult(
            trade_id=trade_id,
            timestamp=signal_row['Timestamp'],
            asset_id=signal_row['Asset_ID'],
            strategy_id=signal_row['Strategy_ID'],
            granularity=signal_row['Granularity'],
            symbol=signal_row['Symbol'],
            signal_value=signal_row['Signal_Value'],
            regime_label=regime_label,
            model_decision=model_decision,
            confidence_score=confidence,
            model_threshold=self.model_artifact.threshold,
            entry_price=risk.entry_price,
            stop_loss=risk.stop_loss,
            take_profit=risk.take_profit,
            atr_value=risk.atr_value,
            correlation_result=correlation_result
        )
        
        # Write pre-execution log
        write_pre_execution_log(self.engine, execution_result)
        
        # Stage 6: Broker execution
        logger.info("Stage 5: Executing broker order...")
        
        order_params = prepare_broker_order(signal, risk, self.symbol_map)
        success, order_id, exec_meta = execute_broker_order(order_params, self.dry_run)
        
        if success:
            logger.info(f"  Order executed: {order_id}")
            execution_result.broker_order_id = order_id
            execution_result.fill_price = exec_meta.get('fill_price')
            execution_result.fill_time = exec_meta.get('fill_time')
            execution_result.slippage_pips = exec_meta.get('slippage_pips')

            alert_text = (
                f"[TRADE APPROVED] {signal.symbol} | Strategy {signal.strategy_id} | "
                f"{('BUY' if signal.signal_value == 1 else 'SELL')} @ {risk.entry_price:.5f} | "
                f"SL: {risk.stop_loss:.5f} | TP: {risk.take_profit:.5f} | "
                f"Conf: {confidence:.2%}"
            )
            send_email(alert_text)
            
            # Update post-execution log
            update_post_execution_log(
                self.engine, trade_id, order_id,
                execution_result.fill_price,
                execution_result.fill_time,
                execution_result.slippage_pips,
                'EXECUTED'
            )
            
            # Add to open positions
            self.open_positions.append({
                'trade_id': trade_id,
                'asset_id': signal.asset_id,
                'symbol': signal.symbol,
                'granularity': signal.granularity,
                'direction': signal.signal_value
            })
        else:
            logger.error(f"  Order execution failed: {exec_meta.get('error')}")
            update_post_execution_log(
                self.engine, trade_id, None, None, None, None, 'FAILED'
            )
            execution_result.veto_reason = f"Broker execution failed: {exec_meta.get('error')}"
        
        return execution_result
    
    def run(
        self, 
        granularity: str = DEFAULT_GRANULARITY,
        lookback_minutes: Optional[int] = 60,
        lookback_bars: Optional[int] = None,
        max_signals: int = 1000
    ) -> List[ExecutionResult]:
        """
        Run the full execution pipeline.
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"Layer 4 Execution Pipeline Starting")
        logger.info(f"Granularity: {granularity}")
        logger.info(f"Dry Run: {self.dry_run}")
        logger.info(f"Model: {self.model_artifact.model_type} (run_id={self.model_artifact.run_id})")
        logger.info(f"Threshold: {self.model_artifact.threshold:.4f}")
        logger.info(f"Expected Features: {len(self.model_artifact.feature_columns)}")
        if lookback_minutes:
            logger.info(f"Lookback: {lookback_minutes} minutes")
        elif lookback_bars:
            logger.info(f"Lookback: {lookback_bars} bars")
        else:
            logger.info(f"Lookback: ALL signals")
        logger.info(f"{'='*80}\n")
        
        # Load symbol map
        self.load_symbol_map()
        
        # Load signals with FULL features
        signals_df = load_live_signals_with_features(
            self.engine, 
            granularity,
            lookback_minutes=lookback_minutes,
            lookback_bars=lookback_bars,
            max_signals=max_signals
        )
        
        if signals_df.empty:
            logger.info("No signals to process")
            return []
        
        # Process each signal
        results = []
        for _, signal_row in signals_df.iterrows():
            try:
                result = self.process_signal(signal_row)
                results.append(result)
            except Exception as e:
                logger.exception(f"Failed to process signal: {e}")
                continue
        
        # Summary
        approved = sum(1 for r in results if r.model_decision == TradeDecision.APPROVED)
        executed = sum(1 for r in results if r.broker_order_id is not None)
        
        logger.info(f"\n{'='*80}")
        logger.info(f"Pipeline Complete")
        logger.info(f"Total signals: {len(results)}")
        logger.info(f"ML approved: {approved}")
        logger.info(f"Executed: {executed}")
        logger.info(f"{'='*80}\n")
        
        return results


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Layer 4 Live Execution Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Run with defaults (recent signals)
  %(prog)s --dry-run                          # Simulate without executing
  %(prog)s --granularity H4                   # Process H4 signals only
  %(prog)s --skip-correlation-check           # Skip correlation gate
  %(prog)s --model-manifest models/custom_manifest.json
  %(prog)s --all-signals                      # Process all signals in database
  %(prog)s --lookback-bars 100                # Process last 100 bars
  %(prog)s --max-signals 500                  # Limit to 500 signals max
        """
    )
    
    parser.add_argument(
        '--granularity',
        type=str,
        default=DEFAULT_GRANULARITY,
        choices=SUPPORTED_GATEKEEPER_GRANULARITIES,
        help=f'Time granularity (default: {DEFAULT_GRANULARITY})'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulate pipeline without executing broker orders'
    )
    
    parser.add_argument(
        '--skip-correlation-check',
        action='store_true',
        help='Skip correlation/exposure gate'
    )
    
    parser.add_argument(
        '--model-manifest',
        type=str,
        help='Path to Layer 3 model manifest (default: use stable alias)'
    )
    
    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level'
    )
    
    # Signal loading options
    signal_group = parser.add_mutually_exclusive_group()
    signal_group.add_argument(
        '--all-signals',
        action='store_true',
        help='Process all signals in database (batch mode)'
    )
    signal_group.add_argument(
        '--lookback-bars',
        type=int,
        metavar='N',
        help='Process last N bars (H1=H hours, H4=H*4 hours)'
    )
    signal_group.add_argument(
        '--lookback-minutes',
        type=int,
        metavar='M',
        default=60,
        help='Process signals from last M minutes (default: 60)'
    )
    
    parser.add_argument(
        '--max-signals',
        type=int,
        default=1000,
        help='Maximum number of signals to process (default: 1000)'
    )
    
    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()
    
    # Setup logging
    global logger
    logger = setup_logging(args.log_level)
    
    try:
        # Create database engine
        engine = create_db_engine()
        
        # Load model artifact
        manifest_path = Path(args.model_manifest) if args.model_manifest else None
        use_stable_alias = manifest_path is None
        
        model_artifact = load_model_artifact(
            use_stable_alias=use_stable_alias,
            manifest_path=manifest_path
        )
        
        # Determine lookback parameters
        lookback_minutes = args.lookback_minutes
        lookback_bars = args.lookback_bars
        if args.all_signals:
            lookback_minutes = None
            lookback_bars = None
        
        # Create and run pipeline
        pipeline = ExecutionPipeline(
            engine=engine,
            model_artifact=model_artifact,
            dry_run=args.dry_run,
            skip_correlation=args.skip_correlation_check
        )
        
        results = pipeline.run(
            granularity=args.granularity,
            lookback_minutes=lookback_minutes,
            lookback_bars=lookback_bars,
            max_signals=args.max_signals
        )

        # No-signal windows are operationally valid and should not fail CI/cron.
        if not results:
            logger.info("Layer 4 completed with no eligible signals in the current window")
        return 0
        
    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
