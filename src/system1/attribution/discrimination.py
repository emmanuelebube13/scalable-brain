"""FIX-S1-003 — regime-discrimination study (does the regime label earn its place?).

The regime->strategy map (regime_strategy_map.json) assumes *specialization*: different
strategies should win in different market regimes. This module quantifies whether that
premise holds on the **causal** regime label (``regime_causal``, FIX-S1-005 — NOT the leaked
``regime_smoothed``), under two tagging schemes:

  * **entry-only** — the production tag (``attribute.tag_regime_at_entry``): the regime in
    force at the entry bar.
  * **dominant-over-trade-life** — the modal causal regime over ``[entry, entry + holding_bars]``
    (hypothesis #1 in the fix doc: an entry-bar label is a weak proxy for a multi-bar trade).

For each strategy it reports the per-regime win-rate, the max-min **spread**, and a
chi-square test of independence between regime and win/loss. A small p-value with a material
spread means the regime carries discriminating information; a flat spread with p > 0.05 means
the regime dimension is cosmetic for that strategy.

This is a **post-hoc measurement only** — it does not change production attribution, and the
dominant-over-life tag uses bars from inside the trade's life (so it is NOT a tradeable,
point-in-time signal; using it to *gate* trades would be look-ahead). It exists to answer
FIX-S1-003 honestly and to gate any promotion of the regime map on real discrimination.

Usage: python -m src.system1.attribution.discrimination
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency
from sqlalchemy import text

from src.common.db import get_engine
from src.system1.attribution import attribute as ATTR
from src.system1.attribution.attribute import UNKNOWN_REGIME

logger = logging.getLogger("system1.discrimination")

# Bar cadence per granularity — used to convert holding_bars into an exit timestamp.
STEP_BY_GRANULARITY: Dict[str, pd.Timedelta] = {
    "H1": pd.Timedelta(hours=1),
    "H4": pd.Timedelta(hours=4),
}

# A spread is only "material" (worth specializing on) above this win-rate gap; below it,
# even a statistically significant chi-square is economically trivial (FIX-S1-003 §5).
MATERIAL_SPREAD = 0.10

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
REPORTS_DIR = os.path.join(_REPO_ROOT, "results", "reports")


def _load_trades_with_holding(engine) -> pd.DataFrame:
    """Load trade outcomes with ``holding_bars`` (needed for the over-life window)."""
    sql = text(
        'SELECT outcome_id, "timestamp" AS entry_time, asset_id, strategy_id, '
        "granularity, is_winner, holding_bars FROM fact_trade_outcomes"
    )
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    df["holding_bars"] = df["holding_bars"].fillna(0).astype(int)
    return df


def dominant_regime_in_window(
    bar_times: np.ndarray, bar_regimes: np.ndarray, entry: Any, exit_: Any
) -> str:
    """Modal regime over bars in ``[entry, exit_]`` (causal labels).

    ``bar_times`` must be sorted ascending. When no bar falls inside the window (e.g. a
    same-bar exit), falls back to the most recent regime at-or-before ``entry`` (the
    entry-only tag); when there is no prior bar either, returns ``UNKNOWN_REGIME``. Ties are
    broken deterministically (lexicographically smallest label, via ``np.unique``).
    """
    lo = int(np.searchsorted(bar_times, entry, side="left"))
    hi = int(np.searchsorted(bar_times, exit_, side="right"))
    window = bar_regimes[lo:hi]
    if window.size == 0:
        j = int(np.searchsorted(bar_times, entry, side="right")) - 1
        return str(bar_regimes[j]) if j >= 0 else UNKNOWN_REGIME
    vals, counts = np.unique(window, return_counts=True)
    return str(vals[int(np.argmax(counts))])


def tag_dominant_regime_over_life(trades: pd.DataFrame, engine) -> pd.DataFrame:
    """Add ``regime_dominant`` = modal causal regime over each trade's holding window.

    Mirrors ``attribute.tag_regime_at_entry``'s per-granularity / per-asset structure but
    aggregates the causal label over ``[entry_time, entry_time + holding_bars * step]``
    instead of reading only the entry bar.
    """
    parts: List[pd.DataFrame] = []
    for gran, tg in trades.groupby("granularity"):
        step = STEP_BY_GRANULARITY.get(str(gran))
        regimes = ATTR._load_regimes(engine, gran)
        for aid, ta in tg.groupby("asset_id"):
            ta = ta.sort_values("entry_time").copy()
            ra = regimes[regimes["asset_id"] == aid].sort_values("bar_time")
            if ra.empty or step is None:
                ta["regime_dominant"] = UNKNOWN_REGIME
                parts.append(ta)
                continue
            bar_times = ra["bar_time"].to_numpy()
            bar_regimes = ra["regime_causal"].to_numpy().astype(object)
            exits = ta["entry_time"] + ta["holding_bars"].astype(int) * step
            entries_np = ta["entry_time"].to_numpy()
            exits_np = exits.to_numpy()
            ta["regime_dominant"] = [
                dominant_regime_in_window(bar_times, bar_regimes, e, x)
                for e, x in zip(entries_np, exits_np)
            ]
            parts.append(ta)
    return pd.concat(parts, ignore_index=True)


def _chi2_pvalue(wins: np.ndarray, losses: np.ndarray) -> Optional[float]:
    """Chi-square p-value for regime (rows) x win/loss (cols) independence.

    Returns ``None`` when the contingency table is degenerate (fewer than 2 regimes, or an
    all-zero row/column), where the test is undefined.
    """
    table = np.vstack([wins, losses]).T.astype(float)
    if table.shape[0] < 2:
        return None
    if (table.sum(axis=1) == 0).any() or (table.sum(axis=0) == 0).any():
        return None
    try:
        _, p, _, _ = chi2_contingency(table)
    except ValueError:
        return None
    return float(p)


def win_rate_spread_table(tagged: pd.DataFrame, regime_col: str) -> pd.DataFrame:
    """Per-strategy win-rate-by-regime, max-min spread, and chi-square p-value.

    ``tagged`` must have ``strategy_id``, ``is_winner`` (0/1), and ``regime_col``. Rows tagged
    ``UNKNOWN_REGIME`` are excluded (no label to attribute to).
    """
    rows: List[Dict[str, Any]] = []
    valid = tagged[tagged[regime_col] != UNKNOWN_REGIME]
    for sid, g in valid.groupby("strategy_id"):
        agg = g.groupby(regime_col)["is_winner"].agg(["sum", "count"])
        wins = agg["sum"].to_numpy(dtype=float)
        losses = (agg["count"] - agg["sum"]).to_numpy(dtype=float)
        win_rate = agg["sum"] / agg["count"]
        p = _chi2_pvalue(wins, losses)
        spread = float(win_rate.max() - win_rate.min()) if len(win_rate) else 0.0
        rows.append(
            {
                "strategy_id": int(sid),
                "n": int(len(g)),
                "spread": round(spread, 4),
                "chi2_p": (round(p, 6) if p is not None else None),
                "discriminates": bool(
                    p is not None and p < 0.05 and spread >= MATERIAL_SPREAD
                ),
                "win_rate_by_regime": {
                    str(r): round(float(v), 4) for r, v in win_rate.items()
                },
            }
        )
    return pd.DataFrame(rows).sort_values("strategy_id").reset_index(drop=True)


def summarize(table: pd.DataFrame) -> Dict[str, Any]:
    """Headline counts for a spread table: how many strategies actually discriminate."""
    return {
        "n_strategies": int(len(table)),
        "n_discriminating": int(table["discriminates"].sum()),
        "max_spread": (float(table["spread"].max()) if len(table) else 0.0),
        "median_spread": (float(table["spread"].median()) if len(table) else 0.0),
    }


def run(write_report: bool = True) -> Dict[str, Any]:
    """Run the discrimination study on real data (log-only; no production artifacts touched)."""
    engine = get_engine()
    trades = _load_trades_with_holding(engine)
    logger.info("Loaded %d trades", len(trades))

    entry_tagged = ATTR.tag_regime_at_entry(
        trades, engine
    )  # adds 'regime' (entry-only)
    dom_tagged = tag_dominant_regime_over_life(trades, engine)  # adds 'regime_dominant'
    merged = entry_tagged.merge(
        dom_tagged[["outcome_id", "regime_dominant"]], on="outcome_id", how="left"
    )

    entry_table = win_rate_spread_table(merged, "regime")
    dominant_table = win_rate_spread_table(merged, "regime_dominant")

    report: Dict[str, Any] = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n_trades": int(len(trades)),
        "regime_label": "regime_causal (FIX-S1-005)",
        "material_spread_threshold": MATERIAL_SPREAD,
        "entry_only": {
            "summary": summarize(entry_table),
            "per_strategy": entry_table.to_dict("records"),
        },
        "dominant_over_life": {
            "summary": summarize(dominant_table),
            "per_strategy": dominant_table.to_dict("records"),
        },
    }
    if write_report:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        path = os.path.join(
            REPORTS_DIR,
            f"regime_discrimination_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json",
        )
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, default=str)
        report["report_path"] = path
        logger.info("Wrote discrimination report -> %s", path)
    return report


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="FIX-S1-003 regime-discrimination study"
    )
    parser.add_argument("--no-report", action="store_true")
    args = parser.parse_args()
    rep = run(write_report=not args.no_report)
    print(
        json.dumps(
            {k: v for k, v in rep.items() if k != "per_strategy"}, indent=2, default=str
        )
    )
    print("\nentry-only summary    :", rep["entry_only"]["summary"])
    print("dominant-over-life sum:", rep["dominant_over_life"]["summary"])


if __name__ == "__main__":
    main()
