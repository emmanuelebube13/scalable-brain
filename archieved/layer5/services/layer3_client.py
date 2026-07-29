"""Layer 3 service client — ML model metadata access.

Reads model artifacts from the models directory and performance
telemetry from Fact_Live_Trades. No model inference is performed here.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import sqlalchemy as sa

from layer5.api.config import MODELS_DIR, LAYER3_MANIFEST_PATH
from layer5.services.db_client import execute_to_records


def _load_manifest() -> Optional[Dict[str, Any]]:
    """Load the champion manifest or the most recent training run manifest."""
    if LAYER3_MANIFEST_PATH.exists():
        with open(LAYER3_MANIFEST_PATH, "r") as f:
            return json.load(f)
    json_files = sorted(MODELS_DIR.glob("ml_gatekeeper_run_*.json"))
    if not json_files:
        return None
    with open(json_files[-1], "r") as f:
        return json.load(f)


def get_model_metadata(engine: sa.engine.Engine) -> Dict[str, Any]:
    """Return champion model metadata sourced from the Layer 3 manifest."""
    manifest = _load_manifest()
    if not manifest:
        return {
            "modelName": "unknown",
            "trainingDate": datetime.utcnow(),
            "trainingDataSize": 0,
            "trainingDataRange": {"start": None, "end": None},
            "threshold": 0.0,
            "supportedGranularities": ["H1", "H4"],
            "version": "unknown",
        }

    best = manifest.get("best_model_meta", {})
    metrics = best.get("metrics", {})
    artifacts = manifest.get("artifacts", {})
    data_window = manifest.get("data_window", {})
    ts_utc = manifest.get("timestamp_utc", datetime.utcnow().isoformat())

    def _parse_dt(val: Optional[str]) -> Optional[datetime]:
        if not val:
            return None
        try:
            return datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                return datetime.fromisoformat(val)
            except ValueError:
                return None

    return {
        "modelName": Path(artifacts.get("model", "unknown")).name,
        "trainingDate": _parse_dt(ts_utc) or datetime.utcnow(),
        "trainingDataSize": manifest.get("row_count_train", 0),
        "trainingDataRange": {
            "start": _parse_dt(data_window.get("train_start")),
            "end": _parse_dt(data_window.get("train_end")),
        },
        "threshold": best.get("threshold", metrics.get("threshold", 0.5)),
        "supportedGranularities": ["H1", "H4"],
        "version": manifest.get("run_id", "unknown"),
    }


def get_model_performance(engine: sa.engine.Engine) -> List[Dict[str, Any]]:
    """Return training metrics from the manifest merged with live DB telemetry."""
    manifest = _load_manifest()
    train: Dict[str, float] = {}
    if manifest:
        best = manifest.get("best_model_meta", {})
        m = best.get("metrics", {})
        train = {
            "Precision": m.get("precision", 0.0),
            "Recall": m.get("recall", 0.0),
            "F1 Score": m.get("f1", 0.0),
            "PR AUC": m.get("pr_auc", 0.0),
            "Brier Score": m.get("brier", 0.0),
            "Expectancy (R)": m.get("expectancy_unit_r", 0.0),
        }

    live7d: float = 0.0
    live30d: float = 0.0
    q7d = sa.text("""
        SELECT AVG(CAST(CASE WHEN Actual_Outcome = 1 THEN 1.0 ELSE 0.0 END AS FLOAT)) * 100.0 AS wr
        FROM Fact_Live_Trades
        WHERE Is_Approved = 1 AND Actual_Outcome IS NOT NULL AND Timestamp >= now() - INTERVAL '7 days'
    """)
    q30d = sa.text("""
        SELECT AVG(CAST(CASE WHEN Actual_Outcome = 1 THEN 1.0 ELSE 0.0 END AS FLOAT)) * 100.0 AS wr
        FROM Fact_Live_Trades
        WHERE Is_Approved = 1 AND Actual_Outcome IS NOT NULL AND Timestamp >= now() - INTERVAL '30 days'
    """)
    r7 = execute_to_records(engine, q7d)
    r30 = execute_to_records(engine, q30d)
    if r7 and r7[0].get("wr") is not None:
        live7d = round(r7[0]["wr"], 1)
    if r30 and r30[0].get("wr") is not None:
        live30d = round(r30[0]["wr"], 1)

    metrics = [
        "Precision",
        "Recall",
        "F1 Score",
        "PR AUC",
        "Brier Score",
        "Expectancy (R)",
    ]
    return [
        {
            "metric": m,
            "training": round(train.get(m, 0.0), 3),
            "live7d": live7d if m in ("Precision", "Recall", "F1 Score") else 0.0,
            "live30d": live30d if m in ("Precision", "Recall", "F1 Score") else 0.0,
        }
        for m in metrics
    ]


def get_feature_importance() -> List[Dict[str, Any]]:
    """Return feature importances from the champion model artifact when available."""
    manifest = _load_manifest()
    features: List[str] = manifest.get("feature_columns", []) if manifest else []
    if not features:
        return []

    importances: Dict[str, float] = {}
    model_path = MODELS_DIR / "best_ml_gatekeeper_sklearn.pkl"
    if model_path.exists():
        try:
            import joblib

            model = joblib.load(model_path)
            if hasattr(model, "feature_importances_"):
                for f, imp in zip(features, model.feature_importances_):
                    importances[f] = float(imp)
        except Exception:
            pass

    if not importances:
        importances = {f: 0.0 for f in features}

    return [
        {"feature": f, "importance": round(importances.get(f, 0.0), 4)}
        for f in features
    ]


def get_calibration_data(engine: sa.engine.Engine) -> List[Dict[str, Any]]:
    """Compute calibration curve from live approved trades."""
    query = sa.text("""
        SELECT
            CAST(Confidence_Score * 10 AS INT) / 10.0 AS bucket,
            AVG(CAST(CASE WHEN Actual_Outcome = 1 THEN 1.0 ELSE 0.0 END AS FLOAT)) AS actual,
            COUNT(*) AS count
        FROM Fact_Live_Trades
        WHERE Is_Approved = 1
          AND Actual_Outcome IS NOT NULL
          AND Confidence_Score IS NOT NULL
        GROUP BY CAST(Confidence_Score * 10 AS INT) / 10.0
        ORDER BY bucket
    """)
    rows = execute_to_records(engine, query)
    return [
        {
            "predicted": round(float(r["bucket"]), 2),
            "actual": round(r["actual"], 3),
            "count": r["count"],
        }
        for r in rows
    ]


def get_drift_alerts(engine: sa.engine.Engine) -> List[Dict[str, Any]]:
    """Return drift alerts computed from live data vs manifest training contract."""
    manifest = _load_manifest()
    threshold = 0.5
    if manifest:
        best = manifest.get("best_model_meta", {})
        threshold = best.get("threshold", threshold)

    query = sa.text("""
        SELECT
            AVG(CAST(CASE WHEN Is_Approved = 1 THEN 1.0 ELSE 0.0 END AS FLOAT)) * 100.0 AS live_rate,
            AVG(CAST(CASE WHEN Confidence_Score BETWEEN :low AND :high THEN 1.0 ELSE 0.0 END AS FLOAT)) * 100.0 AS cluster_pct,
            COUNT(*) AS total
        FROM Fact_Live_Trades
        WHERE Timestamp >= now() - INTERVAL '7 days'
    """)
    rows = execute_to_records(
        engine, query, {"low": threshold - 0.025, "high": threshold + 0.025}
    )
    alerts: List[Dict[str, Any]] = []
    if rows and rows[0].get("live_rate") is not None:
        live_rate = rows[0]["live_rate"]
        cluster_pct = rows[0].get("cluster_pct") or 0.0
        if live_rate < 50:
            alerts.append(
                {
                    "type": "approval_rate",
                    "message": f"Live approval rate ({live_rate:.1f}%) below 50%",
                    "severity": "warning",
                    "timestamp": datetime.now() - timedelta(hours=4),
                }
            )
        if cluster_pct > 20:
            alerts.append(
                {
                    "type": "distribution",
                    "message": f"High concentration near threshold ({cluster_pct:.1f}% of signals)",
                    "severity": "critical" if cluster_pct > 30 else "warning",
                    "timestamp": datetime.now() - timedelta(hours=2),
                }
            )
    return alerts
