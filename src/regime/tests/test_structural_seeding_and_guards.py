"""R2.3 — SMA-seeded EMAs and the input guards.

The seeding defect
------------------
``ewm(adjust=False)`` seeds on the first observation, so a span-200 EMA still carries ~8%
of that one arbitrary price at bar 252 — while the warm-up mask is 252 bars, sized for the
z-score, not the EMA. For roughly a year and a half past the mask the Up/Down call was
partly a function of where the frame began, which is why the same bar could get different
labels from a 3-year window (``run.py``) and a 25-year one
(``publish_strategy_stats.py``).

:func:`test_truncating_the_lookback_barely_moves_a_seeded_ema` is the direct assertion of
the property being fixed. Note what SMA seeding does *not* do: it does not make two frames
with different content agree. It removes the dependence on one arbitrary starting price,
so a truncated window converges to the full-history answer far faster.

The guards
----------
Every operation in the labeller is positional. Unsorted, duplicated, tz-naive or
multi-instrument input produces confidently wrong labels with no exception. Each guard
gets a test that it raises on its own specific malformation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.regime import structural as S


def _frame(closes, start="2020-01-01", tz="UTC"):
    idx = pd.date_range(start, periods=len(closes), freq="D", tz=tz)
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [c * 1.001 for c in closes],
            "Low": [c * 0.999 for c in closes],
            "Close": closes,
        },
        index=idx,
    )


# --------------------------------------------------------------------------- #
# _seeded_ema
# --------------------------------------------------------------------------- #
def test_constant_series_equals_the_constant_from_span_minus_one():
    s = pd.Series([5.0] * 300)
    ema = S._seeded_ema(s, 200)
    assert np.isnan(ema.iloc[198])
    assert ema.iloc[199] == pytest.approx(5.0)
    assert ema.iloc[299] == pytest.approx(5.0)


def test_leading_nans_are_exactly_span_minus_one():
    ema = S._seeded_ema(pd.Series(np.arange(500, dtype="float64")), 200)
    assert int(ema.isna().sum()) == 199


def test_matches_a_hand_computed_sma_seeded_ema():
    vals = [float(i) for i in range(1, 11)]
    span = 4
    alpha = 2.0 / (span + 1.0)
    expected = [np.nan] * (span - 1)
    expected.append(sum(vals[:span]) / span)
    for v in vals[span:]:
        expected.append(alpha * v + (1 - alpha) * expected[-1])

    got = S._seeded_ema(pd.Series(vals), span)
    for a, b in zip(got.tolist(), expected):
        if np.isnan(b):
            assert np.isnan(a)
        else:
            assert a == pytest.approx(b, abs=1e-9)


def test_truncating_the_lookback_barely_moves_a_seeded_ema():
    """THE property being fixed: reproducibility across different lookback windows.

    This is the defect in operational terms. `run.py` computes labels from a 3-year frame,
    `publish_strategy_stats.py` from 25 years, and the Gatekeeper from full history. With
    `ewm(adjust=False)` those three anchor their EMA200 on three different arbitrary
    prices, so they disagree about the same bar — which is why the live label could not be
    reproduced from an archival rebuild, and why any audit of it was approximate.

    Note what SMA seeding does NOT do: it does not make two frames with different content
    agree. It makes a frame's EMA depend on the SMA of its first `span` bars instead of on
    one arbitrary price, so a truncated window converges to the full-history answer far
    faster. That is the claim tested here, against the old behaviour as a control.
    """
    rng = np.random.default_rng(7)
    full = pd.Series(rng.normal(100, 1, 2000).cumsum() / 40 + 100)

    truth = S._seeded_ema(full, 200)  # full history: the answer we want to reproduce
    cut = 800  # a "3-year window" starting part-way through
    window = full.iloc[cut:].reset_index(drop=True)

    seeded = S._seeded_ema(window, 200)
    legacy = window.ewm(span=200, adjust=False).mean()

    # Compare on bars past the 252-bar warm-up mask, where labels are actually emitted.
    at = 252
    truth_at = truth.iloc[cut + at]
    err_seeded = abs(seeded.iloc[at] - truth_at)
    err_legacy = abs(legacy.iloc[at] - truth_at)

    assert err_seeded < err_legacy, (
        f"SMA seeding did not improve lookback reproducibility "
        f"(seeded={err_seeded:.6f}, legacy={err_legacy:.6f})"
    )
    # And the legacy error must be materially non-zero, or the test proves nothing.
    assert err_legacy > 1e-3, "control is vacuous: legacy seeding showed no error here"


def test_the_seed_is_the_sma_of_the_first_span_bars_not_one_price():
    """The mechanism, stated directly: no single observation anchors the series."""
    vals = [1000.0] + [100.0] * 199 + [100.0] * 100
    ema = S._seeded_ema(pd.Series(vals), 200)
    # Seed = mean of the first 200 = (1000 + 199*100)/200 = 104.5, NOT 1000.
    assert ema.iloc[199] == pytest.approx(104.5)


def test_frame_shorter_than_the_span_is_all_nan_and_yields_all_unknown():
    ema = S._seeded_ema(pd.Series([1.0] * 50), 200)
    assert ema.isna().all()

    out = S.build_structural_labels(_frame([1.0 + 0.01 * i for i in range(50)]))
    assert set(out["regime"]) == {S.UNKNOWN}


def test_nan_emas_fall_through_to_unknown_rather_than_comparing_false_silently():
    """A NaN in either EMA makes all four conditions False, which must mean UNKNOWN.

    Asserted rather than assumed: the mapping's final `else` is implicit, and an implicit
    fallthrough that happens to be right is one refactor away from being wrong.
    """
    out = S.build_structural_labels(_frame([100.0 + i for i in range(260)]))
    # Bars inside the EMA200 warm-up (< 199) cannot have a directional label.
    assert set(out["regime"].iloc[:199]) == {S.UNKNOWN}


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #
def test_non_datetime_index_raises():
    df = _frame([1.0] * 10).reset_index(drop=True)
    with pytest.raises(TypeError, match="DatetimeIndex"):
        S.build_structural_labels(df)


def test_tz_naive_index_raises():
    df = _frame([1.0] * 10, tz=None)
    with pytest.raises(ValueError, match="tz-naive"):
        S.build_structural_labels(df)


def test_unsorted_index_raises():
    df = _frame([1.0] * 10)
    df = df.iloc[::-1]
    with pytest.raises(ValueError, match="not sorted"):
        S.build_structural_labels(df)


def test_duplicate_timestamps_raise():
    df = _frame([1.0] * 10)
    df = pd.concat([df, df.iloc[[5]]]).sort_index()
    with pytest.raises(ValueError, match="duplicate timestamps"):
        S.build_structural_labels(df)


@pytest.mark.parametrize("col", ["asset_id", "instrument", "symbol"])
def test_multiple_instruments_in_one_frame_raise(col):
    """Two instruments concatenated would bleed across every rolling window silently."""
    df = _frame([1.0] * 10)
    df[col] = ["A"] * 5 + ["B"] * 5
    with pytest.raises(ValueError, match="instruments in one"):
        S.build_structural_labels(df)


def test_a_single_instrument_column_is_fine():
    df = _frame([1.0 + 0.01 * i for i in range(300)])
    df["asset_id"] = 7
    S.build_structural_labels(df)  # must not raise


# --------------------------------------------------------------------------- #
# Contract preservation
# --------------------------------------------------------------------------- #
def test_default_return_shape_is_unchanged():
    """Existing callers must be unaffected by return_indicators being added."""
    out = S.build_structural_labels(_frame([100.0 + i * 0.1 for i in range(300)]))
    assert list(out.columns) == ["bar_time", "regime"]


def test_return_indicators_adds_columns_without_changing_the_labels():
    df = _frame([100.0 + i * 0.1 for i in range(300)])
    plain = S.build_structural_labels(df)
    rich = S.build_structural_labels(df, return_indicators=True)

    assert plain["regime"].tolist() == rich["regime"].tolist()
    for col in (
        "source_bar_time",
        "adx",
        "ema_fast",
        "ema_slow",
        "atr_pct",
        "vol_zscore",
    ):
        assert col in rich.columns


def test_source_bar_time_is_strictly_earlier_than_bar_time():
    """The shift(1) must be auditable from the data, not just asserted in a docstring."""
    rich = S.build_structural_labels(
        _frame([100.0 + i * 0.1 for i in range(300)]), return_indicators=True
    )
    pairs = rich.dropna(subset=["source_bar_time"])
    assert (pairs["source_bar_time"] < pairs["bar_time"]).all()


def test_bar_time_is_converted_not_relabelled():
    """A non-UTC tz-aware index must be CONVERTED, preserving the instant."""
    idx = pd.date_range("2020-01-01", periods=300, freq="D", tz="America/Sao_Paulo")
    df = pd.DataFrame(
        {
            "Open": 1.0,
            "High": 1.001,
            "Low": 0.999,
            "Close": [100.0 + i * 0.1 for i in range(300)],
        },
        index=idx,
    )
    out = S.build_structural_labels(df)
    assert out["bar_time"].iloc[0] == idx[0]  # same instant, expressed in UTC
    assert str(out["bar_time"].dt.tz) == "UTC"
