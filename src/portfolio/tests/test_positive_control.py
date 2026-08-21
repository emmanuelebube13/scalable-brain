"""The control that makes every other result in this package interpretable.

If ``test_planted_trend_is_detected`` fails, no negative result from this evaluator
means anything — we would be unable to distinguish "the strategy has no edge" from
"the measurement cannot see edge". That is the failure mode that makes months of
measurement worthless, so this test is deliberately the first one in the package.
"""

from __future__ import annotations

import pytest

from src.portfolio.evaluate import compute_metrics, portfolio_returns
from src.portfolio.schedule import build_weight_schedule
from src.portfolio.tests.synthetic import planted_trend_world, random_walk_world


def _sharpe(closes, vol_scaled: bool = False, cost: float = 0.0) -> float:
    schedule = build_weight_schedule(closes)
    net, turnover = portfolio_returns(
        closes, schedule, cost_per_unit_turnover=cost, vol_scaled=vol_scaled
    )
    return compute_metrics(net, turnover).sharpe


def test_planted_trend_is_detected() -> None:
    """A world built so momentum works must score strongly positive."""
    sharpe = _sharpe(planted_trend_world())
    assert sharpe > 0.5, (
        f"positive control failed: planted-trend world scored Sharpe {sharpe:.3f}. "
        f"The evaluator cannot detect an edge that is known to be present, so no "
        f"negative result it produces can be trusted."
    )


def test_planted_trend_survives_vol_scaling() -> None:
    """Inverse-vol scaling must not destroy a signal it is meant to sharpen."""
    assert _sharpe(planted_trend_world(), vol_scaled=True) > 0.5


def test_random_walk_scores_near_zero() -> None:
    """The mirror of the control: no planted signal, so no detected signal.

    A wide band is used deliberately. This asserts the evaluator is not *manufacturing*
    edge from noise; it is not a claim about the precise value, which is one draw.
    """
    sharpe = _sharpe(random_walk_world())
    assert abs(sharpe) < 0.5, (
        f"random-walk world scored Sharpe {sharpe:.3f}; an evaluator that finds "
        f"signal in noise will find it in real data too"
    )


def test_costs_reduce_but_do_not_invert_a_real_edge() -> None:
    """Turnover cost must bite monotonically, not flip the sign of a strong signal."""
    closes = planted_trend_world()
    free = _sharpe(closes, cost=0.0)
    charged = _sharpe(closes, cost=0.0002)
    assert charged < free
    assert charged > 0.0


@pytest.mark.parametrize("vol_scaled", [False, True])
def test_metrics_are_internally_consistent(vol_scaled: bool) -> None:
    """Drawdown, recovery and PF must agree with the return series they describe."""
    closes = planted_trend_world()
    schedule = build_weight_schedule(closes)
    net, turnover = portfolio_returns(closes, schedule, vol_scaled=vol_scaled)
    m = compute_metrics(net, turnover)

    assert m.bars > 0
    assert 0.0 <= m.hit_rate <= 1.0
    assert m.max_drawdown >= 0.0
    assert m.annualized_vol > 0.0
    # A profitable series has PF > 1 and a positive recovery factor; a losing one has
    # both on the other side. They must never disagree with each other.
    if m.total_return > 0:
        assert m.profit_factor > 1.0
        assert m.recovery_factor > 0.0
    else:
        assert m.profit_factor <= 1.0
        assert m.recovery_factor <= 0.0
