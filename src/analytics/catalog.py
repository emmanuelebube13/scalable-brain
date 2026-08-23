"""Pure builder for strategy_catalog.json — every registered strategy, not just winners.

Names/descriptions come from ``dim_strategy``; qualification truth comes from the live
regime→strategy map; per-cell gate failures come from the matching vetting report's
``rejection_detail``. Nothing is recomputed here.
"""

from __future__ import annotations

from collections import defaultdict

from src.analytics import mechanics as MECH
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


def _clean(value: Any) -> Optional[str]:
    """Return a real string, or None for a null/placeholder."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "nan", "unclassified"}:
        return None
    return text


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

    # Mechanics are read from source and notes from a hand-edited overlay, so the
    # catalogue carries HOW each strategy trades and WHY it failed -- not just whether it
    # passed. See src/analytics/mechanics.py for why the two halves are kept separate.
    notes = MECH.load_notes()

    strategies = []
    for row in strategy_dim.sort_values("strategy_id").to_dict("records"):
        sid = int(row["strategy_id"])
        name = str(row["strategy_name"])
        strategies.append(
            MECH.enrich(
                {
                    "strategy_id": str(sid),
                    "name": name,
                    # NULL in the registry must publish as null, not as the literal
                    # strings "None"/"none". The dashboard measured description
                    # populated on 10/67 and family on 19/67 — the rest were absences
                    # rendered as answers, which is worse than an empty field: a reader
                    # cannot tell a missing description from a strategy named "None".
                    "family": _clean(_family(name, str(row["strategy_type"]))),
                    "description": _clean(row["description"]),
                    "granularities": granularities_by_sid.get(sid, []),
                    "qualified": sid in qual_regimes,
                    "qualified_regimes": qual_regimes.get(sid, []),
                    "qualification_run_id": run_id,
                    "gates_passed": gates_passed.get(sid, {}),
                    "gates_failed": gates_failed.get(sid, {}),
                },
                notes,
            )
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc,
        "notes_overlay": "docs/strategy-notes.json",
        "notes_count": sum(1 for s in strategies if s.get("notes_source")),
        "qualification_run_id": run_id,
        "gates": regime_map.get("gates", {}),
        "empty_regimes": regime_map.get("empty_regimes", []),
        "strategies": strategies,
    }
