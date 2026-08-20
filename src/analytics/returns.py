"""Pure builder for trade_returns.json — the simulator's raw material.

Per QUALIFIED (strategy_id, regime, granularity) cell from the live regime→strategy
map, emits the chronological OOS per-trade r_multiple series split per pair, plus an
aggregated ``"pair": "ALL"`` cell. In-sample rows must never appear here (honesty rule
3 of S1-EXPORT-002); ``build_trade_returns`` re-asserts the OOS filter itself so a
caller mistake cannot leak in-sample trades into the export.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

import pandas as pd

from src.validation import walk_forward as WF

SCHEMA_VERSION = "1"

QualifiedCell = Tuple[int, str, str]  # (strategy_id, regime, granularity)


def qualified_cells(regime_map: Dict[str, Any]) -> Set[QualifiedCell]:
    """(strategy_id, regime, granularity) triples the live map actually qualifies.

    Granularity comes from the variant suffix (``...@H1``) — the map is keyed by
    regime with ranked variant entries.
    """
    cells: Set[QualifiedCell] = set()
    for regime, entries in regime_map.get("regimes", {}).items():
        for entry in entries:
            variant = entry.get("variant", "")
            if "@" not in variant:
                continue
            gran = variant.rsplit("@", 1)[1]
            cells.add((int(entry["strategy_id"]), str(regime), gran))
    return cells


def _cell_payload(
    cell: pd.DataFrame,
    strategy_id: int,
    regime: str,
    granularity: str,
    pair: str,
    folds_by_id: Dict[int, WF.Fold],
) -> Dict[str, Any]:
    cell = cell.sort_values("entry_time")
    fids = sorted({int(f) for f in cell["fold_id"].dropna().unique()})
    oos_months = round(
        WF.oos_month_span([folds_by_id[f] for f in fids if f in folds_by_id]), 2
    )
    return {
        "strategy_id": str(strategy_id),
        "regime": regime,
        "granularity": granularity,
        "pair": pair,
        "n_trades": int(len(cell)),
        "oos_months": oos_months,
        "r_multiples": [round(float(r), 4) for r in cell["r_multiple"]],
        "trade_timestamps": [
            t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in cell["entry_time"]
        ],
    }


def build_trade_returns(
    tagged: pd.DataFrame,
    cells: Set[QualifiedCell],
    asset_symbols: Dict[int, str],
    folds_by_gran: Dict[str, Dict[int, WF.Fold]],
) -> Dict[str, Any]:
    """trade_returns.json content: per-pair + ALL series for each qualified cell.

    ``tagged`` may contain in-sample rows; they are dropped here (re-asserted OOS
    filter). Output cells are deterministically ordered.
    """
    oos = tagged[tagged["is_oos"]]
    out: List[Dict[str, Any]] = []
    for sid, regime, gran in sorted(cells):
        folds_by_id = folds_by_gran.get(gran, {})
        cell = oos[
            (oos["strategy_id"] == sid)
            & (oos["regime"] == regime)
            & (oos["granularity"] == gran)
        ]
        if cell.empty:
            continue
        for aid in sorted(cell["asset_id"].unique()):
            pair = asset_symbols.get(int(aid), f"ASSET_{aid}")
            out.append(
                _cell_payload(
                    cell[cell["asset_id"] == aid], sid, regime, gran, pair, folds_by_id
                )
            )
        out.append(_cell_payload(cell, sid, regime, gran, "ALL", folds_by_id))
    return {
        "schema_version": SCHEMA_VERSION,
        "oos_only": True,
        "cells": out,
    }
