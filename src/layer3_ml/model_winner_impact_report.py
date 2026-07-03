#!/usr/bin/env python3
"""
Champion Model Impact Report (Layer 3)
======================================

Loads the current Layer 3 champion model, scores historical labeled signals,
and reports the practical system impact of threshold changes:
- Win rate
- Average trades per week
- Risk/reward ratio (from R_Multiple)
- Expectancy in unit-R

Usage:
    python src/layer3_ml/model_winner_impact_report.py
    python src/layer3_ml/model_winner_impact_report.py --granularity H4 --lookback-days 120
    python src/layer3_ml/model_winner_impact_report.py --threshold-min 0.50 --threshold-max 0.90 --threshold-step 0.05
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import sys

import joblib
import numpy as np
import pandas as pd
from dotenv import load_dotenv

from feature_alignment import (
    align_features_for_inference,
    safe_comprehensive_feature_engineering,
)

ROOT_DIR = Path(__file__).resolve().parents[2]

# Repo root on path so ``src.common`` resolves (canonical PostgreSQL module).
sys.path.insert(0, str(ROOT_DIR))
from src.common.db import get_psycopg2_connection  # noqa: E402

MODELS_DIR = ROOT_DIR / "models"
DEFAULT_MANIFEST = MODELS_DIR / "champion_manifest.json"


@dataclass
class LoadedArtifacts:
    manifest: Dict[str, Any]
    model: Any
    preprocessor: Any
    threshold: float
    model_type: str
    run_id: str


@dataclass
class DbConfig:
    server: str
    user: str
    password: str
    database: str
    port: Optional[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Champion model impact report for Layer 3",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Path to champion manifest JSON",
    )
    parser.add_argument(
        "--granularity",
        type=str,
        default=None,
        choices=["H1", "H4"],
        help="Optional granularity filter",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=180,
        help="How many days of historical signals to analyze",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=100000,
        help="Safety cap on loaded rows",
    )
    parser.add_argument(
        "--threshold-min",
        type=float,
        default=0.40,
        help="Minimum threshold for impact sweep",
    )
    parser.add_argument(
        "--threshold-max",
        type=float,
        default=0.90,
        help="Maximum threshold for impact sweep",
    )
    parser.add_argument(
        "--threshold-step",
        type=float,
        default=0.05,
        help="Threshold step for impact sweep",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional JSON output path",
    )
    return parser.parse_args()


def load_artifacts(manifest_path: Path) -> LoadedArtifacts:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    model_path = (
        Path(manifest["artifact_path"])
        if manifest.get("artifact_path")
        else MODELS_DIR / "champion_model.pkl"
    )
    preprocessor_path = (
        Path(manifest["preprocessor_path"])
        if manifest.get("preprocessor_path")
        else MODELS_DIR / "champion_preprocessor.pkl"
    )

    if not model_path.exists():
        raise FileNotFoundError(f"Model artifact not found: {model_path}")
    if not preprocessor_path.exists():
        raise FileNotFoundError(f"Preprocessor artifact not found: {preprocessor_path}")

    model = joblib.load(model_path)
    preprocessor = joblib.load(preprocessor_path)

    return LoadedArtifacts(
        manifest=manifest,
        model=model,
        preprocessor=preprocessor,
        threshold=float(manifest.get("threshold", 0.5)),
        model_type=str(manifest.get("model_type", "unknown")),
        run_id=str(manifest.get("run_id", "unknown")),
    )


def load_db_config() -> DbConfig:
    load_dotenv(ROOT_DIR / ".env")

    server = os.getenv("DB_SERVER")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASS")
    database = os.getenv("DB_NAME", "ForexBrainDB")
    port = os.getenv("DB_PORT")

    if not all([server, user, password]):
        raise RuntimeError("Missing DB credentials (DB_SERVER/DB_USER/DB_PASS)")

    return DbConfig(
        server=server,
        user=user,
        password=password,
        database=database,
        port=port,
    )


class _ColumnSet(frozenset):
    """Set of column names with case-insensitive membership.

    PostgreSQL folds unquoted identifiers to lowercase; this module's contract
    checks use mixed-case names (e.g. ``'Granularity'``, ``'Is_Winner'``).
    """

    def __contains__(self, item):
        if not isinstance(item, str):
            return super().__contains__(item)
        il = item.lower()
        return any(str(c).lower() == il for c in self)


def connect(cfg: DbConfig):
    """Return a raw PostgreSQL (psycopg2) connection with a UTC session."""
    conn = get_psycopg2_connection()
    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'UTC'")
    conn.commit()
    return conn


def _table_has_column(conn, table_name: str, column_name: str) -> bool:
    q = """
    SELECT 1
    FROM information_schema.columns
    WHERE lower(table_name) = lower(%s) AND lower(column_name) = lower(%s)
    """
    cur = conn.cursor()
    cur.execute(q, (table_name, column_name))
    return cur.fetchone() is not None


def _table_columns(conn, table_name: str) -> "_ColumnSet":
    q = """
    SELECT column_name
    FROM information_schema.columns
    WHERE lower(table_name) = lower(%s)
    """
    cur = conn.cursor()
    cur.execute(q, (table_name,))
    return _ColumnSet(str(r[0]) for r in cur.fetchall())


def load_labeled_signals(
    conn,
    lookback_days: int,
    max_rows: int,
    granularity: Optional[str],
) -> pd.DataFrame:
    signal_cols = _table_columns(conn, "fact_signals")
    regime_cols = _table_columns(conn, "fact_market_regime_v2")
    outcome_cols = _table_columns(conn, "fact_trade_outcomes")

    has_outcome_granularity = "Granularity" in outcome_cols

    outcome_join = """
    LEFT JOIN fact_trade_outcomes t
      ON s.Asset_ID = t.Asset_ID
     AND s.Strategy_ID = t.Strategy_ID
     AND s."timestamp" = t."timestamp"
    """
    if has_outcome_granularity:
        outcome_join += "\n     AND s.Granularity = t.Granularity"

    lookback_cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(
        days=lookback_days
    )

    # Optional columns are selected only when present to avoid schema-coupling.
    # Output labels are double-quoted to preserve the mixed-case DataFrame
    # column contract (PostgreSQL lower-cases unquoted output labels).
    signal_reason_expr = (
        's.Signal_Reason AS "Signal_Reason"'
        if "Signal_Reason" in signal_cols
        else 'NULL AS "Signal_Reason"'
    )
    rule_id_expr = (
        's.Rule_ID AS "Rule_ID"' if "Rule_ID" in signal_cols else 'NULL AS "Rule_ID"'
    )
    confidence_expr = (
        's.Confidence_Score AS "Signal_Confidence"'
        if "Confidence_Score" in signal_cols
        else 'NULL AS "Signal_Confidence"'
    )
    strategy_version_expr = (
        's.Strategy_Version AS "Strategy_Version"'
        if "Strategy_Version" in signal_cols
        else 'NULL AS "Strategy_Version"'
    )
    indicator_snapshot_expr = (
        's.Indicator_Snapshot AS "Indicator_Snapshot"'
        if "Indicator_Snapshot" in signal_cols
        else 'NULL AS "Indicator_Snapshot"'
    )

    session_volume_expr = (
        'r.Session_Volume_Z AS "Session_Volume_Z"'
        if "Session_Volume_Z" in regime_cols
        else 'NULL AS "Session_Volume_Z"'
    )
    regime_version_expr = (
        'r.Regime_Model_Version AS "Regime_Model_Version"'
        if "Regime_Model_Version" in regime_cols
        else 'NULL AS "Regime_Model_Version"'
    )

    if "Is_Winner" not in outcome_cols:
        raise RuntimeError(
            "fact_trade_outcomes is missing required label column 'Is_Winner'"
        )

    is_winner_expr = 't.Is_Winner AS "Is_Winner"'
    r_multiple_expr = (
        't.R_Multiple AS "R_Multiple"'
        if "R_Multiple" in outcome_cols
        else 'NULL AS "R_Multiple"'
    )

    query = f"""
    SELECT
        s."timestamp" AS "Timestamp",
        s.Asset_ID AS "Asset_ID",
        s.Strategy_ID AS "Strategy_ID",
        s.Granularity AS "Granularity",
        s.Signal_Value AS "Signal_Value",
        {signal_reason_expr},
        {rule_id_expr},
        {confidence_expr},
        {strategy_version_expr},
        {indicator_snapshot_expr},
        r.Regime_Label AS "Regime_Label",
        r.ATR_Value AS "ATR_Value",
        r.ADX_Value AS "ADX_Value",
        {session_volume_expr},
        {regime_version_expr},
        {is_winner_expr},
        {r_multiple_expr}
    FROM fact_signals s
    LEFT JOIN fact_market_regime_v2 r
      ON s.Asset_ID = r.Asset_ID
     AND s.Granularity = r.Granularity
     AND r."timestamp" = (
         SELECT MAX(rr."timestamp")
         FROM fact_market_regime_v2 rr
         WHERE rr.Asset_ID = s.Asset_ID
           AND rr.Granularity = s.Granularity
           AND rr."timestamp" <= s."timestamp"
     )
    {outcome_join}
    WHERE s.Signal_Value != 0
      AND s."timestamp" >= %s
      AND t.Is_Winner IS NOT NULL
      {"AND s.Granularity = %s" if granularity else ""}
    ORDER BY s."timestamp" ASC
    LIMIT {int(max_rows)}
    """

    params: List[Any] = [lookback_cutoff]
    if granularity:
        params.append(granularity)

    df = pd.read_sql(query, conn, params=params, parse_dates=["Timestamp"])
    if not df.empty:
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], utc=True).dt.tz_localize(None)
    return df


def add_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    ts = pd.to_datetime(out["Timestamp"], errors="coerce")
    out["Signal_Hour"] = ts.dt.hour
    out["Signal_DayOfWeek"] = ts.dt.dayofweek + 1
    out["Signal_Month"] = ts.dt.month
    out["Signal_Quarter"] = ts.dt.quarter
    out["Is_London_NY_Session"] = out["Signal_Hour"].between(8, 16).astype(float)
    out["Is_Asian_Session"] = out["Signal_Hour"].between(0, 7).astype(float)
    out["Is_US_Session"] = out["Signal_Hour"].between(12, 20).astype(float)
    out["Strategy_Category"] = out["Strategy_ID"].apply(
        lambda x: f"Strat_{int(x)}" if pd.notna(x) else "Unknown"
    )
    return out


def add_strategy_rollups(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values("Timestamp").copy()

    for window in [20, 50, 100]:
        winrate_col = f"Strat_WinRate_{window}"
        expectancy_col = f"Strat_Expectancy_{window}"
        trades_col = f"Strat_Trades_{window}"

        out[winrate_col] = (
            out.groupby("Strategy_ID")["Is_Winner"]
            .transform(
                lambda s: s.shift(1).rolling(window=window, min_periods=5).mean()
            )
            .fillna(0.5)
        )
        out[trades_col] = (
            out.groupby("Strategy_ID")["Is_Winner"]
            .transform(
                lambda s: s.shift(1).rolling(window=window, min_periods=1).count()
            )
            .fillna(0.0)
        )
        if "R_Multiple" in out.columns:
            out[expectancy_col] = (
                out.groupby("Strategy_ID")["R_Multiple"]
                .transform(
                    lambda s: s.shift(1).rolling(window=window, min_periods=5).mean()
                )
                .fillna(0.0)
            )
        else:
            out[expectancy_col] = 0.0

    out["Bars_Since_Last_Trade"] = (
        out.groupby("Strategy_ID")["Timestamp"]
        .diff()
        .dt.total_seconds()
        .div(3600.0)
        .fillna(0.0)
    )

    out["LondonSession_x_Strategy"] = out["Is_London_NY_Session"] * out[
        "Strategy_ID"
    ].fillna(0)

    return out


def build_feature_matrix(
    df_raw: pd.DataFrame, preprocessor: Any, manifest: Dict[str, Any]
) -> pd.DataFrame:
    df = add_temporal_features(df_raw)
    df = add_strategy_rollups(df)
    df = safe_comprehensive_feature_engineering(df)

    expected_columns: List[str]
    if (
        hasattr(preprocessor, "feature_names_in_")
        and preprocessor.feature_names_in_ is not None
    ):
        expected_columns = [str(c) for c in preprocessor.feature_names_in_]
    else:
        expected_columns = [str(c) for c in manifest.get("feature_columns", [])]

    if not expected_columns:
        raise RuntimeError(
            "Could not determine expected feature columns from preprocessor or manifest"
        )

    return align_features_for_inference(df, expected_columns)


def predict_probabilities(
    model: Any, preprocessor: Any, features_df: pd.DataFrame
) -> np.ndarray:
    x = preprocessor.transform(features_df)
    if hasattr(model, "predict_proba"):
        return model.predict_proba(x)[:, 1]
    pred = model.predict(x)
    return np.asarray(pred, dtype=float)


def _weeks_span(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    ts_min = pd.to_datetime(df["Timestamp"], errors="coerce").min()
    ts_max = pd.to_datetime(df["Timestamp"], errors="coerce").max()
    if pd.isna(ts_min) or pd.isna(ts_max):
        return 0.0
    seconds = max(1.0, (ts_max - ts_min).total_seconds())
    return seconds / (7 * 24 * 3600)


def summarize_at_threshold(df_eval: pd.DataFrame, threshold: float) -> Dict[str, Any]:
    selected = df_eval[df_eval["prob"] >= threshold].copy()

    total = int(len(df_eval))
    selected_n = int(len(selected))
    selected_rate = (selected_n / total) if total else 0.0
    weeks = _weeks_span(df_eval)
    trades_per_week = (selected_n / weeks) if weeks > 0 else 0.0

    if selected_n > 0:
        winrate = float(selected["Is_Winner"].mean())
        expectancy_unit_r = float(
            np.mean(np.where(selected["Is_Winner"] == 1, 1.0, -1.0))
        )
    else:
        winrate = 0.0
        expectancy_unit_r = 0.0

    if selected_n > 0 and "R_Multiple" in selected.columns:
        avg_r_multiple = float(selected["R_Multiple"].astype(float).mean())
        win_r = selected.loc[selected["R_Multiple"] > 0, "R_Multiple"].astype(float)
        loss_r = selected.loc[selected["R_Multiple"] < 0, "R_Multiple"].astype(float)
        avg_win_r = float(win_r.mean()) if not win_r.empty else np.nan
        avg_loss_r_abs = float(abs(loss_r.mean())) if not loss_r.empty else np.nan
        rr_ratio = (
            float(avg_win_r / avg_loss_r_abs)
            if pd.notna(avg_win_r) and pd.notna(avg_loss_r_abs) and avg_loss_r_abs > 0
            else np.nan
        )
    else:
        avg_r_multiple = np.nan
        avg_win_r = np.nan
        avg_loss_r_abs = np.nan
        rr_ratio = np.nan

    return {
        "threshold": float(threshold),
        "selected_signals": selected_n,
        "selected_rate": float(selected_rate),
        "avg_trades_per_week": float(trades_per_week),
        "winrate": float(winrate),
        "expectancy_unit_r": float(expectancy_unit_r),
        "avg_r_multiple": float(avg_r_multiple) if pd.notna(avg_r_multiple) else np.nan,
        "avg_win_r": float(avg_win_r) if pd.notna(avg_win_r) else np.nan,
        "avg_loss_r_abs": float(avg_loss_r_abs) if pd.notna(avg_loss_r_abs) else np.nan,
        "risk_reward_ratio": float(rr_ratio) if pd.notna(rr_ratio) else np.nan,
    }


def threshold_grid(
    start: float, stop: float, step: float, include: Optional[float]
) -> List[float]:
    if step <= 0:
        raise ValueError("threshold-step must be > 0")
    values = list(np.round(np.arange(start, stop + step / 2.0, step), 6))
    if include is not None and include not in values:
        values.append(float(round(include, 6)))
    return sorted(set(values))


def print_summary(
    artifacts: LoadedArtifacts,
    df_eval: pd.DataFrame,
    baseline_metrics: Dict[str, Any],
    sweep_df: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    print("\n" + "=" * 88)
    print("LAYER 3 CHAMPION MODEL IMPACT REPORT")
    print("=" * 88)
    print(f"Model type:             {artifacts.model_type}")
    print(f"Run ID:                 {artifacts.run_id}")
    print(f"Manifest threshold:     {artifacts.threshold:.4f}")
    print(f"Rows evaluated:         {len(df_eval)}")
    print(
        f"Data window:            {df_eval['Timestamp'].min()}  ->  {df_eval['Timestamp'].max()}"
    )
    print(f"Granularity filter:     {args.granularity or 'ALL (H1 + H4 if present)'}")

    print("\nBaseline at manifest threshold")
    print("-" * 88)
    print(f"Win rate:               {baseline_metrics['winrate']:.2%}")
    print(f"Avg trades per week:    {baseline_metrics['avg_trades_per_week']:.2f}")
    print(
        f"Risk/Reward ratio:      {baseline_metrics['risk_reward_ratio'] if pd.notna(baseline_metrics['risk_reward_ratio']) else 'n/a'}"
    )
    print(f"Expectancy (unit R):    {baseline_metrics['expectancy_unit_r']:.4f}")
    print(
        f"Selected signals:       {baseline_metrics['selected_signals']} ({baseline_metrics['selected_rate']:.2%})"
    )

    print("\nThreshold impact sweep")
    print("-" * 88)
    display_cols = [
        "threshold",
        "selected_signals",
        "selected_rate",
        "avg_trades_per_week",
        "winrate",
        "risk_reward_ratio",
        "expectancy_unit_r",
    ]
    disp = sweep_df[display_cols].copy()
    for pct_col in ["selected_rate", "winrate"]:
        disp[pct_col] = disp[pct_col].map(lambda x: f"{x:.2%}")
    for num_col in ["avg_trades_per_week", "risk_reward_ratio", "expectancy_unit_r"]:
        disp[num_col] = disp[num_col].map(lambda x: "n/a" if pd.isna(x) else f"{x:.4f}")
    print(disp.to_string(index=False))

    print("\nHow to affect system behavior")
    print("-" * 88)
    print(
        "1. Lower threshold -> more approvals to Layer 4, more trades/week, usually lower precision."
    )
    print(
        "2. Raise threshold -> fewer approvals, usually higher winrate, lower turnover."
    )
    print(
        "3. Retrain champion -> changes score distribution and can shift all operating points."
    )


def main() -> int:
    args = parse_args()

    artifacts = load_artifacts(args.manifest)
    db_cfg = load_db_config()

    with connect(db_cfg) as conn:
        df_raw = load_labeled_signals(
            conn=conn,
            lookback_days=args.lookback_days,
            max_rows=args.max_rows,
            granularity=args.granularity,
        )

    if df_raw.empty:
        print("No labeled signals found for requested window/filter.")
        return 0

    features_df = build_feature_matrix(
        df_raw, artifacts.preprocessor, artifacts.manifest
    )
    probs = predict_probabilities(artifacts.model, artifacts.preprocessor, features_df)

    df_eval = df_raw.copy()
    df_eval["prob"] = probs

    baseline = summarize_at_threshold(df_eval, artifacts.threshold)

    thresholds = threshold_grid(
        start=args.threshold_min,
        stop=args.threshold_max,
        step=args.threshold_step,
        include=artifacts.threshold,
    )
    sweep_rows = [summarize_at_threshold(df_eval, t) for t in thresholds]
    sweep_df = pd.DataFrame(sweep_rows).sort_values("threshold")

    print_summary(artifacts, df_eval, baseline, sweep_df, args)

    if args.output_json:
        payload = {
            "generated_at": datetime.utcnow().isoformat(),
            "model_type": artifacts.model_type,
            "run_id": artifacts.run_id,
            "manifest_threshold": artifacts.threshold,
            "rows_evaluated": int(len(df_eval)),
            "granularity_filter": args.granularity,
            "lookback_days": int(args.lookback_days),
            "baseline": baseline,
            "sweep": sweep_rows,
        }
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nSaved JSON report: {args.output_json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
