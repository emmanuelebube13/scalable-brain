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
from sklearn.metrics import f1_score, precision_score, recall_score, average_precision_score, brier_score_loss
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
import pyodbc
import warnings
import sqlalchemy as sa
from dotenv import load_dotenv
import os
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
MAX_TURNOVER = 0.35
MIN_TURNOVER = 0.01
MIN_EXPECTANCY_UNIT_R = 0.0

# Layer 3 supports H1 and H4 only
SUPPORTED_GATEKEEPER_GRANULARITIES = {'H1', 'H4'}

# Artifact paths
MODELS_DIR = Path('models')
CHAMPION_MODEL_PATH = MODELS_DIR / 'champion_model.pkl'
CHAMPION_PREPROCESSOR_PATH = MODELS_DIR / 'champion_preprocessor.pkl'
CHAMPION_MANIFEST_PATH = MODELS_DIR / 'champion_manifest.json'
ARCHIVE_DIR = MODELS_DIR / 'archive'

warnings.filterwarnings('default')

# Setup paths
SCRIPT_DIR = Path(__file__).resolve().parent
APP_ROOT = SCRIPT_DIR.parents[1]
WORKSPACE_ROOT = APP_ROOT.parent

# Load environment
load_dotenv(APP_ROOT / '.env')
load_dotenv(WORKSPACE_ROOT / '.env')

DB_SERVER = os.getenv('DB_SERVER')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')
DB_NAME = os.getenv('DB_NAME', 'ForexBrainDB')
DB_ODBC_DRIVER = os.getenv('DB_ODBC_DRIVER')
DB_PORT = os.getenv('DB_PORT')
DB_CONNECTION_TIMEOUT = int(os.getenv('DB_CONNECTION_TIMEOUT', '15'))
STRICT_JOIN_CONTRACT = os.getenv('STRICT_JOIN_CONTRACT', '1').lower() in ('1', 'true', 'yes')
DEFAULT_LEGACY_GATEKEEPER_GRANULARITY = os.getenv('LAYER3_LEGACY_GRANULARITY', 'H1')


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
    with open(file_path, 'rb') as f:
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

def select_sqlserver_odbc_driver():
    """Select available SQL Server ODBC driver."""
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
        f"Detected drivers: {sorted(available)}."
    )


SQLSERVER_ODBC_DRIVER = select_sqlserver_odbc_driver()

if not DB_SERVER or not DB_USER or not DB_PASS:
    raise RuntimeError("Missing required DB configuration.")

server_spec = DB_SERVER
if DB_PORT and ',' not in DB_SERVER:
    server_spec = f"{DB_SERVER},{DB_PORT}"

params = urllib.parse.quote_plus(
    f"DRIVER={{{SQLSERVER_ODBC_DRIVER}}};"
    f"SERVER={server_spec};"
    f"DATABASE={DB_NAME};"
    f"UID={DB_USER};"
    f"PWD={DB_PASS};"
    "TrustServerCertificate=yes;"
    f"Connection Timeout={DB_CONNECTION_TIMEOUT};"
)
engine = sa.create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

# Test connection
try:
    with engine.connect() as conn:
        conn.exec_driver_sql('SELECT 1')
except Exception as exc:
    raise RuntimeError("Database connection failed.") from exc


# =============================================================================
# DATA CONTRACT FUNCTIONS
# =============================================================================

def table_columns(engine_obj, table_name):
    inspector = sa.inspect(engine_obj)
    return {col['name'] for col in inspector.get_columns(table_name)}


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
        f"SELECT DISTINCT CAST([{column_name}] AS NVARCHAR(100)) AS value "
        f"FROM {table_name} WHERE [{column_name}] IS NOT NULL"
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
    observed_regime = get_distinct_nonnull_values(engine_obj, regime_table, granularity_col)
    observed_signals = get_distinct_nonnull_values(engine_obj, 'Fact_Signals', granularity_col)
    
    supported = sorted((observed_regime & observed_signals) & SUPPORTED_GATEKEEPER_GRANULARITIES)
    
    unsupported_observed = (observed_regime | observed_signals) - SUPPORTED_GATEKEEPER_GRANULARITIES
    if unsupported_observed:
        print(
            f"[WARN] Legacy mode: Observed unsupported granularities that will be excluded: "
            f"{sorted(unsupported_observed)}."
        )

    if DEFAULT_LEGACY_GATEKEEPER_GRANULARITY in supported:
        chosen = DEFAULT_LEGACY_GATEKEEPER_GRANULARITY
    elif 'H1' in supported:
        chosen = 'H1'
    elif 'H4' in supported:
        chosen = 'H4'
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
    preferred_tables = ['Fact_Market_Regime_V2', 'Fact_Market_Regime']
    for table_name in preferred_tables:
        if table_exists(engine_obj, table_name):
            return table_name
    raise RuntimeError("No regime fact table found.")


def build_query_with_contract(engine_obj):
    """Build training query with proper join contract."""
    regime_table = pick_regime_table(engine_obj)
    fmr_cols = table_columns(engine_obj, regime_table)
    fs_cols = table_columns(engine_obj, 'Fact_Signals')
    fto_cols = table_columns(engine_obj, 'Fact_Trade_Outcomes')

    join_fmr_fs = ["fmr.Timestamp = fs.Timestamp", "fmr.Asset_ID = fs.Asset_ID"]
    join_fs_fto = [
        "fs.Timestamp = fto.Timestamp",
        "fs.Asset_ID = fto.Asset_ID",
        "fs.Strategy_ID = fto.Strategy_ID",
    ]

    granularity_col = require_common_column(
        fmr_cols, fs_cols, ['Granularity', 'Timeframe', 'Bar_Granularity'],
        'regime/signal granularity'
    )

    outcome_granularity_col = first_common_column(
        fto_cols, fto_cols, ['Granularity', 'Timeframe', 'Bar_Granularity']
    )
    legacy_granularity_filter = None
    if outcome_granularity_col is None:
        legacy_granularity_filter = pick_legacy_granularity(engine_obj, regime_table, granularity_col)

    horizon_col = first_common_column(fs_cols, fto_cols, ['Trade_Horizon', 'Horizon', 'Signal_Horizon'])

    join_fmr_fs.append(f"fmr.{granularity_col} = fs.{granularity_col}")
    if outcome_granularity_col:
        join_fs_fto.append(f"fs.{granularity_col} = fto.{outcome_granularity_col}")

    where_clauses = []
    if legacy_granularity_filter:
        where_clauses.append(f"fmr.{granularity_col} = '{legacy_granularity_filter}'")
        where_clauses.append(f"fs.{granularity_col} = '{legacy_granularity_filter}'")
    else:
        supported_list = ", ".join(f"'{g}'" for g in sorted(SUPPORTED_GATEKEEPER_GRANULARITIES))
        where_clauses.append(f"fmr.{granularity_col} IN ({supported_list})")
        where_clauses.append(f"fs.{granularity_col} IN ({supported_list})")

    if horizon_col:
        join_fs_fto.append(f"fs.{horizon_col} = fto.{horizon_col}")

    select_cols = [
        "fs.Timestamp", "fmr.Regime_Label", "fmr.ATR_Value", "fmr.ADX_Value",
        "fs.Asset_ID", "fs.Strategy_ID", f"fs.{granularity_col} AS Granularity_Key",
        "fs.Signal_Value", "fto.Is_Winner",
    ]

    # Optional context columns to enrich model features when present.
    optional_cols = []

    def _maybe_add(col_set, source_alias, col_name, alias=None):
        if col_name in col_set:
            as_name = alias or col_name
            optional_cols.append(f"{source_alias}.{col_name} AS {as_name}")

    # Layer 1 context
    _maybe_add(fmr_cols, 'fmr', 'Session_Volume_Z')
    _maybe_add(fmr_cols, 'fmr', 'Regime_Model_Version')

    # Layer 2 context
    _maybe_add(fs_cols, 'fs', 'Signal_Confidence')
    _maybe_add(fs_cols, 'fs', 'Signal_Strength')
    _maybe_add(fs_cols, 'fs', 'Config_ID')
    _maybe_add(fs_cols, 'fs', 'Priority')
    _maybe_add(fs_cols, 'fs', 'Rule_ID')

    # Layer 0/2->3 training context
    _maybe_add(fto_cols, 'fto', 'R_Multiple')
    _maybe_add(fto_cols, 'fto', 'Holding_Bars')

    if optional_cols:
        select_cols.extend(optional_cols)

    if horizon_col:
        select_cols.append(f"fs.{horizon_col} AS Trade_Horizon_Key")

    query = f"""
SELECT
    {", ".join(select_cols)}
FROM
    {regime_table} fmr
INNER JOIN
    Fact_Signals fs ON {' AND '.join(join_fmr_fs)}
INNER JOIN
    Fact_Trade_Outcomes fto ON {' AND '.join(join_fs_fto)}
{('WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''}
ORDER BY
    fs.Timestamp ASC
"""
    return query


def assert_supervised_event_contract(df_raw):
    """Validate data contract for supervised events."""
    required_cols = ['Timestamp', 'Asset_ID', 'Strategy_ID', 'Granularity_Key']
    missing_required = [col for col in required_cols if col not in df_raw.columns]
    if missing_required:
        raise ValueError(f"Data contract violation: missing columns: {', '.join(missing_required)}")

    key_cols = ['Timestamp', 'Asset_ID', 'Strategy_ID', 'Granularity_Key']
    if 'Trade_Horizon_Key' in df_raw.columns:
        key_cols.append('Trade_Horizon_Key')

    dupes = df_raw.duplicated(subset=key_cols, keep=False)
    if dupes.any():
        sample = df_raw.loc[dupes, key_cols].head(10).to_dict(orient='records')
        raise ValueError(f"Data contract violation: duplicate keys found. Sample: {sample}")


def assert_gatekeeper_granularity_contract(df_raw):
    """Assert that dataset only contains supported granularities."""
    if 'Granularity_Key' not in df_raw.columns:
        raise ValueError("Granularity_Key is required for the gatekeeper model.")

    observed = {str(value) for value in df_raw['Granularity_Key'].dropna().unique()}
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
# MODEL TRAINING
# =============================================================================

def build_preprocessor(X_df):
    """Build sklearn preprocessor for features."""
    numeric_cols = [col for col in X_df.columns if is_numeric_dtype(X_df[col])]
    categorical_cols = [col for col in X_df.columns if col not in numeric_cols]

    categorical_pipeline = Pipeline(
        steps=[
            ('imputer', SimpleImputer(strategy='most_frequent')),
            ('encoder', OneHotEncoder(handle_unknown='ignore', sparse_output=False)),
        ]
    )
    numeric_pipeline = Pipeline(steps=[('imputer', SimpleImputer(strategy='median'))])

    preprocessor = ColumnTransformer(
        transformers=[
            ('num', numeric_pipeline, numeric_cols),
            ('cat', categorical_pipeline, categorical_cols),
        ],
        remainder='drop',
        sparse_threshold=0,
    )
    return preprocessor


def dynamic_pos_weight(y_values):
    """Calculate positive class weight for imbalanced data."""
    y_arr = np.asarray(y_values)
    pos = np.sum(y_arr == 1)
    neg = np.sum(y_arr == 0)
    if pos == 0:
        return 1.0
    return max(1.0, float(neg) / float(pos))


def tree_model_factory(model_type, params, class_ratio):
    """Factory for tree-based models."""
    if model_type == 'xgboost':
        return xgb.XGBClassifier(
            **params, random_state=SEED, scale_pos_weight=class_ratio, eval_metric='logloss'
        )
    if model_type == 'lightgbm':
        return lgb.LGBMClassifier(
            **params, random_state=SEED, verbose=-1, scale_pos_weight=class_ratio
        )
    return RandomForestClassifier(
        **params, random_state=SEED, class_weight='balanced_subsample'
    )


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

    raise RuntimeError(f"Unable to construct valid TimeSeriesSplit for n_samples={n_samples}")


def optuna_objective(trial, model_type, X_train_df, y_train_series):
    """Optuna objective for hyperparameter tuning."""
    if model_type in ('xgboost', 'lightgbm'):
        params = {
            'n_estimators': trial.suggest_int('n_estimators', 80, 300),
            'max_depth': trial.suggest_int('max_depth', 3, 12),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.2),
        }
    else:
        params = {
            'n_estimators': trial.suggest_int('n_estimators', 100, 400),
            'max_depth': trial.suggest_int('max_depth', 4, 24),
            'min_samples_leaf': trial.suggest_int('min_samples_leaf', 1, 10),
        }

    tscv = make_time_series_split(len(X_train_df))
    pr_aucs = []

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
        score = average_precision_score(y_fold_val, prob)
        pr_aucs.append(score)

    return float(np.mean(pr_aucs))


def choose_threshold(
    y_true,
    prob,
    max_turnover=MAX_TURNOVER,
    min_turnover=MIN_TURNOVER,
    min_expectancy=MIN_EXPECTANCY_UNIT_R,
):
    """Choose optimal classification threshold based on trading metrics."""
    candidates = np.linspace(0.2, 0.8, 61)
    best_t = None
    best_score = None
    
    for t in candidates:
        metrics = compute_trading_metrics(y_true, prob, float(t))
        if metrics['turnover'] > max_turnover:
            continue
        if metrics['turnover'] < min_turnover:
            continue
        if metrics['expectancy_unit_r'] <= min_expectancy:
            continue

        score = (
            metrics['expectancy_unit_r'],
            metrics['pr_auc'],
            metrics['f1'],
            -metrics['turnover'],
        )
        if best_score is None or score > best_score:
            best_score = score
            best_t = float(t)

    return best_t


def print_threshold_diagnostics(
    y_true,
    prob,
    label,
    max_turnover,
    min_turnover,
    min_expectancy,
    top_n=8,
):
    """Print threshold sweep diagnostics for debugging viability."""
    rows = []
    for t in np.linspace(0.2, 0.8, 61):
        m = compute_trading_metrics(y_true, prob, float(t))
        m['meets_gates'] = (
            m['turnover'] <= max_turnover
            and m['turnover'] >= min_turnover
            and m['expectancy_unit_r'] > min_expectancy
        )
        rows.append(m)

    df_diag = pd.DataFrame(rows).sort_values(
        by=['meets_gates', 'expectancy_unit_r', 'pr_auc', 'f1', 'turnover'],
        ascending=[False, False, False, False, True],
    )

    feasible = int(df_diag['meets_gates'].sum())
    print(f"\n[Threshold diagnostics: {label}] feasible_thresholds={feasible}/{len(df_diag)}")
    print(df_diag[['threshold', 'turnover', 'expectancy_unit_r', 'precision_at_selected', 'pr_auc', 'f1', 'meets_gates']].head(top_n).to_string(index=False))


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
        'f1': float(f1_score(y_true, pred, zero_division=0)),
        'precision': float(precision_score(y_true, pred, zero_division=0)),
        'recall': float(recall_score(y_true, pred, zero_division=0)),
        'pr_auc': float(average_precision_score(y_true, prob)),
        'brier': float(brier_score_loss(y_true, prob)),
        'turnover': float(selected_count / len(y_true)) if len(y_true) else 0.0,
        'expectancy_unit_r': expectancy,
        'precision_at_selected': precision_at_k,
        'threshold': float(threshold),
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
        return self.X[idx:idx+self.seq_len], self.y[idx+self.seq_len]


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
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', patience=2, factor=0.5)

    pos_weight_value = dynamic_pos_weight(y_lstm_train)
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(pos_weight_value, dtype=torch.float32))

    best_val_loss = float('inf')
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

        epoch_val_loss = float(np.mean(val_losses)) if val_losses else float('inf')
        scheduler.step(epoch_val_loss)

        if epoch_val_loss < best_val_loss:
            best_val_loss = epoch_val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            epochs_without_improve = 0
        else:
            epochs_without_improve += 1

        if epochs_without_improve >= LSTM_PATIENCE:
            print(f"Early stopping LSTM at epoch {epoch + 1}")
            break

    if best_state is not None:
        model.load_state_dict(best_state)

    return {
        'model': model,
        'preprocessor': preprocessor,
        'scaler': scaler,
        'seq_len': SEQ_LEN,
        'best_val_loss': best_val_loss
    }


# =============================================================================
# ARTIFACT MANAGEMENT
# =============================================================================

def archive_current_champion():
    """Archive the current champion model before promoting a new one."""
    if not CHAMPION_MODEL_PATH.exists():
        return
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
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
    artifact_hashes: Dict[str, str]
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
        "artifact_hash": artifact_hashes.get('model', ''),
        "preprocessor_hash": artifact_hashes.get('preprocessor', ''),
        "metrics": metrics,
        "manifest_version": "1.0",
        "created_at": datetime.utcnow().isoformat()
    }


def promote_to_champion(
    model_bundle: Dict[str, Any],
    model_type: str,
    threshold: float,
    feature_columns: List[str],
    run_id: str,
    metrics: Dict[str, Any]
):
    """Promote a model to champion status with proper artifact management."""
    ensure_directories()
    
    # Archive current champion
    archive_current_champion()
    
    # Save new champion
    if model_type == 'lstm':
        # LSTM uses PyTorch
        torch.save(model_bundle['model'].state_dict(), CHAMPION_MODEL_PATH)
        joblib.dump(model_bundle['preprocessor'], CHAMPION_PREPROCESSOR_PATH)
        # Also save scaler separately for LSTM
        scaler_path = MODELS_DIR / 'champion_scaler.pkl'
        joblib.dump(model_bundle['scaler'], scaler_path)
    else:
        # Sklearn models
        joblib.dump(model_bundle['model'], CHAMPION_MODEL_PATH)
        joblib.dump(model_bundle['preprocessor'], CHAMPION_PREPROCESSOR_PATH)
    
    # Calculate hashes
    artifact_hashes = {
        'model': hash_file(CHAMPION_MODEL_PATH),
        'preprocessor': hash_file(CHAMPION_PREPROCESSOR_PATH)
    }
    
    # Create and save manifest
    manifest = create_champion_manifest(
        model_type=model_type,
        threshold=threshold,
        feature_columns=feature_columns,
        run_id=run_id,
        training_timestamp=datetime.utcnow().isoformat(),
        metrics=metrics,
        artifact_hashes=artifact_hashes
    )
    
    with open(CHAMPION_MANIFEST_PATH, 'w') as f:
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
        model_types = ['xgboost', 'lightgbm', 'randomforest']
    
    best_models = {}
    best_model_meta = {}
    all_candidates = {}
    
    for model_type in model_types:
        print(f"\nTraining {model_type}...")
        
        try:
            import optuna
            sampler = optuna.samplers.TPESampler(seed=SEED)
            pruner = optuna.pruners.MedianPruner(n_startup_trials=5)
            study = optuna.create_study(direction='maximize', sampler=sampler, pruner=pruner)
            study.optimize(
                lambda trial: optuna_objective(trial, model_type, X_train_df, y_train),
                n_trials=N_TRIALS,
            )

            best_params = study.best_params
            preprocessor = build_preprocessor(X_train_df)
            X_train_t = preprocessor.fit_transform(X_train_df)
            X_test_t = preprocessor.transform(X_test_df)

            class_ratio = dynamic_pos_weight(y_train)
            best_model = tree_model_factory(model_type, best_params, class_ratio)
            best_model.fit(X_train_t, y_train)

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
                print(f"Rejecting {model_type}: no threshold satisfies gates")
                continue

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
                'model_bundle': {
                    'model': best_model,
                    'preprocessor': preprocessor,
                },
                'meta': {
                    'params': best_params,
                    'class_ratio': class_ratio,
                    'metrics': metrics,
                    'threshold': threshold,
                    'optuna_best_value': study.best_value,
                },
            }

            if (
                metrics['turnover'] > max_turnover
                or metrics['turnover'] < min_turnover
                or metrics['expectancy_unit_r'] <= min_expectancy
            ):
                print(f"Rejecting {model_type} on test gates")
                continue

            best_models[model_type] = {
                'model': best_model,
                'preprocessor': preprocessor,
            }
            best_model_meta[model_type] = all_candidates[model_type]['meta']
            print(f"{model_type} test metrics: {metrics}")
            
        except Exception as e:
            print(f"Error training {model_type}: {e}")
            continue
    
    # Train LSTM
    print("\nTraining LSTM...")
    try:
        lstm_bundle = train_lstm(X_train_df, y_train, X_test_df, y_test)
        
        # Evaluate LSTM
        test_dataset = ForexDataset(
            lstm_bundle['scaler'].transform(lstm_bundle['preprocessor'].transform(X_test_df)),
            y_test.to_numpy(), SEQ_LEN
        )
        test_loader = DataLoader(test_dataset, batch_size=64, shuffle=False)
        model = lstm_bundle['model']
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
            lstm_bundle['scaler'].transform(lstm_bundle['preprocessor'].transform(X_train_df)),
            y_train.to_numpy(), SEQ_LEN
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
        
        if threshold is not None:
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

            all_candidates['lstm'] = {
                'model_bundle': lstm_bundle,
                'meta': {
                    'params': {'hidden_size': 50, 'num_layers': 2},
                    'metrics': metrics,
                    'threshold': threshold,
                },
            }

            if (
                metrics['turnover'] <= max_turnover
                and metrics['turnover'] >= min_turnover
                and metrics['expectancy_unit_r'] > min_expectancy
            ):
                best_models['lstm'] = lstm_bundle
                best_model_meta['lstm'] = all_candidates['lstm']['meta']
                print(f"LSTM test metrics: {metrics}")
    except Exception as e:
        print(f"Error training LSTM: {e}")
    
    return best_models, best_model_meta, all_candidates


def main():
    """Main training pipeline."""
    parser = argparse.ArgumentParser(description='Layer 3 ML Gatekeeper Training')
    parser.add_argument('--model-types', nargs='+', default=['xgboost', 'lightgbm', 'randomforest'])
    parser.add_argument('--promote-as-champion', action='store_true', help='Promote best model to champion')
    parser.add_argument('--dry-run', action='store_true', help='Train without saving')
    parser.add_argument('--selection-mode', choices=['strict', 'fallback'], default='strict',
                        help='strict: fail if no model passes gates; fallback: select best candidate anyway')
    parser.add_argument('--min-turnover', type=float, default=MIN_TURNOVER,
                        help='Minimum selected-trade turnover gate (default: 0.01)')
    parser.add_argument('--max-turnover', type=float, default=MAX_TURNOVER,
                        help='Maximum selected-trade turnover gate (default: 0.35)')
    parser.add_argument('--min-expectancy', type=float, default=MIN_EXPECTANCY_UNIT_R,
                        help='Minimum expectancy gate in unit-R (default: 0.0)')
    parser.add_argument('--print-threshold-diagnostics', action=argparse.BooleanOptionalAction, default=True,
                        help='Print threshold sweep diagnostics for validation and test')
    parser.add_argument('--allow-degenerate-promotion', action='store_true',
                        help='Allow champion promotion even when turnover/expectancy gates are not met')
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
    query = build_query_with_contract(engine)
    df = pd.read_sql(query, engine)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df = df.sort_values('Timestamp').reset_index(drop=True)
    
    print(f"Loaded {len(df)} rows")
    
    # Validate contracts
    assert_supervised_event_contract(df)
    assert_gatekeeper_granularity_contract(df)
    
    # Split data
    train_df, test_df = chronological_split(df, test_size=TEST_SIZE)
    assert_dataset_viable(df, train_df)
    
    # Prepare features
    target_col = 'Is_Winner'
    meta_cols = ['Timestamp', 'Granularity_Key']
    if 'Trade_Horizon_Key' in df.columns:
        meta_cols.append('Trade_Horizon_Key')
    
    feature_cols = [c for c in train_df.columns if c not in [target_col] + meta_cols]
    
    X_train_df = train_df[feature_cols]
    y_train = train_df[target_col].astype(int)
    X_test_df = test_df[feature_cols]
    y_test = test_df[target_col].astype(int)
    
    print(f"Features: {feature_cols}")
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

    if not best_models:
        if args.selection_mode == 'strict':
            raise RuntimeError(
                "No feasible model satisfied turnover/expectancy gates in strict mode. "
                "Use --selection-mode fallback to select the best available candidate."
            )

        if not all_candidates:
            raise RuntimeError("No model candidate produced evaluable metrics for fallback selection.")

        fallback_name = max(
            all_candidates,
            key=lambda k: (
                all_candidates[k]['meta']['metrics']['pr_auc'],
                all_candidates[k]['meta']['metrics']['f1'],
            ),
        )
        fallback_metrics = all_candidates[fallback_name]['meta']['metrics']
        print(
            f"[WARN] No model passed strict gates; selecting best available fallback: "
            f"{fallback_name} (expectancy={fallback_metrics['expectancy_unit_r']:.4f}, "
            f"turnover={fallback_metrics['turnover']:.4f})"
        )
        selected_models = {fallback_name: all_candidates[fallback_name]['model_bundle']}
        selected_model_meta = {fallback_name: all_candidates[fallback_name]['meta']}
    
    # Select champion
    results = []
    for name in selected_models:
        metrics = selected_model_meta[name]['metrics']
        results.append({
            'Model': name,
            'Test_PR_AUC': metrics['pr_auc'],
            'Test_F1': metrics['f1'],
            'Expectancy': metrics['expectancy_unit_r'],
            'Turnover': metrics['turnover'],
            'Threshold': metrics['threshold']
        })
    
    print(f"\n{'='*60}")
    print("Tournament Results")
    print(f"{'='*60}")
    print(pd.DataFrame(results).to_string(index=False))
    
    # Select best by PR-AUC, then F1
    best_model_name = max(results, key=lambda x: (x['Test_PR_AUC'], x['Test_F1']))['Model']
    print(f"\nChampion: {best_model_name}")
    
    # Promote to champion
    if args.promote_as_champion and not args.dry_run:
        champion_metrics = selected_model_meta[best_model_name]['metrics']
        is_degenerate = (
            champion_metrics['turnover'] < args.min_turnover
            or champion_metrics['turnover'] > args.max_turnover
            or champion_metrics['expectancy_unit_r'] <= args.min_expectancy
        )

        if is_degenerate and not args.allow_degenerate_promotion:
            raise RuntimeError(
                "Refusing to promote champion because turnover/expectancy are degenerate under current gates. "
                "Review threshold diagnostics or pass --allow-degenerate-promotion to override."
            )

        manifest = promote_to_champion(
            selected_models[best_model_name],
            best_model_name,
            selected_model_meta[best_model_name]['metrics']['threshold'],
            feature_cols,
            datetime.utcnow().strftime('%Y%m%dT%H%M%SZ'),
            selected_model_meta[best_model_name]['metrics']
        )
        
        # Also save run metadata
        run_id = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
        run_metadata = {
            'run_id': run_id,
            'champion_model': best_model_name,
            'all_results': results,
            'feature_columns': feature_cols,
            'training_window': {
                'train_start': str(train_df['Timestamp'].min()),
                'train_end': str(train_df['Timestamp'].max()),
                'test_start': str(test_df['Timestamp'].min()),
                'test_end': str(test_df['Timestamp'].max()),
            }
        }
        
        metadata_path = MODELS_DIR / f"ml_gatekeeper_run_{run_id}.json"
        with open(metadata_path, 'w') as f:
            json.dump(run_metadata, f, indent=2)
        
        print(f"Run metadata saved: {metadata_path}")
    
    print(f"\n{'='*60}")
    print("Training Complete")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
