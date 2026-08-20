"""Pure builder for frequency_stats.json.

Per qualified cell (per pair + ALL): trades/month distribution, holding time, win/loss
R stats, loss streaks. Plus per-(granularity, pair) causal-regime occupancy so the
consumer can estimate LIVE frequency as occupancy × signal cadence × gatekeeper
approval rate. OOS trades only, same re-asserted filter as returns.py.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

import numpy as np
import pandas as pd

from src.analytics.returns import QualifiedCell

SCHEMA_VERSION = "1"


def bar_hours(granularity: str) -> float:
    """Hours per bar for OANDA-style granularity codes (H1, H4, D1, M30, W)."""
    g = granularity.upper()
    unit, num = g[0], g[1:] or "1"
    factor = {"M": 1 / 60, "H": 1.0, "D": 24.0, "W": 168.0}.get(unit)
    if factor is None:
        raise ValueError(f"unknown granularity {granularity!r}")
    return float(num) * factor


def max_consecutive_losses(is_winner: pd.Series) -> int:
    """Longest run of consecutive losing trades (chronological order assumed)."""
    worst = run = 0
    for w in is_winner:
        run = 0 if w else run + 1
        worst = max(worst, run)
    return worst


def _trades_per_month(entry_times: pd.Series) -> Dict[str, float]:
    """Mean/p50/p90 of trades per calendar month over the cell's observed span.

    Zero-trade months inside the span count — a cell that traded 12 times in one month
    of a two-year span must not report 12 trades/month.
    """
    naive = entry_times.dt.tz_convert("UTC").dt.tz_localize(None)
    monthly = naive.dt.to_period("M").value_counts()
    span = pd.period_range(naive.min(), naive.max(), freq="M")
    counts = monthly.reindex(span, fill_value=0).to_numpy(dtype=float)
    return {
        "mean": round(float(counts.mean()), 3),
        "p50": round(float(np.percentile(counts, 50)), 3),
        "p90": round(float(np.percentile(counts, 90)), 3),
    }


def _cell_stats(cell: pd.DataFrame, granularity: str) -> Dict[str, Any]:
    cell = cell.sort_values("entry_time")
    r = cell["r_multiple"].to_numpy(dtype=float)
    wins, losses = r[r > 0], r[r <= 0]
    hold_hours = cell["holding_bars"].to_numpy(dtype=float) * bar_hours(granularity)
    return {
        "n_trades": int(len(cell)),
        "trades_per_month": _trades_per_month(cell["entry_time"]),
        "holding_hours_mean": round(float(hold_hours.mean()), 2),
        "holding_hours_median": round(float(np.median(hold_hours)), 2),
        "win_rate": round(float(cell["is_winner"].mean()), 4),
        "avg_win_r": round(float(wins.mean()), 4) if len(wins) else None,
        "avg_loss_r": round(float(losses.mean()), 4) if len(losses) else None,
        "max_consecutive_losses": max_consecutive_losses(cell["is_winner"]),
    }


def build_frequency_stats(
    tagged: pd.DataFrame,
    cells: Set[QualifiedCell],
    asset_symbols: Dict[int, str],
    occupancy: pd.DataFrame,
    gatekeeper_approval_rate: Optional[float],
) -> Dict[str, Any]:
    """frequency_stats.json content (OOS-only cell stats + regime occupancy)."""
    oos = tagged[tagged["is_oos"]]
    cell_rows: List[Dict[str, Any]] = []
    for sid, regime, gran in sorted(cells):
        cell = oos[
            (oos["strategy_id"] == sid)
            & (oos["regime"] == regime)
            & (oos["granularity"] == gran)
        ]
        if cell.empty:
            continue
        base = {"strategy_id": str(sid), "regime": regime, "granularity": gran}
        for aid in sorted(cell["asset_id"].unique()):
            pair = asset_symbols.get(int(aid), f"ASSET_{aid}")
            cell_rows.append(
                {
                    **base,
                    "pair": pair,
                    **_cell_stats(cell[cell["asset_id"] == aid], gran),
                }
            )
        cell_rows.append({**base, "pair": "ALL", **_cell_stats(cell, gran)})

    occ_rows: List[Dict[str, Any]] = []
    for (gran, aid), grp in occupancy.groupby(["granularity", "asset_id"]):
        occ_rows.append(
            {
                "granularity": str(gran),
                "pair": asset_symbols.get(int(aid), f"ASSET_{aid}"),
                "n_bars": int(grp["n_bars"].sum()),
                "occupancy": {
                    str(row["regime"]): round(float(row["occupancy"]), 4)
                    for _, row in grp.iterrows()
                },
            }
        )
    occ_rows.sort(key=lambda r: (r["granularity"], r["pair"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "oos_only": True,
        "gatekeeper_oos_approval_rate": gatekeeper_approval_rate,
        "cells": cell_rows,
        "regime_occupancy": occ_rows,
    }
