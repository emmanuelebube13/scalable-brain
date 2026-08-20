"""FIX-S1-014 — integrity disqualification must beat the performance gates.

The live map consisted entirely of `Range_Stochastic_Divergence` (strategy_id 10),
which reads the future via a centred rolling window and emits zero signals when
computed causally. Its attribution metrics (PF 1.92, Sharpe 1.07) are real numbers
describing a backtest it could never have traded.

The essential property, and the reason these tests exist: **re-running vetting must
not re-qualify it.** Removing it from `regime_strategy_map.json` by hand would be
silently undone by the next `vet --live`, because the attribution rows still look
excellent. So the disqualification has to be in code, ahead of the gates.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from src.vetting import vet as V


def _passing_cell(strategy_id: int, regime: str = "Ranging") -> Dict[str, Any]:
    """A cell whose metrics clear every gate comfortably.

    Deliberately excellent: if the disqualification only fired on weak metrics it
    would be indistinguishable from an ordinary gate rejection.
    """
    return {
        "strategy_id": strategy_id,
        "strategy_name": f"Strategy_{strategy_id}",
        "variant": f"Strategy_{strategy_id}@H1",
        "regime": regime,
        "granularity": "H1",
        "profit_factor": 3.06,
        "sharpe": 1.74,
        "max_drawdown": 0.04,
        "win_rate": 0.65,
        "recovery_factor": 6.23,
        "oos_months": 83.67,
        "trade_count": 332,
        "low_confidence": False,
    }


def test_disqualified_strategy_is_rejected_despite_passing_metrics() -> None:
    """The whole point: excellent numbers must not rescue a barred strategy."""
    sid = next(iter(V.INTEGRITY_DISQUALIFIED))
    cell = _passing_cell(sid)

    # Sanity: these metrics really would pass on merit.
    from src.vetting import gates as G

    passed, failures = G.evaluate_gates(cell)
    assert passed, f"fixture is not actually gate-passing: {failures}"

    out = V.build([cell], run_id="test")
    qualified = [s for entries in out["map"]["regimes"].values() for s in entries]
    assert qualified == [], "a disqualified strategy reached the live map"


def test_integrity_failure_is_counted_separately_from_gate_failures() -> None:
    """A disqualification is not a near miss and must not be filed as one."""
    sid = next(iter(V.INTEGRITY_DISQUALIFIED))
    out = V.build([_passing_cell(sid)], run_id="test")

    detail = out["rejection_detail"]
    assert len(detail) == 1
    assert detail[0]["failed_gates"] == ["INTEGRITY_DISQUALIFIED"]
    assert detail[0]["strategy_id"] == sid


def test_rejection_carries_its_reason_so_the_report_explains_itself() -> None:
    """A reader of the report should not have to find the FIX document."""
    sid, reason = next(iter(V.INTEGRITY_DISQUALIFIED.items()))
    out = V.build([_passing_cell(sid)], run_id="test")

    recorded = out["rejection_detail"][0]["integrity_reason"]
    assert recorded == reason
    assert "look-ahead" in recorded.lower()
    assert "FIX-S1-014" in recorded


def test_clean_strategies_are_unaffected() -> None:
    """The bar must be surgical — nine of the ten audited strategies were clean."""
    clean_id = max(V.INTEGRITY_DISQUALIFIED) + 1000
    assert clean_id not in V.INTEGRITY_DISQUALIFIED

    out = V.build([_passing_cell(clean_id)], run_id="test")
    qualified = [
        s["strategy_id"] for entries in out["map"]["regimes"].values() for s in entries
    ]
    assert qualified == [clean_id]


def test_empty_qualified_set_produces_a_valid_empty_map() -> None:
    """M1 — honest zero. An empty map is the correct output, not an error.

    Strategy 10 was the only qualified strategy, so barring it empties the map.
    That must serialise cleanly rather than raising, because the honest state has
    to be representable.
    """
    sid = next(iter(V.INTEGRITY_DISQUALIFIED))
    out = V.build([_passing_cell(sid, regime=r) for r in V.REGIMES], run_id="test")

    regime_map = out["map"]

    # A starved regime is OMITTED from `regimes` and recorded in `empty_regimes`;
    # absence is how starvation is expressed. With the only strategy barred, every
    # regime starves, so `regimes` is empty and all four are listed as starved.
    assert regime_map["regimes"] == {}
    assert set(regime_map["empty_regimes"]) == set(V.REGIMES)
    assert out["rejection_detail"]

    # Downstream must be able to consume it. `_update_registry` iterates
    # regimes.values() to build the qualified set — empty here means every strategy
    # is correctly reset to is_qualified = false.
    qualified_ids = {
        s["strategy_id"] for e in regime_map["regimes"].values() for s in e
    }
    assert qualified_ids == set()

    import json

    json.dumps(regime_map)  # must be serialisable


def test_disqualification_survives_a_rerun() -> None:
    """Idempotence. The failure mode this guards against is a hand-edited map file
    being silently undone by the next vetting run."""
    sid = next(iter(V.INTEGRITY_DISQUALIFIED))
    cells = [_passing_cell(sid)]

    for _ in range(3):
        out = V.build(cells, run_id="test")
        qualified = [s for e in out["map"]["regimes"].values() for s in e]
        assert qualified == []


@pytest.mark.parametrize("as_type", [int, str])
def test_strategy_id_type_does_not_defeat_the_bar(as_type: Any) -> None:
    """`_load_cells` casts to int, but a caller passing a string id must not slip
    past the blocklist through a type mismatch."""
    sid = next(iter(V.INTEGRITY_DISQUALIFIED))
    cell = _passing_cell(sid)
    cell["strategy_id"] = as_type(sid)

    out = V.build([cell], run_id="test")
    assert [s for e in out["map"]["regimes"].values() for s in e] == []
