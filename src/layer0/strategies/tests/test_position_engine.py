"""Tests for the position engine (spec §3, §9).

``test_v1_equivalence`` is first on purpose: it is the stop-work condition of
this build (docs/PROMPT.md, "The two things most likely to go wrong" #1). It
proves the new engine reproduces the incumbent T6 execution semantics
bit-for-bit on a no-gap fixture, before any of the richer v2 features
(scale-outs, breakeven, trailing, pendings) are trusted.

Fill-convention tests below each cite the spec clause they pin down.
"""

from __future__ import annotations

from typing import List, Sequence

import numpy as np
import pandas as pd
import pytest

from src.layer0.core_engine.backtest_engine import BacktestConfig, BacktestEngine
from src.layer0.data_access.indicators import get_pip_value
from src.layer0.strategies.contract import Stage, Strategy, StrategyMetadata
from src.layer0.strategies.contract_v2 import (
    ExitLeg,
    OrderIntent,
    SignalStrategyAdapter,
    StopRule,
)
from src.layer0.strategies.engine_adapter import ContractStrategyAdapter
from src.layer0.strategies.position_engine import (
    PositionEngine,
    realized_r_multiple,
)

PAIR = "EUR_USD"

#: v2 exit reasons -> the incumbent T6 vocabulary, for equivalence comparison.
_T6_REASON = {
    "STOP": "stop_loss",
    "TAKE_PROFIT": "take_profit",
    "TIME": "time_stop",
    "OPPOSITE": "signal_reverse",
    "END_OF_DATA": "end_of_data",
}
PIP = float(get_pip_value(PAIR))
SLIP = float(BacktestConfig().slippage_pips) * PIP  # adverse slippage per fill


class ToyMaCross(Strategy):
    """Toy v1 strategy for the equivalence test: fast/slow SMA cross.

    Fast periods so the shaped fixture produces stops, take-profits,
    time-stops, signal reversals and an end-of-data close within ~400 bars.
    """

    FAST = 3
    SLOW = 8

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id="toy_ma_cross",
            name="Toy MA Cross",
            version="0.1.0",
            author="engine tests",
            hypothesis=(
                "A fast moving average crossing a slow one captures short "
                "momentum bursts often enough that the claim is falsifiable."
            ),
            granularities=["H1"],
            pairs=[PAIR],
            stage=Stage.RESEARCH,
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["sma"]

    @property
    def warmup_bars(self) -> int:
        return 50

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        fast = df["Close"].rolling(self.FAST, min_periods=self.FAST).mean()
        slow = df["Close"].rolling(self.SLOW, min_periods=self.SLOW).mean()
        cross_up = (fast > slow) & (fast.shift(1) <= slow.shift(1))
        cross_down = (fast < slow) & (fast.shift(1) >= slow.shift(1))
        signals = pd.Series(0, index=df.index, dtype=int)
        signals[cross_up.fillna(False)] = 1
        signals[cross_down.fillna(False)] = -1
        return signals


WARMUP = max(ToyMaCross().warmup_bars, ContractStrategyAdapter.ATR_PERIOD * 3)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Shaped log-return segments (n_bars, drift, noise): a whipsaw region giving
# stops/TPs/reversals under the 3/8 cross, then a noisy decline + rally that
# inflate ATR, a near-frozen smooth rise (neither 1xATR stop nor 3xATR target
# is reachable for 50 bars -> time stop), and a choppy dip/rally tail that
# leaves a position open at the end of data.
_FIXTURE_SEGMENTS = [
    (52, 0.0, 0.0002),
    (15, 0.0012, 0.0002),
    (25, -0.0015, 0.0002),
    (15, 0.0010, 0.0002),
    (12, 0.0009, 0.0006),
    (70, 0.0, 0.00015),
    (12, 0.0008, 0.0006),
    (30, -0.0004, 0.00015),
    (20, -0.0006, 0.0002),
    (26, 0.0003, 0.00015),
    (25, -0.0005, 0.0016),
    (5, 0.0006, 0.0004),
    (65, 0.00005, 0.00001),
    (10, 0.0004, 0.0006),
    (5, -0.0005, 0.0004),
    (5, 0.0005, 0.0004),
    (5, 0.00002, 0.00002),
]


def _no_gap_fixture(seed: int = 1) -> pd.DataFrame:
    """Hourly no-gap fixture: ``Open[t] == Close[t-1]`` exactly (same floats).

    Deterministic: built from fixed segments and a seeded RandomState. The
    final bars carry no signal (verified in the test), which T6 requires for
    the trade sets to align (T6 opens and EOD-closes a final-bar signal; the
    engine has no bar t+1 to fill such an intent on and rejects it).
    """
    rng = np.random.RandomState(seed)
    log_ret = np.concatenate(
        [drift + rng.normal(0.0, noise, nb) for nb, drift, noise in _FIXTURE_SEGMENTS]
    )
    n = len(log_ret)
    idx = pd.date_range("2021-03-01", periods=n, freq="h", tz="UTC")
    close = 1.1000 * np.exp(np.cumsum(log_ret))
    open_ = np.empty(n)
    open_[0] = close[0] * np.exp(-log_ret[0])
    open_[1:] = close[:-1]  # the no-gap bridge: exact same float values
    spread = np.abs(rng.normal(0.00012, 0.00004, n))
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": 1000.0},
        index=idx,
    )


def _mk_frame(rows: Sequence[tuple], start: str = "2022-01-01") -> pd.DataFrame:
    """Small crafted frame from (open, high, low, close) rows."""
    idx = pd.date_range(start, periods=len(rows), freq="h", tz="UTC")
    data = np.array(rows, dtype=float)
    return pd.DataFrame(
        {
            "Open": data[:, 0],
            "High": data[:, 1],
            "Low": data[:, 2],
            "Close": data[:, 3],
            "Volume": 1000.0,
        },
        index=idx,
    )


def _mk_intent(df: pd.DataFrame, bar: int, **overrides) -> OrderIntent:
    kwargs = dict(
        decision_bar=df.index[bar],
        direction=1,
        entry="market",
        entry_price=None,
        stop=StopRule(price=1.0900),
        exits=[ExitLeg(fraction=1.0, kind="take_profit", price=1.1200, label="TP")],
        strategy_id="engine_test",
    )
    kwargs.update(overrides)
    return OrderIntent(**kwargs)


# ---------------------------------------------------------------------------
# 1. test_v1_equivalence — THE stop-work condition (spec §9 #1)
# ---------------------------------------------------------------------------


def test_v1_equivalence() -> None:
    """A v1 strategy via SignalStrategyAdapter reproduces T6 r-multiples 1:1.

    Path 1 (incumbent): ContractStrategyAdapter + BacktestEngine (T6).
    Path 2 (new):       SignalStrategyAdapter -> OrderIntents -> PositionEngine.

    The fixture is no-gap (Open[t] == Close[t-1]), the documented bridge:
    the engine fills market intents at the open of bar t+1 (F1/F2) which is
    bit-identical to T6's fill at the close of bar t. On gapped real data the
    t -> t+1 timing shift is the deliberate, documented semantic change.
    """
    strategy = ToyMaCross()
    df = _no_gap_fixture()

    # Sanity: the no-gap bridge actually holds on the fixture, and the final
    # bar carries no signal (see _no_gap_fixture's docstring).
    opens = df["Open"].to_numpy(dtype=float)
    closes = df["Close"].to_numpy(dtype=float)
    assert (opens[1:] == closes[:-1]).all()
    assert int(strategy.generate_signals(df).iloc[-1]) == 0

    # Path 1 — incumbent T6.
    t6_result = BacktestEngine(BacktestConfig()).run_backtest(
        ContractStrategyAdapter(strategy),
        df.copy(),
        asset=PAIR,
        granularity="H1",
        warmup_bars=WARMUP,
    )
    t6_r = [t.r_multiple for t in t6_result.trades]

    # Path 2 — v2 adapter + position engine.
    v2 = SignalStrategyAdapter(strategy, PAIR)
    position_of = {ts: i for i, ts in enumerate(df.index)}
    intents = [
        o
        for o in v2.generate_orders({"H1": df})
        if position_of[o.decision_bar] >= WARMUP
    ]
    engine_result = PositionEngine().run(df, intents, pair=PAIR, granularity="H1")
    v2_r = engine_result.trades["r_multiple"].tolist()

    # The fixture must actually exercise every exit path, otherwise the
    # comparison proves nothing about stops/TPs/time-stops/reversals/EOD.
    t6_reasons = {t.exit_reason for t in t6_result.trades}
    assert t6_reasons == {
        "stop_loss",
        "take_profit",
        "time_stop",
        "signal_reverse",
        "end_of_data",
    }, f"fixture does not exercise all exit paths: {sorted(t6_reasons)}"

    assert len(t6_r) > 0
    assert len(v2_r) == len(t6_r)

    # --- Structural equivalence: this part IS exact. ------------------------
    # Same trades, same order, same exit reasons, and bit-identical entry
    # fills. If any of these drift, execution semantics really have changed.
    t6_entries = [t.entry_price for t in t6_result.trades]
    v2_entries = engine_result.trades["entry_price"].tolist()
    assert v2_entries == pytest.approx(t6_entries, abs=0.0, rel=0.0)
    assert [t.exit_reason for t in t6_result.trades] == [
        _T6_REASON[r] for r in engine_result.trades["exit_reason"].tolist()
    ]

    # --- Numeric equivalence: bounded, and the residual is explained. -------
    # The residual is NOT an engine difference. It comes from a latent defect
    # in the incumbent path: `engine_adapter.calculate_indicators` writes
    # df["atr"] (lower case) but `StrategyBase.calculate_stop_loss` tests for
    # df["ATR"] (upper case). The lookup misses, so T6 recomputes ATR from
    # scratch on the prefix available at each entry. `indicators.atr` uses
    # `ewm(span=..., adjust=False)`, which is recursive and seed-dependent, so
    # every T6 stop is warmup-dependent: badly seeded on the first trades and
    # converging thereafter. v2 computes ATR once over the whole frame, which
    # is the correct behaviour — so exact agreement with the incumbent is not
    # achievable here, and would not be desirable.
    #
    # Reproduce: atr(full).loc[t] - atr(slice_from_50).loc[t] ~ 9e-6 at t = bar 55.
    diffs = np.abs(np.array(v2_r, dtype=float) - np.array(t6_r, dtype=float))
    assert float(diffs.max()) <= 1e-4, (
        f"v1-equivalence broken: max |dr| = {diffs.max()!r} over {len(t6_r)} "
        "trades — larger than the known ATR-seeding artifact, so this is a real "
        "execution-semantics change"
    )

    # The signature of a seeding artifact is decay: the ewm forgets its seed, so
    # later trades must agree far more tightly than the first. A constant offset
    # would mean something else is wrong.
    assert float(np.median(diffs[len(diffs) // 2 :])) <= 1e-6, (
        "the discrepancy is not decaying across trades — it is not ATR seeding, "
        "so do not accept it as one"
    )


# ---------------------------------------------------------------------------
# 2. test_fill_order — spec §3.2 per-bar order of operations
# ---------------------------------------------------------------------------


def test_fill_order_stop_before_target_same_bar() -> None:
    """F5/§3.2: a bar covering both the stop and TP1 fills the stop ONLY,
    closing all remaining fraction, before any exit leg is considered."""
    df = _mk_frame(
        [
            (1.1000, 1.1001, 1.0999, 1.1000),  # 0: decision bar
            (1.1000, 1.1005, 1.0995, 1.1002),  # 1: market fill at open
            (1.1002, 1.1015, 1.0895, 1.1000),  # 2: covers stop AND TP
        ]
    )
    intent = _mk_intent(df, 0, stop=StopRule(price=1.0900))
    res = PositionEngine().run(df, [intent], pair=PAIR)
    assert len(res.trades) == 1
    trade = res.trades.iloc[0]
    assert trade["exit_reason"] == "STOP"
    assert trade["legs_filled"] == 0
    # Fill at the stop level with adverse slippage, not at the TP level.
    assert trade["exit_price"] == pytest.approx(1.0900 - SLIP)
    expected_r = realized_r_multiple(1, 1.1000 + SLIP, 1.0900, [(1.0, 1.0900 - SLIP)])
    assert trade["r_multiple"] == expected_r


def test_fill_order_exit_frees_capacity_for_pending() -> None:
    """§3.2: stops (step 2) run before pending fills (step 5) and admission
    (step 6): a position stopped out on bar t frees F12 capacity, so a
    pending decided on bar 0 is admitted at the end of bar t and fills on
    bar t+1 — never on its eligible bar t (decision #6, documented)."""
    df = _mk_frame(
        [
            (1.1000, 1.1001, 1.0999, 1.1000),  # 0: decision bar
            (1.1000, 1.1006, 1.0898, 1.0995),  # 1: long fills, stops out; high
            #                                touches the pending level already
            (1.0995, 1.1010, 1.0990, 1.1008),  # 2: pending triggers here
            (1.1008, 1.1012, 1.1005, 1.1010),  # 3
        ]
    )
    market = _mk_intent(df, 0, tag="first", stop=StopRule(price=1.0900))
    pending = _mk_intent(
        df,
        0,
        tag="second",
        entry="buy_stop",
        entry_price=1.1005,
        decision_close=1.1000,
        stop=StopRule(price=1.0950),
        exits=[ExitLeg(fraction=1.0, kind="take_profit", price=1.1020, label="TP")],
    )
    res = PositionEngine().run(df, [market, pending], pair=PAIR)
    assert len(res.trades) == 2
    stopped, pend = res.trades.iloc[0], res.trades.iloc[1]
    assert stopped["exit_reason"] == "STOP"
    assert stopped["exit_time"] == df.index[1]
    # The pending did NOT fill on bar 1 even though high[1] >= its level:
    # decided at 0, admitted at END of bar 1, first fill attempt bar 2.
    assert pend["entry_time"] == df.index[2]
    assert pend["entry_price"] == pytest.approx(max(1.1005, 1.0995) + SLIP)


# ---------------------------------------------------------------------------
# 3. test_gap_through_stop — F6
# ---------------------------------------------------------------------------


def test_gap_through_stop() -> None:
    """F6: a bar opening beyond the stop fills at the OPEN, not the stop
    level; the loss exceeds 1R and the trade row is flagged gapped."""
    df = _mk_frame(
        [
            (1.1000, 1.1001, 1.0999, 1.1000),  # 0: decision
            (1.1000, 1.1005, 1.0995, 1.1000),  # 1: fill at open
            (1.0800, 1.0805, 1.0790, 1.0795),  # 2: opens beyond the stop
        ]
    )
    intent = _mk_intent(df, 0, stop=StopRule(price=1.0900))
    res = PositionEngine().run(df, [intent], pair=PAIR)
    trade = res.trades.iloc[0]
    assert trade["exit_reason"] == "STOP"
    assert trade["exit_price"] == pytest.approx(1.0800 - SLIP)  # the open
    assert bool(trade["gapped"]) is True
    assert trade["r_multiple"] < -1.0  # loss exceeds 1R


# ---------------------------------------------------------------------------
# 4. test_scale_out_arithmetic — spec §9 #5
# ---------------------------------------------------------------------------


def test_scale_out_arithmetic() -> None:
    """Three 1/3 legs at hand-computed levels; r_multiple matches the hand
    computation exactly (single computation site: realized_r_multiple)."""
    third = 1 / 3
    df = _mk_frame(
        [
            (1.1000, 1.1001, 1.0999, 1.1000),  # 0: decision
            (1.1000, 1.1005, 1.0995, 1.1002),  # 1: fill
            (1.1002, 1.1015, 1.1000, 1.1012),  # 2: TP1
            (1.1012, 1.1025, 1.1010, 1.1022),  # 3: TP2
            (1.1022, 1.1035, 1.1020, 1.1032),  # 4: TP3
        ]
    )
    levels = [1.1010, 1.1020, 1.1030]
    intent = _mk_intent(
        df,
        0,
        stop=StopRule(price=1.0900),
        exits=[
            ExitLeg(fraction=third, kind="take_profit", price=lv, label=f"TP{i}")
            for i, lv in enumerate(levels, start=1)
        ],
    )
    res = PositionEngine().run(df, [intent], pair=PAIR)
    trade = res.trades.iloc[0]
    entry = 1.1000 + SLIP
    exits = [lv - SLIP for lv in levels]
    hand = 0.0
    for xp in exits:
        hand += third * 1 * (xp - entry)
    hand /= abs(entry - 1.0900)
    assert trade["r_multiple"] == hand
    assert trade["legs_filled"] == 3
    assert trade["exit_reason"] == "TAKE_PROFIT"
    assert res.leg_fills["fill_price"].tolist() == pytest.approx(exits)


# ---------------------------------------------------------------------------
# 5. test_breakeven_at_close — F8, and attack #12 (PROMPT.md)
# ---------------------------------------------------------------------------


def test_breakeven_at_close() -> None:
    """F8: the stop moves at the CLOSE of the bar where the triggering leg
    filled — protection is not available intrabar on that bar. Attack #12:
    the breakeven rule must never fire before the triggering leg fills."""
    df = _mk_frame(
        [
            (1.1000, 1.1001, 1.0999, 1.1000),  # 0: decision
            (1.1000, 1.1006, 1.0995, 1.1003),  # 1: fill; high crosses the
            #  would-be breakeven level but TP1 is NOT touched -> no move
            (1.1003, 1.1015, 1.1001, 1.1012),  # 2: TP1 fills; low dips below
            #  the would-be breakeven level -> old stop must still govern
            (1.1012, 1.1013, 1.1001, 1.1011),  # 3: dips below breakeven ->
            #  stop fills at the NEW level
        ]
    )
    half = 0.5
    intent = _mk_intent(
        df,
        0,
        stop=StopRule(
            price=1.0900, move_to_breakeven_on="TP1", breakeven_offset_pips=2.0
        ),
        exits=[
            ExitLeg(fraction=half, kind="take_profit", price=1.1010, label="TP1"),
            ExitLeg(fraction=half, kind="take_profit", price=1.1020, label="TP2"),
        ],
    )
    res = PositionEngine().run(df, [intent], pair=PAIR)
    entry = 1.1000 + SLIP
    breakeven = entry + 2.0 * PIP

    # Stop history: initial at the fill bar, breakeven at the close of bar 2
    # (the TP1 bar) — never on bar 1, when the level was crossed but the leg
    # had not filled.
    hist = res.stop_history
    assert hist["reason"].tolist() == ["initial", "breakeven"]
    assert hist["bar_time"].tolist() == [df.index[1], df.index[2]]
    assert hist["stop_price"].tolist() == pytest.approx([1.0900, breakeven])

    fills = res.leg_fills
    assert fills["label"].tolist() == ["TP1", "STOP"]
    assert fills["fill_time"].tolist() == [df.index[2], df.index[3]]
    assert fills["fill_price"].tolist() == pytest.approx(
        [1.1010 - SLIP, breakeven - SLIP]
    )
    trade = res.trades.iloc[0]
    assert trade["exit_reason"] == "STOP"
    assert trade["legs_filled"] == 1
    hand = half * 1 * (1.1010 - SLIP - entry) + half * 1 * (breakeven - SLIP - entry)
    assert trade["r_multiple"] == hand / abs(entry - 1.0900)


# ---------------------------------------------------------------------------
# 6. test_deterministic — spec §9 #11
# ---------------------------------------------------------------------------


def test_deterministic() -> None:
    """Same inputs twice -> identical frames (exact equality)."""
    strategy = ToyMaCross()
    df = _no_gap_fixture()
    v2 = SignalStrategyAdapter(strategy, PAIR)
    position_of = {ts: i for i, ts in enumerate(df.index)}
    intents = [
        o
        for o in v2.generate_orders({"H1": df})
        if position_of[o.decision_bar] >= WARMUP
    ]
    first = PositionEngine().run(df, intents, pair=PAIR, granularity="H1")
    second = PositionEngine().run(df, intents, pair=PAIR, granularity="H1")
    pd.testing.assert_frame_equal(first.trades, second.trades)
    pd.testing.assert_frame_equal(first.leg_fills, second.leg_fills)
    pd.testing.assert_frame_equal(first.stop_history, second.stop_history)


# ---------------------------------------------------------------------------
# 7. test_stop_never_widens — spec §9 #12
# ---------------------------------------------------------------------------


def test_stop_never_widens() -> None:
    """Adversarial path with a trailing stop: rallies ratchet the stop up;
    sharp drops must never move it back down. The stop sequence is
    monotonically non-decreasing for a long, by construction."""
    rows = [(1.1000, 1.1001, 1.0999, 1.1000)]  # 0: decision
    price = 1.1000
    for i in range(1, 9):  # steady rally: trailing stop should ratchet up
        o = price
        c = price + 0.0005
        rows.append((o, c + 0.0002, o - 0.0002, c))
        price = c
    # Sharp pullback bar with a long lower wick: candidate trail drops far
    # below the current stop — the stop must NOT move down.
    rows.append((price, price + 0.0001, price - 0.0020, price - 0.0004))
    price -= 0.0004
    # Recovery, then a final bar that takes out the (raised) stop.
    rows.append((price, price + 0.0006, price - 0.0001, price + 0.0005))
    price += 0.0005
    rows.append((price, price + 0.0001, price - 0.0030, price - 0.0028))
    df = _mk_frame(rows)
    intent = _mk_intent(
        df,
        0,
        stop=StopRule(price=1.0900, trail_atr_multiple=2.0),
        exits=[ExitLeg(fraction=1.0, kind="take_profit", price=1.1400, label="TP")],
    )
    res = PositionEngine().run(df, [intent], pair=PAIR)
    stops = res.stop_history["stop_price"].to_numpy(dtype=float)
    assert len(stops) >= 3  # initial plus at least two trailing moves
    assert (np.diff(stops) >= 0.0).all(), f"stop widened: {stops}"
    assert res.trades.iloc[0]["exit_reason"] == "STOP"


# ---------------------------------------------------------------------------
# F3 — pending fills, incl. gap-through
# ---------------------------------------------------------------------------


def test_pending_buy_stop_gap_through_fills_at_open() -> None:
    """F3: a buy_stop whose trigger bar gaps through the level fills at the
    open (worse), plus adverse slippage; gapped=True on the trade row."""
    df = _mk_frame(
        [
            (1.1000, 1.1001, 1.0999, 1.1000),  # 0: decision (close 1.1000)
            (1.1000, 1.1004, 1.0998, 1.1002),  # 1: eligible; admitted at end
            (1.1012, 1.1015, 1.1008, 1.1010),  # 2: opens above the stop level
            (1.1010, 1.1011, 1.1005, 1.1008),  # 3
        ]
    )
    intent = _mk_intent(
        df,
        0,
        entry="buy_stop",
        entry_price=1.1005,
        decision_close=1.1000,
        stop=StopRule(price=1.0950),
        exits=[ExitLeg(fraction=1.0, kind="take_profit", price=1.1050, label="TP")],
    )
    res = PositionEngine().run(df, [intent], pair=PAIR)
    trade = res.trades.iloc[0]
    assert trade["entry_time"] == df.index[2]
    assert trade["entry_price"] == pytest.approx(1.1012 + SLIP)
    assert bool(trade["gapped"]) is True


def test_pending_limit_fills_at_level_exactly() -> None:
    """F3: limits fill at L exactly (no price improvement from a gap beyond
    L), with adverse slippage applied per F10."""
    df = _mk_frame(
        [
            (1.1000, 1.1001, 1.0999, 1.1000),  # 0: decision
            (1.1000, 1.1004, 1.0998, 1.1002),  # 1: admitted at end
            (1.1005, 1.1015, 1.1004, 1.1012),  # 2: opens above L, trades higher
            (1.1012, 1.1013, 1.1009, 1.1010),  # 3
        ]
    )
    intent = _mk_intent(
        df,
        0,
        direction=-1,
        entry="sell_limit",
        entry_price=1.1010,
        decision_close=1.1000,
        stop=StopRule(price=1.1060),
        exits=[ExitLeg(fraction=1.0, kind="take_profit", price=1.0950, label="TP")],
    )
    res = PositionEngine().run(df, [intent], pair=PAIR)
    trade = res.trades.iloc[0]
    assert trade["entry_time"] == df.index[2]
    # fill at L exactly, not at the better open of 1.1005->1.1015 gap
    assert trade["entry_price"] == pytest.approx(1.1010 - SLIP)
    assert bool(trade["gapped"]) is False


# ---------------------------------------------------------------------------
# F4 — expiry
# ---------------------------------------------------------------------------


def test_pending_expiry() -> None:
    """F4: a pending not filled within expires_after_bars is cancelled; a
    later bar that would have triggered it does not fill (expiry, §3.2 step
    1, runs before pending fills, step 5)."""
    df = _mk_frame(
        [
            (1.1000, 1.1001, 1.0999, 1.1000),  # 0: decision
            (1.1000, 1.1003, 1.0998, 1.1001),  # 1: admitted at end
            (1.1001, 1.1004, 1.0999, 1.1002),  # 2: attempt 1
            (1.1002, 1.1004, 1.1000, 1.1003),  # 3: attempt 2
            (1.1003, 1.2000, 1.1002, 1.1999),  # 4: would trigger — too late
        ]
    )
    intent = _mk_intent(
        df,
        0,
        entry="buy_stop",
        entry_price=1.1050,
        decision_close=1.1000,
        expires_after_bars=2,
        stop=StopRule(price=1.0900),
        exits=[ExitLeg(fraction=1.0, kind="take_profit", price=1.1100, label="TP")],
    )
    res = PositionEngine().run(df, [intent], pair=PAIR)
    assert len(res.trades) == 0
    assert len(res.expired_orders) == 1
    assert res.expired_orders[0].reason == "EXPIRED"
    assert res.expired_orders[0].bar == df.index[4]


# ---------------------------------------------------------------------------
# F7 — multiple legs in one bar
# ---------------------------------------------------------------------------


def test_multi_leg_single_bar() -> None:
    """F7: one bar covering TP1 and TP2 fills both, nearest first, each at
    its own level."""
    df = _mk_frame(
        [
            (1.1000, 1.1001, 1.0999, 1.1000),  # 0: decision
            (1.1000, 1.1004, 1.0995, 1.1002),  # 1: fill
            (1.1002, 1.1025, 1.1000, 1.1022),  # 2: covers both TPs
        ]
    )
    half = 0.5
    intent = _mk_intent(
        df,
        0,
        stop=StopRule(price=1.0900),
        exits=[
            ExitLeg(fraction=half, kind="take_profit", price=1.1020, label="TP2"),
            ExitLeg(fraction=half, kind="take_profit", price=1.1010, label="TP1"),
        ],
    )
    res = PositionEngine().run(df, [intent], pair=PAIR)
    # Declared out of order; engine fills nearest-first anyway.
    assert res.leg_fills["label"].tolist() == ["TP1", "TP2"]
    assert res.leg_fills["fill_price"].tolist() == pytest.approx(
        [1.1010 - SLIP, 1.1020 - SLIP]
    )
    trade = res.trades.iloc[0]
    assert trade["legs_filled"] == 2
    assert trade["exit_time"] == df.index[2]


# ---------------------------------------------------------------------------
# F11 — end of data
# ---------------------------------------------------------------------------


def test_end_of_data_close_has_no_slippage() -> None:
    """F11: open remainders close at the final bar's close, reason
    END_OF_DATA, flagged, with NO slippage (matches T6's EOD path)."""
    df = _mk_frame(
        [
            (1.1000, 1.1001, 1.0999, 1.1000),
            (1.1000, 1.1004, 1.0998, 1.1002),
            (1.1002, 1.1005, 1.1000, 1.1003),
        ]
    )
    intent = _mk_intent(df, 0, stop=StopRule(price=1.0900))
    res = PositionEngine().run(df, [intent], pair=PAIR)
    trade = res.trades.iloc[0]
    assert trade["exit_reason"] == "END_OF_DATA"
    assert trade["exit_price"] == 1.1003  # exact final close, no slippage
    assert not res.leg_fills.iloc[0]["slippage_applied"]
    assert res.end_of_data_open == 1
    assert res.end_of_data_flag is True
    assert res.config.max_concurrent_positions == 1  # F12 echo


# ---------------------------------------------------------------------------
# F12 — concurrency
# ---------------------------------------------------------------------------


def test_concurrency_second_intent_rejected() -> None:
    """F12: with the default cap of 1, a second intent eligible on the same
    bar is rejected and reported; an opposite-direction intent without
    close_on_opposite is likewise rejected."""
    df = _mk_frame(
        [
            (1.1000, 1.1001, 1.0999, 1.1000),
            (1.1000, 1.1004, 1.0998, 1.1002),
            (1.1002, 1.1005, 1.1000, 1.1003),
        ]
    )
    first = _mk_intent(df, 0, tag="A", stop=StopRule(price=1.0900))
    second = _mk_intent(df, 0, tag="B", stop=StopRule(price=1.0900))
    third = _mk_intent(
        df,
        0,
        tag="C",
        direction=-1,
        stop=StopRule(price=1.1100),
        exits=[ExitLeg(fraction=1.0, kind="take_profit", price=1.0800, label="TP")],
    )
    res = PositionEngine().run(df, [first, second, third], pair=PAIR)
    assert len(res.trades) == 1
    assert res.trades.iloc[0]["tag"] == "A"
    reasons = [r.reason.split(":")[0] for r in res.rejected_orders]
    assert reasons == ["MAX_CONCURRENT_POSITIONS", "MAX_CONCURRENT_POSITIONS"]
    assert {r.intent.tag for r in res.rejected_orders} == {"B", "C"}


# ---------------------------------------------------------------------------
# Attack #5 (engine side): pending through the market at admission
# ---------------------------------------------------------------------------


def test_attack5_engine_rejects_disguised_pending() -> None:
    """A buy_stop priced below the decision-bar close is an instant fill
    disguised as a pending order. With decision_close absent the dataclass
    cannot check it, so the ENGINE must reject it at admission (contract_v2
    module docstring; PROMPT.md attack #5)."""
    df = _mk_frame(
        [
            (1.1000, 1.1001, 1.0999, 1.1000),  # decision bar, close 1.1000
            (1.1000, 1.1004, 1.0998, 1.1002),
            (1.1002, 1.1005, 1.1000, 1.1003),
        ]
    )
    intent = _mk_intent(
        df,
        0,
        entry="buy_stop",
        entry_price=1.0950,  # below the decision-bar close
        decision_close=None,  # bypasses the dataclass check on purpose
        stop=StopRule(price=1.0900),
        exits=[ExitLeg(fraction=1.0, kind="take_profit", price=1.1000, label="TP")],
    )
    res = PositionEngine().run(df, [intent], pair=PAIR)
    assert len(res.trades) == 0
    assert len(res.rejected_orders) == 1
    assert res.rejected_orders[0].reason.startswith("DISGUISED_INSTANT_FILL")


# ---------------------------------------------------------------------------
# time_exit_after_bars — counted from the DECISION bar, exit at that close
# ---------------------------------------------------------------------------


def test_time_exit_counts_from_decision_bar() -> None:
    """time_exit_after_bars=N exits the whole remainder at the close of bar
    decision_bar + N with adverse slippage (T6 max_bars_hold semantics)."""
    df = _mk_frame(
        [
            (1.1000, 1.1001, 1.0999, 1.1000),  # 0: decision
            (1.1000, 1.1004, 1.0998, 1.1002),  # 1: fill at open
            (1.1002, 1.1005, 1.1000, 1.1003),  # 2
            (1.1003, 1.1006, 1.1001, 1.1004),  # 3 = decision + 3: time exit
            (1.1004, 1.1007, 1.1002, 1.1005),  # 4
        ]
    )
    intent = _mk_intent(df, 0, stop=StopRule(price=1.0900), time_exit_after_bars=3)
    res = PositionEngine().run(df, [intent], pair=PAIR)
    trade = res.trades.iloc[0]
    assert trade["exit_reason"] == "TIME"
    assert trade["exit_time"] == df.index[3]
    assert trade["exit_price"] == pytest.approx(1.1004 - SLIP)


def test_fractional_time_leg() -> None:
    """A fractional ExitLeg(kind="time") closes its fraction at the close of
    the bar `bars` after the fill bar; the rest of the plan keeps running."""
    half = 0.5
    df = _mk_frame(
        [
            (1.1000, 1.1001, 1.0999, 1.1000),  # 0: decision
            (1.1000, 1.1004, 1.0998, 1.1002),  # 1: fill
            (1.1002, 1.1005, 1.1000, 1.1003),  # 2
            (1.1003, 1.1006, 1.1001, 1.1004),  # 3 = fill+2: time leg fills
            (1.1004, 1.1015, 1.1002, 1.1013),  # 4: TP leg fills
        ]
    )
    intent = _mk_intent(
        df,
        0,
        stop=StopRule(price=1.0900),
        exits=[
            ExitLeg(fraction=half, kind="take_profit", price=1.1010, label="TP"),
            ExitLeg(fraction=half, kind="time", bars=2, label="T"),
        ],
    )
    res = PositionEngine().run(df, [intent], pair=PAIR)
    fills = res.leg_fills
    assert fills["label"].tolist() == ["T", "TP"]
    assert fills["fill_time"].tolist() == [df.index[3], df.index[4]]
    assert fills["fill_price"].tolist() == pytest.approx([1.1004 - SLIP, 1.1010 - SLIP])
    assert res.trades.iloc[0]["legs_filled"] == 2


# ---------------------------------------------------------------------------
# H1-resolution eligibility hook (spec §5, decision #8)
# ---------------------------------------------------------------------------


def test_eligibility_fn_delays_fills() -> None:
    """eligibility_fn maps an intent to its earliest eligible timestamp; the
    fill happens at the first resolution bar at/after it (never before
    decision_bar+1). This is the hook the H1 harness uses (spec §5)."""
    df = _mk_frame(
        [
            (1.1000, 1.1001, 1.0999, 1.1000),  # 0: decision
            (1.1000, 1.1004, 1.0998, 1.1002),  # 1: default eligible bar
            (1.1002, 1.1005, 1.1000, 1.1003),  # 2
            (1.1003, 1.1006, 1.1001, 1.1004),  # 3: eligibility_fn target
            (1.1004, 1.1007, 1.1002, 1.1005),  # 4
        ]
    )
    intent = _mk_intent(df, 0, stop=StopRule(price=1.0900))
    eligible_ts = df.index[3]
    res = PositionEngine().run(
        df,
        [intent],
        pair=PAIR,
        eligibility_fn=lambda _intent: eligible_ts,
    )
    trade = res.trades.iloc[0]
    assert trade["entry_time"] == df.index[3]
    assert trade["entry_price"] == pytest.approx(1.1003 + SLIP)
    assert res.config.eligibility.startswith("first resolution bar")


def test_fractional_trailing_leg_rejected() -> None:
    """Trailing only PART of a position is unimplemented, so an intent carrying
    a ``fraction < 1.0`` trailing leg is rejected with a reason rather than
    silently approximated."""
    df = _mk_frame(
        [
            (1.1000, 1.1001, 1.0999, 1.1000),
            (1.1000, 1.1004, 1.0998, 1.1002),
        ]
    )
    intent = _mk_intent(
        df,
        0,
        stop=StopRule(price=1.0900),
        exits=[
            ExitLeg(fraction=0.5, kind="take_profit", price=1.1200, label="TP"),
            ExitLeg(fraction=0.5, kind="trailing", atr_multiple=2.0, label="TR"),
        ],
    )
    res = PositionEngine().run(df, [intent], pair=PAIR)
    assert len(res.trades) == 0
    assert res.rejected_orders[0].reason.startswith("TRAILING_LEG_UNSUPPORTED")
    assert "FRACTIONAL" in res.rejected_orders[0].reason


def test_whole_position_trailing_leg_is_accepted_and_trails() -> None:
    """A single ``ExitLeg(kind="trailing", fraction=1.0)`` is the declarative
    equivalent of ``StopRule.trail_atr_multiple``.

    It exists because a "trail until stopped out" strategy has no take-profit to
    declare, yet the contract demands at least one leg summing to 1.0. Rejecting
    it made four Wave-2 strategies emit orders that could never become trades.
    """
    rows = [(1.1000, 1.1010, 1.0990, 1.1000)] * 30
    rows += [
        (
            1.1000 + i * 0.0020,
            1.1015 + i * 0.0020,
            1.0995 + i * 0.0020,
            1.1010 + i * 0.0020,
        )
        for i in range(20)
    ]
    df = _mk_frame(rows)
    intent = _mk_intent(
        df,
        29,
        stop=StopRule(price=1.0900),
        exits=[ExitLeg(fraction=1.0, kind="trailing", atr_multiple=2.0, label="TR")],
    )
    res = PositionEngine().run(df, [intent], pair=PAIR)

    assert not res.rejected_orders, res.rejected_orders[0].reason
    # The trail ratchets the stop up as price rises: at least one recorded move.
    hist = res.stop_history
    moves = hist[hist["reason"] == "trailing"]
    assert len(moves) > 0, "a whole-position trailing leg must move the stop"
    assert (moves["stop_price"] > 1.0900).all()


def test_trailing_leg_and_stoprule_trail_do_not_double_apply() -> None:
    """Several specs describe one trailing mechanism twice — once on the
    StopRule and once as an exit leg. The StopRule wins, so the position trails
    once, at the StopRule's distance, not at the sum of the two."""
    rows = [(1.1000, 1.1010, 1.0990, 1.1000)] * 30
    rows += [
        (
            1.1000 + i * 0.0020,
            1.1015 + i * 0.0020,
            1.0995 + i * 0.0020,
            1.1010 + i * 0.0020,
        )
        for i in range(20)
    ]
    df = _mk_frame(rows)

    both = _mk_intent(
        df,
        29,
        stop=StopRule(price=1.0900, trail_atr_multiple=2.0),
        exits=[ExitLeg(fraction=1.0, kind="trailing", atr_multiple=99.0, label="TR")],
    )
    stoprule_only = _mk_intent(
        df,
        29,
        stop=StopRule(price=1.0900, trail_atr_multiple=2.0),
        # bars far beyond the frame, so the control exits at exactly the same
        # point as the other run and the two trail series stay comparable.
        exits=[ExitLeg(fraction=1.0, kind="time", bars=500, label="T")],
    )
    a = PositionEngine().run(df, [both], pair=PAIR)
    b = PositionEngine().run(df, [stoprule_only], pair=PAIR)

    trail_a = a.stop_history[a.stop_history["reason"] == "trailing"]["stop_price"]
    trail_b = b.stop_history[b.stop_history["reason"] == "trailing"]["stop_price"]
    assert len(trail_a) > 0, "the StopRule trail must fire at all"
    assert list(trail_a) == list(
        trail_b
    ), "the leg's 99.0 multiple must be ignored entirely"


# ---------------------------------------------------------------------------
# F1/F2 — market fill timing and slippage (explicit micro-test)
# ---------------------------------------------------------------------------


def test_market_fill_at_next_open_with_slippage() -> None:
    """F1/F2: decision at close of bar t -> fill at the OPEN of bar t+1 with
    direction-adverse slippage. Never on bar t."""
    df = _mk_frame(
        [
            (1.1000, 1.1001, 1.0999, 1.1000),  # 0: decision
            (1.1007, 1.1009, 1.1005, 1.1008),  # 1: fill at THIS open (gap ok)
        ]
    )
    intent = _mk_intent(df, 0, stop=StopRule(price=1.0900))
    res = PositionEngine().run(df, [intent], pair=PAIR)
    trade = res.trades.iloc[0]
    assert trade["entry_time"] == df.index[1]
    assert trade["entry_price"] == pytest.approx(1.1007 + SLIP)
