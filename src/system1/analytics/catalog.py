"""Pure builder for strategy_catalog.json — every registered strategy, not just winners.

Names/descriptions come from ``dim_strategy``; qualification truth comes from the live
regime→strategy map; per-cell gate failures come from the matching vetting report's
``rejection_detail``. Nothing is recomputed here.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

import pandas as pd

SCHEMA_VERSION = "1"

_FAMILY_BY_PREFIX = (
    ("Trend_", "trend"),
    ("Range_", "mean-reversion"),
    ("VCP", "breakout"),
    ("Support", "support-resistance"),
)


def _family(name: str, strategy_type: str) -> str:
    for prefix, family in _FAMILY_BY_PREFIX:
        if name.startswith(prefix):
            return family
    return strategy_type.lower().replace("_", "-")


def build_catalog(
    strategy_dim: pd.DataFrame,
    regime_map: Dict[str, Any],
    vetting_report: Optional[Dict[str, Any]],
    granularities_by_sid: Dict[int, List[str]],
    generated_at_utc: str,
) -> Dict[str, Any]:
    run_id = regime_map.get("qualification_run_id")

    # qualified cells + their OOS metrics, keyed by strategy
    qual_regimes: Dict[int, List[str]] = defaultdict(list)
    gates_passed: Dict[int, Dict[str, Any]] = defaultdict(dict)
    for regime, entries in regime_map.get("regimes", {}).items():
        for entry in entries:
            sid = int(entry["strategy_id"])
            if regime not in qual_regimes[sid]:
                qual_regimes[sid].append(regime)
            gates_passed[sid][f"{entry['variant']}@{regime}"] = entry.get("metrics", {})

    # per-cell gate failures from the vetting report (may be absent for old runs)
    gates_failed: Dict[int, Dict[str, List[str]]] = defaultdict(dict)
    if vetting_report:
        for rej in vetting_report.get("rejection_detail", []):
            sid = int(rej["strategy_id"])
            key = f"{rej['variant']}@{rej['regime']}"
            gates_failed[sid][key] = list(rej.get("failed_gates", []))

    strategies = []
    for row in strategy_dim.sort_values("strategy_id").to_dict("records"):
        sid = int(row["strategy_id"])
        name = str(row["strategy_name"])
        strategies.append(
            {
                "strategy_id": str(sid),
                "name": name,
                "family": _family(name, str(row["strategy_type"])),
                "description": str(row["description"]),
                "granularities": granularities_by_sid.get(sid, []),
                "qualified": sid in qual_regimes,
                "qualified_regimes": qual_regimes.get(sid, []),
                "qualification_run_id": run_id,
                "gates_passed": gates_passed.get(sid, {}),
                "gates_failed": gates_failed.get(sid, {}),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc,
        "qualification_run_id": run_id,
        "gates": regime_map.get("gates", {}),
        "empty_regimes": regime_map.get("empty_regimes", []),
        "strategies": strategies,
    }
