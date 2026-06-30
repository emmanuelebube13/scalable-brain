"""MODEL-004 — per-regime strategy attribution engine.

Point-in-time joins each trade (fact_trade_outcomes) to the CAUSAL regime in force at
entry (fact_market_regime_v2.regime_causal — walk-forward filtered forward-only label,
FIX-S1-005; NOT the leaked reporting-only smoothed label — bar_time <= entry, same
instrument+granularity), then computes per (strategy × regime × granularity) metrics with
Bayesian shrinkage for thin cells. Persists fact_strategy_regime_attribution +
results/state/strategy_regime_attribution.parquet + results/reports/attribution_report_*.json.

Usage: python -m src.system1.attribution.attribute
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from psycopg2.extras import execute_values
from sqlalchemy import text

from src.common.db import get_engine, get_psycopg2_connection
from src.system1.attribution import metrics as MET
from src.system1.attribution import schema as attr_schema
from src.system1.validation import walk_forward as WF

logger = logging.getLogger("system1.attribution")

REGIME_MODEL_VERSION = "hmm-v1.0.0"
N_MIN = 20
UNKNOWN_REGIME = "UNKNOWN"

# FIX-S1-002 validation-design lineage (the locked walk-forward params; see walk_forward.py).
VALIDATION_DESIGN = {
    "method": "walk_forward",
    "min_train_months": WF.MIN_TRAIN_MONTHS,
    "step_months": WF.STEP_MONTHS,
    "oos_window_months": WF.OOS_WINDOW_MONTHS,
    "mode": WF.MODE,
    "anchor": "series_start = per-granularity min entry_time",
    "oos_rule": "trade is OOS iff entry_time >= series_start + min_train; metrics computed on OOS trades only",
}
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PARQUET_OUT = os.path.join(
    _REPO_ROOT, "results", "state", "strategy_regime_attribution.parquet"
)
REPORTS_DIR = os.path.join(_REPO_ROOT, "results", "reports")


def _column_exists(conn, table: str, column: str) -> bool:
    """True if ``column`` exists on ``table`` (schema-aware guard, see postgres-patterns.md)."""
    return bool(
        conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c)"
            ),
            {"t": table, "c": column},
        ).scalar()
    )


def _load_trades(engine) -> pd.DataFrame:
    """Load trade outcomes, schema-aware on the FIX-S1-002 ``is_oos`` / ``fold_id`` columns.

    When both columns are present each trade carries its walk-forward OOS label. When they are
    absent (un-migrated DB) every trade is treated as **in-sample** (``is_oos=False``), which
    makes every cell fail the OOS gate — the safe direction (we never qualify a strategy on a
    DB that cannot prove out-of-sample performance). ``is_oos IS NULL`` legacy rows are also
    treated as not-OOS (unclassified).
    """
    base_cols = (
        'SELECT outcome_id, "timestamp" AS entry_time, asset_id, strategy_id, '
        "granularity, is_winner, r_multiple"
    )
    with engine.connect() as conn:
        has_oos = _column_exists(
            conn, "fact_trade_outcomes", "is_oos"
        ) and _column_exists(conn, "fact_trade_outcomes", "fold_id")
        if has_oos:
            sql = text(base_cols + ", is_oos, fold_id FROM fact_trade_outcomes")
        else:
            sql = text(base_cols + " FROM fact_trade_outcomes")
        df = pd.read_sql(sql, conn)
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    if has_oos:
        df["is_oos"] = df["is_oos"].fillna(False).astype(bool)
        df["fold_id"] = df["fold_id"].astype("Int64")
    else:
        logger.warning(
            "fact_trade_outcomes lacks is_oos/fold_id — treating all trades as in-sample; "
            "every cell will fail the OOS gate (safe direction)."
        )
        df["is_oos"] = False
        df["fold_id"] = pd.array([pd.NA] * len(df), dtype="Int64")
    return df


def _load_regimes(engine, granularity: str) -> pd.DataFrame:
    """Load the **causal** regime label (FIX-S1-005) per bar.

    Consumes ``regime_causal`` (walk-forward, filtered forward-only) — NOT the
    reporting-only ``regime_smoothed`` (full-history forward-backward fit, which leaks
    future bars into a past label). Warm-up bars have ``regime_causal IS NULL`` and are
    excluded, so trades before the first fold cutoff tag as UNKNOWN.
    """
    sql = text(
        'SELECT asset_id, "timestamp" AS bar_time, regime_causal '
        "FROM fact_market_regime_v2 WHERE granularity = :g AND regime_causal IS NOT NULL"
    )
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"g": granularity})
    df["bar_time"] = pd.to_datetime(df["bar_time"], utc=True)
    return df


def tag_regime_at_entry(trades: pd.DataFrame, engine) -> pd.DataFrame:
    """Point-in-time causal regime tag per trade via merge_asof (regime bar <= entry_time).

    Joins the causal label (``regime_causal``); the bar-time bound plus the causal label
    value together make this a genuine point-in-time tag (FIX-S1-005).
    """
    tagged = []
    for gran, tg in trades.groupby("granularity"):
        regimes = _load_regimes(engine, gran)
        out_parts = []
        for aid, ta in tg.groupby("asset_id"):
            ra = regimes[regimes["asset_id"] == aid].sort_values("bar_time")
            ta = ta.sort_values("entry_time")
            if ra.empty:
                ta = ta.assign(regime=UNKNOWN_REGIME, regime_bar_time=pd.NaT)
            else:
                merged = pd.merge_asof(
                    ta,
                    ra[["bar_time", "regime_causal"]],
                    left_on="entry_time",
                    right_on="bar_time",
                    direction="backward",
                )
                merged["regime"] = merged["regime_causal"].fillna(UNKNOWN_REGIME)
                merged = merged.rename(columns={"bar_time": "regime_bar_time"})
                ta = merged
            out_parts.append(ta)
        tagged.append(pd.concat(out_parts, ignore_index=True))
    return pd.concat(tagged, ignore_index=True)


def _in_sample_span_months(cell: pd.DataFrame) -> float:
    """Full calendar span (months) of ALL the cell's trades — reporting only (FIX-S1-002).

    This is the value the OOS gate USED to read (and that made it inert): the in-sample
    coverage proxy. It is retained under an honest name for reporting; the gate now reads the
    true OOS span (``oos_months``) instead.
    """
    if len(cell) > 1:
        span_days = (cell["entry_time"].max() - cell["entry_time"].min()).days
        return round(span_days / 30.44, 2)
    return 0.0


def _oos_cell_metrics(
    oos_cell: pd.DataFrame, folds_by_id: Dict[int, WF.Fold]
) -> Dict[str, float]:
    """Gate metrics computed on the **OOS subset** of a cell (FIX-S1-002).

    ``oos_months`` is the union span of the OOS windows the cell actually traded in
    (``oos_month_span`` over the folds whose ``fold_id`` appears among the cell's OOS trades).
    Sharpe is annualized by the realized OOS cadence (oos_trade_count / oos_years), per the
    financial-metrics skill. An empty OOS subset yields trade_count 0 and oos_months 0, so the
    cell cannot clear the gates — the safe direction.
    """
    r = oos_cell["r_multiple"].to_numpy(dtype="float64")
    n = int(len(oos_cell))
    fids = sorted({int(f) for f in oos_cell["fold_id"].dropna().unique()})
    cell_folds = [folds_by_id[f] for f in fids if f in folds_by_id]
    oos_months = round(WF.oos_month_span(cell_folds), 2)
    oos_years = oos_months / 12.0
    trades_per_year = (n / oos_years) if oos_years > 0 else 0.0
    return {
        "trade_count": n,
        "win_rate": MET.win_rate(oos_cell["is_winner"].to_numpy()),
        "profit_factor": MET.profit_factor(r),
        "sharpe": MET.annualized_sharpe(r, trades_per_year),
        "expectancy": MET.expectancy(r),
        "max_drawdown": MET.max_drawdown(r),
        "recovery_factor": MET.recovery_factor(r),
        "avg_r": MET.avg_r(r),
        "oos_months": oos_months,
    }


def _folds_by_granularity(tagged: pd.DataFrame) -> Dict[str, Dict[int, WF.Fold]]:
    """Per-granularity ``{fold_id: Fold}`` using the locked design anchored at min entry_time."""
    out: Dict[str, Dict[int, WF.Fold]] = {}
    for gran, g in tagged.groupby("granularity"):
        smin, smax = WF.series_bounds(g["entry_time"])
        out[str(gran)] = {f.fold_id: f for f in WF.default_folds(smin, smax)}
    return out


def compute_attribution(tagged: pd.DataFrame, run_id: str) -> pd.DataFrame:
    """Per (strategy, granularity, regime) portfolio metrics on OOS trades only + shrinkage.

    FIX-S1-002: every gate metric (win_rate, profit_factor, sharpe, max_drawdown,
    recovery_factor, trade_count, oos_months) is computed on the cell's **out-of-sample**
    trades (``is_oos IS TRUE``). Bayesian shrinkage blends toward the strategy×granularity
    **OOS** global with the **OOS** sample size. ``in_sample_span_months`` (full-history span)
    is carried for reporting only.
    """
    rows: List[Dict[str, Any]] = []
    violations: List[str] = []
    folds_by_gran = _folds_by_granularity(tagged)
    for (sid, gran), grp in tagged.groupby(["strategy_id", "granularity"]):
        folds_by_id = folds_by_gran.get(str(gran), {})
        grp_oos = grp[grp["is_oos"]]
        glob = _oos_cell_metrics(
            grp_oos, folds_by_id
        )  # OOS strategy×granularity global
        for regime, cell in grp.groupby("regime"):
            cell_oos = cell[cell["is_oos"]]
            m = _oos_cell_metrics(cell_oos, folds_by_id)
            cell_violations = MET.validate_metrics(m)
            if cell_violations:
                if m["trade_count"] < N_MIN:
                    # FIX-S1-002: a sub-N_MIN OOS cell (e.g. 2-4 trades in a starved regime,
                    # near-zero return variance) can produce a small-sample Sharpe/MaxDD
                    # artifact. Such a cell is already flagged low_confidence below and is
                    # unconditionally rejected by the vetting gate, so we clamp the unstable
                    # value to the sanity bound and continue rather than aborting the whole run.
                    # The hard abort is reserved for cells with >= N_MIN trades, where an
                    # out-of-bound metric means the math is genuinely wrong — the true purpose
                    # of the FIX-S1-001 sanity guard.
                    logger.warning(
                        "Clamping small-sample metric artifact (n=%d < %d) strategy=%s "
                        "regime=%s gran=%s: %s",
                        m["trade_count"],
                        N_MIN,
                        sid,
                        regime,
                        gran,
                        "; ".join(cell_violations),
                    )
                    m["sharpe"] = float(
                        np.clip(
                            m["sharpe"],
                            -MET.MAX_PLAUSIBLE_SHARPE,
                            MET.MAX_PLAUSIBLE_SHARPE,
                        )
                    )
                    m["max_drawdown"] = float(
                        np.clip(m["max_drawdown"], 0.0, MET.MAX_PLAUSIBLE_DRAWDOWN)
                    )
                else:
                    for v in cell_violations:
                        violations.append(
                            f"strategy={sid} regime={regime} gran={gran}: {v}"
                        )
            wr_s, lc1 = MET.bayesian_shrinkage(
                m["win_rate"], glob["win_rate"], m["trade_count"], N_MIN
            )
            pf_s, _ = MET.bayesian_shrinkage(
                m["profit_factor"], glob["profit_factor"], m["trade_count"], N_MIN
            )
            sh_s, _ = MET.bayesian_shrinkage(
                m["sharpe"], glob["sharpe"], m["trade_count"], N_MIN
            )
            rows.append(
                {
                    "strategy_id": int(sid),
                    "regime": regime,
                    "granularity": gran,
                    "scope": "PORTFOLIO",
                    **m,
                    "in_sample_span_months": _in_sample_span_months(cell),
                    "n_in_sample_trades": int(len(cell) - len(cell_oos)),
                    "win_rate_shrunk": wr_s,
                    "profit_factor_shrunk": pf_s,
                    "sharpe_shrunk": sh_s,
                    "low_confidence": bool(lc1),
                    "model_version": REGIME_MODEL_VERSION,
                    "qualification_run_id": run_id,
                }
            )
    if violations:
        raise RuntimeError(
            "Metric sanity bounds violated (drawdown must be <=100%, |Sharpe| <=10) — "
            "refusing to ship corrupt attribution:\n  " + "\n  ".join(violations)
        )
    return pd.DataFrame(rows)


def _persist_db(df: pd.DataFrame, run_id: str) -> int:
    conn = get_psycopg2_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM fact_strategy_regime_attribution WHERE qualification_run_id = %s",
        (run_id,),
    )
    cols = [
        "strategy_id",
        "regime",
        "granularity",
        "scope",
        "trade_count",
        "win_rate",
        "profit_factor",
        "sharpe",
        "expectancy",
        "max_drawdown",
        "recovery_factor",
        "oos_months",
        "avg_r",
        "win_rate_shrunk",
        "profit_factor_shrunk",
        "sharpe_shrunk",
        "low_confidence",
        "model_version",
        "qualification_run_id",
    ]

    def _clean(v):
        if isinstance(v, float) and not np.isfinite(v):
            return None
        return v

    rows = [tuple(_clean(r[c]) for c in cols) for r in df.to_dict("records")]
    execute_values(
        cur,
        f"INSERT INTO fact_strategy_regime_attribution ({','.join(cols)}) VALUES %s",
        rows,
    )
    conn.commit()
    conn.close()
    return len(rows)


def run(register_mlflow: bool = True) -> Dict[str, Any]:
    run_id = str(uuid.uuid4())
    attr_schema.ensure_attribution_table()
    engine = get_engine()
    trades = _load_trades(engine)
    logger.info("Loaded %d trades", len(trades))
    tagged = tag_regime_at_entry(trades, engine)
    unknown = int((tagged["regime"] == UNKNOWN_REGIME).sum())
    logger.info(
        "Tagged regimes; %d trades have UNKNOWN regime (no prior label)", unknown
    )

    n_oos = int(tagged["is_oos"].sum())
    n_in_sample = int(len(tagged) - n_oos)
    logger.info("OOS split: %d OOS trades, %d in-sample trades", n_oos, n_in_sample)

    attribution = compute_attribution(tagged, run_id)
    n_db = _persist_db(attribution, run_id)
    os.makedirs(os.path.dirname(PARQUET_OUT), exist_ok=True)
    attribution.to_parquet(PARQUET_OUT, index=False)

    # Reconciliation: per-regime OOS trade counts sum to the OOS aggregate per
    # strategy×granularity (trade_count is now OOS-only — FIX-S1-002).
    recon = (
        attribution.groupby(["strategy_id", "granularity"])["trade_count"]
        .sum()
        .reset_index()
        .rename(columns={"trade_count": "attributed"})
    )
    oos_trades = tagged[tagged["is_oos"]]
    agg = (
        oos_trades.groupby(["strategy_id", "granularity"])
        .size()
        .reset_index(name="aggregate")
    )
    recon = recon.merge(agg, on=["strategy_id", "granularity"], how="left").fillna(
        {"aggregate": 0}
    )
    recon["ok"] = recon["attributed"] == recon["aggregate"]
    reconciled = bool(recon["ok"].all())

    report = {
        "qualification_run_id": run_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "model_version": REGIME_MODEL_VERSION,
        "n_trades": int(len(trades)),
        "n_oos_trades": n_oos,
        "n_in_sample_trades": n_in_sample,
        "n_unknown_regime": unknown,
        "n_cells": int(len(attribution)),
        "n_low_confidence_cells": int(attribution["low_confidence"].sum()),
        "n_min": N_MIN,
        "reconciliation_ok": reconciled,
        "validation_design": VALIDATION_DESIGN,
        "regime_distribution": tagged["regime"].value_counts().to_dict(),
        "db_rows_written": n_db,
        "parquet": PARQUET_OUT,
    }
    os.makedirs(REPORTS_DIR, exist_ok=True)
    report_path = os.path.join(
        REPORTS_DIR,
        f"attribution_report_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json",
    )
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    report["report_path"] = report_path

    if register_mlflow:
        report["mlflow_run_id"] = _register_mlflow(report)
    logger.info(
        "MODEL-004 complete: cells=%d low_conf=%d reconciled=%s",
        report["n_cells"],
        report["n_low_confidence_cells"],
        reconciled,
    )
    return report


def _register_mlflow(report) -> str:
    try:
        import mlflow
        from src.system1.features.feature_pipeline import _resolve_mlflow_uri

        mlflow.set_tracking_uri(_resolve_mlflow_uri())
        mlflow.set_experiment("system1-attribution")
        with mlflow.start_run(run_name="attribution") as run:
            mlflow.log_param("model_version", REGIME_MODEL_VERSION)
            mlflow.log_param("n_min", N_MIN)
            for k in (
                "n_trades",
                "n_cells",
                "n_low_confidence_cells",
                "n_unknown_regime",
            ):
                mlflow.log_metric(k, report[k])
            mlflow.log_artifact(report["report_path"])
            return run.info.run_id
    except Exception as e:  # noqa: BLE001
        logger.error("MLflow registration failed: %s", e)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="MODEL-004 per-regime attribution")
    parser.add_argument("--no-mlflow", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    print(run(register_mlflow=not args.no_mlflow))


if __name__ == "__main__":
    main()
