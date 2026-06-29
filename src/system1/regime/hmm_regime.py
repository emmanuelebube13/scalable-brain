"""MODEL-003 — 4-state Gaussian HMM regime engine (K-Means fallback retained).

For each regime granularity (D1 primary, H4, H1 legacy) the engine:
  1. computes the regime feature vector via the shared MODEL-002 definitions,
  2. fits a fixed-seed 4-state Gaussian HMM (per-instrument sequences),
  3. deterministically maps states → {Trending-Up, Trending-Down, Ranging, High-Vol},
  4. emits per-bar probabilities + a 3-bar persistence-smoothed label,
  5. falls back to K-Means if the HMM fails a quality/accuracy gate,
  6. upserts additive columns into fact_market_regime_v2 and serialises the model.

Run detached (HMM EM is multi-minute on H1):
    python -m src.system1.regime.hmm_regime            # all granularities
    python -m src.system1.regime.hmm_regime --granularity D1
"""
from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from psycopg2.extras import execute_values
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text

from src.common.db import get_engine
from src.layer0.ingest_oanda_prices import get_db_connection, read_env
from src.system1.features import definitions as D
from src.system1.regime import mapping as M
from src.system1.regime import schema as regime_schema

logger = logging.getLogger("system1.regime.hmm")

# HMM input = the MODEL-002 regime feature contract plus a point-in-time persistent
# trend (trailing-20 mean of returns_1) so directional regimes are learnable. trend_20
# is derived here (causal); it does NOT change the MODEL-002 feature-store schema.
DIRECTION_FEATURE = "trend_20"
TREND_WINDOW = 20
FEATURE_NAMES: List[str] = D.REGIME_FEATURE_COLUMNS + [DIRECTION_FEATURE]
# Post-standardization weights. atr_14/volatility_20/adx_14 are all volatility proxies,
# so an unweighted HMM carves volatility bands and ignores direction. Upweighting the
# persistent trend lets the model separate directional regimes (Up/Down) too.
FEATURE_WEIGHTS = {"atr_14": 1.0, "adx_14": 1.0, "volatility_20": 1.0, "returns_1": 0.5, "trend_20": 3.0}
REGIME_GRANULARITIES = ["D1", "H4", "H1"]
SEED = 42
MODEL_VERSION = "hmm-v1.0.0"
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MODEL_PATH = os.path.join(_REPO_ROOT, "models", "hmm_model.joblib")
HOLDOUT_FRAC = 0.20
ACCURACY_GATE = 0.70


# --------------------------------------------------------------------------- #
# Data loading (reuses MODEL-002 feature definitions)
# --------------------------------------------------------------------------- #
def load_features(conn, granularity: str) -> pd.DataFrame:
    """Per-instrument feature computation; returns rows with all regime features non-null."""
    sql = (
        'SELECT asset_id, "timestamp" AS bar_time_utc, "Open" AS open, high, low, '
        '"Close" AS close, volume FROM fact_market_prices WHERE granularity = %s '
        'ORDER BY asset_id, "timestamp"'
    )
    df = pd.read_sql(sql, conn, params=(granularity,))
    df["bar_time_utc"] = pd.to_datetime(df["bar_time_utc"], utc=True)
    frames = []
    for _, grp in df.groupby("asset_id", sort=True):
        grp = grp.sort_values("bar_time_utc").reset_index(drop=True)
        feats = D.compute_features(grp)
        # Derived point-in-time persistent trend (trailing mean of 1-bar log returns).
        feats[DIRECTION_FEATURE] = (
            feats["returns_1"].rolling(TREND_WINDOW, min_periods=TREND_WINDOW).mean()
        )
        frames.append(feats)
    out = pd.concat(frames, ignore_index=True)
    out = out.dropna(subset=FEATURE_NAMES).reset_index(drop=True)
    return out.sort_values(["asset_id", "bar_time_utc"]).reset_index(drop=True)


def _sequences(df: pd.DataFrame) -> Tuple[np.ndarray, List[int]]:
    """Stacked feature matrix + per-instrument sequence lengths (for hmmlearn)."""
    lengths = []
    mats = []
    for _, grp in df.groupby("asset_id", sort=True):
        mats.append(grp[FEATURE_NAMES].to_numpy(dtype="float64"))
        lengths.append(len(grp))
    return np.vstack(mats), lengths


# --------------------------------------------------------------------------- #
# HMM fit + fallback
# --------------------------------------------------------------------------- #
def fit_hmm(Xs: np.ndarray, lengths: List[int]) -> GaussianHMM:
    hmm = GaussianHMM(
        n_components=4,
        covariance_type="diag",
        n_iter=1000,
        tol=1e-4,
        random_state=SEED,
        init_params="stmc",
        verbose=False,
    )
    hmm.fit(Xs, lengths)
    return hmm


def kmeans_fallback(Xs: np.ndarray) -> Tuple[np.ndarray, np.ndarray, Dict[int, str], Any]:
    """4-cluster K-Means fallback. Returns (labels, onehot_probs, mapping, model)."""
    km = KMeans(n_clusters=4, random_state=SEED, n_init=10).fit(Xs)
    mapping = M.map_states_to_labels(km.cluster_centers_, FEATURE_NAMES, DIRECTION_FEATURE)
    labels = km.labels_
    onehot = np.zeros((len(labels), 4))
    onehot[np.arange(len(labels)), labels] = 1.0
    return labels, onehot, mapping, km


# --------------------------------------------------------------------------- #
# Persistence + per-instrument assembly
# --------------------------------------------------------------------------- #
def assemble_regime_rows(
    df: pd.DataFrame,
    raw_state: np.ndarray,
    probs_state: np.ndarray,
    mapping: Dict[int, str],
    model_name: str,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Map states→labels, order probs, smooth per instrument; return rows + flicker stats."""
    ordered_probs = M.order_probabilities(probs_state, mapping)
    # regime_raw = argmax of the (semantic-ordered) probability vector, so that
    # argmax(prob_*) == regime_raw holds for every row (the posterior argmax can differ
    # from the Viterbi state used for quality checks). For K-Means probs are one-hot.
    raw_idx = np.argmax(ordered_probs, axis=1)
    raw_labels = np.array([M.SEMANTIC_ORDER[i] for i in raw_idx])
    df = df.copy()
    df["regime_raw"] = raw_labels
    for i, col in enumerate(M.PROB_COLUMNS):
        df[col] = ordered_probs[:, i]

    smoothed_all = np.empty(len(df), dtype=object)
    flick_raw, flick_sm, segs = [], [], 0
    for _, grp in df.groupby("asset_id", sort=True):
        idx = grp.index.to_numpy()
        raw_seq = grp["regime_raw"].tolist()
        sm = M.persistence_smooth(raw_seq, min_bars=3) if model_name == "HMM" else raw_seq
        smoothed_all[idx] = sm
        flick_raw.append(M.flicker_rate(raw_seq))
        flick_sm.append(M.flicker_rate(sm))
    df["regime_smoothed"] = smoothed_all
    stats = {
        "flicker_raw": float(np.mean(flick_raw)) if flick_raw else 0.0,
        "flicker_smoothed": float(np.mean(flick_sm)) if flick_sm else 0.0,
    }
    return df, stats


# --------------------------------------------------------------------------- #
# DB write
# --------------------------------------------------------------------------- #
UPSERT_SQL = """
    INSERT INTO fact_market_regime_v2
        (asset_id, "timestamp", granularity, regime_label, atr_value, adx_value,
         regime_model_version, regime_model, regime_raw, regime_smoothed,
         prob_trending_up, prob_trending_down, prob_ranging, prob_high_vol, model_version)
    VALUES %s
    ON CONFLICT ("timestamp", asset_id, granularity) DO UPDATE SET
        regime_label = EXCLUDED.regime_label,
        atr_value = EXCLUDED.atr_value,
        adx_value = EXCLUDED.adx_value,
        regime_model_version = EXCLUDED.regime_model_version,
        regime_model = EXCLUDED.regime_model,
        regime_raw = EXCLUDED.regime_raw,
        regime_smoothed = EXCLUDED.regime_smoothed,
        prob_trending_up = EXCLUDED.prob_trending_up,
        prob_trending_down = EXCLUDED.prob_trending_down,
        prob_ranging = EXCLUDED.prob_ranging,
        prob_high_vol = EXCLUDED.prob_high_vol,
        model_version = EXCLUDED.model_version
"""


def write_rows(conn, df: pd.DataFrame, granularity: str, model_name: str) -> int:
    rows = [
        (
            int(r.asset_id),
            r.bar_time_utc.to_pydatetime(),
            granularity,
            r.regime_smoothed,
            float(r.atr_14),
            float(r.adx_14),
            MODEL_VERSION,
            model_name,
            r.regime_raw,
            r.regime_smoothed,
            float(r.prob_trending_up),
            float(r.prob_trending_down),
            float(r.prob_ranging),
            float(r.prob_high_vol),
            MODEL_VERSION,
        )
        for r in df.itertuples(index=False)
    ]
    cur = conn.cursor()
    execute_values(cur, UPSERT_SQL, rows, page_size=2000)
    conn.commit()
    return len(rows)


# --------------------------------------------------------------------------- #
# Per-granularity driver
# --------------------------------------------------------------------------- #
def _train_mask(df: pd.DataFrame) -> np.ndarray:
    """Per-instrument time-based train mask: last HOLDOUT_FRAC of each sequence = holdout."""
    pos = df.groupby("asset_id").cumcount().to_numpy()
    size = df.groupby("asset_id")["asset_id"].transform("size").to_numpy()
    return pos < (size * (1 - HOLDOUT_FRAC))


def _train_sequences(X: np.ndarray, df: pd.DataFrame, train_mask: np.ndarray) -> Tuple[np.ndarray, List[int]]:
    """Contiguous per-instrument TRAIN feature matrix + lengths (for a reference fit)."""
    mats, lengths, start = [], [], 0
    for _, grp in df.groupby("asset_id", sort=True):
        n = len(grp)
        m = train_mask[start : start + n]
        mats.append(X[start : start + n][m])
        lengths.append(int(m.sum()))
        start += n
    return np.vstack(mats), lengths


def _reference_labels(
    X: np.ndarray, df: pd.DataFrame, lengths: List[int], train_mask: np.ndarray, kind: str
) -> List[str]:
    """Semantic regime labels from a reference model fit on the TRAIN split only.

    Out-of-sample stability reference: a model of the same kind, fit on train only, is
    used to label *all* bars. Agreement between this and the production model (fit on
    all data) on the holdout measures whether the regime structure generalises.
    """
    Xtr, tr_lengths = _train_sequences(X, df, train_mask)
    if kind == "HMM":
        ref = fit_hmm(Xtr, tr_lengths)
        states = ref.predict(X, lengths)
        means = ref.means_
    else:
        ref = KMeans(n_clusters=4, random_state=SEED, n_init=10).fit(Xtr)
        states = ref.predict(X)
        means = ref.cluster_centers_
    mp = M.map_states_to_labels(means, FEATURE_NAMES, DIRECTION_FEATURE)
    return [mp[s] for s in states]


def process_granularity(conn, granularity: str) -> Dict[str, Any]:
    logger.info("[%s] loading features…", granularity)
    df = load_features(conn, granularity)
    n = len(df)
    logger.info("[%s] %d feature rows across %d instruments", granularity, n, df["asset_id"].nunique())

    scaler = StandardScaler()
    Xs = scaler.fit_transform(df[FEATURE_NAMES].to_numpy(dtype="float64"))
    weights = np.array([FEATURE_WEIGHTS[f] for f in FEATURE_NAMES], dtype="float64")
    Xs = Xs * weights  # emphasise the directional feature so the HMM learns direction
    _, lengths = _sequences(df)
    train_mask = _train_mask(df)

    model_name = "HMM"
    reason = None
    fitted: Any = None
    probs_state = None
    mapping: Dict[int, str] = {}
    holdout_acc = 0.0
    passed = False
    try:
        hmm = fit_hmm(Xs, lengths)
        raw_state = hmm.predict(Xs, lengths)
        passed, reason = M.check_hmm_quality(hmm.monitor_.converged, hmm.covars_, raw_state, 4)
        if passed:
            # Out-of-sample regime stability: agreement with a train-only HMM on holdout.
            ref_labels = _reference_labels(Xs, df, lengths, train_mask, "HMM")
            holdout_acc, _ = M.aligned_accuracy(raw_state, ref_labels, train_mask)
            if holdout_acc < ACCURACY_GATE:
                passed, reason = False, f"stability accuracy {holdout_acc:.3f} < {ACCURACY_GATE}"
        if passed:
            probs_state = hmm.predict_proba(Xs, lengths)
            mapping = M.map_states_to_labels(hmm.means_, FEATURE_NAMES, DIRECTION_FEATURE)
            fitted = hmm
        else:
            logger.warning("[%s] HMM gate failed (%s) → K-Means fallback", granularity, reason)
    except Exception as e:  # noqa: BLE001
        passed, reason = False, f"exception: {e}"
        logger.warning("[%s] HMM error: %s → K-Means fallback", granularity, e)

    if not passed:
        model_name = "KMeans"
        raw_state, probs_state, mapping, fitted = kmeans_fallback(Xs)
        ref_labels = _reference_labels(Xs, df, lengths, train_mask, "KMeans")
        holdout_acc, _ = M.aligned_accuracy(raw_state, ref_labels, train_mask)

    rows_df, flick = assemble_regime_rows(df, raw_state, probs_state, mapping, model_name)
    written = write_rows(conn, rows_df, granularity, model_name)

    state_counts = pd.Series([mapping[s] for s in raw_state]).value_counts().to_dict()
    result = {
        "granularity": granularity,
        "rows": int(n),
        "written": int(written),
        "model": model_name,
        "fallback_reason": reason,
        "converged": bool(getattr(getattr(fitted, "monitor_", None), "converged", False))
        if model_name == "HMM" else None,
        "holdout_accuracy": round(holdout_acc, 4),
        "flicker_raw": round(flick["flicker_raw"], 5),
        "flicker_smoothed": round(flick["flicker_smoothed"], 5),
        "label_distribution": {k: int(v) for k, v in state_counts.items()},
        "mapping": {int(k): v for k, v in mapping.items()},
    }
    result["_model_obj"] = {
        "model": fitted,
        "scaler": scaler,
        "mapping": {int(k): v for k, v in mapping.items()},
        "weights": weights.tolist(),
    }
    logger.info("[%s] done: model=%s acc=%.3f flick raw=%.4f→sm=%.4f",
                granularity, model_name, holdout_acc, flick["flicker_raw"], flick["flicker_smoothed"])
    return result


def run(granularities: List[str] = None, register_mlflow: bool = True) -> Dict[str, Any]:
    granularities = granularities or REGIME_GRANULARITIES
    regime_schema.ensure_regime_columns()
    env = read_env()
    conn = get_db_connection(env)
    results: List[Dict[str, Any]] = []
    model_bundle: Dict[str, Any] = {}
    try:
        for g in granularities:
            r = process_granularity(conn, g)
            model_bundle[g] = r.pop("_model_obj")
            results.append(r)
    finally:
        conn.close()

    # Serialize HMM package (per-granularity models + scalers + mappings).
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(
        {
            "models": model_bundle,
            "feature_names": FEATURE_NAMES,
            "feature_weights": FEATURE_WEIGHTS,
            "direction_feature": DIRECTION_FEATURE,
            "trend_window": TREND_WINDOW,
            "seed": SEED,
            "model_version": MODEL_VERSION,
            "primary_granularity": "D1",
            "feature_set_version": "1.0.0",
            "semantic_order": M.SEMANTIC_ORDER,
        },
        MODEL_PATH,
    )
    logger.info("Serialized HMM package → %s", MODEL_PATH)

    summary = {"model_version": MODEL_VERSION, "model_path": MODEL_PATH, "per_granularity": results}
    if register_mlflow:
        summary["mlflow_run_id"] = _register_mlflow(summary)
    logger.info("MODEL-003 complete: %s", {r["granularity"]: r["model"] for r in results})
    return summary


def _register_mlflow(summary) -> str:
    try:
        import mlflow

        from src.system1.features.feature_pipeline import _resolve_mlflow_uri

        mlflow.set_tracking_uri(_resolve_mlflow_uri())
        mlflow.set_experiment("system1-regime-hmm")
        with mlflow.start_run(run_name=MODEL_VERSION) as run:
            mlflow.log_param("model_version", MODEL_VERSION)
            mlflow.log_param("seed", SEED)
            for r in summary["per_granularity"]:
                g = r["granularity"]
                mlflow.log_param(f"model_{g}", r["model"])
                mlflow.log_metric(f"acc_{g}", r["holdout_accuracy"])
                mlflow.log_metric(f"flicker_raw_{g}", r["flicker_raw"])
                mlflow.log_metric(f"flicker_smoothed_{g}", r["flicker_smoothed"])
            mlflow.log_artifact(MODEL_PATH)
            return run.info.run_id
    except Exception as e:  # noqa: BLE001
        logger.error("MLflow registration failed: %s", e)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="MODEL-003 HMM regime engine")
    parser.add_argument("--granularity", choices=REGIME_GRANULARITIES, default=None)
    parser.add_argument("--no-mlflow", action="store_true")
    parser.add_argument("--log-file", default="model003_regime.log")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(args.log_file)],
    )
    gr = [args.granularity] if args.granularity else None
    summary = run(gr, register_mlflow=not args.no_mlflow)
    print({k: v for k, v in summary.items() if k != "per_granularity"})
    for r in summary["per_granularity"]:
        print(r)


if __name__ == "__main__":
    main()
