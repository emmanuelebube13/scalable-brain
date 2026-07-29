"""I/O readers for the analytics export (S1-EXPORT-002).

Everything here reads; nothing writes. The causal-regime tag reuses the proven
point-in-time join from MODEL-004 (``attribution.tag_regime_at_entry`` — regime bar
<= entry_time, causal label only, FIX-S1-005) so the export cannot re-introduce the
leaked smoothed label.
"""

from __future__ import annotations

import glob
import json
import logging
import os
from typing import Any, Dict, Optional

import pandas as pd
from sqlalchemy import text

from src.system1.attribution.attribute import _column_exists, tag_regime_at_entry

logger = logging.getLogger("system1.analytics.extract")

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
REGIME_MAP_PATH = os.path.join(
    _REPO_ROOT, "results", "state", "regime_strategy_map.json"
)
REPORTS_DIR = os.path.join(_REPO_ROOT, "results", "reports")
CHAMPION_MANIFEST = os.path.join(_REPO_ROOT, "models", "champion_manifest.json")


def load_trades(engine) -> pd.DataFrame:
    """All trade outcomes with their walk-forward OOS labels and holding time.

    Unlike attribution (which degrades to all-in-sample when the FIX-S1-002 columns are
    missing), the export REQUIRES ``is_oos``/``fold_id``: without them we cannot honour
    the "OOS trades only" honesty rule, so we abort rather than publish in-sample data.
    """
    with engine.connect() as conn:
        if not (
            _column_exists(conn, "fact_trade_outcomes", "is_oos")
            and _column_exists(conn, "fact_trade_outcomes", "fold_id")
        ):
            raise SystemExit(
                "fact_trade_outcomes lacks is_oos/fold_id — cannot publish an honest "
                "OOS-only export; run the FIX-S1-002 migration first"
            )
        df = pd.read_sql(
            text(
                'SELECT outcome_id, "timestamp" AS entry_time, asset_id, strategy_id, '
                "granularity, is_winner, r_multiple, holding_bars, is_oos, fold_id "
                "FROM fact_trade_outcomes"
            ),
            conn,
        )
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    df["is_oos"] = df["is_oos"].fillna(False).astype(bool)
    df["fold_id"] = df["fold_id"].astype("Int64")
    return df


def load_tagged_trades(engine) -> pd.DataFrame:
    """ALL trades tagged with the causal regime in force at entry.

    Returns the full set (not just OOS) because walk-forward folds must anchor at the
    per-granularity series start of the whole history (same convention as attribution's
    ``_folds_by_granularity``); callers filter ``is_oos`` after fold construction.
    """
    trades = load_trades(engine)
    tagged = tag_regime_at_entry(trades, engine)
    logger.info(
        "Trades: %d total, %d OOS after causal tag",
        len(tagged),
        int(tagged["is_oos"].sum()),
    )
    return tagged


def load_asset_symbols(engine) -> Dict[int, str]:
    """asset_id -> instrument symbol (e.g. 1 -> EUR_USD) from dim_asset."""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT asset_id, symbol FROM dim_asset")).fetchall()
    return {int(a): str(s) for a, s in rows}


def load_strategy_dim(engine) -> pd.DataFrame:
    """Strategy registry: id, name, family (strategy_type), description, is_active."""
    with engine.connect() as conn:
        return pd.read_sql(
            text(
                "SELECT strategy_id, strategy_name, strategy_type, description, "
                "is_active FROM dim_strategy ORDER BY strategy_id"
            ),
            conn,
        )


def load_regime_occupancy(engine) -> pd.DataFrame:
    """Fraction of causally-labelled bars in each regime per (granularity, asset).

    Only bars with a non-null causal label count — warm-up bars have no honest label
    and are excluded from both numerator and denominator.
    """
    with engine.connect() as conn:
        df = pd.read_sql(
            text(
                "SELECT granularity, asset_id, regime_causal AS regime, "
                "count(*) AS n_bars FROM fact_market_regime_v2 "
                "WHERE regime_causal IS NOT NULL "
                "GROUP BY granularity, asset_id, regime_causal"
            ),
            conn,
        )
    totals = df.groupby(["granularity", "asset_id"])["n_bars"].transform("sum")
    df["occupancy"] = df["n_bars"] / totals
    return df


def load_regime_strategy_map(path: str = REGIME_MAP_PATH) -> Dict[str, Any]:
    """The live vetting output (qualified cells + gates + qualification_run_id)."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_vetting_report(qualification_run_id: str) -> Optional[Dict[str, Any]]:
    """The vetting report matching the live map's run id (has per-cell failed gates).

    Returns None when no matching report exists locally (older run, cleaned reports
    dir) — the catalog then ships without per-cell failure detail rather than lying.
    """
    for path in sorted(
        glob.glob(os.path.join(REPORTS_DIR, "vetting_report_*.json")), reverse=True
    ):
        with open(path, encoding="utf-8") as fh:
            report = json.load(fh)
        if report.get("qualification_run_id") == qualification_run_id:
            return report
    logger.warning("No vetting report found for run %s", qualification_run_id)
    return None


def load_gatekeeper_approval_rate(path: str = CHAMPION_MANIFEST) -> Optional[float]:
    """OOS approval rate of the live gatekeeper champion, or None if unreadable."""
    try:
        with open(path, encoding="utf-8") as fh:
            return float(json.load(fh)["oos_uplift"]["oos_approval_rate"])
    except (OSError, KeyError, TypeError, ValueError):
        logger.warning("champion manifest unreadable — approval_rate omitted")
        return None
