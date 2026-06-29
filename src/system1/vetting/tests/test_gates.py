"""MODEL-005 gate boundary + ranking/weights tests (no DB/network). Skill: vetting-gate.md."""
from __future__ import annotations

from src.system1.vetting import gates as G


def make_cell(pf=1.5, sharpe=0.8, maxdd=0.25, winrate=0.40, recovery=3.0, oos=60,
              low_confidence=False, trade_count=100, strategy_id=1):
    return {
        "strategy_id": strategy_id, "variant": f"S{strategy_id}",
        "profit_factor": pf, "sharpe": sharpe, "max_drawdown": maxdd,
        "win_rate": winrate, "recovery_factor": recovery, "oos_months": oos,
        "low_confidence": low_confidence, "trade_count": trade_count,
    }


def test_boundary_acceptance():
    passed, failures = G.evaluate_gates(make_cell())  # all exactly at threshold
    assert passed and failures == []


def test_boundary_rejection_all_six():
    cell = make_cell(pf=1.49, sharpe=0.79, maxdd=0.26, winrate=0.39, recovery=2.99, oos=59)
    passed, failures = G.evaluate_gates(cell)
    assert not passed and len(failures) == 6


def test_low_confidence_always_rejected():
    cell = make_cell(pf=3.0, sharpe=2.0, maxdd=0.05, winrate=0.8, recovery=10.0, oos=120,
                     low_confidence=True, trade_count=5)
    passed, failures = G.evaluate_gates(cell)
    assert not passed and failures == ["LOW_CONFIDENCE"]


def test_individual_gate_boundaries():
    assert G.evaluate_gates(make_cell(pf=1.49))[0] is False
    assert G.evaluate_gates(make_cell(sharpe=0.79))[0] is False
    assert G.evaluate_gates(make_cell(maxdd=0.2501))[0] is False
    assert G.evaluate_gates(make_cell(winrate=0.399))[0] is False
    assert G.evaluate_gates(make_cell(recovery=2.99))[0] is False
    assert G.evaluate_gates(make_cell(oos=59))[0] is False


def test_ranking_dense_and_ordered():
    a = make_cell(strategy_id=1, sharpe=2.0)
    b = make_cell(strategy_id=2, sharpe=1.0)
    c = make_cell(strategy_id=3, sharpe=1.5)
    ranked = G.rank_cells([b, c, a])
    assert [r["rank"] for r in ranked] == [1, 2, 3]
    assert ranked[0]["strategy_id"] == 1  # highest sharpe → highest composite → rank 1


def test_weights_sum_to_one():
    ranked = G.rank_cells([make_cell(strategy_id=i, sharpe=1.0 + i * 0.3) for i in range(3)])
    w = G.normalized_weights(ranked)
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert all(0 <= v <= 1 for v in w.values())
