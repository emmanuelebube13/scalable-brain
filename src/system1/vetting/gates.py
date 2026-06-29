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
    scored.sort(
        key=lambda c: (-c["composite_score"], -c["trade_count"], c["max_drawdown"])
    )
    for i, c in enumerate(scored, start=1):
        c["rank"] = i
    return scored


def _variant_key(cell: Dict) -> str:
    """Stable per-cell weight key matching the (strategy, granularity) variant identity
    used everywhere else in the map (``vet._load_cells`` builds ``variant`` as
    ``f"{strategy_name}@{granularity}"`` and ``regime_strategy_map.json`` carries it).

    Prefer the cell's ``variant`` field; fall back to ``f"{strategy_id}@{granularity}"``
    when no name is available, so the key is still unique per granularity variant.
    Keying by ``strategy_id`` alone is the FIX-S1-004 bug: a strategy that qualifies at
    two granularities in one regime collides on a single key and the weights stop
    summing to 1.0.
    """
    variant = cell.get("variant")
    if variant:
        return str(variant)
    return f"{cell['strategy_id']}@{cell.get('granularity', '?')}"


def normalized_weights(ranked_cells: List[Dict]) -> Dict[str, float]:
    """Per-regime weights ∝ composite score (shifted positive), summing to 1.0.

    Duplicate-strategy policy — **keep-both (a)**: when one ``strategy_id`` qualifies at
    more than one granularity in a regime (e.g. ``Range_Stochastic_Divergence@H1`` and
    ``@H4``), each (strategy, granularity) **variant** is a distinct cell with its own
    composite score and gets its OWN weight; the weights across all variants in the
    regime sum to 1.0. We deliberately do NOT collapse variants to one weight per
    ``strategy_id`` — the variants are genuinely different (strategy, granularity) cells
    that the rest of MODEL-005 (the regime map, the ranking) treats as separate
    qualifiers, and collapsing would silently discard a qualified variant's allocation.

    Keys are the variant identity (``_variant_key``), NOT ``str(strategy_id)``, so two
    granularity variants of one strategy keep distinct keys. (Keying by ``strategy_id``
    is the FIX-S1-004 collision bug.) Caller asserts the per-regime sum-to-1 invariant
    (see ``vet._assert_weights_normalized``) so a degenerate map can never be published.
    """
    if not ranked_cells:
        return {}
    scores = [c["composite_score"] for c in ranked_cells]
    floor = min(scores)
    shifted = [s - floor + 1e-6 for s in scores]  # strictly positive
    total = sum(shifted)
    return {_variant_key(c): w / total for c, w in zip(ranked_cells, shifted)}
