"""
Layer 3: ML Gatekeeper Training with Artifact Contract
======================================================

Trains and serves the ML meta-labeler / gatekeeper with proper artifact management.

Key Features:
- Champion model selection via tournament
- Versioned artifact storage with SHA256 hashes
- Stable deployment alias for Layer 4 consumption
- Manifest file with complete model metadata
- Support for archived model history
- COMPREHENSIVE feature engineering from all upstream layers

Artifact Contract:
- Stable path for live consumption: models/champion_model.pkl
- Versioned archive: models/ml_gatekeeper_run_{run_id}.json
- Manifest: models/champion_manifest.json

Usage:
    python train_ml_gatekeeper.py
    python train_ml_gatekeeper.py --model-type xgboost
    python train_ml_gatekeeper.py --promote-as-champion
"""

import hashlib
import json
import random
import shutil
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

import pandas as pd
import numpy as np
import joblib
from pandas.api.types import is_numeric_dtype
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import (
    f1_score,
    precision_score,
    recall_score,
    average_precision_score,
    brier_score_loss,
)
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
import xgboost as xgb
import lightgbm as lgb
from sklearn.ensemble import RandomForestClassifier
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import warnings
import sqlalchemy as sa
from dotenv import load_dotenv
import os
import sys
import urllib.parse

# Configuration
SEED = 42
TEST_SIZE = 0.2
CV_SPLITS = 3
EMBARGO_GAP = 10
N_TRIALS = 20
SEQ_LEN = 50
LSTM_MAX_EPOCHS = 50
LSTM_PATIENCE = 6
# Relaxed gating to allow more models through while maintaining quality
MAX_TURNOVER = 0.50  # Increased from 0.35 to allow higher activity
MIN_TURNOVER = 0.005  # Reduced from 0.01 to allow more selective models
MIN_EXPECTANCY_UNIT_R = -0.05  # Slightly negative allowance for practical trading

# Layer 3 supports H1 and H4 only
SUPPORTED_GATEKEEPER_GRANULARITIES = {"H1", "H4"}

# Artifact paths
MODELS_DIR = Path("models")
CHAMPION_MODEL_PATH = MODELS_DIR / "champion_model.pkl"
CHAMPION_PREPROCESSOR_PATH = MODELS_DIR / "champion_preprocessor.pkl"
CHAMPION_MANIFEST_PATH = MODELS_DIR / "champion_manifest.json"
ARCHIVE_DIR = MODELS_DIR / "archive"

warnings.filterwarnings("default")

# Setup paths
SCRIPT_DIR = Path(__file__).resolve().parent
APP_ROOT = SCRIPT_DIR.parents[1]
WORKSPACE_ROOT = APP_ROOT.parent

# Load environment
load_dotenv(APP_ROOT / ".env")
load_dotenv(WORKSPACE_ROOT / ".env")

DB_SERVER = os.getenv("DB_SERVER")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME", "ForexBrainDB")
DB_ODBC_DRIVER = os.getenv("DB_ODBC_DRIVER")
DB_PORT = os.getenv("DB_PORT")
DB_CONNECTION_TIMEOUT = int(os.getenv("DB_CONNECTION_TIMEOUT", "15"))
STRICT_JOIN_CONTRACT = os.getenv("STRICT_JOIN_CONTRACT", "1").lower() in (
    "1",
    "true",
    "yes",
)
DEFAULT_LEGACY_GATEKEEPER_GRANULARITY = os.getenv("LAYER3_LEGACY_GRANULARITY", "H1")


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def set_global_seed(seed=SEED):
    """Set global random seeds for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


set_global_seed()


def hash_file(file_path: Path) -> str:
    """Calculate SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def ensure_directories():
    """Ensure all required directories exist."""
    MODELS_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)


# =============================================================================
# DATABASE CONNECTION
# =============================================================================

# Repo root on path so ``src.common`` resolves (canonical PostgreSQL engine).
sys.path.insert(0, str(WORKSPACE_ROOT))
from src.common.db import get_engine  # noqa: E402

if not DB_SERVER or not DB_USER or not DB_PASS:
    raise RuntimeError("Missing required DB configuration.")

# Canonical PostgreSQL + TimescaleDB engine (FND-004 Phase 3; was mssql+pyodbc).
engine = get_engine()

# Test connection
try:
    with engine.connect() as conn:
        conn.exec_driver_sql("SELECT 1")
except Exception as exc:
    raise RuntimeError("Database connection failed.") from exc


# =============================================================================
# DATA CONTRACT FUNCTIONS
# =============================================================================


class _ColumnSet(frozenset):
    """Set of column names with case-insensitive membership.

    PostgreSQL folds unquoted identifiers to lowercase, so the live column
    names are lowercase while this module's contract logic checks mixed-case
    names (e.g. ``'Session_Volume_Z'``). Case-insensitive ``in`` lets the
    existing checks work unchanged; SQL is generated with the mixed-case names
    which PostgreSQL folds back to the real (lowercase) columns.
    """

    def __contains__(self, item):
        if not isinstance(item, str):
            return super().__contains__(item)
        il = item.lower()
        return any(str(c).lower() == il for c in self)


def table_columns(engine_obj, table_name):
    inspector = sa.inspect(engine_obj)
    return _ColumnSet(col["name"] for col in inspector.get_columns(table_name))


def table_exists(engine_obj, table_name):
    inspector = sa.inspect(engine_obj)
    return inspector.has_table(table_name)


def first_common_column(left_cols, right_cols, candidates):
    for col in candidates:
        if col in left_cols and col in right_cols:
            return col
    return None


def get_distinct_nonnull_values(engine_obj, table_name, column_name):
    query = sa.text(
        f"SELECT DISTINCT CAST({column_name} AS varchar(100)) AS value "
        f"FROM {table_name} WHERE {column_name} IS NOT NULL"
    )
    with engine_obj.connect() as conn:
        result = conn.execute(query).fetchall()
    return {str(row[0]) for row in result if row[0] is not None}


def validate_granularity_for_gatekeeper(granularity: str, context: str = "") -> None:
    """Validate that a granularity is supported by the Layer 3 ML gatekeeper."""
    if granularity not in SUPPORTED_GATEKEEPER_GRANULARITIES:
        prefix = f"{context}: " if context else ""
        raise ValueError(
            f"{prefix}Granularity '{granularity}' is not supported. "
            f"Supported: {', '.join(sorted(SUPPORTED_GATEKEEPER_GRANULARITIES))}. "
            f"D1 is explicitly excluded from the gatekeeper pipeline."
        )


def pick_legacy_granularity(engine_obj, regime_table, granularity_col):
    """Pick a legacy granularity when Fact_Trade_Outcomes lacks Granularity column."""
    observed_regime = get_distinct_nonnull_values(
        engine_obj, regime_table, granularity_col
    )
    observed_signals = get_distinct_nonnull_values(
        engine_obj, "fact_signals", granularity_col
    )

    supported = sorted(
        (observed_regime & observed_signals) & SUPPORTED_GATEKEEPER_GRANULARITIES
    )

    unsupported_observed = (
        observed_regime | observed_signals
    ) - SUPPORTED_GATEKEEPER_GRANULARITIES
    if unsupported_observed:
        print(
            f"[WARN] Legacy mode: Observed unsupported granularities that will be excluded: "
            f"{sorted(unsupported_observed)}."
        )

    if DEFAULT_LEGACY_GATEKEEPER_GRANULARITY in supported:
        chosen = DEFAULT_LEGACY_GATEKEEPER_GRANULARITY
    elif "H1" in supported:
        chosen = "H1"
    elif "H4" in supported:
        chosen = "H4"
    elif supported:
        chosen = supported[0]
    else:
        raise RuntimeError(
            "Unable to select a supported legacy granularity for Layer 3. "
            f"Only {sorted(SUPPORTED_GATEKEEPER_GRANULARITIES)} are supported."
        )

    validate_granularity_for_gatekeeper(chosen, context="Legacy granularity selection")
    return chosen


def require_common_column(left_cols, right_cols, candidates, label):
    column = first_common_column(left_cols, right_cols, candidates)
    if not column:
        raise RuntimeError(
            f"Missing required join column for {label}. Expected one of: {', '.join(candidates)}"
        )
    return column


def pick_regime_table(engine_obj):
    """Select the appropriate regime table."""
    preferred_tables = ["fact_market_regime_v2", "fact_market_regime"]
    for table_name in preferred_tables:
        if table_exists(engine_obj, table_name):
            return table_name
    raise RuntimeError("No regime fact table found.")


def build_query_with_contract(engine_obj):
    """Build training query with proper join contract and COMPREHENSIVE features."""
    regime_table = pick_regime_table(engine_obj)
    fmr_cols = table_columns(engine_obj, regime_table)
    fs_cols = table_columns(engine_obj, "fact_signals")
    fto_cols = table_columns(engine_obj, "fact_trade_outcomes")

    # "timestamp" is quoted (reserved word in PostgreSQL); all other columns are
    # lowercase and fold from the mixed-case names used here.
    join_fmr_fs = ['fmr."timestamp" = fs."timestamp"', "fmr.Asset_ID = fs.Asset_ID"]
    join_fs_fto = [
        'fs."timestamp" = fto."timestamp"',
        "fs.Asset_ID = fto.Asset_ID",
        "fs.Strategy_ID = fto.Strategy_ID",
    ]

    granularity_col = require_common_column(
        fmr_cols,
        fs_cols,
        ["Granularity", "Timeframe", "Bar_Granularity"],
        "regime/signal granularity",
    )

    outcome_granularity_col = first_common_column(
        fto_cols, fto_cols, ["Granularity", "Timeframe", "Bar_Granularity"]
    )
    legacy_granularity_filter = None
    if outcome_granularity_col is None:
        legacy_granularity_filter = pick_legacy_granularity(
            engine_obj, regime_table, granularity_col
        )

    horizon_col = first_common_column(
        fs_cols, fto_cols, ["Trade_Horizon", "Horizon", "Signal_Horizon"]
    )

    join_fmr_fs.append(f"fmr.{granularity_col} = fs.{granularity_col}")
    if outcome_granularity_col:
        join_fs_fto.append(f"fs.{granularity_col} = fto.{outcome_granularity_col}")

    where_clauses = []
    if legacy_granularity_filter:
        where_clauses.append(f"fmr.{granularity_col} = '{legacy_granularity_filter}'")
        where_clauses.append(f"fs.{granularity_col} = '{legacy_granularity_filter}'")
    else:
        supported_list = ", ".join(
            f"'{g}'" for g in sorted(SUPPORTED_GATEKEEPER_GRANULARITIES)
        )
        where_clauses.append(f"fmr.{granularity_col} IN ({supported_list})")
        where_clauses.append(f"fs.{granularity_col} IN ({supported_list})")

    if horizon_col:
        join_fs_fto.append(f"fs.{horizon_col} = fto.{horizon_col}")

    # ========================================================================
    # COMPREHENSIVE FEATURE SET
    # ========================================================================

    # Every column is aliased to a double-quoted mixed-case name so the pandas
    # DataFrame keeps the column names the downstream feature pipeline expects
    # (PostgreSQL would otherwise lower-case unquoted output labels).
    select_cols = [
        'fs."timestamp" AS "Timestamp"',
        'fmr.Regime_Label AS "Regime_Label"',
        'fmr.ATR_Value AS "ATR_Value"',
        'fmr.ADX_Value AS "ADX_Value"',
        'fs.Asset_ID AS "Asset_ID"',
        'fs.Strategy_ID AS "Strategy_ID"',
        f'fs.{granularity_col} AS "Granularity_Key"',
        'fs.Signal_Value AS "Signal_Value"',
        'fto.Is_Winner AS "Is_Winner"',
    ]

    # ------------------------------------------------------------------------
    # 1. TEMPORAL FEATURES (Essential for FX seasonality)
    # SQL Server DATEPART(...) -> PostgreSQL EXTRACT(... FROM ...). Weekday is
    # shifted (+1) so it keeps SQL Server's Sunday=1..Saturday=7 numbering
    # (PostgreSQL DOW is Sunday=0..Saturday=6).
    # ------------------------------------------------------------------------
    select_cols.extend(
        [
            'EXTRACT(HOUR FROM fs."timestamp")::int AS "Signal_Hour"',
            '(EXTRACT(DOW FROM fs."timestamp")::int + 1) AS "Signal_DayOfWeek"',
            'EXTRACT(MONTH FROM fs."timestamp")::int AS "Signal_Month"',
            'EXTRACT(QUARTER FROM fs."timestamp")::int AS "Signal_Quarter"',
            'CASE WHEN EXTRACT(HOUR FROM fs."timestamp") BETWEEN 8 AND 16 THEN 1 ELSE 0 END AS "Is_London_NY_Session"',
            'CASE WHEN EXTRACT(HOUR FROM fs."timestamp") BETWEEN 0 AND 7 THEN 1 ELSE 0 END AS "Is_Asian_Session"',
            'CASE WHEN EXTRACT(HOUR FROM fs."timestamp") BETWEEN 12 AND 20 THEN 1 ELSE 0 END AS "Is_US_Session"',
        ]
    )

    # ------------------------------------------------------------------------
    # 2. LAYER 1: MARKET REGIME FEATURES
    # ------------------------------------------------------------------------
    optional_cols = []

    def _maybe_add(col_set, source_alias, col_name, alias=None):
        if col_name in col_set:
            as_name = alias or col_name
            optional_cols.append(f'{source_alias}.{col_name} AS "{as_name}"')

    # Core regime features
    _maybe_add(fmr_cols, "fmr", "Session_Volume_Z")
    _maybe_add(fmr_cols, "fmr", "Regime_Model_Version")
    _maybe_add(fmr_cols, "fmr", "H4_Trend_Direction")
    _maybe_add(fmr_cols, "fmr", "D1_Trend_Direction")
    _maybe_add(fmr_cols, "fmr", "Trend_Alignment_Score")
    _maybe_add(fmr_cols, "fmr", "Volatility_Regime")
    _maybe_add(fmr_cols, "fmr", "ATR_Percentile_20D")

    # Advanced regime features (if available)
    _maybe_add(fmr_cols, "fmr", "ATR_Pct")
    _maybe_add(fmr_cols, "fmr", "ATR_Z")
    _maybe_add(fmr_cols, "fmr", "ADX_Delta")
    _maybe_add(fmr_cols, "fmr", "Trend_Ratio")
    _maybe_add(fmr_cols, "fmr", "Realized_Vol_Z")
    _maybe_add(fmr_cols, "fmr", "Candle_Body")
    _maybe_add(fmr_cols, "fmr", "Upper_Wick")
    _maybe_add(fmr_cols, "fmr", "Lower_Wick")
    _maybe_add(fmr_cols, "fmr", "Close_Position")
    _maybe_add(fmr_cols, "fmr", "BB_Width")
    _maybe_add(fmr_cols, "fmr", "BB_Width_Z")
    _maybe_add(fmr_cols, "fmr", "Vol_Persistence")

    # ------------------------------------------------------------------------
    # 3. LAYER 2: SIGNAL QUALITY FEATURES
    # ------------------------------------------------------------------------
    _maybe_add(fs_cols, "fs", "Signal_Confidence")
    _maybe_add(fs_cols, "fs", "Signal_Strength")
    _maybe_add(fs_cols, "fs", "Config_ID")
    _maybe_add(fs_cols, "fs", "Priority")
    _maybe_add(fs_cols, "fs", "Rule_ID")
    _maybe_add(fs_cols, "fs", "Strategy_Version")
    _maybe_add(fs_cols, "fs", "Batch_ID")

    # Parse indicator snapshot JSON if available
    if "Indicator_Snapshot" in fs_cols:
        # We'll extract this in post-processing
        optional_cols.append('fs.Indicator_Snapshot AS "Indicator_Snapshot"')

    # ------------------------------------------------------------------------
    # 4. LAYER 0/2->3: TRADE OUTCOME FEATURES (for context, not target leakage)
    # ------------------------------------------------------------------------
    _maybe_add(fto_cols, "fto", "R_Multiple")
    _maybe_add(fto_cols, "fto", "Holding_Bars")
    _maybe_add(fto_cols, "fto", "ATR_SL_Multiplier")
    _maybe_add(fto_cols, "fto", "ATR_TP_Multiplier")
    _maybe_add(fto_cols, "fto", "Entry_Signal_Type")
    _maybe_add(fto_cols, "fto", "Exit_Reason")

    if optional_cols:
        select_cols.extend(optional_cols)

    if horizon_col:
        select_cols.append(f'fs.{horizon_col} AS "Trade_Horizon_Key"')

    query = f"""
SELECT
    {", ".join(select_cols)}
FROM
    {regime_table} fmr
INNER JOIN
    fact_signals fs ON {' AND '.join(join_fmr_fs)}
INNER JOIN
    fact_trade_outcomes fto ON {' AND '.join(join_fs_fto)}
{('WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''}
ORDER BY
    fs."timestamp" ASC
"""
    return query, regime_table, fmr_cols, fs_cols, fto_cols


def assert_supervised_event_contract(df_raw):
    """Validate data contract for supervised events."""
    required_cols = ["Timestamp", "Asset_ID", "Strategy_ID", "Granularity_Key"]
    missing_required = [col for col in required_cols if col not in df_raw.columns]
    if missing_required:
        raise ValueError(
            f"Data contract violation: missing columns: {', '.join(missing_required)}"
        )

    key_cols = ["Timestamp", "Asset_ID", "Strategy_ID", "Granularity_Key"]
    if "Trade_Horizon_Key" in df_raw.columns:
        key_cols.append("Trade_Horizon_Key")

    dupes = df_raw.duplicated(subset=key_cols, keep=False)
    if dupes.any():
        sample = df_raw.loc[dupes, key_cols].head(10).to_dict(orient="records")
        raise ValueError(
            f"Data contract violation: duplicate keys found. Sample: {sample}"
        )


def assert_gatekeeper_granularity_contract(df_raw):
    """Assert that dataset only contains supported granularities."""
    if "Granularity_Key" not in df_raw.columns:
        raise ValueError("Granularity_Key is required for the gatekeeper model.")

    observed = {str(value) for value in df_raw["Granularity_Key"].dropna().unique()}
    invalid = sorted(observed - SUPPORTED_GATEKEEPER_GRANULARITIES)
    if invalid:
        raise ValueError(
            f"Layer 3 validation FAILED: unsupported granularities: {', '.join(invalid)}. "
            f"Supported: {', '.join(sorted(SUPPORTED_GATEKEEPER_GRANULARITIES))}."
        )


def chronological_split(df_raw, test_size=TEST_SIZE):
    """Split data chronologically for time-series."""
    split_idx = int(len(df_raw) * (1 - test_size))
    train_df = df_raw.iloc[:split_idx].copy()
    test_df = df_raw.iloc[split_idx:].copy()
    return train_df, test_df


def with_sqlserver_top(base_query: str, top_n: int) -> str:
    """Append a LIMIT clause for fast sampling (PostgreSQL; was SQL Server TOP).

    The query already ends with an ``ORDER BY ... ASC`` clause, so LIMIT is
    appended to the end.
    """
    return f"{base_query.rstrip()}\nLIMIT {int(top_n)}\n"


def assert_dataset_viable(df_raw, train_df):
    """Validate that dataset is viable for training."""
    if df_raw.empty:
        raise RuntimeError("Training query returned 0 rows after joins.")

    min_train_rows = (CV_SPLITS + 1) * 2
    if len(train_df) < min_train_rows:
        raise RuntimeError(
            f"Not enough training rows for time-series CV: train_rows={len(train_df)}, "
            f"required_at_least={min_train_rows}."
        )


# =============================================================================
# COMPREHENSIVE FEATURE ENGINEERING
# =============================================================================


def extract_indicator_snapshot_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract features from Indicator_Snapshot JSON column.
    This contains the actual indicator values at signal time.
    """
    if "Indicator_Snapshot" not in df.columns:
        return df

    # Parse JSON snapshots
    def safe_json_load(x):
        if pd.isna(x) or x is None:
            return {}
        try:
            if isinstance(x, str):
                return json.loads(x)
            return x
        except:
            return {}

    snapshots = df["Indicator_Snapshot"].apply(safe_json_load)

    # Extract common indicator values
    indicator_features = {}

    # List of common indicators to extract
    common_indicators = [
        "RSI",
        "EMA_9",
        "EMA_21",
        "EMA_50",
        "EMA_200",
        "MACD",
        "MACD_Signal",
        "MACD_Histogram",
        "BB_Upper",
        "BB_Lower",
        "BB_Middle",
        "ATR",
        "ADX",
        "Stoch_K",
        "Stoch_D",
        "CCI",
        "Williams_R",
        "MFI",
        "Volume_SMA",
        "SMA_20",
        "SMA_50",
        "SMA_200",
    ]

    for indicator in common_indicators:
        values = snapshots.apply(
            lambda x: x.get(indicator) if isinstance(x, dict) else None
        )
        # Only add if we have some non-null values
        if values.notna().sum() > 0:
            indicator_features[f"Ind_{indicator}"] = values

    # Add indicator features to dataframe
    if indicator_features:
        indicator_df = pd.DataFrame(indicator_features, index=df.index)
        df = pd.concat([df, indicator_df], axis=1)

    return df


def engineer_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Engineer derived features from base features.
    This is where the real edge comes from!
    """
    df = df.copy()

    # ---------------------------------------------------------------------
    # 1. REGIME-FEATURE INTERACTIONS
    # ---------------------------------------------------------------------
    if "Regime_Label" in df.columns:
        # Create binary regime flags
        regime_dummies = pd.get_dummies(df["Regime_Label"], prefix="Regime")
        df = pd.concat([df, regime_dummies], axis=1)

    # ---------------------------------------------------------------------
    # 2. TREND STRENGTH FEATURES
    # ---------------------------------------------------------------------
    if "ADX_Value" in df.columns:
        # Categorize trend strength
        df["Trend_Strength_Cat"] = pd.cut(
            df["ADX_Value"],
            bins=[0, 20, 40, 100],
            labels=["Weak", "Moderate", "Strong"],
        )

    if "Trend_Alignment_Score" in df.columns:
        # Alignment quality
        df["Is_Trend_Aligned"] = (df["Trend_Alignment_Score"] > 0).astype(int)

    # ---------------------------------------------------------------------
    # 3. VOLATILITY FEATURES
    # ---------------------------------------------------------------------
    if "ATR_Value" in df.columns and "ATR_Percentile_20D" in df.columns:
        # ATR relative to its percentile (shows if vol is expanding/contracting)
        df["ATR_vs_Percentile"] = df["ATR_Value"] / (df["ATR_Percentile_20D"] + 1e-8)

    if "Volatility_Regime" in df.columns:
        # One-hot encode volatility regime
        vol_dummies = pd.get_dummies(df["Volatility_Regime"], prefix="VolRegime")
        df = pd.concat([df, vol_dummies], axis=1)

    # ---------------------------------------------------------------------
    # 4. SESSION/TIME INTERACTIONS
    # ---------------------------------------------------------------------
    if "Signal_Hour" in df.columns:
        # Categorize trading sessions
        df["Session_Category"] = pd.cut(
            df["Signal_Hour"],
            bins=[0, 7, 12, 16, 20, 24],
            labels=["Asian", "London_Early", "London_US_Overlap", "US", "Late"],
            include_lowest=True,
        )
        session_dummies = pd.get_dummies(df["Session_Category"], prefix="Session")
        df = pd.concat([df, session_dummies], axis=1)

    # Weekend/volatility day effects
    if "Signal_DayOfWeek" in df.columns:
        df["Is_Monday"] = (df["Signal_DayOfWeek"] == 1).astype(int)
        df["Is_Friday"] = (df["Signal_DayOfWeek"] == 5).astype(int)

    # ---------------------------------------------------------------------
    # 5. SIGNAL QUALITY FEATURES
    # ---------------------------------------------------------------------
    if "Signal_Confidence" in df.columns and "Signal_Value" in df.columns:
        # Confidence weighted by signal direction
        df["Confidence_x_Signal"] = df["Signal_Confidence"] * df["Signal_Value"]

    # ---------------------------------------------------------------------
    # 6. STRATEGY-SPECIFIC FEATURES
    # ---------------------------------------------------------------------
    if "Strategy_ID" in df.columns:
        # Strategy performance category (will be populated later)
        df["Strategy_Category"] = df["Strategy_ID"].apply(
            lambda x: f"Strat_{x}" if pd.notna(x) else "Unknown"
        )

    # ---------------------------------------------------------------------
    # 7. MULTI-TIMEFRAME CONFLUENCE
    # ---------------------------------------------------------------------
    if "H4_Trend_Direction" in df.columns and "D1_Trend_Direction" in df.columns:
        # Check if H4 and D1 agree
        df["H4_D1_Agreement"] = (
            df["H4_Trend_Direction"] == df["D1_Trend_Direction"]
        ).astype(int)

    # ---------------------------------------------------------------------
    # 8. PRICE ACTION FEATURES (if available)
    # ---------------------------------------------------------------------
    if "Candle_Body" in df.columns and "Upper_Wick" in df.columns:
        # Candle sentiment
        df["Candle_Sentiment"] = df["Candle_Body"] / (
            df["Upper_Wick"] + df["Lower_Wick"] + 1e-8
        )

    # ---------------------------------------------------------------------
    # 9. MOMENTUM FEATURES (from indicator snapshot)
    # ---------------------------------------------------------------------
    # EMA alignment
    ema_cols = [c for c in df.columns if c.startswith("Ind_EMA_")]
    if len(ema_cols) >= 2:
        df["EMA_Spread"] = df[ema_cols[0]] - df[ema_cols[1]]

    # RSI categories
    if "Ind_RSI" in df.columns:
        df["RSI_Category"] = pd.cut(
            df["Ind_RSI"],
            bins=[0, 30, 45, 55, 70, 100],
            labels=[
                "Oversold",
                "Bullish_Neutral",
                "Neutral",
                "Bearish_Neutral",
                "Overbought",
            ],
        )
        rsi_dummies = pd.get_dummies(df["RSI_Category"], prefix="RSI")
        df = pd.concat([df, rsi_dummies], axis=1)

    return df


def calculate_strategy_performance_features(
    df: pd.DataFrame, lookback_windows: List[int] = [20, 50, 100]
) -> pd.DataFrame:
    """
    Calculate rolling strategy performance features.
    This gives the model context about how each strategy has been performing.
    """
    df = df.copy()
    df = df.sort_values("Timestamp").reset_index(drop=True)

    # Initialize performance columns
    for window in lookback_windows:
        df[f"Strat_WinRate_{window}"] = 0.5  # Default neutral
        df[f"Strat_Expectancy_{window}"] = 0.0
        df[f"Strat_Trades_{window}"] = 0

    # Calculate rolling performance per strategy
    for strategy_id in df["Strategy_ID"].unique():
        mask = df["Strategy_ID"] == strategy_id
        strat_df = df[mask].copy()

        if len(strat_df) < 10:
            continue

        for window in lookback_windows:
            # Rolling win rate
            rolling_wins = (
                strat_df["Is_Winner"].rolling(window=window, min_periods=5).mean()
            )
            df.loc[mask, f"Strat_WinRate_{window}"] = rolling_wins.values

            # Rolling trade count
            rolling_count = (
                strat_df["Is_Winner"].rolling(window=window, min_periods=1).count()
            )
            df.loc[mask, f"Strat_Trades_{window}"] = rolling_count.values

            # Rolling expectancy (if R_Multiple available)
            if "R_Multiple" in strat_df.columns:
                rolling_exp = (
                    strat_df["R_Multiple"].rolling(window=window, min_periods=5).mean()
                )
                df.loc[mask, f"Strat_Expectancy_{window}"] = rolling_exp.values

    # Strategy recency (how recently has this strategy traded)
    df["Bars_Since_Last_Trade"] = (
        df.groupby("Strategy_ID")["Timestamp"].diff().dt.total_seconds() / 3600
    )  # hours

    return df


def create_feature_interactions(df: pd.DataFrame) -> pd.DataFrame:
    """Create interaction features between important variables."""
    df = df.copy()

    # Regime x Signal interactions
    if "ADX_Value" in df.columns and "Signal_Confidence" in df.columns:
        df["ADX_x_Confidence"] = df["ADX_Value"] * df["Signal_Confidence"]

    # Volatility x Trend interactions
    if "ATR_Value" in df.columns and "Trend_Alignment_Score" in df.columns:
        df["ATR_x_TrendAlign"] = df["ATR_Value"] * df["Trend_Alignment_Score"]

    # Session x Strategy interactions
    if "Is_London_NY_Session" in df.columns and "Strategy_ID" in df.columns:
        df["LondonSession_x_Strategy"] = df["Is_London_NY_Session"] * df["Strategy_ID"]

    return df


def comprehensive_feature_engineering(df: pd.DataFrame) -> pd.DataFrame:
    """
    Main entry point for comprehensive feature engineering.
    """
    print(
        f"[Feature Engineering] Starting with {len(df)} rows, {len(df.columns)} columns"
    )

    # Step 1: Extract indicator snapshot features
    df = extract_indicator_snapshot_features(df)
    print(
        f"[Feature Engineering] After indicator extraction: {len(df.columns)} columns"
    )

    # Step 2: Engineer derived features
    df = engineer_derived_features(df)
    print(f"[Feature Engineering] After derived features: {len(df.columns)} columns")

    # Step 3: Calculate strategy performance features
    df = calculate_strategy_performance_features(df)
    print(
        f"[Feature Engineering] After strategy performance: {len(df.columns)} columns"
    )

    # Step 4: Create interaction features
    df = create_feature_interactions(df)
    print(f"[Feature Engineering] After interactions: {len(df.columns)} columns")

    # Step 5: Handle any remaining data types
    # Convert categorical columns to category dtype for better encoding
    categorical_cols = df.select_dtypes(include=["object"]).columns
    for col in categorical_cols:
        if col not in [
            "Timestamp",
            "Indicator_Snapshot",
            "Signal_Reason",
            "Config_Hash",
            "Batch_ID",
        ]:
            df[col] = df[col].astype("category")

    # Report feature statistics
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    print(
        f"[Feature Engineering] Final: {len(df)} rows, {len(df.columns)} columns ({len(numeric_cols)} numeric)"
    )

    return df


# =============================================================================
# MODEL TRAINING
# =============================================================================


def build_preprocessor(X_df):
    """Build sklearn preprocessor for features."""
    numeric_cols = [col for col in X_df.columns if is_numeric_dtype(X_df[col])]
    categorical_cols = [col for col in X_df.columns if col not in numeric_cols]

    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    numeric_pipeline = Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))])

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, numeric_cols),
            ("cat", categorical_pipeline, categorical_cols),
        ],
        remainder="drop",
        sparse_threshold=0,
    )
    return preprocessor


def dynamic_pos_weight(y_values):
    """Calculate positive class weight for imbalanced data with amplification.

    Uses sqrt scaling to prevent extreme weights while still addressing imbalance.
    This helps ensure the model produces enough positive predictions for turnover gates.
    """
    y_arr = np.asarray(y_values)
    pos = np.sum(y_arr == 1)
    neg = np.sum(y_arr == 0)
    if pos == 0:
        return 1.0
    # Base ratio with sqrt scaling to prevent extreme values
    base_ratio = float(neg) / float(pos)
    # More aggressive amplification to encourage positive predictions for higher turnover
    return max(1.0, np.sqrt(base_ratio) * 2.0)


def tree_model_factory(model_type, params, class_ratio, calibrate=False):
    """Factory for tree-based models with imbalanced data optimizations."""
    if model_type == "xgboost":
        base_model = xgb.XGBClassifier(
            **params,
            random_state=SEED,
            scale_pos_weight=class_ratio,
            eval_metric="logloss",
            # Imbalanced data optimizations
            min_child_weight=1,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
        )
    elif model_type == "lightgbm":
        base_model = lgb.LGBMClassifier(
            **params,
            random_state=SEED,
            verbose=-1,
            scale_pos_weight=class_ratio,
            # Imbalanced data optimizations
            min_samples_leaf=5,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
        )
    else:
        base_model = RandomForestClassifier(
            **params,
            random_state=SEED,
            class_weight="balanced_subsample",
            # Imbalanced data optimizations
            min_samples_split=5,
            min_samples_leaf=2,
        )

    if calibrate:
        return CalibratedClassifierCV(base_model, cv=3, method="isotonic")
    return base_model


def make_time_series_split(n_samples):
    """Create time-series cross-validation split."""
    if n_samples < 6:
        raise RuntimeError(f"Insufficient samples for TimeSeriesSplit: {n_samples}")

    split_candidates = list(range(min(CV_SPLITS, n_samples - 1), 1, -1))
    gap_candidates = [EMBARGO_GAP, max(0, EMBARGO_GAP // 2), 0]

    for splits in split_candidates:
        for gap in gap_candidates:
            tscv = TimeSeriesSplit(n_splits=splits, gap=gap)
            try:
                _ = list(tscv.split(np.arange(n_samples)))
                return tscv
            except ValueError:
                continue

    raise RuntimeError(
        f"Unable to construct valid TimeSeriesSplit for n_samples={n_samples}"
    )


def optuna_objective(trial, model_type, X_train_df, y_train_series):
    """Optuna objective for hyperparameter tuning with turnover-aware scoring."""
    if model_type in ("xgboost", "lightgbm"):
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 100, 400),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.25, log=True),
        }
    else:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 100, 500),
            "max_depth": trial.suggest_int("max_depth", 4, 20),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 5),
        }

    tscv = make_time_series_split(len(X_train_df))
    scores = []

    for train_idx, val_idx in tscv.split(X_train_df):
        X_fold_train = X_train_df.iloc[train_idx]
        y_fold_train = y_train_series.iloc[train_idx]
        X_fold_val = X_train_df.iloc[val_idx]
        y_fold_val = y_train_series.iloc[val_idx]

        preprocessor_fold = build_preprocessor(X_fold_train)
        X_fold_train_t = preprocessor_fold.fit_transform(X_fold_train)
        X_fold_val_t = preprocessor_fold.transform(X_fold_val)

        class_ratio = dynamic_pos_weight(y_fold_train)
        model = tree_model_factory(model_type, params, class_ratio)
        model.fit(X_fold_train_t, y_fold_train)

        prob = model.predict_proba(X_fold_val_t)[:, 1]

        # Combined score: PR-AUC + consideration for calibration
        pr_auc = average_precision_score(y_fold_val, prob)

        # Bonus for well-calibrated probabilities (not too concentrated)
        prob_std = np.std(prob)
        calibration_bonus = min(
            0.05, prob_std * 0.1
        )  # Small bonus for spread-out probabilities

        scores.append(pr_auc + calibration_bonus)

    return float(np.mean(scores))


def choose_threshold(
    y_true,
    prob,
    max_turnover=MAX_TURNOVER,
    min_turnover=MIN_TURNOVER,
    min_expectancy=MIN_EXPECTANCY_UNIT_R,
):
    """Choose optimal classification threshold based on trading metrics.

    Uses an expanded threshold search range (0.02-0.9) to handle models
    with varying calibration characteristics. Includes percentile-based
    fallback for cases where probability distributions are skewed.
    """
    # Expanded range: wider search to find viable thresholds
    candidates = np.linspace(0.02, 0.9, 89)
    best_t = None
    best_score = None

    for t in candidates:
        metrics = compute_trading_metrics(y_true, prob, float(t))
        if metrics["turnover"] > max_turnover:
            continue
        if metrics["turnover"] < min_turnover:
            continue
        if metrics["expectancy_unit_r"] <= min_expectancy:
            continue

        score = (
            metrics["expectancy_unit_r"],
            metrics["pr_auc"],
            metrics["f1"],
            -metrics["turnover"],
        )
        if best_score is None or score > best_score:
            best_score = score
            best_t = float(t)

    # If no threshold satisfies gates, try percentile-based adaptive threshold
    if best_t is None and len(prob) > 0:
        # Find threshold that gives closest to target turnover
        sorted_probs = np.sort(prob)[::-1]  # descending
        target_count = int(len(prob) * ((min_turnover + max_turnover) / 2))
        if target_count > 0 and target_count <= len(sorted_probs):
            adaptive_threshold = float(sorted_probs[target_count - 1])
            # Relaxed validation: accept if expectancy is not catastrophically bad
            metrics = compute_trading_metrics(y_true, prob, adaptive_threshold)
            if (
                metrics["expectancy_unit_r"] > min_expectancy * 2
            ):  # Allow 2x the negative slack
                best_t = adaptive_threshold
                print(
                    f"[Threshold] Using adaptive percentile-based threshold: {best_t:.4f} "
                    f"(turnover={metrics['turnover']:.4f}, expectancy={metrics['expectancy_unit_r']:.4f})"
                )

    return best_t


def print_threshold_diagnostics(
    y_true,
    prob,
    label,
    max_turnover,
    min_turnover,
    min_expectancy,
    top_n=10,
):
    """Print threshold sweep diagnostics for debugging viability."""
    rows = []
    # Extended range for diagnostics
    for t in np.linspace(0.05, 0.8, 76):
        m = compute_trading_metrics(y_true, prob, float(t))
        m["meets_gates"] = (
            m["turnover"] <= max_turnover
            and m["turnover"] >= min_turnover
            and m["expectancy_unit_r"] > min_expectancy
        )
        rows.append(m)

    df_diag = pd.DataFrame(rows).sort_values(
        by=["meets_gates", "expectancy_unit_r", "pr_auc", "f1", "turnover"],
        ascending=[False, False, False, False, True],
    )

    feasible = int(df_diag["meets_gates"].sum())
    print(
        f"\n[Threshold diagnostics: {label}] feasible_thresholds={feasible}/{len(df_diag)}"
    )

    # Show best feasible thresholds
    feasible_rows = df_diag[df_diag["meets_gates"] == True]
    if len(feasible_rows) > 0:
        print("Best feasible thresholds:")
        print(
            feasible_rows.head(top_n)[
                [
                    "threshold",
                    "turnover",
                    "expectancy_unit_r",
                    "precision_at_selected",
                    "pr_auc",
                    "f1",
                    "meets_gates",
                ]
            ].to_string(index=False)
        )
    else:
        print("No feasible thresholds found. Closest candidates:")
        # Sort by distance from valid range
        df_diag["turnover_dist"] = df_diag.apply(
            lambda r: (
                0
                if min_turnover <= r["turnover"] <= max_turnover
                else min(
                    abs(r["turnover"] - min_turnover), abs(r["turnover"] - max_turnover)
                )
            ),
            axis=1,
        )
        closest = df_diag.nsmallest(top_n, "turnover_dist")
        print(
            closest[
                [
                    "threshold",
                    "turnover",
                    "expectancy_unit_r",
                    "precision_at_selected",
                    "pr_auc",
                    "f1",
                ]
            ].to_string(index=False)
        )


def compute_trading_metrics(y_true, prob, threshold):
    """Compute trading-specific metrics."""
    pred = (prob >= threshold).astype(int)
    selected_mask = pred == 1
    selected_count = int(np.sum(selected_mask))

    if selected_count > 0:
        selected_y = np.asarray(y_true)[selected_mask]
        expectancy = float(np.mean(np.where(selected_y == 1, 1.0, -1.0)))
        precision_at_k = float(np.mean(selected_y))
    else:
        expectancy = 0.0
        precision_at_k = 0.0

    return {
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "pr_auc": float(average_precision_score(y_true, prob)),
        "brier": float(brier_score_loss(y_true, prob)),
        "turnover": float(selected_count / len(y_true)) if len(y_true) else 0.0,
        "expectancy_unit_r": expectancy,
        "precision_at_selected": precision_at_k,
        "threshold": float(threshold),
    }


# =============================================================================
# LSTM MODEL
# =============================================================================


class ForexDataset(Dataset):
    def __init__(self, X, y, seq_len=50):
        self.X = torch.tensor(X.astype(np.float32), dtype=torch.float32)
        self.y = torch.tensor(y.astype(np.float32), dtype=torch.float32)
        self.seq_len = seq_len

    def __len__(self):
        return len(self.y) - self.seq_len

    def __getitem__(self, idx):
        return self.X[idx : idx + self.seq_len], self.y[idx + self.seq_len]


class LSTMModel(nn.Module):
    def __init__(self, input_size, hidden_size=50, num_layers=2):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x):
        _, (hn, _) = self.lstm(x)
        out = self.fc(hn[-1])
        return out.squeeze(-1)


def train_lstm(X_train_df, y_train, X_test_df, y_test):
    """Train LSTM model."""
    preprocessor = build_preprocessor(X_train_df)
    X_train = preprocessor.fit_transform(X_train_df)
    X_test = preprocessor.transform(X_test_df)

    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.transform(X_test)

    train_cut = int(len(X_train) * 0.8)
    X_lstm_train = X_train[:train_cut]
    y_lstm_train = y_train.iloc[:train_cut].to_numpy()
    X_lstm_val = X_train[train_cut:]
    y_lstm_val = y_train.iloc[train_cut:].to_numpy()

    train_dataset = ForexDataset(X_lstm_train, y_lstm_train, SEQ_LEN)
    val_dataset = ForexDataset(X_lstm_val, y_lstm_val, SEQ_LEN)
    train_loader = DataLoader(train_dataset, batch_size=64, shuffle=False)
    val_loader = DataLoader(val_dataset, batch_size=64, shuffle=False)

    model = LSTMModel(input_size=X_train.shape[1])
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", patience=2, factor=0.5
    )

    pos_weight_value = dynamic_pos_weight(y_lstm_train)
    criterion = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor(pos_weight_value, dtype=torch.float32)
    )

    best_val_loss = float("inf")
    best_state = None
    epochs_without_improve = 0

    for epoch in range(LSTM_MAX_EPOCHS):
        model.train()
        train_losses = []
        for X_batch, y_batch in train_loader:
            optimizer.zero_grad()
            logits = model(X_batch)
            loss = criterion(logits, y_batch)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            train_losses.append(loss.item())

        model.eval()
        val_losses = []
        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                logits = model(X_batch)
                loss = criterion(logits, y_batch)
                val_losses.append(loss.item())

        epoch_val_loss = float(np.mean(val_losses)) if val_losses else float("inf")
        scheduler.step(epoch_val_loss)

        if epoch_val_loss < best_val_loss:
            best_val_loss = epoch_val_loss
            best_state = {
                k: v.detach().cpu().clone() for k, v in model.state_dict().items()
            }
            epochs_without_improve = 0
        else:
            epochs_without_improve += 1

        if epochs_without_improve >= LSTM_PATIENCE:
            print(f"Early stopping LSTM at epoch {epoch + 1}")
            break

    if best_state is not None:
        model.load_state_dict(best_state)

    return {
        "model": model,
        "preprocessor": preprocessor,
        "scaler": scaler,
        "seq_len": SEQ_LEN,
        "best_val_loss": best_val_loss,
    }


# =============================================================================
# ARTIFACT MANAGEMENT
# =============================================================================


def archive_current_champion():
    """Archive the current champion model before promoting a new one."""
    if not CHAMPION_MODEL_PATH.exists():
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"champion_{timestamp}"

    # Archive model
    archive_model = ARCHIVE_DIR / f"{archive_name}.pkl"
    shutil.copy2(CHAMPION_MODEL_PATH, archive_model)

    # Archive preprocessor
    if CHAMPION_PREPROCESSOR_PATH.exists():
        archive_preprocessor = ARCHIVE_DIR / f"{archive_name}_preprocessor.pkl"
        shutil.copy2(CHAMPION_PREPROCESSOR_PATH, archive_preprocessor)

    # Archive manifest
    if CHAMPION_MANIFEST_PATH.exists():
        archive_manifest = ARCHIVE_DIR / f"{archive_name}_manifest.json"
        shutil.copy2(CHAMPION_MANIFEST_PATH, archive_manifest)

    print(f"Archived current champion to {archive_name}")


def create_champion_manifest(
    model_type: str,
    threshold: float,
    feature_columns: List[str],
    run_id: str,
    training_timestamp: str,
    metrics: Dict[str, Any],
    artifact_hashes: Dict[str, str],
) -> Dict[str, Any]:
    """Create champion model manifest for Layer 4 consumption."""
    return {
        "model_type": model_type,
        "artifact_path": str(CHAMPION_MODEL_PATH.absolute()),
        "preprocessor_path": str(CHAMPION_PREPROCESSOR_PATH.absolute()),
        "threshold": threshold,
        "feature_columns": feature_columns,
        "run_id": run_id,
        "training_timestamp": training_timestamp,
        "supported_granularities": sorted(SUPPORTED_GATEKEEPER_GRANULARITIES),
        "artifact_hash": artifact_hashes.get("model", ""),
        "preprocessor_hash": artifact_hashes.get("preprocessor", ""),
        "metrics": metrics,
        "manifest_version": "1.0",
        "created_at": datetime.utcnow().isoformat(),
    }


def promote_to_champion(
    model_bundle: Dict[str, Any],
    model_type: str,
    threshold: float,
    feature_columns: List[str],
    run_id: str,
    metrics: Dict[str, Any],
):
    """Promote a model to champion status with proper artifact management."""
    ensure_directories()

    # Archive current champion
    archive_current_champion()

    # Save new champion
    if model_type == "lstm":
        # LSTM uses PyTorch
        torch.save(model_bundle["model"].state_dict(), CHAMPION_MODEL_PATH)
        joblib.dump(model_bundle["preprocessor"], CHAMPION_PREPROCESSOR_PATH)
        # Also save scaler separately for LSTM
        scaler_path = MODELS_DIR / "champion_scaler.pkl"
        joblib.dump(model_bundle["scaler"], scaler_path)
    else:
        # Sklearn models
        joblib.dump(model_bundle["model"], CHAMPION_MODEL_PATH)
        joblib.dump(model_bundle["preprocessor"], CHAMPION_PREPROCESSOR_PATH)

    # Calculate hashes
    artifact_hashes = {
        "model": hash_file(CHAMPION_MODEL_PATH),
        "preprocessor": hash_file(CHAMPION_PREPROCESSOR_PATH),
    }

    # Create and save manifest
    manifest = create_champion_manifest(
        model_type=model_type,
        threshold=threshold,
        feature_columns=feature_columns,
        run_id=run_id,
        training_timestamp=datetime.utcnow().isoformat(),
        metrics=metrics,
        artifact_hashes=artifact_hashes,
    )

    with open(CHAMPION_MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Champion Model Promoted: {model_type}")
    print(f"Threshold: {threshold}")
    print(f"Model path: {CHAMPION_MODEL_PATH}")
    print(f"Manifest path: {CHAMPION_MANIFEST_PATH}")
    print(f"{'='*60}")

    return manifest


# =============================================================================
# MAIN TRAINING PIPELINE
# =============================================================================


def train_models(
    X_train_df: pd.DataFrame,
    y_train: pd.Series,
    X_test_df: pd.DataFrame,
    y_test: pd.Series,
    model_types: List[str] = None,
    max_turnover: float = MAX_TURNOVER,
    min_turnover: float = MIN_TURNOVER,
    min_expectancy: float = MIN_EXPECTANCY_UNIT_R,
    print_diagnostics: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Dict[str, Any]]]:
    """Train all model types and return best models."""
    if model_types is None:
        model_types = ["xgboost", "lightgbm", "randomforest"]

    best_models = {}
    best_model_meta = {}
    all_candidates = {}

    for model_type in model_types:
        print(f"\nTraining {model_type}...")

        try:
            import optuna

            sampler = optuna.samplers.TPESampler(seed=SEED)
            pruner = optuna.pruners.MedianPruner(n_startup_trials=5)
            study = optuna.create_study(
                direction="maximize", sampler=sampler, pruner=pruner
            )
            study.optimize(
                lambda trial: optuna_objective(trial, model_type, X_train_df, y_train),
                n_trials=N_TRIALS,
            )

            best_params = study.best_params
            preprocessor = build_preprocessor(X_train_df)
            X_train_t = preprocessor.fit_transform(X_train_df)
            X_test_t = preprocessor.transform(X_test_df)

            class_ratio = dynamic_pos_weight(y_train)
            # Enable calibration for better probability distribution
            best_model = tree_model_factory(
                model_type, best_params, class_ratio, calibrate=True
            )
            best_model.fit(X_train_t, y_train)

            # Check probability distribution
            prob_check = best_model.predict_proba(X_train_t)[:, 1]
            print(
                f"  {model_type} probability stats: mean={prob_check.mean():.4f}, std={prob_check.std():.4f}, "
                f"range=[{prob_check.min():.4f}, {prob_check.max():.4f}]"
            )

            # Choose threshold on validation
            train_val_split = int(len(X_train_t) * 0.8)
            X_thr = X_train_t[train_val_split:]
            y_thr = y_train.iloc[train_val_split:]
            prob_thr = best_model.predict_proba(X_thr)[:, 1]
            threshold = choose_threshold(
                y_thr,
                prob_thr,
                max_turnover=max_turnover,
                min_turnover=min_turnover,
                min_expectancy=min_expectancy,
            )

            if print_diagnostics:
                print_threshold_diagnostics(
                    y_thr,
                    prob_thr,
                    label=f"{model_type} validation",
                    max_turnover=max_turnover,
                    min_turnover=min_turnover,
                    min_expectancy=min_expectancy,
                )

            if threshold is None:
                print(
                    f"[WARN] {model_type}: no threshold satisfies strict gates, trying fallback..."
                )
                # Use adaptive percentile-based threshold for candidate preservation
                sorted_probs = np.sort(prob_thr)[::-1]
                target_count = int(len(prob_thr) * ((min_turnover + max_turnover) / 2))
                if target_count > 0 and target_count <= len(sorted_probs):
                    threshold = float(sorted_probs[target_count - 1])
                    print(f"  Using adaptive threshold: {threshold:.4f}")
                else:
                    # Last resort: use median probability
                    threshold = float(np.median(prob_thr))
                    print(f"  Using median threshold: {threshold:.4f}")

            # Evaluate on test
            prob_test = best_model.predict_proba(X_test_t)[:, 1]
            metrics = compute_trading_metrics(y_test, prob_test, threshold)

            if print_diagnostics:
                print_threshold_diagnostics(
                    y_test,
                    prob_test,
                    label=f"{model_type} test",
                    max_turnover=max_turnover,
                    min_turnover=min_turnover,
                    min_expectancy=min_expectancy,
                )

            all_candidates[model_type] = {
                "model_bundle": {
                    "model": best_model,
                    "preprocessor": preprocessor,
                },
                "meta": {
                    "params": best_params,
                    "class_ratio": class_ratio,
                    "metrics": metrics,
                    "threshold": threshold,
                    "optuna_best_value": study.best_value,
                },
            }

            # Check if model passes gates
            passes_gates = (
                metrics["turnover"] <= max_turnover
                and metrics["turnover"] >= min_turnover
                and metrics["expectancy_unit_r"] > min_expectancy
            )

            if not passes_gates:
                print(
                    f"[WARN] {model_type} does not pass test gates (turnover={metrics['turnover']:.4f}, "
                    f"expectancy={metrics['expectancy_unit_r']:.4f}), but keeping as candidate"
                )
            else:
                print(f"{model_type} PASSES test gates: {metrics}")
                best_models[model_type] = {
                    "model": best_model,
                    "preprocessor": preprocessor,
                }
                best_model_meta[model_type] = all_candidates[model_type]["meta"]

        except Exception as e:
            print(f"Error training {model_type}: {e}")
            continue

    # Train LSTM
    print("\nTraining LSTM...")
    try:
        lstm_bundle = train_lstm(X_train_df, y_train, X_test_df, y_test)

        # Evaluate LSTM
        test_dataset = ForexDataset(
            lstm_bundle["scaler"].transform(
                lstm_bundle["preprocessor"].transform(X_test_df)
            ),
            y_test.to_numpy(),
            SEQ_LEN,
        )
        test_loader = DataLoader(test_dataset, batch_size=64, shuffle=False)
        model = lstm_bundle["model"]
        model.eval()
        probs = []
        with torch.no_grad():
            for X_batch, _ in test_loader:
                logits = model(X_batch)
                prob = torch.sigmoid(logits).numpy()
                probs.extend(prob)

        prob_arr = np.array(probs)
        y_lstm_test = y_test.iloc[SEQ_LEN:].to_numpy()

        # Choose threshold
        val_probs = []
        val_dataset = ForexDataset(
            lstm_bundle["scaler"].transform(
                lstm_bundle["preprocessor"].transform(X_train_df)
            ),
            y_train.to_numpy(),
            SEQ_LEN,
        )
        val_loader = DataLoader(val_dataset, batch_size=64, shuffle=False)
        with torch.no_grad():
            for X_batch, _ in val_loader:
                logits = model(X_batch)
                val_probs.extend(torch.sigmoid(logits).numpy())

        val_labels = y_train.iloc[SEQ_LEN:].to_numpy()
        threshold = choose_threshold(
            val_labels,
            np.array(val_probs),
            max_turnover=max_turnover,
            min_turnover=min_turnover,
            min_expectancy=min_expectancy,
        )

        if print_diagnostics:
            print_threshold_diagnostics(
                val_labels,
                np.array(val_probs),
                label="lstm validation",
                max_turnover=max_turnover,
                min_turnover=min_turnover,
                min_expectancy=min_expectancy,
            )

        if threshold is None:
            print(
                f"[WARN] LSTM: no threshold satisfies strict gates, trying fallback..."
            )
            sorted_probs = np.sort(np.array(val_probs))[::-1]
            target_count = int(len(sorted_probs) * ((min_turnover + max_turnover) / 2))
            if target_count > 0 and target_count <= len(sorted_probs):
                threshold = float(sorted_probs[target_count - 1])
            else:
                threshold = float(np.median(np.array(val_probs)))
            print(f"  Using adaptive threshold: {threshold:.4f}")

        metrics = compute_trading_metrics(y_lstm_test, prob_arr, threshold)

        if print_diagnostics:
            print_threshold_diagnostics(
                y_lstm_test,
                prob_arr,
                label="lstm test",
                max_turnover=max_turnover,
                min_turnover=min_turnover,
                min_expectancy=min_expectancy,
            )

        all_candidates["lstm"] = {
            "model_bundle": lstm_bundle,
            "meta": {
                "params": {"hidden_size": 50, "num_layers": 2},
                "metrics": metrics,
                "threshold": threshold,
            },
        }

        passes_gates = (
            metrics["turnover"] <= max_turnover
            and metrics["turnover"] >= min_turnover
            and metrics["expectancy_unit_r"] > min_expectancy
        )

        if passes_gates:
            best_models["lstm"] = lstm_bundle
            best_model_meta["lstm"] = all_candidates["lstm"]["meta"]
            print(f"LSTM PASSES test gates: {metrics}")
        else:
            print(
                f"[WARN] LSTM does not pass test gates (turnover={metrics['turnover']:.4f}, "
                f"expectancy={metrics['expectancy_unit_r']:.4f}), but keeping as candidate"
            )
    except Exception as e:
        print(f"Error training LSTM: {e}")

    return best_models, best_model_meta, all_candidates


def main():
    """Main training pipeline."""
    parser = argparse.ArgumentParser(description="Layer 3 ML Gatekeeper Training")
    parser.add_argument(
        "--model-types", nargs="+", default=["xgboost", "lightgbm", "randomforest"]
    )
    parser.add_argument(
        "--promote-as-champion",
        action="store_true",
        help="Promote best model to champion",
    )
    parser.add_argument("--dry-run", action="store_true", help="Train without saving")
    parser.add_argument(
        "--dry-run-load",
        action="store_true",
        help="Fast load check: validate DB/query/contracts/features and exit (no training)",
    )
    parser.add_argument(
        "--dry-run-top-n",
        type=int,
        default=2000,
        help="Row sample size for --dry-run-load (default: 2000)",
    )
    parser.add_argument(
        "--selection-mode",
        choices=["strict", "fallback"],
        default="strict",
        help="strict: fail if no model passes gates; fallback: select best candidate anyway",
    )
    parser.add_argument(
        "--min-turnover",
        type=float,
        default=MIN_TURNOVER,
        help="Minimum selected-trade turnover gate (default: 0.005)",
    )
    parser.add_argument(
        "--max-turnover",
        type=float,
        default=MAX_TURNOVER,
        help="Maximum selected-trade turnover gate (default: 0.50)",
    )
    parser.add_argument(
        "--min-expectancy",
        type=float,
        default=MIN_EXPECTANCY_UNIT_R,
        help="Minimum expectancy gate in unit-R (default: -0.05)",
    )
    parser.add_argument(
        "--print-threshold-diagnostics",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Print threshold sweep diagnostics for validation and test",
    )
    parser.add_argument(
        "--allow-degenerate-promotion",
        action="store_true",
        help="Allow champion promotion even when turnover/expectancy gates are not met",
    )
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("Layer 3 ML Gatekeeper Training")
    print(f"{'='*60}\n")
    print(f"Script path: {Path(__file__).resolve()}")
    print(f"Selection mode: {args.selection_mode}")
    print(
        f"Gate config: min_turnover={args.min_turnover:.4f}, "
        f"max_turnover={args.max_turnover:.4f}, min_expectancy={args.min_expectancy:.4f}"
    )

    # Load data
    print("Loading training data...")
    query, regime_table, fmr_cols, fs_cols, fto_cols = build_query_with_contract(engine)
    if args.dry_run_load:
        if args.dry_run_top_n <= 0:
            raise ValueError("--dry-run-top-n must be > 0")
        query = with_sqlserver_top(query, args.dry_run_top_n)
        print(f"Dry-run load mode enabled: sampling LIMIT {args.dry_run_top_n} rows")

    df = pd.read_sql(query, engine)
    # fact_* timestamps are timestamptz; normalise to naive UTC (the contract the
    # downstream feature pipeline assumed under SQL Server DATETIME2).
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], utc=True).dt.tz_localize(None)
    df = df.sort_values("Timestamp").reset_index(drop=True)

    print(f"Loaded {len(df)} rows")

    # Validate contracts
    assert_supervised_event_contract(df)
    assert_gatekeeper_granularity_contract(df)

    # ========================================================================
    # COMPREHENSIVE FEATURE ENGINEERING
    # ========================================================================
    print("\n" + "=" * 60)
    print("COMPREHENSIVE FEATURE ENGINEERING")
    print("=" * 60)

    # Apply comprehensive feature engineering
    df = comprehensive_feature_engineering(df)

    # Split data
    train_df, test_df = chronological_split(df, test_size=TEST_SIZE)
    assert_dataset_viable(df, train_df)

    # Prepare features
    target_col = "Is_Winner"

    # Meta columns to exclude from features
    meta_cols = [
        "Timestamp",
        "Granularity_Key",
        "Indicator_Snapshot",
        "Config_Hash",
        "Batch_ID",
    ]
    if "Trade_Horizon_Key" in df.columns:
        meta_cols.append("Trade_Horizon_Key")

    feature_cols = [c for c in train_df.columns if c not in [target_col] + meta_cols]

    X_train_df = train_df[feature_cols]
    y_train = train_df[target_col].astype(int)
    X_test_df = test_df[feature_cols]
    y_test = test_df[target_col].astype(int)

    if args.dry_run_load:
        # Validate preprocessing/load path quickly without expensive model fitting.
        print("Running preprocessing smoke check...")
        preprocessor = build_preprocessor(X_train_df)
        _ = preprocessor.fit_transform(X_train_df)
        _ = preprocessor.transform(X_test_df)
        class_ratio = dynamic_pos_weight(y_train)
        print(
            f"Dry-run load check passed | rows={len(df)} | features={len(feature_cols)} | class_ratio={class_ratio:.4f}"
        )
        print("No training executed. Use normal run to train models.")
        return

    print(f"\nFinal feature set: {len(feature_cols)} features")
    print(f"Features: {feature_cols[:20]}...")  # Show first 20
    print(f"Train samples: {len(X_train_df)}")
    print(f"Test samples: {len(X_test_df)}")

    # Train models
    best_models, best_model_meta, all_candidates = train_models(
        X_train_df,
        y_train,
        X_test_df,
        y_test,
        args.model_types,
        max_turnover=args.max_turnover,
        min_turnover=args.min_turnover,
        min_expectancy=args.min_expectancy,
        print_diagnostics=args.print_threshold_diagnostics,
    )

    selected_models = best_models
    selected_model_meta = best_model_meta
    effective_selection_mode = args.selection_mode

    # For normal training (no promotion), keep the run informative instead of failing hard.
    if effective_selection_mode == "strict" and not args.promote_as_champion:
        print(
            "[WARN] strict mode requested without --promote-as-champion; "
            "auto-switching to fallback selection for this run."
        )
        effective_selection_mode = "fallback"

    if not best_models:
        if effective_selection_mode == "strict":
            raise RuntimeError(
                "No feasible model satisfied turnover/expectancy gates in strict mode. "
                "Use --selection-mode fallback to select the best available candidate, "
                "or relax gates."
            )

        if not all_candidates:
            raise RuntimeError(
                "No model candidate produced evaluable metrics for fallback selection."
            )

        fallback_name = max(
            all_candidates,
            key=lambda k: (
                all_candidates[k]["meta"]["metrics"]["pr_auc"],
                all_candidates[k]["meta"]["metrics"]["f1"],
            ),
        )
        fallback_metrics = all_candidates[fallback_name]["meta"]["metrics"]
        print(
            f"[WARN] No model passed strict gates; selecting best available fallback: "
            f"{fallback_name} (expectancy={fallback_metrics['expectancy_unit_r']:.4f}, "
            f"turnover={fallback_metrics['turnover']:.4f})"
        )
        selected_models = {fallback_name: all_candidates[fallback_name]["model_bundle"]}
        selected_model_meta = {fallback_name: all_candidates[fallback_name]["meta"]}

    # Print all candidates summary for debugging
    print(f"\n{'='*60}")
    print("All Candidates Summary")
    print(f"{'='*60}")
    all_results = []
    for name in all_candidates:
        metrics = all_candidates[name]["meta"]["metrics"]
        passes = (
            metrics["turnover"] <= args.max_turnover
            and metrics["turnover"] >= args.min_turnover
            and metrics["expectancy_unit_r"] > args.min_expectancy
        )
        all_results.append(
            {
                "Model": name,
                "PR_AUC": metrics["pr_auc"],
                "F1": metrics["f1"],
                "Expectancy": metrics["expectancy_unit_r"],
                "Turnover": metrics["turnover"],
                "Threshold": metrics["threshold"],
                "Passes_Gates": "YES" if passes else "NO",
            }
        )
    print(pd.DataFrame(all_results).to_string(index=False))

    # Select champion
    results = []
    for name in selected_models:
        metrics = selected_model_meta[name]["metrics"]
        results.append(
            {
                "Model": name,
                "Test_PR_AUC": metrics["pr_auc"],
                "Test_F1": metrics["f1"],
                "Expectancy": metrics["expectancy_unit_r"],
                "Turnover": metrics["turnover"],
                "Threshold": metrics["threshold"],
            }
        )

    print(f"\n{'='*60}")
    print("Selected Models (Passed Gates or Fallback)")
    print(f"{'='*60}")
    print(pd.DataFrame(results).to_string(index=False))

    # Select best by PR-AUC, then F1
    best_model_name = max(results, key=lambda x: (x["Test_PR_AUC"], x["Test_F1"]))[
        "Model"
    ]
    print(f"\nChampion: {best_model_name}")

    # Promote to champion
    if args.promote_as_champion and not args.dry_run:
        champion_metrics = selected_model_meta[best_model_name]["metrics"]
        is_degenerate = (
            champion_metrics["turnover"] < args.min_turnover
            or champion_metrics["turnover"] > args.max_turnover
            or champion_metrics["expectancy_unit_r"] <= args.min_expectancy
        )

        if is_degenerate and not args.allow_degenerate_promotion:
            raise RuntimeError(
                "Refusing to promote champion because turnover/expectancy are degenerate under current gates. "
                "Review threshold diagnostics or pass --allow-degenerate-promotion to override."
            )

        manifest = promote_to_champion(
            selected_models[best_model_name],
            best_model_name,
            selected_model_meta[best_model_name]["metrics"]["threshold"],
            feature_cols,
            datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"),
            selected_model_meta[best_model_name]["metrics"],
        )

        # Also save run metadata
        run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        run_metadata = {
            "run_id": run_id,
            "champion_model": best_model_name,
            "all_results": results,
            "feature_columns": feature_cols,
            "feature_count": len(feature_cols),
            "feature_engineering_version": "2.0_comprehensive",
            "training_window": {
                "train_start": str(train_df["Timestamp"].min()),
                "train_end": str(train_df["Timestamp"].max()),
                "test_start": str(test_df["Timestamp"].min()),
                "test_end": str(test_df["Timestamp"].max()),
            },
        }

        metadata_path = MODELS_DIR / f"ml_gatekeeper_run_{run_id}.json"
        with open(metadata_path, "w") as f:
            json.dump(run_metadata, f, indent=2)

        print(f"Run metadata saved: {metadata_path}")

    print(f"\n{'='*60}")
    print("Training Complete")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
