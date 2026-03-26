"""
retrain_orchestrator.py - Continuous Training (CT) Pipeline for Scalable Brain
================================================================================
ICE 4 Deliverable: Production-grade Champion vs. Challenger model retraining
orchestrator with compliance audit logging and rollback capability.

Pipeline Steps:
    1. Ingest latest regime + trade outcome data from ForexBrainDB (SQL Server)
    2. Preprocess (One-Hot Encoding, dropna) and chronological 80/20 split
    3. Train XGBoost Challenger model
    4. Score Challenger vs. existing Champion on the same holdout set
    5. Promote Challenger only if AUC strictly improves; archive every artifact
    6. Generate detailed compliance report to logs/model_performance_results.txt
"""

import os
import sys
import shutil
import logging
from datetime import datetime

import pandas as pd
import numpy as np
import joblib
import sqlalchemy as sa
import urllib.parse
from dotenv import load_dotenv
from xgboost import XGBClassifier
from sklearn.metrics import (
    roc_auc_score,
    accuracy_score,
    classification_report,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Resolve all paths relative to the project root (one level up from scripts/)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
CHAMPION_PATH = os.path.join(PROJECT_ROOT, "models", "best_ml_gatekeeper.pkl")
ARCHIVE_DIR = os.path.join(PROJECT_ROOT, "models", "archive")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
REPORT_PATH = os.path.join(LOG_DIR, "model_performance_results.txt")

# Ensure output directories exist
os.makedirs(ARCHIVE_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# Console + file logging for operational monitoring
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, "retrain_orchestrator.log")),
    ],
)
log = logging.getLogger("retrain_orchestrator")

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_engine():
    """Create a SQLAlchemy engine from .env credentials."""
    load_dotenv(ENV_PATH)
    db_server = os.getenv("DB_SERVER", "localhost")
    db_user = os.getenv("DB_USER")
    db_pass = os.getenv("DB_PASS")
    db_name = os.getenv("DB_NAME", "ForexBrainDB")

    if not db_user or not db_pass:
        log.error("DB_USER or DB_PASS not set in .env - aborting.")
        sys.exit(1)

    conn_str = urllib.parse.quote_plus(
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={db_server};DATABASE={db_name};"
        f"UID={db_user};PWD={db_pass}"
    )
    return sa.create_engine(f"mssql+pyodbc:///?odbc_connect={conn_str}")

# ---------------------------------------------------------------------------
# Data ingestion & preprocessing
# ---------------------------------------------------------------------------

TRAINING_QUERY = """
SELECT
    fmr.Regime_Label,
    fmr.ATR_Value,
    fmr.ADX_Value,
    fs.Asset_ID,
    fs.Strategy_ID,
    fs.Signal_Value,
    fto.Is_Winner
FROM
    Fact_Market_Regime  fmr
INNER JOIN
    Fact_Signals        fs  ON fmr.Timestamp = fs.Timestamp
                            AND fmr.Asset_ID  = fs.Asset_ID
INNER JOIN
    Fact_Trade_Outcomes fto ON fs.Timestamp   = fto.Timestamp
                            AND fs.Asset_ID   = fto.Asset_ID
                            AND fs.Strategy_ID = fto.Strategy_ID
ORDER BY
    fs.Timestamp ASC
"""


def ingest_and_preprocess(engine):
    """Pull training data, clean, one-hot encode, and chronological split."""
    log.info("Fetching training data from ForexBrainDB ...")
    df = pd.read_sql(TRAINING_QUERY, engine)
    row_count_raw = len(df)
    log.info(f"Raw rows fetched: {row_count_raw}")

    df = df.dropna()
    log.info(f"Rows after dropna: {len(df)}")

    if len(df) < 50:
        log.error("Insufficient data for training (< 50 rows). Aborting.")
        sys.exit(1)

    # One-hot encode categorical columns (mirrors train_ml_gatekeeper.py)
    df = pd.get_dummies(
        df,
        columns=["Regime_Label", "Asset_ID", "Strategy_ID"],
        drop_first=True,
    )

    X = df.drop("Is_Winner", axis=1)
    y = df["Is_Winner"]

    # Strict chronological split - no shuffle (time-series integrity)
    split_idx = int(len(X) * 0.80)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    log.info(
        f"Split -> Train: {len(X_train)} rows | Test: {len(X_test)} rows"
    )
    return X_train, X_test, y_train, y_test, row_count_raw

# ---------------------------------------------------------------------------
# Model training
# ---------------------------------------------------------------------------

def train_challenger(X_train, y_train):
    """Train a new XGBoost Challenger model."""
    log.info("Training XGBoost Challenger model ...")
    challenger = XGBClassifier(
        n_estimators=150,
        max_depth=6,
        learning_rate=0.1,
        scale_pos_weight=3,       # 3x weight on winners (matches existing pipeline)
        random_state=42,
        use_label_encoder=False,
        eval_metric="logloss",
    )
    challenger.fit(X_train, y_train)
    log.info("Challenger training complete.")
    return challenger

# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def evaluate_model(model, X_test, y_test, label="Model"):
    """Return AUC-ROC, accuracy, and classification report for a model."""
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    auc = roc_auc_score(y_test, y_proba)
    acc = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, zero_division=0)

    log.info(f"{label} -> AUC: {auc:.4f} | Accuracy: {acc:.4f}")
    return auc, acc, report


def get_feature_importances(model, feature_names, top_n=5):
    """Extract top-N feature importances from tree-based model."""
    importances = model.feature_importances_
    fi = pd.Series(importances, index=feature_names).sort_values(ascending=False)
    return fi.head(top_n)

# ---------------------------------------------------------------------------
# Champion vs. Challenger promotion logic
# ---------------------------------------------------------------------------

def load_champion(X_test, y_test):
    """Load the existing champion and evaluate it on the SAME test set.

    If the champion cannot be loaded or its feature set doesn't match,
    return None so the Challenger wins by default.
    """
    if not os.path.exists(CHAMPION_PATH):
        log.warning("No existing champion found - Challenger wins by default.")
        return None, None, None, None

    try:
        champion = joblib.load(CHAMPION_PATH)
    except Exception as exc:
        log.warning(f"Failed to load champion model: {exc}")
        return None, None, None, None

    # Align features: the champion may have been trained on a different OHE set.
    expected = list(getattr(champion, "feature_names_in_", []))
    if not expected:
        log.warning("Champion lacks feature_names_in_ - skipping comparison.")
        return None, None, None, None

    # Build an aligned test set (missing cols filled with 0, extra cols dropped)
    X_aligned = X_test.reindex(columns=expected, fill_value=0)

    try:
        auc, acc, report = evaluate_model(champion, X_aligned, y_test, label="Champion")
        return champion, auc, acc, report
    except Exception as exc:
        log.warning(f"Champion evaluation failed: {exc}")
        return None, None, None, None

# ---------------------------------------------------------------------------
# Compliance audit report (ICE 4 requirement)
# ---------------------------------------------------------------------------

def write_report(
    timestamp,
    dataset_size,
    challenger_auc,
    challenger_acc,
    challenger_report,
    champion_auc,
    feature_importances,
    promoted,
):
    """Write a detailed text report to logs/model_performance_results.txt."""
    separator = "=" * 70

    lines = [
        separator,
        "  SCALABLE BRAIN - MODEL RETRAINING COMPLIANCE REPORT",
        separator,
        f"  Run Timestamp   : {timestamp}",
        f"  Dataset Size    : {dataset_size} rows (raw, pre-dropna)",
        separator,
        "",
        "--- CHALLENGER MODEL (XGBoost) ---",
        f"  AUC-ROC  : {challenger_auc:.6f}",
        f"  Accuracy : {challenger_acc:.6f}",
        "",
        "  Classification Report:",
        challenger_report,
        "",
        "--- TOP 5 FEATURE IMPORTANCES ---",
    ]

    for feat, imp in feature_importances.items():
        lines.append(f"  {feat:<40s} {imp:.6f}")

    lines += [
        "",
        separator,
        f"  Champion AUC : {champion_auc if champion_auc is not None else 'N/A (no prior champion)'}",
        f"  Challenger AUC : {challenger_auc:.6f}",
        "",
    ]

    if promoted:
        lines.append(
            "  >> DECISION: CHALLENGER PROMOTED TO PRODUCTION <<"
        )
    else:
        lines.append(
            "  >> DECISION: CHALLENGER REJECTED - CHAMPION RETAINED <<"
        )

    lines += [separator, ""]

    report_text = "\n".join(lines)

    with open(REPORT_PATH, "w") as f:
        f.write(report_text)

    log.info(f"Compliance report written to {REPORT_PATH}")

    # Also print to stdout for cron visibility
    print(report_text)

# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def main():
    run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_tag = datetime.now().strftime("%Y%m%d")
    log.info(f"=== Continuous Training Pipeline Started | {run_ts} ===")

    # 1. Data ingestion & preprocessing
    engine = get_engine()
    X_train, X_test, y_train, y_test, dataset_size = ingest_and_preprocess(engine)

    # 2. Train Challenger
    challenger = train_challenger(X_train, y_train)
    challenger_auc, challenger_acc, challenger_report = evaluate_model(
        challenger, X_test, y_test, label="Challenger"
    )

    # 3. Feature importances
    feature_importances = get_feature_importances(
        challenger, X_train.columns.tolist()
    )

    # 4. Archive the Challenger artifact (always, for rollback)
    archive_path = os.path.join(ARCHIVE_DIR, f"xgb_{date_tag}.pkl")
    joblib.dump(challenger, archive_path)
    log.info(f"Challenger archived to {archive_path}")

    # 5. Champion vs. Challenger
    _, champion_auc, _, _ = load_champion(X_test, y_test)

    promoted = False
    if champion_auc is None:
        # No valid champion - auto-promote
        promoted = True
    elif challenger_auc > champion_auc:
        promoted = True

    if promoted:
        # Back up current champion before overwriting
        if os.path.exists(CHAMPION_PATH):
            backup_path = os.path.join(ARCHIVE_DIR, f"champion_backup_{date_tag}.pkl")
            shutil.copy2(CHAMPION_PATH, backup_path)
            log.info(f"Previous champion backed up to {backup_path}")

        joblib.dump(challenger, CHAMPION_PATH)
        log.info("Challenger PROMOTED to production.")
    else:
        log.info(
            f"Challenger REJECTED (AUC {challenger_auc:.4f} <= Champion {champion_auc:.4f}). "
            "Champion retained."
        )

    # 6. Compliance report
    write_report(
        timestamp=run_ts,
        dataset_size=dataset_size,
        challenger_auc=challenger_auc,
        challenger_acc=challenger_acc,
        challenger_report=challenger_report,
        champion_auc=champion_auc,
        feature_importances=feature_importances,
        promoted=promoted,
    )

    log.info("=== Continuous Training Pipeline Complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
