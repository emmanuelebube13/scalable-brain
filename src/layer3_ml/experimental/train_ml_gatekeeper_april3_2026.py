import hashlib
import json
import random
from datetime import datetime
from pathlib import Path

import pandas as pd
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
import joblib
import optuna
import numpy as np
import pyodbc
import warnings
import sqlalchemy as sa
from dotenv import load_dotenv
import os
import urllib.parse

SEED = 42
TEST_SIZE = 0.2
CV_SPLITS = 3
EMBARGO_GAP = 10
N_TRIALS = 20
SEQ_LEN = 50
LSTM_MAX_EPOCHS = 50
LSTM_PATIENCE = 6
MAX_TURNOVER = 0.35
MIN_EXPECTANCY_UNIT_R = 0.0
# Layer 3 ML Gatekeeper: Strictly supports H1 and H4 for training/inference.
# D1 is NOT supported in the gatekeeper pipeline - use D1 as a macro feature instead.
# To extend: add 'D1' here AND implement proper join contract handling for D1 outcomes.
SUPPORTED_GATEKEEPER_GRANULARITIES = {'H1', 'H4'}


def validate_granularity_for_gatekeeper(granularity: str, context: str = "") -> None:
    """
    Validate that a granularity is supported by the Layer 3 ML gatekeeper.
    
    Args:
        granularity: The granularity value to validate (e.g., 'H1', 'H4', 'D1')
        context: Additional context for the error message (e.g., 'legacy fallback')
    
    Raises:
        ValueError: If granularity is not in SUPPORTED_GATEKEEPER_GRANULARITIES
    """
    if granularity not in SUPPORTED_GATEKEEPER_GRANULARITIES:
        prefix = f"{context}: " if context else ""
        raise ValueError(
            f"{prefix}Granularity '{granularity}' is not supported by the Layer 3 ML gatekeeper. "
            f"Supported granularities: {', '.join(sorted(SUPPORTED_GATEKEEPER_GRANULARITIES))}. "
            f"D1 is explicitly excluded from the gatekeeper training pipeline. "
            f"If you need D1 features, use it as a macro/context feature rather than a trading timeframe."
        )


def set_global_seed(seed=SEED):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


set_global_seed()

warnings.filterwarnings('default')

SCRIPT_DIR = Path(__file__).resolve().parent
APP_ROOT = SCRIPT_DIR.parents[1]
WORKSPACE_ROOT = APP_ROOT.parent

# Load env from app root first, then fallback to workspace root.
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


def select_sqlserver_odbc_driver():
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
        f"Detected drivers: {sorted(available)}. "
        "Install 'ODBC Driver 18 for SQL Server' or set DB_ODBC_DRIVER to an installed driver."
    )


SQLSERVER_ODBC_DRIVER = select_sqlserver_odbc_driver()

if not DB_SERVER or not DB_USER or not DB_PASS:
    raise RuntimeError(
        "Missing required DB configuration. Ensure DB_SERVER, DB_USER, and DB_PASS are set in .env."
    )

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

try:
    with engine.connect() as conn:
        conn.exec_driver_sql('SELECT 1')
except Exception as exc:
    raise RuntimeError(
        "Database connection failed. "
        f"Driver={SQLSERVER_ODBC_DRIVER}, Server={server_spec}, Database={DB_NAME}. "
        "Verify SQL Server is reachable from this machine (host/port/firewall/VPN), "
        "and credentials are correct."
    ) from exc

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


def get_distinct_nonnull_count(engine_obj, table_name, column_name):
    query = sa.text(
        f"SELECT COUNT(DISTINCT CAST([{column_name}] AS NVARCHAR(100))) AS distinct_count "
        f"FROM {table_name} WHERE [{column_name}] IS NOT NULL"
    )
    with engine_obj.connect() as conn:
        result = conn.execute(query).scalar_one()
    return int(result)


def get_distinct_nonnull_values(engine_obj, table_name, column_name):
    query = sa.text(
        f"SELECT DISTINCT CAST([{column_name}] AS NVARCHAR(100)) AS value "
        f"FROM {table_name} WHERE [{column_name}] IS NOT NULL"
    )
    with engine_obj.connect() as conn:
        result = conn.execute(query).fetchall()
    return {str(row[0]) for row in result if row[0] is not None}


def pick_legacy_granularity(engine_obj, regime_table, granularity_col):
    """
    Pick a legacy granularity when Fact_Trade_Outcomes lacks Granularity column.
    
    IMPORTANT: Only H1 and H4 are supported. D1 is explicitly rejected even if present.
    """
    observed_regime = get_distinct_nonnull_values(engine_obj, regime_table, granularity_col)
    observed_signals = get_distinct_nonnull_values(engine_obj, 'Fact_Signals', granularity_col)
    
    # Filter to only supported granularities (H1/H4) - explicitly exclude D1
    supported = sorted((observed_regime & observed_signals) & SUPPORTED_GATEKEEPER_GRANULARITIES)
    
    # Log if D1 or other unsupported granularities were observed
    unsupported_observed = (observed_regime | observed_signals) - SUPPORTED_GATEKEEPER_GRANULARITIES
    if unsupported_observed:
        print(
            f"[WARN] Legacy mode: Observed unsupported granularities that will be excluded: "
            f"{sorted(unsupported_observed)}. Layer 3 gatekeeper only supports {sorted(SUPPORTED_GATEKEEPER_GRANULARITIES)}."
        )

    if DEFAULT_LEGACY_GATEKEEPER_GRANULARITY in supported:
        chosen = DEFAULT_LEGACY_GATEKEEPER_GRANULARITY
    elif 'H1' in supported:
        chosen = 'H1'
    elif 'H4' in supported:
        chosen = 'H4'
    elif supported:
        # This shouldn't happen given SUPPORTED_GATEKEEPER_GRANULARITIES, but be defensive
        chosen = supported[0]
    else:
        combined = sorted((observed_regime & observed_signals) or (observed_regime or observed_signals))
        # Check if there's exactly one supported granularity available
        supported_in_combined = [g for g in combined if g in SUPPORTED_GATEKEEPER_GRANULARITIES]
        if len(supported_in_combined) == 1:
            chosen = supported_in_combined[0]
        else:
            raise RuntimeError(
                "Unable to select a supported legacy granularity for Layer 3. "
                f"Observed regime granularities: {sorted(observed_regime)}; "
                f"observed signal granularities: {sorted(observed_signals)}. "
                f"Only {sorted(SUPPORTED_GATEKEEPER_GRANULARITIES)} are supported. "
                f"D1 is explicitly not supported in the gatekeeper pipeline."
            )

    # Validate the chosen granularity before returning
    validate_granularity_for_gatekeeper(chosen, context="Legacy granularity selection")
    
    print(
        "[INFO] Legacy Fact_Trade_Outcomes detected without Granularity; "
        f"filtering the dataset to granularity='{chosen}' (supported: {sorted(SUPPORTED_GATEKEEPER_GRANULARITIES)})"
    )
    return chosen


def require_common_column(left_cols, right_cols, candidates, label):
    column = first_common_column(left_cols, right_cols, candidates)
    if not column:
        raise RuntimeError(
            f"Missing required join column for {label}. Expected one of: {', '.join(candidates)}"
        )
    return column


def pick_regime_table(engine_obj):
    preferred_tables = ['Fact_Market_Regime_V2', 'Fact_Market_Regime']
    for table_name in preferred_tables:
        if table_exists(engine_obj, table_name):
            return table_name
    raise RuntimeError(
        "No regime fact table found. Expected Fact_Market_Regime_V2 or Fact_Market_Regime to exist."
    )


def build_query_with_contract(engine_obj):
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
        fmr_cols,
        fs_cols,
        ['Granularity', 'Timeframe', 'Bar_Granularity'],
        'regime/signal granularity'
    )

    outcome_granularity_col = first_common_column(
        fto_cols,
        fto_cols,
        ['Granularity', 'Timeframe', 'Bar_Granularity']
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
        # Legacy mode: filter to the single chosen granularity (H1 or H4 only)
        where_clauses.append(f"fmr.{granularity_col} = '{legacy_granularity_filter}'")
        where_clauses.append(f"fs.{granularity_col} = '{legacy_granularity_filter}'")
    else:
        # Modern mode: explicitly restrict to supported granularities (H1/H4) at query level
        # This prevents D1 data from sneaking in if it exists in the database
        supported_list = ", ".join(f"'{g}'" for g in sorted(SUPPORTED_GATEKEEPER_GRANULARITIES))
        where_clauses.append(f"fmr.{granularity_col} IN ({supported_list})")
        where_clauses.append(f"fs.{granularity_col} IN ({supported_list})")

    if horizon_col:
        join_fs_fto.append(f"fs.{horizon_col} = fto.{horizon_col}")

    select_cols = [
        "fs.Timestamp",
        "fmr.Regime_Label",
        "fmr.ATR_Value",
        "fmr.ADX_Value",
        "fs.Asset_ID",
        "fs.Strategy_ID",
        f"fs.{granularity_col} AS Granularity_Key",
        "fs.Signal_Value",
        "fto.Is_Winner",
    ]

    if horizon_col:
        select_cols.append(f"fs.{horizon_col} AS Trade_Horizon_Key")

    query = f"""
SELECT
    {",\n    ".join(select_cols)}
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
    print(
        "Join contract keys:",
        {
            'strict': STRICT_JOIN_CONTRACT,
            'regime_table': regime_table,
            'horizon_col': horizon_col,
            'granularity_col': granularity_col,
        },
    )
    return query


def assert_supervised_event_contract(df_raw):
    required_cols = ['Timestamp', 'Asset_ID', 'Strategy_ID', 'Granularity_Key']
    missing_required = [col for col in required_cols if col not in df_raw.columns]
    if missing_required:
        raise ValueError(
            f"Data contract violation: missing required columns: {', '.join(missing_required)}"
        )

    key_cols = ['Timestamp', 'Asset_ID', 'Strategy_ID', 'Granularity_Key']
    if 'Trade_Horizon_Key' in df_raw.columns:
        key_cols.append('Trade_Horizon_Key')

    dupes = df_raw.duplicated(subset=key_cols, keep=False)
    if dupes.any():
        sample = df_raw.loc[dupes, key_cols].head(10).to_dict(orient='records')
        raise ValueError(
            "Data contract violation: duplicate supervised event keys found. "
            f"Sample duplicates: {sample}"
        )


def assert_gatekeeper_granularity_contract(df_raw):
    """
    Assert that the loaded dataset only contains supported granularities.
    
    This is a hard contract: Layer 3 gatekeeper ONLY supports H1 and H4.
    D1 is explicitly rejected - use it as a macro feature, not a trading timeframe.
    """
    if 'Granularity_Key' not in df_raw.columns:
        raise ValueError("Granularity_Key is required for the gatekeeper model.")

    observed = {str(value) for value in df_raw['Granularity_Key'].dropna().unique()}
    invalid = sorted(observed - SUPPORTED_GATEKEEPER_GRANULARITIES)
    if invalid:
        raise ValueError(
            f"Layer 3 ML gatekeeper validation FAILED: observed unsupported granularities: {', '.join(invalid)}. "
            f"The gatekeeper strictly supports only: {', '.join(sorted(SUPPORTED_GATEKEEPER_GRANULARITIES))}. "
            f"D1 is explicitly NOT supported in the gatekeeper pipeline. "
            f"To use D1 data, add it as a macro/context feature rather than including it in the training dataset. "
            f"If you believe this is an error, check that your upstream tables (Fact_Market_Regime_V2, Fact_Signals) "
            f"do not contain D1 data, or that STRICT_JOIN_CONTRACT filtering is working correctly."
        )


def print_missingness_report(df_raw):
    missing = df_raw.isna().mean().sort_values(ascending=False)
    missing = missing[missing > 0]
    if not missing.empty:
        print("Missingness report (ratio):")
        print(missing.to_string())


def chronological_split(df_raw, test_size=TEST_SIZE):
    split_idx = int(len(df_raw) * (1 - test_size))
    train_df = df_raw.iloc[:split_idx].copy()
    test_df = df_raw.iloc[split_idx:].copy()
    return train_df, test_df


def get_table_count(engine_obj, table_name):
    query = sa.text(f"SELECT COUNT(1) AS row_count FROM {table_name}")
    with engine_obj.connect() as conn:
        result = conn.execute(query).scalar_one()
    return int(result)


def assert_dataset_viable(df_raw, train_df):
    if df_raw.empty:
        counts = {
            'Fact_Market_Regime_V2': get_table_count(engine, 'Fact_Market_Regime_V2') if table_exists(engine, 'Fact_Market_Regime_V2') else None,
            'Fact_Market_Regime': get_table_count(engine, 'Fact_Market_Regime') if table_exists(engine, 'Fact_Market_Regime') else None,
            'Fact_Signals': get_table_count(engine, 'Fact_Signals'),
            'Fact_Trade_Outcomes': get_table_count(engine, 'Fact_Trade_Outcomes'),
        }
        raise RuntimeError(
            "Training query returned 0 rows after joins. "
            f"Table counts: {counts}. "
            "This usually means the upstream regime or outcomes tables have not been populated yet, "
            "or the join keys do not align across pipeline versions. "
            "Run the regime ingestion script for the current table version and the trade-outcome evaluator, "
            "then rerun training. If needed for diagnosis, set STRICT_JOIN_CONTRACT=0 to isolate optional horizon joins; granularity remains required."
        )

    min_train_rows = (CV_SPLITS + 1) * 2
    if len(train_df) < min_train_rows:
        raise RuntimeError(
            f"Not enough training rows for time-series CV: train_rows={len(train_df)}, "
            f"required_at_least={min_train_rows}."
        )


def make_time_series_split(n_samples):
    if n_samples < 6:
        raise RuntimeError(f"Insufficient samples for TimeSeriesSplit: {n_samples}")

    split_candidates = list(range(min(CV_SPLITS, n_samples - 1), 1, -1))
    gap_candidates = [EMBARGO_GAP, max(0, EMBARGO_GAP // 2), 0]

    for splits in split_candidates:
        for gap in gap_candidates:
            tscv = TimeSeriesSplit(n_splits=splits, gap=gap)
            try:
                _ = list(tscv.split(np.arange(n_samples)))
                if gap < EMBARGO_GAP:
                    print(
                        f"Adjusted CV settings for sample size: n_splits={splits}, gap={gap} (requested gap={EMBARGO_GAP})"
                    )
                return tscv
            except ValueError:
                continue

    raise RuntimeError(
        f"Unable to construct a valid TimeSeriesSplit for n_samples={n_samples}. "
        "Reduce CV_SPLITS/EMBARGO_GAP or increase training data volume."
    )


def build_preprocessor(X_df):
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
    y_arr = np.asarray(y_values)
    pos = np.sum(y_arr == 1)
    neg = np.sum(y_arr == 0)
    if pos == 0:
        return 1.0
    return max(1.0, float(neg) / float(pos))


def tree_model_factory(model_type, params, class_ratio):
    if model_type == 'xgboost':
        return xgb.XGBClassifier(
            **params,
            random_state=SEED,
            scale_pos_weight=class_ratio,
            eval_metric='logloss',
        )
    if model_type == 'lightgbm':
        return lgb.LGBMClassifier(
            **params,
            random_state=SEED,
            verbose=-1,
            scale_pos_weight=class_ratio,
        )
    return RandomForestClassifier(
        **params,
        random_state=SEED,
        class_weight='balanced_subsample',
    )


def optuna_objective(trial, model_type, X_train_df, y_train_series):
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


def choose_threshold(y_true, prob, max_turnover=MAX_TURNOVER, min_expectancy=MIN_EXPECTANCY_UNIT_R):
    candidates = np.linspace(0.2, 0.8, 61)
    best_t = None
    best_score = None
    for t in candidates:
        metrics = compute_trading_metrics(y_true, prob, float(t))
        if metrics['turnover'] > max_turnover:
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

    if best_t is None:
        return None

    return best_t


def compute_trading_metrics(y_true, prob, threshold):
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

    out = {
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
    return out


def hash_file(file_path):
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


query = build_query_with_contract(engine)
df = pd.read_sql(query, engine)
df['Timestamp'] = pd.to_datetime(df['Timestamp'])
df = df.sort_values('Timestamp').reset_index(drop=True)

assert_supervised_event_contract(df)
assert_gatekeeper_granularity_contract(df)
print_missingness_report(df)

target_col = 'Is_Winner'
meta_cols = ['Timestamp', 'Granularity_Key']
if 'Trade_Horizon_Key' in df.columns:
    meta_cols.append('Trade_Horizon_Key')

train_df, test_df = chronological_split(df, test_size=TEST_SIZE)
assert_dataset_viable(df, train_df)

X_train_df = train_df.drop(columns=[target_col] + meta_cols)
y_train = train_df[target_col].astype(int)
X_test_df = test_df.drop(columns=[target_col] + meta_cols)
y_test = test_df[target_col].astype(int)

models = ['xgboost', 'lightgbm', 'randomforest']
best_models = {}
best_model_meta = {}

for m in models:
    print(f"Starting Optuna tuning for {m}...")
    sampler = optuna.samplers.TPESampler(seed=SEED)
    pruner = optuna.pruners.MedianPruner(n_startup_trials=5)
    study = optuna.create_study(direction='maximize', sampler=sampler, pruner=pruner)
    study.optimize(
        lambda trial: optuna_objective(trial, m, X_train_df, y_train),
        n_trials=N_TRIALS,
    )

    best_params = study.best_params
    preprocessor = build_preprocessor(X_train_df)
    X_train_t = preprocessor.fit_transform(X_train_df)
    X_test_t = preprocessor.transform(X_test_df)

    class_ratio = dynamic_pos_weight(y_train)
    best_model = tree_model_factory(m, best_params, class_ratio)
    best_model.fit(X_train_t, y_train)

    train_val_split = int(len(X_train_t) * 0.8)
    X_thr = X_train_t[train_val_split:]
    y_thr = y_train.iloc[train_val_split:]
    prob_thr = best_model.predict_proba(X_thr)[:, 1]
    threshold = choose_threshold(y_thr, prob_thr)
    if threshold is None:
        print(
            f"Rejecting {m} on validation gates: no threshold satisfies "
            f"turnover <= {MAX_TURNOVER} and expectancy > {MIN_EXPECTANCY_UNIT_R}."
        )
        continue

    prob_test = best_model.predict_proba(X_test_t)[:, 1]
    metrics = compute_trading_metrics(y_test, prob_test, threshold)

    if metrics['turnover'] > MAX_TURNOVER or metrics['expectancy_unit_r'] <= MIN_EXPECTANCY_UNIT_R:
        print(
            f"Rejecting {m} on test gates: turnover={metrics['turnover']:.3f}, "
            f"expectancy={metrics['expectancy_unit_r']:.3f}"
        )
        continue

    best_models[m] = {
        'model': best_model,
        'preprocessor': preprocessor,
    }
    best_model_meta[m] = {
        'params': best_params,
        'class_ratio': class_ratio,
        'metrics': metrics,
        'threshold': threshold,
        'optuna_best_value': study.best_value,
    }
    print(f"Best {m} params: {best_params}")
    print(f"{m} test metrics: {metrics}")

# Simple LSTM (for time-series) 
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

# Train LSTM 
print("Training PyTorch LSTM...")
preprocessor_lstm = build_preprocessor(X_train_df)
X_train_lstm = preprocessor_lstm.fit_transform(X_train_df)
X_test_lstm = preprocessor_lstm.transform(X_test_df)

scaler = StandardScaler()
X_train_lstm = scaler.fit_transform(X_train_lstm)
X_test_lstm = scaler.transform(X_test_lstm)

train_cut = int(len(X_train_lstm) * 0.8)
X_lstm_train = X_train_lstm[:train_cut]
y_lstm_train = y_train.iloc[:train_cut].to_numpy()
X_lstm_val = X_train_lstm[train_cut:]
y_lstm_val = y_train.iloc[train_cut:].to_numpy()

seq_len = SEQ_LEN
train_dataset = ForexDataset(X_lstm_train, y_lstm_train, seq_len)
val_dataset = ForexDataset(X_lstm_val, y_lstm_val, seq_len)
train_loader = DataLoader(train_dataset, batch_size=64, shuffle=False)
val_loader = DataLoader(val_dataset, batch_size=64, shuffle=False)

model = LSTMModel(input_size=X_train_lstm.shape[1])
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

best_models['lstm'] = {
    'model': model,
    'preprocessor': preprocessor_lstm,
    'scaler': scaler,
    'seq_len': seq_len,
}

# Evaluate all on test set
print("Evaluating all models...")
results = []
for name, bundle in best_models.items():
    if name == 'lstm':
        test_dataset = ForexDataset(X_test_lstm, y_test.to_numpy(), seq_len)
        test_loader = DataLoader(test_dataset, batch_size=64, shuffle=False)
        model = bundle['model']
        model.eval()
        probs = []
        with torch.no_grad():
            for X_batch, _ in test_loader:
                logits = model(X_batch)
                prob = torch.sigmoid(logits).numpy()
                probs.extend(prob)
        prob_arr = np.array(probs)
        y_lstm_test = y_test.iloc[seq_len:].to_numpy()
        train_probs = []
        train_dataset_for_threshold = ForexDataset(X_lstm_val, y_lstm_val, seq_len)
        train_loader_for_threshold = DataLoader(train_dataset_for_threshold, batch_size=64, shuffle=False)
        with torch.no_grad():
            for X_batch, _ in train_loader_for_threshold:
                logits = model(X_batch)
                train_probs.extend(torch.sigmoid(logits).numpy())
        threshold = choose_threshold(y_lstm_val[seq_len:], np.array(train_probs))
        if threshold is None:
            print(f"Rejecting LSTM: no feasible threshold satisfied turnover/expectancy gates.")
            continue
        metrics = compute_trading_metrics(y_lstm_test, prob_arr, threshold)
        if metrics['turnover'] > MAX_TURNOVER or metrics['expectancy_unit_r'] <= MIN_EXPECTANCY_UNIT_R:
            print(
                f"Rejecting LSTM on test gates: turnover={metrics['turnover']:.3f}, "
                f"expectancy={metrics['expectancy_unit_r']:.3f}"
            )
            continue
        best_model_meta['lstm'] = {
            'params': {'hidden_size': 50, 'num_layers': 2},
            'class_ratio': pos_weight_value,
            'metrics': metrics,
            'threshold': threshold,
            'optuna_best_value': None,
            'best_val_loss': best_val_loss,
        }
        best_models['lstm'] = {
            'model': model,
            'preprocessor': preprocessor_lstm,
            'scaler': scaler,
            'seq_len': seq_len,
        }
    else:
        metrics = best_model_meta[name]['metrics']

    results.append(
        {
            'Model': name,
            'Test_F1': metrics['f1'],
            'Test_PR_AUC': metrics['pr_auc'],
            'Precision': metrics['precision'],
            'Recall': metrics['recall'],
            'Brier': metrics['brier'],
            'Turnover': metrics['turnover'],
            'Expectancy_UnitR': metrics['expectancy_unit_r'],
            'Threshold': metrics['threshold'],
        }
    )
    
print("\n=== FINAL TOURNAMENT RESULTS ===")
print(pd.DataFrame(results))

if not results:
    raise RuntimeError(
        f"No feasible Layer 3 model satisfied turnover <= {MAX_TURNOVER} and expectancy > {MIN_EXPECTANCY_UNIT_R}."
    )

# Save best using multi-metric rank (PR-AUC primary, F1 tie-break)
best_model_name = max(results, key=lambda x: (x['Test_PR_AUC'], x['Test_F1']))['Model']
os.makedirs('models', exist_ok=True)

artifact_paths = {}

if best_model_name == 'lstm':
    lstm_bundle = best_models['lstm']
    torch_path = 'models/best_ml_gatekeeper_lstm.pt'
    torch.save(lstm_bundle['model'].state_dict(), torch_path)
    artifact_paths['model'] = torch_path

    preprocessor_path = 'models/best_ml_gatekeeper_lstm_preprocessor.pkl'
    scaler_path = 'models/best_ml_gatekeeper_lstm_scaler.pkl'
    joblib.dump(lstm_bundle['preprocessor'], preprocessor_path)
    joblib.dump(lstm_bundle['scaler'], scaler_path)
    artifact_paths['preprocessor'] = preprocessor_path
    artifact_paths['scaler'] = scaler_path
else:
    sklearn_bundle = best_models[best_model_name]
    model_path = 'models/best_ml_gatekeeper_sklearn.pkl'
    preprocessor_path = 'models/best_ml_gatekeeper_preprocessor.pkl'
    joblib.dump(sklearn_bundle['model'], model_path)
    joblib.dump(sklearn_bundle['preprocessor'], preprocessor_path)
    artifact_paths['model'] = model_path
    artifact_paths['preprocessor'] = preprocessor_path

artifact_hashes = {path: hash_file(path) for path in artifact_paths.values()}

run_id = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
run_metadata = {
    'run_id': run_id,
    'seed': SEED,
    'timestamp_utc': datetime.utcnow().isoformat(),
    'row_count_total': int(len(df)),
    'row_count_train': int(len(train_df)),
    'row_count_test': int(len(test_df)),
    'data_window': {
        'train_start': str(train_df['Timestamp'].min()),
        'train_end': str(train_df['Timestamp'].max()),
        'test_start': str(test_df['Timestamp'].min()),
        'test_end': str(test_df['Timestamp'].max()),
    },
    'feature_columns': list(X_train_df.columns),
    'model_results': results,
    'best_model': best_model_name,
    'best_model_meta': best_model_meta.get(best_model_name, {}),
    'artifacts': artifact_paths,
    'artifact_hashes_sha256': artifact_hashes,
    'monitoring_gates': {
        'min_pr_auc': 0.15,
        'min_f1': 0.10,
        'max_brier': 0.30,
        'max_turnover': 0.35,
    },
}

metadata_path = f"models/ml_gatekeeper_run_{run_id}.json"
with open(metadata_path, 'w', encoding='utf-8') as f:
    json.dump(run_metadata, f, indent=2)

print(f"\nChampion model saved: {best_model_name}")
print(f"Run metadata saved: {metadata_path}")