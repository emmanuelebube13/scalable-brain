"""MODEL-005 — pure vetting gates + composite ranking (no DB/network). Skill: vetting-gate.md."""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

# Weighting policy (FIX-S1-001): softmax over composite scores with a minimum-weight
# floor. ``TEMPERATURE`` controls how sharply capital concentrates on higher scores
# (higher -> flatter); ``MIN_WEIGHT`` is the capital floor every qualified variant is
# guaranteed, so no secondary qualifier is starved. When a regime has more variants
# than the floor can accommodate (n > 1/MIN_WEIGHT), the floor degrades gracefully to
# the equal-weight cap 1/n.
TEMPERATURE = 1.0
MIN_WEIGHT = 0.05

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
    # FIX-S1-002: oos_months is now TRUE out-of-sample coverage (the union span of the
    # walk-forward OOS windows the cell traded in), NOT the full in-sample trade span it used
    # to measure. The 60-month threshold is unchanged — it is now real, so this gate can
    # actually fire (a cell with little/no OOS history fails here). No gate-logic change.
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


def _apply_floor(weights: List[float], floor: float) -> List[float]:
    """Lift every weight to at least ``floor`` while keeping the sum at 1.0.

    Water-filling: pin any weight whose proportional share would fall below ``floor``
    to exactly ``floor``, then redistribute the remaining mass among the unpinned
    weights *in proportion to their original (softmax) magnitude* — so the relative
    ranking of the non-starved variants is preserved. Repeats until the pinned set is
    stable. Assumes ``floor * len(weights) <= 1`` (guaranteed by the ``floor = min(
    MIN_WEIGHT, 1/n)`` feasibility guard in :func:`normalized_weights`).
    """
    n = len(weights)
    if n == 0 or floor <= 0.0:
        return weights
    pinned = [False] * n
    while True:
        base = sum(w for w, p in zip(weights, pinned) if not p)
        remaining = 1.0 - floor * sum(pinned)
        if base <= 0.0:
            break  # everything pinned (only reachable when floor == 1/n)
        newly_pinned = False
        for i, (w, p) in enumerate(zip(weights, pinned)):
            if not p and remaining * w / base < floor:
                pinned[i] = True
                newly_pinned = True
        if not newly_pinned:
            break
    base = sum(w for w, p in zip(weights, pinned) if not p)
    remaining = 1.0 - floor * sum(pinned)
    out: List[float] = []
    for w, p in zip(weights, pinned):
        out.append(floor if p else (remaining * w / base if base > 0.0 else floor))
    return out


def normalized_weights(
    ranked_cells: List[Dict],
    *,
    temperature: float = TEMPERATURE,
    min_weight: float = MIN_WEIGHT,
) -> Dict[str, float]:
    """Per-regime capital weights via softmax over composite scores, summing to 1.0.

    FIX-S1-001 (sizing-contract / weight-starvation): the previous shift-by-floor
    normalization (``s - min(scores) + 1e-6``) forced the lowest-ranked qualified
    variant to ``1e-6/total`` — effectively zero capital — which starved every
    secondary qualifier and defeated the multi-tenant architecture. We now use a
    **temperature-scaled softmax** (magnitude-preserving: a bigger edge earns more
    capital) followed by a **minimum-weight floor** (:func:`_apply_floor`) that
    guarantees no qualified variant drops below ``min_weight``. The softmax is
    numerically stabilized by subtracting the max score before exponentiating.

    The floor is clamped to the equal-weight cap ``1/n`` so it is always feasible:
    when a regime has more variants than ``1/min_weight`` can seat, every variant
    converges to the equal weight ``1/n`` rather than raising.

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
    n = len(ranked_cells)
    floor = min(min_weight, 1.0 / n)  # feasibility: floor * n <= 1
    scores = [c["composite_score"] for c in ranked_cells]
    hi = max(scores)  # numerical stability: exp(0) == 1 for the top score
    exps = [math.exp((s - hi) / temperature) for s in scores]
    total = sum(exps)
    weights = [e / total for e in exps]
    weights = _apply_floor(weights, floor)
    return {_variant_key(c): w for c, w in zip(ranked_cells, weights)}
