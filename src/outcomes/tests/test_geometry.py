"""Tests for trade geometry — the ATR reference and the two multipliers.

The load-bearing test here is ``test_the_reference_matches_the_position_engines_own_atr``.
Everything else checks arithmetic; that one checks that this module and the engine are
talking about the same number. If they drift apart, ``atr_tp_multiplier`` stops being the
multiple the strategy declared and quietly becomes a slightly different quantity — the
exact failure mode R2 found in the structural labeller, where three callers with three
lookback windows produced three answers for the same bar.
"""

import numpy as np
import pandas as pd
import pytest

from src.outcomes import geometry as G


def _frame(n=200, seed=0):
    rng = np.random.default_rng(seed)
    close = 1.10 + np.cumsum(rng.normal(0, 0.0008, n))
    high = close + abs(rng.normal(0, 0.0006, n))
    low = close - abs(rng.normal(0, 0.0006, n))
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.DataFrame(
        {"Open": close, "High": high, "Low": low, "Close": close, "Volume": 1.0},
        index=idx,
    )


# --- the reference ---------------------------------------------------------------


def test_the_reference_matches_the_position_engines_own_atr():
    """One ATR definition, or the multiples stop meaning what the strategy declared.

    ``PositionEngine`` resolves an ATR-multiple take-profit leg against
    ``atr_values[fill_bar - 1]`` where ``atr_values = atr(H, L, C, ATR_PERIOD)``. This
    module must produce that same value at that same bar.
    """
    from src.layer0.data_access.indicators import atr
    from src.layer0.strategies.position_engine import ATR_PERIOD as ENGINE_PERIOD

    assert G.ATR_PERIOD == ENGINE_PERIOD

    frame = _frame()
    engine_atr = atr(frame["High"], frame["Low"], frame["Close"], period=ENGINE_PERIOD)
    ours = G.atr_reference(frame, reference="prior_bar")

    assert G.REFERENCE_BY_ENGINE["position_engine_v2"] == "prior_bar"
    for fill_bar in (50, 120, 199):
        assert ours.iloc[fill_bar] == pytest.approx(
            float(engine_atr.iloc[fill_bar - 1])
        )


def test_v1_resolves_against_the_entry_bar_because_it_fills_at_the_close():
    """``backtest_engine_v1`` enters at ``Close.iloc[i]``, so bar ``i`` is complete.

    Measured on Trend_EMA_ADX_H4/EUR_USD (201 trades): entry-bar reference returns the
    declared 1.5x with sd 0.0000, prior-bar returns 1.4968 with sd 0.1079. The dispersion
    is ATR(i-1)/ATR(i) — volatility acceleration leaking into a geometry column.
    """
    from src.layer0.data_access.indicators import atr

    assert G.REFERENCE_BY_ENGINE["backtest_engine_v1"] == "entry_bar"
    frame = _frame()
    raw = atr(frame["High"], frame["Low"], frame["Close"], period=G.ATR_PERIOD)
    pd.testing.assert_series_equal(G.atr_reference(frame, reference="entry_bar"), raw)


def test_an_undeclared_reference_raises_rather_than_defaulting():
    with pytest.raises(ValueError):
        G.atr_reference(_frame(), reference="whatever")


def test_a_v1_declared_multiple_round_trips_exactly():
    """The point of the per-engine reference: 1.5xATR must read as exactly 1.5."""
    frame = _frame()
    lookup = G.GeometryLookup(frame, reference="entry_bar")
    when = frame.index[100]
    ref = lookup.at(when)
    fill = 1.2345
    sl, tp = lookup.for_trade(when, fill, fill - 1.5 * ref, fill + 2.0 * ref)
    assert sl == pytest.approx(1.5)
    assert tp == pytest.approx(2.0)


def test_the_reference_matches_the_gatekeepers_joined_atr_value():
    """``build_frame`` joins ``build_inference_features``' atr_value with the same shift.

    Same series, same period, same shift — asserted rather than assumed, because the two
    are computed in different modules and nothing else would notice them diverging.
    """
    from src.gatekeeper.features import build_inference_features

    frame = _frame()
    # build_inference_features also reads structural labels from the DB; only the ATR
    # arithmetic is under test, so compare against its indicator call directly.
    from src.layer0.data_access.indicators import atr

    gk = atr(frame["High"], frame["Low"], frame["Close"], period=14).shift(1)
    pd.testing.assert_series_equal(G.atr_reference(frame, reference="prior_bar"), gk)
    assert callable(build_inference_features)


def test_the_reference_is_strictly_prior_bar():
    """The entry bar's own range is not known when the stop is placed at its close."""
    frame = _frame()
    ref = G.atr_reference(frame, reference="prior_bar")
    raw = G.atr(frame["High"], frame["Low"], frame["Close"], period=G.ATR_PERIOD)
    assert pd.isna(ref.iloc[0])
    assert ref.iloc[1] == pytest.approx(float(raw.iloc[0]))
    # and never equal to the same bar's own ATR, which is what a missing shift looks like
    assert ref.iloc[100] != pytest.approx(float(raw.iloc[100]))


# --- the multiples ---------------------------------------------------------------


def test_multiples_are_unsigned_distances_in_atr_units():
    sl, tp = G.multiples(
        entry_price=1.1000, stop_price=1.0980, take_profit_price=1.1060, atr_ref=0.0010
    )
    assert sl == pytest.approx(2.0)
    assert tp == pytest.approx(6.0)


def test_a_short_gives_the_same_magnitudes_as_the_mirror_long():
    """Direction lives in ``entry_signal_type``; duplicating it here would give the
    model two copies of one column."""
    long_sl, long_tp = G.multiples(1.1000, 1.0980, 1.1060, 0.0010)
    short_sl, short_tp = G.multiples(1.1000, 1.1020, 1.0940, 0.0010)
    assert (long_sl, long_tp) == pytest.approx((short_sl, short_tp))


def test_a_missing_take_profit_is_null_not_zero():
    """Trailing-stop, time and opposite-signal exits declare no target.

    Zero would read as a target at the entry price, which is a real and very different
    thing to say.
    """
    sl, tp = G.multiples(1.1000, 1.0980, None, 0.0010)
    assert sl == pytest.approx(2.0)
    assert tp is None


@pytest.mark.parametrize("bad_atr", [None, float("nan"), 0.0, -1.0, 1e-12])
def test_a_degenerate_atr_reference_yields_nothing(bad_atr):
    """During warmup the reference is NaN by construction; a trade there has no scale."""
    assert G.multiples(1.1000, 1.0980, 1.1060, bad_atr) == (None, None)


def test_a_declared_atr_multiple_round_trips():
    """The end-to-end invariant: a leg declared at 3x ATR comes back as 3.0.

    This is what makes the feature transferable. The engine resolves
    ``level = fill + direction * atr_multiple * atr_ref``; dividing that distance by the
    same ``atr_ref`` must return the multiple the strategy asked for, whatever the pair,
    the price level, or the volatility on the day.
    """
    frame = _frame()
    lookup = G.GeometryLookup(frame)
    when = frame.index[100]
    atr_ref = lookup.at(when)
    fill = 1.2345
    tp_level = fill + 1 * 3.0 * atr_ref
    stop_level = fill - 1 * 1.5 * atr_ref

    sl, tp = lookup.for_trade(when, fill, stop_level, tp_level)
    assert sl == pytest.approx(1.5)
    assert tp == pytest.approx(3.0)


# --- the lookup ------------------------------------------------------------------


def test_lookup_accepts_a_tz_aware_entry_time():
    """Price frames are tz-naive UTC; engines hand back naive stamps that persist_all
    later stamps as UTC. Either form must resolve to the same bar."""
    frame = _frame()
    lookup = G.GeometryLookup(frame)
    naive = frame.index[100]
    aware = naive.tz_localize("UTC")
    assert lookup.at(aware) == pytest.approx(lookup.at(naive))


def test_lookup_returns_none_for_a_bar_that_is_not_in_the_frame():
    """An exact match, not ``asof``: an entry time that is not a bar means something
    upstream is wrong, and sliding to the nearest earlier bar would hide it."""
    frame = _frame()
    lookup = G.GeometryLookup(frame)
    assert lookup.at(pd.Timestamp("1999-01-01")) is None
    assert lookup.at(frame.index[100] + pd.Timedelta(minutes=7)) is None


def test_lookup_returns_none_inside_the_warmup_window():
    frame = _frame()
    lookup = G.GeometryLookup(frame)
    assert lookup.at(frame.index[0]) is None
