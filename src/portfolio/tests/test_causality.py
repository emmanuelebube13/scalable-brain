"""Look-ahead guards for the portfolio path.

``assert_no_lookahead_v2`` protects the single-pair contract by truncating frames and
re-emitting orders. Nothing protected the cross-sectional path, because the
cross-sectional path did not exist. These are its equivalents: cadence and weights must
be truncation-stable, and a weight decided at bar ``t`` must not claim bar ``t``'s own
return.

FIX-S1-013 is the reason this file is not optional. A centred rolling window put a
strategy with a fictional PF 3.24 into the live map for months; the class of bug is
"the measurement quietly saw the future", and the portfolio path has two fresh places
for it to hide.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.layer0.strategies.research.currency_momentum_factor import (
    direction_for_currency_weight,
    net_tercile_weights,
)
from src.portfolio.evaluate import expand_weights, portfolio_returns
from src.portfolio.schedule import (
    LOOKBACK_BARS,
    build_weight_schedule,
    currency_weights_at,
    pair_is_usd_base,
    rebalance_bars,
)
from src.portfolio.tests.synthetic import PAIR_LEGS, planted_trend_world

# --------------------------------------------------------------------------- shift


def _toy_closes(n: int = 12) -> pd.DataFrame:
    index = pd.bdate_range("2020-01-01", periods=n, tz="UTC", name="timestamp")
    rng = np.random.default_rng(3)
    data = {pair: 1.0 + np.cumsum(rng.normal(0, 0.01, size=n)) for pair in PAIR_LEGS}
    return pd.DataFrame(data, index=index)


def test_weight_does_not_claim_its_own_decision_bar() -> None:
    """A weight decided at the close of bar i earns nothing until bar i+1."""
    closes = _toy_closes()
    decision = 4
    schedule = pd.DataFrame(
        [{p: (1.0 if p == "EUR_USD" else 0.0) for p in closes.columns}],
        index=pd.DatetimeIndex([closes.index[decision]], name="timestamp"),
    )[list(closes.columns)]

    net, _ = portfolio_returns(closes, schedule)
    returns = closes.pct_change()

    assert net.iloc[decision] == pytest.approx(
        0.0
    ), "weight earned its own decision bar"
    assert net.iloc[decision + 1] == pytest.approx(
        float(returns["EUR_USD"].iloc[decision + 1])
    )


def test_removing_the_shift_inflates_the_result() -> None:
    """The shift is load-bearing, not cosmetic — prove it changes the answer."""
    closes = planted_trend_world(n_bars=2000)
    schedule = build_weight_schedule(closes)
    honest, _ = portfolio_returns(closes, schedule)

    weights = expand_weights(schedule, closes.index)
    cheating = (weights * closes.pct_change()).sum(axis=1)  # no .shift(1)

    def sharpe(s: pd.Series) -> float:
        s = s.dropna()
        return float(s.mean() / s.std() * np.sqrt(252))

    assert sharpe(cheating) > sharpe(honest), (
        "peeking at the decision bar did not change the result, which means the "
        "shift under test is not actually doing anything"
    )


# ------------------------------------------------------------------------ cadence


def test_rebalance_cadence_is_one_per_calendar_month() -> None:
    closes = planted_trend_world(n_bars=1500)
    bars = rebalance_bars(closes.index)
    stamps = closes.index[bars]
    months = [(t.year, t.month) for t in stamps]
    assert len(months) == len(set(months)), "more than one rebalance in a month"
    assert all(b >= LOOKBACK_BARS for b in bars), "rebalance inside the warmup"


def test_cadence_is_truncation_stable() -> None:
    """Truncating the future must not change which past bars were rebalance bars."""
    closes = planted_trend_world(n_bars=1500)
    cut = 1200
    full = [b for b in rebalance_bars(closes.index) if b < cut]
    truncated = rebalance_bars(closes.index[:cut])
    assert full == truncated


def test_weights_are_truncation_stable() -> None:
    """The whole schedule up to the cut must be byte-identical after truncation."""
    closes = planted_trend_world(n_bars=1500)
    cut = 1200
    full = build_weight_schedule(closes)
    truncated = build_weight_schedule(closes.iloc[:cut])

    shared = full.index.intersection(truncated.index)
    assert len(shared) > 5, "too few shared rebalances to be a meaningful check"
    pd.testing.assert_frame_equal(full.loc[shared], truncated.loc[shared])


def test_signal_uses_only_closed_bars() -> None:
    """currency_weights_at(i) must be unchanged by anything after bar i."""
    closes = planted_trend_world(n_bars=1200)
    i = 900
    before = currency_weights_at(closes, i)
    mutated = closes.copy()
    mutated.iloc[i + 1 :] *= 1.5  # violently change the future
    assert currency_weights_at(mutated, i) == before


# ---------------------------------------------------------------- ranking contract


def test_currency_weights_sum_to_zero() -> None:
    """The cross-section is dollar-neutral by construction; drift means a sign error."""
    closes = planted_trend_world(n_bars=1500)
    for i in rebalance_bars(closes.index)[:20]:
        weights = currency_weights_at(closes, i)
        assert sum(weights.values()) == pytest.approx(0.0, abs=1e-12)


def test_five_currency_degeneracy_is_preserved() -> None:
    """§2/§10 row 2: with five currencies the median one nets to exactly zero."""
    mom = {"EUR": 0.5, "GBP": 0.3, "JPY": 0.1, "AUD": -0.2, "CAD": -0.4}
    weights = net_tercile_weights(mom)
    assert weights["JPY"] == pytest.approx(0.0)
    assert weights["EUR"] == pytest.approx(1 / 3)
    assert weights["CAD"] == pytest.approx(-1 / 3)


def test_pair_weight_sign_agrees_with_the_pinned_direction_function() -> None:
    """Our continuous mapping must match the fixture-pinned discrete one."""
    closes = planted_trend_world(n_bars=1500)
    schedule = build_weight_schedule(closes)
    i = rebalance_bars(closes.index)[10]
    stamp = closes.index[i]
    currency = currency_weights_at(closes, i)

    for pair in schedule.columns:
        from src.portfolio.schedule import PAIR_TO_CURRENCY

        cw = currency[PAIR_TO_CURRENCY[pair]]
        pair_weight = float(schedule.loc[stamp, pair])
        if cw == 0.0:
            assert pair_weight == pytest.approx(0.0)
            continue
        expected = direction_for_currency_weight(cw, usd_base=pair_is_usd_base(pair))
        assert np.sign(pair_weight) == expected
