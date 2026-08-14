"""Spec §9 #7 — multi-timeframe causality, asserted AT THE BOUNDARY BAR.

The rule, stated once: *a context bar may inform a decision only after that
context bar has closed.* Bars are stamped at their OPEN, so the naive
``context.index <= decision_ts`` admits the bar that is still forming — whose
High/Low/Close have not happened yet.

That mistake is invisible to an average-case test and invisible to the
truncation probe itself (truncation never removes the offending row, so the
strategy sees identical data both times and the probe agrees with itself).
Every assertion below therefore targets the exact boundary, not an aggregate.

Regression origin: the delivered Wave-1 ``_truncate_frames`` used
``df.index <= last_ts``. A strategy reading the still-forming daily bar emitted
108 orders off future information and ``assert_no_lookahead_v2`` passed it clean.
"""

from __future__ import annotations

from typing import List, Mapping, Sequence

import numpy as np
import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import (
    ExitLeg,
    LookAheadError,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
    assert_no_lookahead_v2,
    closed_context_frame,
)

PAIR = "EUR_USD"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _h4_frame(days: int = 40, start: str = "2020-01-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=days * 6, freq="4h", tz="UTC")
    rng = np.random.default_rng(7)
    px = 1.10 + np.cumsum(rng.normal(0.0, 1e-4, len(idx)))
    return pd.DataFrame(
        {"Open": px, "High": px + 2e-4, "Low": px - 2e-4, "Close": px, "Volume": 1.0},
        index=idx,
    )


def _d1_from(h4: pd.DataFrame) -> pd.DataFrame:
    return (
        h4.resample("1D")
        .agg(
            {
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            }
        )
        .dropna()
    )


# ---------------------------------------------------------------------------
# 1. closed_context_frame — the boundary itself
# ---------------------------------------------------------------------------


def test_closed_context_frame_excludes_the_still_forming_bar() -> None:
    """A D1 bar stamped at t is admissible only from t + 1 day, never before."""
    h4 = _h4_frame()
    d1 = _d1_from(h4)
    bar_open = d1.index[10]
    bar_close = bar_open + pd.Timedelta(days=1)

    # One nanosecond before its close the bar is still forming -> excluded.
    just_before = closed_context_frame(
        d1, "D1", bar_close - pd.Timedelta(nanoseconds=1)
    )
    assert bar_open not in just_before.index

    # At its close it becomes knowable -> included.
    at_close = closed_context_frame(d1, "D1", bar_close)
    assert at_close.index[-1] == bar_open

    # The naive rule would have admitted it a full day early. Pin that contrast:
    # this is precisely the delivered bug.
    assert bar_open in d1.loc[d1.index <= bar_open].index


@pytest.mark.parametrize(
    "gran,step",
    [
        ("H1", pd.Timedelta(hours=1)),
        ("H4", pd.Timedelta(hours=4)),
        ("W1", pd.Timedelta(weeks=1)),
    ],
)
def test_closed_context_frame_boundary_for_every_granularity(
    gran: str, step: pd.Timedelta
) -> None:
    idx = pd.date_range("2020-01-06", periods=30, freq=step, tz="UTC")
    ctx = pd.DataFrame({"Close": np.arange(len(idx), dtype=float)}, index=idx)
    target = idx[5]
    assert (
        target
        not in closed_context_frame(
            ctx, gran, target + step - pd.Timedelta(nanoseconds=1)
        ).index
    )
    assert closed_context_frame(ctx, gran, target + step).index[-1] == target


def test_closed_context_frame_rejects_unknown_granularity() -> None:
    idx = pd.date_range("2020-01-01", periods=3, freq="1D", tz="UTC")
    ctx = pd.DataFrame({"Close": [1.0, 2.0, 3.0]}, index=idx)
    with pytest.raises(ValueError, match="unknown context granularity"):
        closed_context_frame(ctx, "M15", idx[-1])


# ---------------------------------------------------------------------------
# 2. The spec's required test: a synthetic D1 flip is invisible until it closes
# ---------------------------------------------------------------------------


def test_synthetic_d1_flip_is_invisible_to_h4_until_the_d1_close() -> None:
    """Construct a D1 trend that flips on a known day; assert no H4 decision
    reflects the flip before the D1 bar carrying it has closed."""
    h4 = _h4_frame(days=30)
    d1 = _d1_from(h4)

    flip_pos = 12
    flip_open = d1.index[flip_pos]
    flip_close = flip_open + pd.Timedelta(days=1)

    # trend = -1 before the flip bar, +1 from the flip bar onward.
    trend = pd.Series(-1.0, index=d1.index)
    trend.iloc[flip_pos:] = 1.0
    d1 = d1.assign(trend=trend)

    # For every H4 bar, the trend value that is legitimately knowable there.
    for ts in h4.index:
        visible = closed_context_frame(d1, "D1", ts)
        if visible.empty:
            continue
        knowable = float(visible["trend"].iloc[-1])
        if ts < flip_close:
            assert knowable == -1.0, (
                f"H4 bar {ts} saw the flip before the D1 bar carrying it closed "
                f"at {flip_close} — look-ahead"
            )

    # And the very first bar that may see it does see it, so the test is not
    # passing vacuously by hiding the flip forever.
    first_eligible = h4.index[h4.index >= flip_close][0]
    assert (
        float(closed_context_frame(d1, "D1", first_eligible)["trend"].iloc[-1]) == 1.0
    )


# ---------------------------------------------------------------------------
# 3. Regression: a strategy peeking at the still-forming bar must be rejected
# ---------------------------------------------------------------------------


class _PeeksAtStillFormingDaily(StrategyV2):
    """Reads the current (unfinished) D1 bar's Close — unknowable intraday.

    Uses the naive ``index <= t`` rule deliberately. Before the fix this passed
    ``assert_no_lookahead_v2`` while emitting >100 orders off future data.
    """

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="peeks_still_forming_daily",
            name="Peeks At Still-Forming Daily",
            version="0.1.0",
            author="wave1-review",
            hypothesis=(
                "deliberately reads the still-forming daily bar so the probe has "
                "something real to catch"
            ),
            granularities=["H4"],
            pairs=[PAIR],
            primary_granularity="H4",
            context_granularities=("D1",),
            simulate_on="H4",
        )

    @property
    def required_indicators(self) -> List[str]:
        return []

    @property
    def warmup_bars(self) -> int:
        return 30

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h4, d1 = frames["H4"], frames["D1"]
        out: List[OrderIntent] = []
        for i in range(self.warmup_bars, len(h4)):
            ts = h4.index[i]
            elig = d1.loc[d1.index <= ts]  # the naive, leaking rule
            if elig.empty:
                continue
            bar = elig.iloc[-1]
            if float(bar["Close"]) > float(bar["Open"]):
                entry = float(h4["Close"].iloc[i])
                out.append(
                    OrderIntent(
                        decision_bar=ts,
                        direction=1,
                        entry="market",
                        entry_price=None,
                        stop=StopRule(price=entry - 0.0020),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="take_profit",
                                price=entry + 0.0060,
                                label="TP1",
                            )
                        ],
                    )
                )
        return out


def test_peeking_at_still_forming_context_bar_is_rejected() -> None:
    h4 = _h4_frame()
    frames = {"H4": h4, "D1": _d1_from(h4)}
    strategy = _PeeksAtStillFormingDaily()

    # The strategy really does fire — otherwise the probe would pass vacuously,
    # which is the FIX-S1-013 hole.
    assert len(strategy.generate_orders(frames)) > 50

    with pytest.raises(LookAheadError):
        assert_no_lookahead_v2(strategy, frames)


class _UsesOnlyClosedDaily(_PeeksAtStillFormingDaily):
    """Identical, except it respects the close rule. Must be accepted."""

    @property
    def metadata(self) -> StrategyMetadataV2:
        base = super().metadata
        return StrategyMetadataV2(
            strategy_id="uses_only_closed_daily",
            name="Uses Only Closed Daily",
            version=base.version,
            author=base.author,
            hypothesis=base.hypothesis,
            granularities=list(base.granularities),
            pairs=list(base.pairs),
            primary_granularity=base.primary_granularity,
            context_granularities=base.context_granularities,
            simulate_on=base.simulate_on,
        )

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h4, d1 = frames["H4"], frames["D1"]
        out: List[OrderIntent] = []
        for i in range(self.warmup_bars, len(h4)):
            ts = h4.index[i]
            elig = closed_context_frame(d1, "D1", ts)  # the causal rule
            if elig.empty:
                continue
            bar = elig.iloc[-1]
            if float(bar["Close"]) > float(bar["Open"]):
                entry = float(h4["Close"].iloc[i])
                out.append(
                    OrderIntent(
                        decision_bar=ts,
                        direction=1,
                        entry="market",
                        entry_price=None,
                        stop=StopRule(price=entry - 0.0020),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="take_profit",
                                price=entry + 0.0060,
                                label="TP1",
                            )
                        ],
                    )
                )
        return out


def test_using_only_closed_context_bars_is_accepted() -> None:
    """The honest twin of the test above — proves the fix rejects leakage
    rather than simply rejecting every multi-timeframe strategy."""
    h4 = _h4_frame()
    frames = {"H4": h4, "D1": _d1_from(h4)}
    strategy = _UsesOnlyClosedDaily()

    assert len(strategy.generate_orders(frames)) > 20
    assert_no_lookahead_v2(strategy, frames)
