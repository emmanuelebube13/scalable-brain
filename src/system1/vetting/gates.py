"""MODEL-005 — pure vetting gates + composite ranking (no DB/network). Skill: vetting-gate.md."""
from __future__ import annotations

from typing import Dict, List, Tuple

# Gate thresholds (all must pass; low-confidence cells always rejected).
GATES = {
    "profit_factor": 1.5,
    "sharpe": 0.8,
    "max_drawdown": 0.25,
    "win_rate": 0.40,
    "recovery_factor": 3.0,
    "oos_months": 60,
}

RANKING_RULE = "0.5*sharpe + 0.3*profit_factor + 0.2*recovery_factor - max_drawdown"


def evaluate_gates(cell: Dict) -> Tuple[bool, List[str]]:
    """Return (passed, failures). low_confidence is an unconditional rejection."""
    if cell.get("low_confidence", False):
        return False, ["LOW_CONFIDENCE"]
    failures: List[str] = []
    if cell["profit_factor"] < GATES["profit_factor"]:
        failures.append(f"PF={cell['profit_factor']:.2f} < 1.50")
    if cell["sharpe"] < GATES["sharpe"]:
        failures.append(f"Sharpe={cell['sharpe']:.2f} < 0.80")
    if cell["max_drawdown"] > GATES["max_drawdown"]:
        failures.append(f"MaxDD={cell['max_drawdown']:.1%} > 25%")
    if cell["win_rate"] < GATES["win_rate"]:
        failures.append(f"WinRate={cell['win_rate']:.1%} < 40%")
    if cell["recovery_factor"] < GATES["recovery_factor"]:
        failures.append(f"Recovery={cell['recovery_factor']:.2f} < 3.00")
    if cell.get("oos_months", 0) < GATES["oos_months"]:
        failures.append(f"OOS={cell['oos_months']}mo < 60mo")
    return len(failures) == 0, failures


def composite_score(cell: Dict) -> float:
    """Higher is better. 0.5*sharpe + 0.3*pf + 0.2*recovery - maxdd penalty."""
    return (
        0.5 * float(cell["sharpe"])
        + 0.3 * float(cell["profit_factor"])
        + 0.2 * float(cell["recovery_factor"])
        - float(cell["max_drawdown"])
    )


def rank_cells(cells: List[Dict]) -> List[Dict]:
    """Sort qualifying cells by composite score desc; tie-break: trade_count desc, maxdd asc.
    Returns the cells with dense ``rank`` (1..n) and ``composite_score`` attached."""
    scored = [{**c, "composite_score": composite_score(c)} for c in cells]
    scored.sort(key=lambda c: (-c["composite_score"], -c["trade_count"], c["max_drawdown"]))
    for i, c in enumerate(scored, start=1):
        c["rank"] = i
    return scored


def normalized_weights(ranked_cells: List[Dict]) -> Dict[str, float]:
    """Per-regime weights ∝ composite score (shifted positive), summing to 1.0."""
    if not ranked_cells:
        return {}
    scores = [c["composite_score"] for c in ranked_cells]
    floor = min(scores)
    shifted = [s - floor + 1e-6 for s in scores]  # strictly positive
    total = sum(shifted)
    return {
        str(c["strategy_id"]): w / total for c, w in zip(ranked_cells, shifted)
    }
