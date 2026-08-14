"""Tests for causal_structure — boundary tests, not average-case tests.

The whole point of the module is causality: a swing OCCURS at bar k but is
KNOWABLE only at bar k+period. An average-case test passes vacuously here —
that is exactly how centred-window look-ahead survived qualification and
reached production (FIX-S1-013, docs/LOOKAHEAD_FINDINGS.md). Every test here
asserts at a specific boundary bar.

Covers spec §9 acceptance #8 (test_causal_swings): a toy StrategyV2 built on
confirmed_swing_points passes assert_no_lookahead_v2; the equivalent strategy
built on indicators.detect_swing_points fails it.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Mapping, Sequence

import numpy as np
import pandas as pd
import pytest

from src.layer0.data_access.indicators import detect_swing_points
from src.layer0.strategies.causal_structure import (
    confirmed_swing_points,
    last_n_confirmed_highs,
    last_n_confirmed_lows,
    zigzag_swings,
)
from src.layer0.strategies.contract_v2 import (
    ExitLeg,
    LookAheadError,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
    assert_no_lookahead_v2,
)

# ---------------------------------------------------------------------------
# helpers / fixtures
# ---------------------------------------------------------------------------


def _series(values: Sequence[float], start: str = "2021-01-01") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq="h", tz="UTC")
    return pd.Series(values, index=idx, dtype=float)


def _oscillating_frame(n: int = 400) -> pd.DataFrame:
    """Sawtooth frame: a clean swing high every 37 bars, so truncation probes
    provably cover firing bars (FIX-S1-013: quiet windows prove nothing)."""
    idx = pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC")
    close = pd.Series(np.arange(n, dtype=float) % 37 + 100.0, index=idx)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": 1000.0,
        },
        index=idx,
    )


def _random_walk(n: int = 2000, seed: int = 3) -> tuple[pd.Series, pd.Series]:
    rng = np.random.default_rng(seed)
    mid = 100.0 + rng.normal(0.0, 1.0, n).cumsum()
    idx = pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC")
    high = pd.Series(mid + rng.uniform(0.05, 0.35, n), index=idx)
    low = pd.Series(mid - rng.uniform(0.05, 0.35, n), index=idx)
    return high, low


def _v2meta(sid: str) -> StrategyMetadataV2:
    return StrategyMetadataV2(
        strategy_id=sid,
        name="swing test strategy",
        version="0.0.1",
        author="wave1 agent C tests",
        hypothesis="A test strategy trading confirmed swing levels, edge fully stated.",
        granularities=["H1"],
        pairs=["EUR_USD"],
        primary_granularity="H1",
    )


def _breakout_intent(
    sid: str, decision_bar: pd.Timestamp, level: float, decision_close: float
) -> OrderIntent:
    """buy_stop two points above the swing level; valid only when the level is
    above the decision-bar close (otherwise an instant fill in disguise)."""
    entry = level + 2.0
    return OrderIntent(
        decision_bar=decision_bar,
        direction=1,
        entry="buy_stop",
        entry_price=entry,
        decision_close=decision_close,
        stop=StopRule(price=entry - 7.0),
        exits=[
            ExitLeg(fraction=1.0, kind="take_profit", price=entry + 11.0, label="TP")
        ],
        strategy_id=sid,
    )


class _CausalSwingStrategy(StrategyV2):
    """Honest: acts on confirmed_swing_points, stamped at confirmation bars."""

    @property
    def metadata(self) -> StrategyMetadataV2:
        return _v2meta("causal_swing_test")

    @property
    def required_indicators(self) -> List[str]:
        return ["confirmed_swing_points"]

    @property
    def warmup_bars(self) -> int:
        return 10

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        df = frames["H1"]
        swing_highs, _ = confirmed_swing_points(df["High"], df["Low"], period=5)
        close = df["Close"]
        orders: List[OrderIntent] = []
        for ts, level in swing_highs.items():
            if pd.isna(level):
                continue
            decision_close = float(close.loc[ts])
            if not level + 2.0 > decision_close:
                continue  # pending stop must sit above the market
            orders.append(
                _breakout_intent(self.strategy_id, ts, float(level), decision_close)
            )
        return orders


class _LegacySwingStrategy(StrategyV2):
    """Cheating twin: indicators.detect_swing_points (rolling(center=True))."""

    @property
    def metadata(self) -> StrategyMetadataV2:
        return _v2meta("legacy_swing_test")

    @property
    def required_indicators(self) -> List[str]:
        return ["detect_swing_points"]

    @property
    def warmup_bars(self) -> int:
        return 10

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        df = frames["H1"]
        swing_highs, _ = detect_swing_points(df["High"], df["Low"], period=5)
        close = df["Close"]
        orders: List[OrderIntent] = []
        for ts in df.index[swing_highs.fillna(False)]:
            level = float(df["High"].loc[ts])
            orders.append(
                _breakout_intent(self.strategy_id, ts, level, float(close.loc[ts]))
            )
        return orders


# ---------------------------------------------------------------------------
# acceptance #8: the contract probe blesses the new function, bans the old one
# ---------------------------------------------------------------------------


def test_causal_swings_passes_assert_no_lookahead_v2():
    assert_no_lookahead_v2(_CausalSwingStrategy(), {"H1": _oscillating_frame()})


def test_detect_swing_points_fails_assert_no_lookahead_v2():
    """The old centred-window function must be rejected by the same probe."""
    with pytest.raises(LookAheadError):
        assert_no_lookahead_v2(_LegacySwingStrategy(), {"H1": _oscillating_frame()})


# ---------------------------------------------------------------------------
# boundary stamp semantics
# ---------------------------------------------------------------------------


def test_boundary_stamp_marks_confirmation_bar_with_occurrence_level():
    """period=3, spike at bar 5: NaN at bars 5..7, the level appears at bar 8,
    and the carried value is high[5] — the occurrence level, not the price at
    the confirmation bar."""
    high = _series([10, 10, 10, 10, 10, 20, 10, 10, 10, 12, 11, 10])
    low = _series([9.0] * 12)
    swing_highs, swing_lows = confirmed_swing_points(high, low, period=3)

    assert swing_highs.iloc[5:8].isna().all(), "unknowable before k+period"
    assert swing_highs.iloc[8] == 20.0
    assert swing_highs.iloc[8] == high.iloc[5], "carries the occurrence level"
    assert swing_highs.iloc[9:].isna().all(), "no phantom marks"
    assert swing_lows.isna().all()


def test_confirmation_breaks_only_on_strict_exceed():
    """A later bar EQUAL to the swing level does not break confirmation; one
    strictly above it does (and becomes a candidate in its own right)."""
    low = _series([9.0] * 12)

    tied = _series([10, 10, 10, 10, 10, 20, 10, 20, 10, 10, 10, 10])
    sh_tied, _ = confirmed_swing_points(tied, low, period=3)
    assert sh_tied.iloc[8] == 20.0, "a tie at k+2 must not break confirmation"

    broken = _series([10, 10, 10, 10, 10, 20, 10, 21, 10, 10, 10, 10])
    sh_broken, _ = confirmed_swing_points(broken, low, period=3)
    assert pd.isna(sh_broken.iloc[8]), "bar 7 exceeded the level: no mark at k+period"
    # bar 7 (21.0) is itself a candidate and confirms at bar 10.
    assert sh_broken.iloc[10] == 21.0


def test_occurrence_requires_strictly_greater_prior_window():
    """An equal high anywhere in the prior `period` bars kills the candidate."""
    low = _series([9.0] * 12)
    high = _series([10, 10, 10, 10, 20, 20, 10, 10, 10, 10, 10, 10])
    swing_highs, _ = confirmed_swing_points(high, low, period=3)
    # bar 4 confirms at 7 (tie at bar 5 does not break); bar 5 never candidates.
    assert swing_highs.iloc[7] == 20.0
    assert pd.isna(swing_highs.iloc[8])
    assert swing_highs.notna().sum() == 1


def test_swing_lows_mirror():
    low = _series([10, 10, 10, 10, 10, 5, 10, 10, 10, 10, 10, 10])
    high = _series([11.0] * 12)
    _, swing_lows = confirmed_swing_points(high, low, period=3)
    assert swing_lows.iloc[5:8].isna().all()
    assert swing_lows.iloc[8] == 5.0
    assert swing_lows.notna().sum() == 1


def test_tail_bars_never_confirm():
    """The last `period` bars have no confirmation window — always NaN."""
    high, low = _random_walk(300, seed=11)
    swing_highs, swing_lows = confirmed_swing_points(high, low, period=5)
    assert swing_highs.iloc[-5:].isna().all()
    assert swing_lows.iloc[-5:].isna().all()


# ---------------------------------------------------------------------------
# truncation invariance — the direct causality property
# ---------------------------------------------------------------------------


def test_truncation_invariance_sharpest():
    """Truncate INSIDE the confirmation window: at m=k+period (frame ends at
    k+period-1) there is no mark; one bar later the mark appears, carrying the
    level from k. This is the sharpest boundary in the module."""
    high = _series([10, 10, 10, 10, 10, 20, 10, 10, 10, 12, 11, 10])
    low = _series([9.0] * 12)
    full_highs, full_lows = confirmed_swing_points(high, low, period=3)

    cut_inside = 8  # frame ends at bar 7 = k+period-1
    part_highs, part_lows = confirmed_swing_points(
        high.iloc[:cut_inside], low.iloc[:cut_inside], period=3
    )
    pd.testing.assert_series_equal(part_highs, full_highs.iloc[:cut_inside])
    pd.testing.assert_series_equal(part_lows, full_lows.iloc[:cut_inside])
    assert part_highs.isna().all(), "no mark while the window is incomplete"

    cut_at = 9  # frame now ends at bar 8 = k+period
    part_highs, _ = confirmed_swing_points(
        high.iloc[:cut_at], low.iloc[:cut_at], period=3
    )
    pd.testing.assert_series_equal(part_highs, full_highs.iloc[:cut_at])
    assert part_highs.iloc[8] == 20.0, "mark appears the bar the window closes"


@pytest.mark.parametrize("m", [37, 50, 101, 173, 299])
def test_truncation_invariance_random_walk(m: int):
    """On a random walk, truncating anywhere must not change any shared bar."""
    high, low = _random_walk(300, seed=7)
    full_highs, full_lows = confirmed_swing_points(high, low, period=5)
    part_highs, part_lows = confirmed_swing_points(
        high.iloc[:m], low.iloc[:m], period=5
    )
    pd.testing.assert_series_equal(part_highs, full_highs.iloc[:m])
    pd.testing.assert_series_equal(part_lows, full_lows.iloc[:m])


# ---------------------------------------------------------------------------
# zigzag
# ---------------------------------------------------------------------------


def test_zigzag_schema_and_stamp_invariants():
    high, low = _random_walk(2000, seed=5)
    zz = zigzag_swings(high, low, depth=5, deviation_pips=12.0, backstep=3)
    assert list(zz.columns) == ["confirm_time", "occur_time", "kind", "level"]
    assert len(zz) > 0
    assert set(zz["kind"]) <= {"high", "low"}
    # confirm_time is exactly depth bars after occur_time; level is the
    # occurrence-bar price. This pins the stamp to the causal convention.
    pos_of = {ts: i for i, ts in enumerate(high.index)}
    for row in zz.itertuples():
        c, o = pos_of[row.confirm_time], pos_of[row.occur_time]
        assert c - o == 5
        src = high if row.kind == "high" else low
        assert row.level == src.iloc[o]


def test_zigzag_alternation_deviation_backstep():
    high, low = _random_walk(2000, seed=5)
    depth, deviation, backstep = 5, 12.0, 3
    zz = zigzag_swings(
        high, low, depth=depth, deviation_pips=deviation, backstep=backstep
    )
    kinds = zz["kind"].to_numpy()
    levels = zz["level"].to_numpy()
    # strict alternation
    assert (kinds[1:] != kinds[:-1]).all()
    # every accepted reversal moves at least deviation_pips * pip_value
    min_dev = deviation * 0.0001
    for i in range(1, len(zz)):
        moved = levels[i] - levels[i - 1]
        if kinds[i] == "high":
            assert moved >= min_dev - 1e-12
        else:
            assert -moved >= min_dev - 1e-12
    # backstep on occurrence bars
    pos_of = {ts: i for i, ts in enumerate(high.index)}
    occur = [pos_of[ts] for ts in zz["occur_time"]]
    for i in range(1, len(occur)):
        assert occur[i] - occur[i - 1] >= backstep


@pytest.mark.parametrize("m", [700, 1234, 1999])
def test_zigzag_never_repaints(m: int):
    """Truncating the frame must leave every already-knowable pivot identical."""
    high, low = _random_walk(2000, seed=5)
    kwargs = dict(depth=5, deviation_pips=12.0, backstep=3)
    full = zigzag_swings(high, low, **kwargs)
    part = zigzag_swings(high.iloc[:m], low.iloc[:m], **kwargs)
    cut = high.index[m - 1]
    knowable = full[full["confirm_time"] <= cut].reset_index(drop=True)
    pd.testing.assert_frame_equal(knowable, part.reset_index(drop=True))


def test_zigzag_deviation_blocks_small_reversals():
    """Hand-computed pivot sequence: H20 (confirms bar 5), L5 (bar 8), H28
    (bar 11), L4 (bar 14). Deviation is measured from the LAST PIVOT, so a
    gate of 16 units blocks L5 (20-5=15) and H28 (still measured from H20:
    28-20=8, since seeking never flipped), but admits L4 (20-4=16). Also
    exercises a non-default pip_value instead of assuming a pair convention."""
    high = _series([10, 10, 10, 20, 10, 10, 10, 10, 10, 28, 10, 10, 10, 10, 10])
    low = _series([12, 12, 12, 12, 12, 12, 5, 12, 12, 12, 12, 12, 4, 12, 12])
    zz_free = zigzag_swings(high, low, depth=2, deviation_pips=0.0, backstep=0)
    assert zz_free["kind"].tolist() == ["high", "low", "high", "low"]
    assert zz_free["level"].tolist() == [20.0, 5.0, 28.0, 4.0]

    zz_strict = zigzag_swings(
        high, low, depth=2, deviation_pips=16.0, backstep=0, pip_value=1.0
    )
    assert zz_strict["kind"].tolist() == ["high", "low"]
    assert zz_strict["level"].tolist() == [20.0, 4.0]
    assert zz_strict["occur_time"].iloc[1] == low.index[12]


def test_zigzag_empty_input():
    high = _series([], start="2021-01-01")
    low = _series([], start="2021-01-01")
    zz = zigzag_swings(high, low)
    assert list(zz.columns) == ["confirm_time", "occur_time", "kind", "level"]
    assert len(zz) == 0


# ---------------------------------------------------------------------------
# last_n_confirmed_highs / last_n_confirmed_lows
# ---------------------------------------------------------------------------


def _two_swing_fixture() -> tuple[pd.Series, pd.Series]:
    """period=2: swing high 20 occurs at bar 3, confirms at bar 5; swing high
    30 occurs at bar 7, confirms at bar 9. (Bar 6's 15 is broken by bar 7.)"""
    high = _series([10, 10, 10, 20, 10, 10, 15, 30, 10, 10, 10, 10, 10, 10])
    low = _series([9.0] * 14)
    return high, low


def test_last_n_columns_shift_on_new_confirmation():
    high, low = _two_swing_fixture()
    df = last_n_confirmed_highs(high, low, n=2, period=2)

    before = df.iloc[8]  # last bar BEFORE the second confirmation
    assert before["level_1"] == 20.0
    assert pd.isna(before["level_2"])

    at = df.iloc[9]  # the confirmation bar itself: columns shift
    assert at["level_1"] == 30.0
    assert at["level_2"] == before["level_1"]
    assert at["occur_1"] == high.index[7], "occurrence bar of the 30 swing"
    assert at["occur_2"] == high.index[3]

    after = df.iloc[10]  # carried forward unchanged
    assert after["level_1"] == 30.0 and after["level_2"] == 20.0


def test_last_n_row_schema():
    high, low = _two_swing_fixture()
    df = last_n_confirmed_highs(high, low, n=3, period=2)
    assert list(df.columns) == [
        "level_1",
        "level_2",
        "level_3",
        "occur_1",
        "occur_2",
        "occur_3",
    ]
    assert df.index.equals(high.index)
    assert pd.api.types.is_datetime64_any_dtype(df["occur_1"])


@pytest.mark.parametrize("m", [5, 6, 9, 10, 14])
def test_last_n_never_sees_a_future_confirmation(m: int):
    """Recomputing on frame.iloc[:m] must reproduce row m-1 exactly — no row
    may contain a level whose confirmation bar is in its future."""
    high, low = _two_swing_fixture()
    full = last_n_confirmed_highs(high, low, n=2, period=2)
    part = last_n_confirmed_highs(high.iloc[:m], low.iloc[:m], n=2, period=2)
    pd.testing.assert_series_equal(part.iloc[-1], full.iloc[m - 1])
    pd.testing.assert_frame_equal(part, full.iloc[:m])


def test_last_n_confirmed_lows_mirror():
    high, low = _two_swing_fixture()
    # mirror the fixture: the highs become lows (inverted swings)
    df = last_n_confirmed_lows(30.0 - low, 30.0 - high, n=2, period=2)
    assert df.iloc[8]["level_1"] == 10.0  # mirrored 20
    assert df.iloc[9]["level_1"] == 0.0  # mirrored 30
    assert df.iloc[9]["level_2"] == 10.0
    assert df.iloc[9]["occur_1"] == high.index[7]


def test_last_n_random_walk_truncation():
    high, low = _random_walk(400, seed=13)
    full = last_n_confirmed_highs(high, low, n=3, period=5)
    for m in (97, 250, 399):
        part = last_n_confirmed_highs(high.iloc[:m], low.iloc[:m], n=3, period=5)
        pd.testing.assert_frame_equal(part, full.iloc[:m])


# ---------------------------------------------------------------------------
# hygiene: scale, input validation, no banned threshold literals
# ---------------------------------------------------------------------------


def test_handles_long_frame_without_pain():
    """~130k bars (the EUR_USD H1 history) — must be effectively instant."""
    import time

    high, low = _random_walk(130_000, seed=17)
    start = time.perf_counter()
    swing_highs, swing_lows = confirmed_swing_points(high, low, period=5)
    zz = zigzag_swings(high, low)
    highs_df = last_n_confirmed_highs(high, low, n=4, period=5)
    lows_df = last_n_confirmed_lows(high, low, n=4, period=5)
    elapsed = time.perf_counter() - start
    assert elapsed < 20.0, f"too slow on 130k bars: {elapsed:.1f}s"
    assert len(highs_df) == 130_000 and len(lows_df) == 130_000
    assert swing_highs.notna().sum() > 0 and len(zz) > 0


def test_input_validation():
    high, low = _two_swing_fixture()
    with pytest.raises(ValueError):
        confirmed_swing_points(high, low, period=0)
    with pytest.raises(ValueError):
        confirmed_swing_points(high, low.iloc[::-1], period=2)  # index mismatch
    with pytest.raises(ValueError):
        zigzag_swings(high, low, depth=2, deviation_pips=-1.0)
    with pytest.raises(ValueError):
        zigzag_swings(high, low, depth=2, pip_value=0.0)
    with pytest.raises(ValueError):
        last_n_confirmed_highs(high, low, n=0, period=2)


def test_no_gate_threshold_literals_in_module():
    """Spec §1.3 / acceptance #9: thresholds are imported, never re-typed.
    The literals are assembled so this test file does not itself trip a scan."""
    src = Path(
        __import__("src.layer0.strategies.causal_structure", fromlist=["x"]).__file__
    ).read_text()
    forbidden = ["1." + "5", "0." + "8", "0." + "25", "0." + "4", "3." + "0", "6" + "0"]
    for literal in forbidden:
        assert literal not in src, f"gate threshold {literal!r} in causal_structure.py"
