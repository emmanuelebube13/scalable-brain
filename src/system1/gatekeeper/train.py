"""MODEL-006 — train the regime-aware ML gatekeeper with OOS uplift gating.

Training set = backtested trades (fact_trade_outcomes) joined point-in-time to the CAUSAL
regime (fact_market_regime_v2.regime_causal / prob_causal_* — walk-forward filtered
forward-only labels, FIX-S1-005; the leaked reporting-only smoothed columns are never
consumed): features = [atr_value, adx_value, prob_causal_trending_up/down/ranging/high_vol]
+ causal regime / strategy_id / entry_signal_type (one-hot); label = is_winner.
Expanding-window walk-forward folds calibrate a regime-aware dynamic threshold and measure
OOS uplift (approved vs rejected r_multiple, bootstrap-significant).

Writes the champion contract. Use ``--dry-run`` to write a PROPOSED bundle
(models/proposed_champion_*) without overwriting the live champion (log-only; rule #1).

Usage: python -m src.system1.gatekeeper.train --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.model_selection import GridSearchCV
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sqlalchemy import text
from xgboost import XGBClassifier

from src.common.db import get_engine
from src.system1.gatekeeper import thresholds as TH

logger = logging.getLogger("system1.gatekeeper")

REGIME_MODEL_VERSION = "hmm-v1.0.0"
FEATURE_SET_VERSION = "1.0.0"
# FIX-S1-005: the gatekeeper trains on the CAUSAL regime label/probs (walk-forward,
# filtered forward-only) — never the reporting-only smoothed columns, which leak the
# future into a past bar and contaminate the OOS uplift proof.
NUMERIC = [
    "atr_value",
    "adx_value",
    "prob_causal_trending_up",
    "prob_causal_trending_down",
    "prob_causal_ranging",
    "prob_causal_high_vol",
]
CATEGORICAL = ["regime_causal", "strategy_id", "entry_signal_type"]
REGIME_FEATURES = [
    "prob_causal_trending_up",
    "prob_causal_trending_down",
    "prob_causal_ranging",
    "prob_causal_high_vol",
    "regime_causal",
]
MIN_TURNOVER, MAX_TURNOVER = 0.05, 0.60
N_FOLDS = 5
N_BOOTSTRAP = 20000
SEED = 42
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MODELS_DIR = os.path.join(_REPO_ROOT, "models")

PARAM_GRID = {
    "max_depth": [3, 4, 5],
    "n_estimators": [100, 200, 300],
    "learning_rate": [0.03, 0.05, 0.08],
    "subsample": [0.7, 0.8, 0.9],
}


class GatekeeperRefused(Exception):
    pass


def build_frame() -> pd.DataFrame:
    """Trades joined point-in-time (regime bar <= entry) to CAUSAL regime probs + features.

    FIX-S1-005: joins ``regime_causal`` / ``prob_causal_*`` (walk-forward, filtered
    forward-only) — the only labels safe to train/score on. Warm-up bars have
    ``regime_causal IS NULL`` and are excluded by the join filter.
    """
    engine = get_engine()
    with engine.connect() as conn:
        trades = pd.read_sql(
            text(
                'SELECT outcome_id, "timestamp" AS entry_time, asset_id, granularity, strategy_id, '
                "entry_signal_type, is_winner, r_multiple FROM fact_trade_outcomes"
            ),
            conn,
        )
        regimes = pd.read_sql(
            text(
                'SELECT asset_id, granularity, "timestamp" AS bar_time, regime_causal, '
                "atr_value, adx_value, prob_causal_trending_up, prob_causal_trending_down, "
                "prob_causal_ranging, prob_causal_high_vol "
                "FROM fact_market_regime_v2 WHERE regime_causal IS NOT NULL"
            ),
            conn,
        )
    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)
    regimes["bar_time"] = pd.to_datetime(regimes["bar_time"], utc=True)
    parts = []
    for (aid, gran), tg in trades.groupby(["asset_id", "granularity"]):
        rg = regimes[
            (regimes["asset_id"] == aid) & (regimes["granularity"] == gran)
        ].sort_values("bar_time")
        if rg.empty:
            continue
        merged = pd.merge_asof(
            tg.sort_values("entry_time"),
            rg,
            left_on="entry_time",
            right_on="bar_time",
            direction="backward",
        )
        parts.append(merged)
    frame = pd.concat(parts, ignore_index=True)
    frame["strategy_id"] = frame["strategy_id"].astype(str)
    frame["entry_signal_type"] = frame["entry_signal_type"].astype(str)
    frame = frame.dropna(subset=NUMERIC + CATEGORICAL)
    return frame.sort_values("entry_time").reset_index(drop=True)


def _derive_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived interaction features (no look-ahead)."""
    df = df.copy()
    df["volatility_regime"] = (df["prob_causal_high_vol"] > 0.3).astype(float)
    df["trending_strength"] = (
        df["prob_causal_trending_up"] + df["prob_causal_trending_down"]
    )
    df["adx_over_atr"] = np.where(
        df["atr_value"] > 1e-8, df["adx_value"] / df["atr_value"], 0.0
    )
    return df


NUMERIC_DERIVED = NUMERIC + ["volatility_regime", "trending_strength", "adx_over_atr"]


def _make_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        [
            ("num", StandardScaler(), NUMERIC_DERIVED),
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL,
            ),
        ]
    )


def _fit_model(pre: ColumnTransformer, X: pd.DataFrame, y: np.ndarray) -> XGBClassifier:
    """Fit with hyperparameter search, using class-weight for imbalanced winners (~38%)."""
    Xt = pre.transform(X)
    scale_pos = max(1.0, float((y == 0).sum() / max(1, (y == 1).sum())))
    base = XGBClassifier(
        eval_metric="logloss",
        random_state=SEED,
        n_jobs=4,
        verbosity=0,
        scale_pos_weight=scale_pos,
    )
    gs = GridSearchCV(
        base,
        PARAM_GRID,
        scoring="neg_log_loss",
        cv=3,
        n_jobs=4,
        verbose=0,
    )
    gs.fit(Xt, y)
    logger.info("best params: %s", gs.best_params_)
    return gs.best_estimator_


def _scores(model, pre, X) -> np.ndarray:
    return model.predict_proba(pre.transform(X))[:, 1]


def _walk_forward(frame: pd.DataFrame) -> Dict[str, Any]:
    """Expanding-window folds -> aggregated OOS approved/rejected returns + per-regime thresholds."""
    blocks = np.array_split(frame, N_FOLDS + 1)
    approved_all: List[float] = []
    rejected_all: List[float] = []
    last_thresholds: Dict[str, float] = {}
    feature_cols = NUMERIC_DERIVED + CATEGORICAL
    for i in range(1, N_FOLDS + 1):
        train = pd.concat(blocks[:i]).reset_index(drop=True)
        oos = blocks[i]
        cut = int(len(train) * 0.8)
        tr, val = train.iloc[:cut], train.iloc[cut:]
        if len(tr) < 200 or len(val) < 50 or len(oos) < 50:
            continue
        pre = _make_preprocessor().fit(tr[feature_cols])
        model = _fit_model(pre, tr[feature_cols], tr["is_winner"].to_numpy())
        val_scores = _scores(model, pre, val[feature_cols])
        thr_map = _calibrate_regime_thresholds(val, val_scores)
        last_thresholds = thr_map
        oos_scores = _scores(model, pre, oos[feature_cols])
        approved_mask = _apply_thresholds(oos, oos_scores, thr_map)
        approved_all.extend(oos["r_multiple"].to_numpy()[approved_mask].tolist())
        rejected_all.extend(oos["r_multiple"].to_numpy()[~approved_mask].tolist())
    return {
        "approved": approved_all,
        "rejected": rejected_all,
        "thresholds": last_thresholds,
    }


def _calibrate_regime_thresholds(
    df: pd.DataFrame, scores: np.ndarray
) -> Dict[str, float]:
    thr_map: Dict[str, float] = {}
    for regime, idx in df.groupby("regime_causal").groups.items():
        pos = df.index.get_indexer(idx)
        s = scores[pos]
        r = df["r_multiple"].to_numpy()[pos]
        if len(s) >= 30:
            thr, _ = TH.calibrate_threshold(s, r, MIN_TURNOVER, MAX_TURNOVER)
            thr_map[str(regime)] = thr
    thr_map["fallback"], _ = TH.calibrate_threshold(
        scores, df["r_multiple"].to_numpy(), MIN_TURNOVER, MAX_TURNOVER
    )
    return thr_map


def _apply_thresholds(
    df: pd.DataFrame, scores: np.ndarray, thr_map: Dict[str, float]
) -> np.ndarray:
    thr = (
        df["regime_causal"]
        .map(lambda r: thr_map.get(str(r), thr_map["fallback"]))
        .to_numpy()
    )
    return scores >= thr


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def run(register_mlflow: bool = True, dry_run: bool = False) -> Dict[str, Any]:
    """Train the gatekeeper and write the champion bundle.

    ``dry_run=True`` (the FIX-S1-005 default invocation) writes a PROPOSED bundle
    (``models/proposed_champion_model.pkl`` / ``proposed_champion_preprocessor.pkl`` /
    ``proposed_champion_manifest.json``) and NEVER overwrites the live champion bundle
    — honouring global rule #1 (log-only, no auto-promotion). The trainer previously
    always overwrote ``champion_model.pkl`` etc. (silent auto-promote); that is now
    gated behind the explicit (non-dry-run) path.
    """
    frame = build_frame()
    frame = _derive_features(frame)
    logger.info(
        "Training frame: %d trades, win rate %.3f",
        len(frame),
        frame["is_winner"].mean(),
    )

    wf = _walk_forward(frame)
    uplift, p_value, significant = TH.oos_uplift_test(
        wf["approved"],
        wf["rejected"],
        n_bootstrap=N_BOOTSTRAP,
        seed=SEED,
    )
    n_app, n_rej = len(wf["approved"]), len(wf["rejected"])
    oos_approval = n_app / (n_app + n_rej) if (n_app + n_rej) else 0.0
    logger.info(
        "OOS uplift=%.6f p=%.6f sig=%s approval=%.4f n_approved=%d n_rejected=%d",
        uplift,
        p_value,
        significant,
        oos_approval,
        n_app,
        n_rej,
    )

    if TH.is_degenerate(oos_approval, MIN_TURNOVER, MAX_TURNOVER):
        raise GatekeeperRefused(
            f"degenerate approval rate {oos_approval:.3f} outside [{MIN_TURNOVER},{MAX_TURNOVER}]"
        )

    feature_cols = NUMERIC_DERIVED + CATEGORICAL
    pre = _make_preprocessor().fit(frame[feature_cols])
    model = _fit_model(pre, frame[feature_cols], frame["is_winner"].to_numpy())
    dynamic_thresholds = wf["thresholds"]

    os.makedirs(MODELS_DIR, exist_ok=True)
    prefix = "proposed_champion" if dry_run else "champion"
    model_basename = f"{prefix}_model.pkl"
    pre_basename = f"{prefix}_preprocessor.pkl"
    manifest_basename = f"{prefix}_manifest.json"
    model_path = os.path.join(MODELS_DIR, model_basename)
    pre_path = os.path.join(MODELS_DIR, pre_basename)
    joblib.dump(model, model_path)
    joblib.dump(pre, pre_path)
    manifest = {
        "model_type": "xgboost",
        "schema_version": "1.0.0",
        "features": feature_cols,
        "regime_features": REGIME_FEATURES,
        "dynamic_thresholds": dynamic_thresholds,
        "turnover_band": [MIN_TURNOVER, MAX_TURNOVER],
        "oos_uplift": {
            "uplift": round(uplift, 6),
            "p_value": round(p_value, 6),
            "significant": significant,
            "oos_approval_rate": round(oos_approval, 4),
            "n_approved": n_app,
            "n_rejected": n_rej,
            "n_folds": N_FOLDS,
        },
        "regime_model_version": REGIME_MODEL_VERSION,
        "feature_set_version": FEATURE_SET_VERSION,
        "n_train": int(len(frame)),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "sha256": {
            model_basename: _sha256(model_path),
            pre_basename: _sha256(pre_path),
        },
    }
    manifest_path = os.path.join(MODELS_DIR, manifest_basename)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    manifest["sha256"][manifest_basename] = _sha256(manifest_path)

    result = {
        "n_train": len(frame),
        "oos_uplift": uplift,
        "p_value": p_value,
        "significant": significant,
        "oos_approval_rate": oos_approval,
        "dynamic_thresholds": dynamic_thresholds,
        "manifest": manifest_path,
        "dry_run": dry_run,
    }
    if register_mlflow:
        result["mlflow_run_id"] = _register_mlflow(manifest)
    logger.info(
        "MODEL-006 %s bundle written: %s",
        "PROPOSED (dry-run, live champion untouched)" if dry_run else "champion",
        model_path,
    )
    return result


def _register_mlflow(manifest) -> str:
    try:
        import mlflow
        from src.system1.features.feature_pipeline import _resolve_mlflow_uri

        mlflow.set_tracking_uri(_resolve_mlflow_uri())
        mlflow.set_experiment("system1-gatekeeper")
        with mlflow.start_run(run_name="gatekeeper") as run:
            mlflow.log_param("regime_features", ",".join(REGIME_FEATURES))
            mlflow.log_param("features", ",".join(manifest["features"]))
            mlflow.log_param("turnover_band", str(manifest["turnover_band"]))
            mlflow.log_metric("oos_uplift", manifest["oos_uplift"]["uplift"])
            mlflow.log_metric("oos_p_value", manifest["oos_uplift"]["p_value"])
            mlflow.log_metric(
                "oos_approval_rate", manifest["oos_uplift"]["oos_approval_rate"]
            )
            mlflow.log_artifact(os.path.join(MODELS_DIR, "champion_manifest.json"))
            return run.info.run_id
    except Exception as e:  # noqa: BLE001
        logger.error("MLflow registration failed: %s", e)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="MODEL-006 gatekeeper trainer")
    parser.add_argument("--no-mlflow", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write models/proposed_champion_* and never overwrite the live champion "
        "(log-only; global rule #1). Default invocation for FIX-S1-005.",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    try:
        print(run(register_mlflow=not args.no_mlflow, dry_run=args.dry_run))
    except GatekeeperRefused as e:
        logger.error("GATEKEEPER REFUSED: %s", e)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
