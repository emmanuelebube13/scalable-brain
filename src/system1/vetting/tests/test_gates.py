"""MODEL-005 gate boundary + ranking/weights tests (no DB/network). Skill: vetting-gate.md."""

from __future__ import annotations

import random

import pytest

from src.system1.vetting import gates as G
from src.system1.vetting import vet


def make_cell(
    pf=1.5,
    sharpe=0.8,
    maxdd=0.25,
    winrate=0.40,
    recovery=3.0,
    oos=60,
    low_confidence=False,
    trade_count=100,
    strategy_id=1,
    granularity="H1",
    variant=None,
    regime="Ranging",
):
    return {
        "strategy_id": strategy_id,
        "variant": variant if variant is not None else f"S{strategy_id}@{granularity}",
        "granularity": granularity,
        "regime": regime,
        "profit_factor": pf,
        "sharpe": sharpe,
        "max_drawdown": maxdd,
        "win_rate": winrate,
        "recovery_factor": recovery,
        "oos_months": oos,
        "low_confidence": low_confidence,
        "trade_count": trade_count,
    }


def test_boundary_acceptance():
    passed, failures = G.evaluate_gates(make_cell())  # all exactly at threshold
    assert passed and failures == []


def test_boundary_rejection_all_six():
    cell = make_cell(
        pf=1.49, sharpe=0.79, maxdd=0.26, winrate=0.39, recovery=2.99, oos=59
    )
    passed, failures = G.evaluate_gates(cell)
    assert not passed and len(failures) == 6


def test_low_confidence_always_rejected():
    cell = make_cell(
        pf=3.0,
        sharpe=2.0,
        maxdd=0.05,
        winrate=0.8,
        recovery=10.0,
        oos=120,
        low_confidence=True,
        trade_count=5,
    )
    passed, failures = G.evaluate_gates(cell)
    assert not passed and failures == ["LOW_CONFIDENCE"]


def test_oos_gate_can_return_false_and_symmetric_pass():
    """FIX-S1-002: the (now-real, OOS-only) oos_months gate CAN fire. A healthy cell with
    oos_months=12 is rejected with an OOS failure; the symmetric oos_months=72 cell passes.
    Guards against the gate going inert again."""
    starved = make_cell(oos=12)
    passed, failures = G.evaluate_gates(starved)
    assert passed is False and any(f.startswith("OOS") for f in failures)

    healthy = make_cell(oos=72)
    passed, failures = G.evaluate_gates(healthy)
    assert passed is True and failures == []


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
    ranked = G.rank_cells(
        [make_cell(strategy_id=i, sharpe=1.0 + i * 0.3) for i in range(3)]
    )
    w = G.normalized_weights(ranked)
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert all(0 <= v <= 1 for v in w.values())


# --- FIX-S1-004: duplicate strategy_id across granularities must not collapse weights ---


def test_weights_keep_both_variants_same_strategy_id():
    """Regression for FIX-S1-004: one strategy_id qualifying at two granularities in a
    regime keeps TWO distinct variant keys whose weights sum to 1.0 (it used to collapse
    onto a single ``str(strategy_id)`` key, leaving Ranging at ~5e-08)."""
    h1 = make_cell(
        strategy_id=10,
        granularity="H1",
        sharpe=3.69,
        recovery=100.0,
        variant="Range_Stochastic_Divergence@H1",
    )
    h4 = make_cell(
        strategy_id=10,
        granularity="H4",
        sharpe=1.16,
        recovery=7.63,
        variant="Range_Stochastic_Divergence@H4",
    )
    ranked = G.rank_cells([h1, h4])
    w = G.normalized_weights(ranked)
    assert set(w) == {
        "Range_Stochastic_Divergence@H1",
        "Range_Stochastic_Divergence@H4",
    }  # two distinct keys, NOT collapsed to "10"
    assert len(w) == 2
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_single_cell_regime_weight_is_one():
    w = G.normalized_weights(G.rank_cells([make_cell(strategy_id=7)]))
    assert list(w.values()) == [1.0] or abs(sum(w.values()) - 1.0) < 1e-9
    assert len(w) == 1


def test_weights_sum_to_one_property():
    """Property: for arbitrary ranked-cell lists, weights sum to 1.0 (±1e-9) and never
    collide (one key per cell), including repeated strategy_ids across granularities."""
    rng = random.Random(20260629)
    for _ in range(500):
        n = rng.randint(1, 10)
        cells = []
        for i in range(n):
            sid = rng.randint(1, 4)  # deliberately small pool -> duplicate strategy_ids
            gran = rng.choice(["H1", "H4", "D1"])
            cells.append(
                make_cell(
                    strategy_id=sid,
                    granularity=gran,
                    variant=f"S{sid}@{gran}#{i}",  # unique per cell
                    sharpe=rng.uniform(0.8, 4.0),
                    pf=rng.uniform(1.5, 3.0),
                    recovery=rng.uniform(3.0, 100.0),
                    maxdd=rng.uniform(0.01, 0.25),
                )
            )
        w = G.normalized_weights(G.rank_cells(cells))
        assert len(w) == n  # no key collisions
        assert abs(sum(w.values()) - 1.0) < 1e-9


def test_assert_weights_normalized_raises_on_broken():
    """The vet.build post-condition CAN fire: a non-summing regime raises and fails the run."""
    with pytest.raises(vet.WeightsNotNormalized):
        vet._assert_weights_normalized({"Ranging": {"10": 5e-08}})  # the shipped bug


def test_assert_weights_normalized_passes_normal_and_empty():
    # Empty regimes are skipped; well-formed regimes pass.
    vet._assert_weights_normalized({"High-Vol": {}, "Ranging": {"a": 0.6, "b": 0.4}})


def test_build_post_condition_raises_on_collapsed_weights(monkeypatch):
    """End-to-end: if normalized_weights ever returned a degenerate map, build() fails the
    run rather than emitting it (proves the guard is wired into build, not just standalone).
    """
    monkeypatch.setattr(G, "normalized_weights", lambda ranked: {"10": 5e-08})
    cells = [make_cell(strategy_id=10, regime="Ranging")]  # qualifies at threshold
    with pytest.raises(vet.WeightsNotNormalized):
        vet.build(cells, run_id="test-run")


def test_build_post_condition_passes_with_real_weights():
    """build() with two same-strategy_id variants in one regime now sums to 1.0 and succeeds."""
    cells = [
        make_cell(
            strategy_id=10,
            granularity="H1",
            regime="Ranging",
            sharpe=3.69,
            recovery=100.0,
            variant="Range_Stochastic_Divergence@H1",
        ),
        make_cell(
            strategy_id=10,
            granularity="H4",
            regime="Ranging",
            sharpe=1.16,
            recovery=7.63,
            variant="Range_Stochastic_Divergence@H4",
        ),
    ]
    out = vet.build(cells, run_id="test-run")
    ranging = out["weights"]["weights"]["Ranging"]
    assert len(ranging) == 2
    assert abs(sum(ranging.values()) - 1.0) < 1e-6
