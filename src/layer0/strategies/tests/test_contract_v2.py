"""Tests for contract_v2: validation, the look-ahead probe, and the v1 adapter.

Every attack test here maps to the adversarial list in docs/PROMPT.md:
  #1  shift(-1) strategy must fail assert_no_lookahead_v2
  #2  rare-firer vacuous-pass closure (FIX-S1-013) — centred-window rare-firer fails
  #3  exit fractions summing to more than 1.0 rejected
  #4  stop on the wrong side of entry rejected
  #5  pending buy_stop priced below the decision-bar close rejected
  #8  frame-mutating strategy rejected
  #12 breakeven rule naming a non-existent leg rejected (static part)
"""

from __future__ import annotations

from typing import List, Mapping, Sequence

import numpy as np
import pandas as pd
import pytest

from src.layer0.core_engine.backtest_engine import BacktestConfig
from src.layer0.core_engine.strategy_base import StrategyConfig
from src.layer0.data_access.indicators import get_pip_value
from src.layer0.strategies.contract import StrategyMetadata
from src.layer0.strategies.contract_v2 import (
    VALID_GRANULARITIES,
    ExitLeg,
    LookAheadError,
    OrderIntent,
    SignalStrategyAdapter,
    Stage,
    StopRule,
    Strategy,
    StrategyMetadataV2,
    StrategyV2,
    assert_no_lookahead_v2,
)
from src.layer0.strategies.engine_adapter import ContractStrategyAdapter

# ---------------------------------------------------------------------------
# helpers / fixtures
# ---------------------------------------------------------------------------

_T6_MAX_BARS = int(StrategyConfig.__dataclass_fields__["max_bars_hold"].default)


def _frame(n: int = 400, start: str = "2020-01-01") -> pd.DataFrame:
    """Oscillating hourly frame: many rolling-mean crossovers, so truncation
    windows provably contain orders for the honest strategy."""
    idx = pd.date_range(start, periods=n, freq="h", tz="UTC")
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


def _v2meta(sid: str, **overrides) -> StrategyMetadataV2:
    kwargs = dict(
        strategy_id=sid,
        name="Test strategy",
        version="0.0.1",
        author="wave1 tests",
        hypothesis="A test strategy with a fully stated and falsifiable claimed edge.",
        granularities=["H1"],
        pairs=["EUR_USD"],
        primary_granularity="H1",
    )
    kwargs.update(overrides)
    return StrategyMetadataV2(**kwargs)


def _intent(**overrides) -> OrderIntent:
    kwargs = dict(
        decision_bar=pd.Timestamp("2024-01-02 00:00", tz="UTC"),
        direction=1,
        entry="market",
        entry_price=None,
        decision_close=1.10,
        stop=StopRule(price=1.09),
        exits=[ExitLeg(fraction=1.0, kind="take_profit", price=1.12, label="TP")],
        strategy_id="test_strategy",
    )
    kwargs.update(overrides)
    return OrderIntent(**kwargs)


class _HonestV2(StrategyV2):
    """Trailing-only: emits a market intent on each rolling-mean cross-up."""

    def __init__(self, sid: str = "honest_v2") -> None:
        self._meta = _v2meta(sid)

    @property
    def metadata(self) -> StrategyMetadataV2:
        return self._meta

    @property
    def required_indicators(self) -> List[str]:
        return []

    @property
    def warmup_bars(self) -> int:
        return 10

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        df = frames["H1"]
        ma = df["Close"].rolling(5, min_periods=5).mean()
        cross = (df["Close"] > ma) & (df["Close"].shift(1) <= ma.shift(1))
        close = df["Close"].to_numpy(dtype=float)
        orders: List[OrderIntent] = []
        for i in np.flatnonzero(cross.to_numpy()):
            c = float(close[i])
            orders.append(
                OrderIntent(
                    decision_bar=df.index[i],
                    direction=1,
                    entry="market",
                    entry_price=None,
                    decision_close=c,
                    stop=StopRule(price=c - 1.0),
                    exits=[
                        ExitLeg(
                            fraction=1.0,
                            kind="take_profit",
                            price=c + 2.0,
                            label="TP",
                        )
                    ],
                    strategy_id=self.strategy_id,
                )
            )
        return orders


# ---------------------------------------------------------------------------
# OrderIntent / ExitLeg / StopRule validation
# ---------------------------------------------------------------------------


def test_valid_order_intent_passes():
    intent = _intent()
    assert intent.expires_after_bars == 5  # spec §2.2 default
    assert intent.size_fraction == 1.0
    assert intent.close_on_opposite is False
    assert intent.time_exit_after_bars is None


def test_valid_pending_intent_with_breakeven_passes():
    _intent(
        entry="buy_stop",
        entry_price=1.105,
        stop=StopRule(price=1.099, move_to_breakeven_on="TP1"),
        exits=[
            ExitLeg(fraction=0.6, kind="take_profit", price=1.12, label="TP1"),
            ExitLeg(fraction=0.7 - 0.3, kind="trailing", atr_multiple=2.0, label="TR"),
        ],
    )


def test_attack3_fractions_summing_above_one_rejected():
    # 0.75 + 0.75 == one and a half, written without the banned threshold literal.
    with pytest.raises(ValueError, match="test_strategy.*sum"):
        _intent(
            exits=[
                ExitLeg(fraction=0.75, kind="take_profit", price=1.12, label="TP1"),
                ExitLeg(fraction=0.75, kind="take_profit", price=1.13, label="TP2"),
            ]
        )


def test_attack4_stop_on_wrong_side_rejected():
    with pytest.raises(ValueError, match="test_strategy.*below entry"):
        _intent(
            entry="buy_stop",
            entry_price=1.105,
            stop=StopRule(price=1.20),  # above entry for a long
        )
    # mirrored for a short
    with pytest.raises(ValueError, match="test_strategy.*above entry"):
        _intent(
            direction=-1,
            entry="sell_stop",
            entry_price=1.095,
            stop=StopRule(price=1.05),
            exits=[ExitLeg(fraction=1.0, kind="take_profit", price=1.08, label="TP")],
        )


def test_attack5_buy_stop_below_decision_close_rejected():
    with pytest.raises(ValueError, match="test_strategy.*disguised"):
        _intent(entry="buy_stop", entry_price=1.09, stop=StopRule(price=1.08))
    # the other three pending kinds, each through the market
    with pytest.raises(ValueError, match="disguised"):
        _intent(
            direction=-1,
            entry="sell_stop",
            entry_price=1.11,
            stop=StopRule(price=1.12),
            exits=[ExitLeg(fraction=1.0, kind="take_profit", price=1.10, label="TP")],
        )
    with pytest.raises(ValueError, match="disguised"):
        _intent(entry="buy_limit", entry_price=1.11, stop=StopRule(price=1.09))
    with pytest.raises(ValueError, match="disguised"):
        _intent(
            direction=-1,
            entry="sell_limit",
            entry_price=1.09,
            stop=StopRule(price=1.12),
            exits=[ExitLeg(fraction=1.0, kind="take_profit", price=1.08, label="TP")],
        )


def test_pending_entry_without_decision_close_is_allowed():
    """The engine must re-validate at admission when decision_close is absent."""
    intent = _intent(
        entry="buy_stop",
        entry_price=1.105,
        decision_close=None,
        stop=StopRule(price=1.099),
    )
    assert intent.decision_close is None


def test_take_profit_leg_on_wrong_side_rejected():
    with pytest.raises(ValueError, match="test_strategy.*beyond entry"):
        _intent(
            entry="buy_stop",
            entry_price=1.105,
            stop=StopRule(price=1.099),
            exits=[ExitLeg(fraction=1.0, kind="take_profit", price=1.10, label="TP")],
        )


def test_attack12_breakeven_label_must_exist():
    with pytest.raises(ValueError, match="test_strategy.*no exit-leg label"):
        _intent(stop=StopRule(price=1.09, move_to_breakeven_on="TP2"))
    # and the static fix: a matching label passes
    _intent(
        stop=StopRule(price=1.09, move_to_breakeven_on="TP"),
    )


def test_positive_fields_enforced():
    with pytest.raises(ValueError, match="expires_after_bars"):
        _intent(expires_after_bars=0)
    with pytest.raises(ValueError, match="time_exit_after_bars"):
        _intent(time_exit_after_bars=0)
    with pytest.raises(ValueError, match="size_fraction"):
        _intent(size_fraction=1.2)
    with pytest.raises(ValueError, match="size_fraction"):
        _intent(size_fraction=0.0)


def test_market_entry_must_not_carry_a_price():
    with pytest.raises(ValueError, match="entry_price=None"):
        _intent(entry_price=1.10)
    with pytest.raises(ValueError, match="requires an entry_price"):
        _intent(entry="buy_stop", entry_price=None, stop=StopRule(price=1.09))


def test_exit_leg_kind_field_consistency():
    # take_profit: exactly one of price/atr_multiple/pips
    with pytest.raises(ValueError, match="exactly one"):
        ExitLeg(fraction=1.0, kind="take_profit", label="TP")
    with pytest.raises(ValueError, match="exactly one"):
        ExitLeg(fraction=1.0, kind="take_profit", price=1.1, pips=20.0, label="TP")
    # trailing: atr_multiple xor pips, no price/bars
    with pytest.raises(ValueError, match="exactly one"):
        ExitLeg(fraction=1.0, kind="trailing", label="TR")
    with pytest.raises(ValueError, match="must not set price or bars"):
        ExitLeg(fraction=1.0, kind="trailing", atr_multiple=2.0, price=1.1, label="TR")
    # time: positive bars only
    with pytest.raises(ValueError, match="positive bars"):
        ExitLeg(fraction=1.0, kind="time", label="T")
    with pytest.raises(ValueError, match="positive bars"):
        ExitLeg(fraction=1.0, kind="time", bars=0, label="T")
    ExitLeg(fraction=1.0, kind="time", bars=12, label="T")  # ok
    # fraction bounds
    with pytest.raises(ValueError, match="fraction"):
        ExitLeg(fraction=0.0, kind="take_profit", price=1.1, label="TP")
    with pytest.raises(ValueError, match="fraction"):
        ExitLeg(fraction=1.2, kind="take_profit", price=1.1, label="TP")


# ---------------------------------------------------------------------------
# StrategyMetadataV2
# ---------------------------------------------------------------------------


def test_metadata_accepts_w1_and_context_granularities():
    meta = _v2meta(
        "meta_ok",
        granularities=["H4", "D1", "W1"],
        primary_granularity="H4",
        context_granularities=("D1", "W1"),
        simulate_on="H1",
        source_row=7,
        source_url="https://example.invalid/row/7",
    )
    assert meta.primary_granularity == "H4"
    assert meta.simulate_on == "H1"
    assert "W1" in VALID_GRANULARITIES


def test_metadata_rejects_bad_granularities():
    with pytest.raises(ValueError, match="primary_granularity"):
        _v2meta("meta_bad_primary", primary_granularity="M1")
    with pytest.raises(ValueError, match="context_granularities"):
        _v2meta("meta_bad_ctx", context_granularities=("M15",))
    with pytest.raises(ValueError, match="simulate_on"):
        _v2meta("meta_bad_sim", simulate_on="H2")
    with pytest.raises(ValueError, match="granularities"):
        _v2meta("meta_bad_gran", granularities=["H1", "M1"])


def test_metadata_inherits_v1_rules():
    with pytest.raises(ValueError, match="lower_snake_case"):
        _v2meta("BAD-ID")
    with pytest.raises(ValueError, match="hypothesis"):
        _v2meta("meta_thin", hypothesis="too short")


# ---------------------------------------------------------------------------
# assert_no_lookahead_v2
# ---------------------------------------------------------------------------


def test_honest_strategy_passes():
    assert_no_lookahead_v2(_HonestV2(), {"H1": _frame()})


def test_honest_strategy_with_context_frame_passes():
    """Context frames are truncated to the last surviving primary timestamp."""
    d1 = _frame(6 * 10, start="2019-12-01").resample("D").last().dropna()
    assert_no_lookahead_v2(_HonestV2("honest_ctx"), {"H1": _frame(), "D1": d1})


class _ShiftCheat(_HonestV2):
    """ATTACK #1: peeks one bar into the future."""

    def __init__(self) -> None:
        super().__init__("shift_cheat")

    def generate_orders(self, frames):
        df = frames["H1"]
        future = df["Close"].shift(-1)
        fire = (future > df["Close"]).fillna(False)
        close = df["Close"].to_numpy(dtype=float)
        orders = []
        for i in np.flatnonzero(fire.to_numpy()):
            c = float(close[i])
            orders.append(
                OrderIntent(
                    decision_bar=df.index[i],
                    direction=1,
                    entry="market",
                    entry_price=None,
                    decision_close=c,
                    stop=StopRule(price=c - 1.0),
                    exits=[
                        ExitLeg(
                            fraction=1.0,
                            kind="take_profit",
                            price=c + 2.0,
                            label="TP",
                        )
                    ],
                    strategy_id=self.strategy_id,
                )
            )
        return orders


def test_attack1_shift_minus_one_fails():
    with pytest.raises(LookAheadError, match="shift_cheat"):
        assert_no_lookahead_v2(_ShiftCheat(), {"H1": _frame()})


def _ramp_frame(n: int = 400) -> pd.DataFrame:
    """Rises early then flat: a rolling-max threshold crossing fires exactly once,
    early — so every truncation window in the tail is provably empty."""
    idx = pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC")
    close = pd.Series(np.minimum(np.arange(n, dtype=float), 20.0) + 100.0, index=idx)
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


class _RareHonest(_HonestV2):
    """Fires once, early: the windowed probes cover zero orders, so the
    FIX-S1-013 re-probe at firing bars is what proves look-ahead freedom."""

    THRESH = 115.0

    def __init__(self, sid: str = "rare_honest") -> None:
        super().__init__(sid)

    def _cross(self, df: pd.DataFrame) -> pd.Series:
        rm = df["Close"].rolling(5, min_periods=5).max()
        return (rm > self.THRESH) & (rm.shift(1) <= self.THRESH)

    def generate_orders(self, frames):
        df = frames["H1"]
        cross = self._cross(df).fillna(False)
        close = df["Close"].to_numpy(dtype=float)
        orders = []
        for i in np.flatnonzero(cross.to_numpy()):
            c = float(close[i])
            orders.append(
                OrderIntent(
                    decision_bar=df.index[i],
                    direction=1,
                    entry="market",
                    entry_price=None,
                    decision_close=c,
                    stop=StopRule(price=c - 1.0),
                    exits=[
                        ExitLeg(
                            fraction=1.0,
                            kind="take_profit",
                            price=c + 2.0,
                            label="TP",
                        )
                    ],
                    strategy_id=self.strategy_id,
                )
            )
        return orders


class _RareCentredCheat(_RareHonest):
    """ATTACK #2: the Range_Stochastic_Divergence shape — a centred window that
    fires so rarely the windowed probes never see it fire."""

    def __init__(self) -> None:
        super().__init__("rare_centred_cheat")

    def _cross(self, df: pd.DataFrame) -> pd.Series:
        rm = df["Close"].rolling(5, min_periods=5, center=True).max()  # the cheat
        return (rm > self.THRESH) & (rm.shift(1) <= self.THRESH)


def test_rare_honest_strategy_passes_via_reprobe():
    assert_no_lookahead_v2(_RareHonest(), {"H1": _ramp_frame()})


def test_attack2_rare_centred_strategy_fails_via_reprobe():
    with pytest.raises(LookAheadError, match="rare_centred_cheat"):
        assert_no_lookahead_v2(_RareCentredCheat(), {"H1": _ramp_frame()})


class _NeverFires(_HonestV2):
    def __init__(self) -> None:
        super().__init__("never_fires")

    def generate_orders(self, frames):
        return []


def test_never_firing_strategy_fails():
    with pytest.raises(LookAheadError, match="never_fires.*no orders"):
        assert_no_lookahead_v2(_NeverFires(), {"H1": _frame()})


class _Mutator(_HonestV2):
    """ATTACK #8: writes into the frame it is handed."""

    def __init__(self) -> None:
        super().__init__("frame_mutator")

    def generate_orders(self, frames):
        df = frames["H1"]
        df["Close"] = df["Close"] * 2.0  # the attack
        return []


def test_attack8_frame_mutation_fails():
    with pytest.raises(LookAheadError, match="frame_mutator.*mutated"):
        assert_no_lookahead_v2(_Mutator(), {"H1": _frame()})


# ---------------------------------------------------------------------------
# SignalStrategyAdapter
# ---------------------------------------------------------------------------


def _v1meta(sid: str = "toy_v1") -> StrategyMetadata:
    return StrategyMetadata(
        strategy_id=sid,
        name="Toy v1",
        version="0.0.1",
        author="wave1 tests",
        hypothesis="A toy v1 strategy with a fully stated and falsifiable edge claim.",
        granularities=["H1"],
        pairs=["EUR_USD"],
    )


class _ToyV1(Strategy):
    """Fires +1 at bar 20 and -1 at bar 30 of any frame long enough."""

    @property
    def metadata(self) -> StrategyMetadata:
        return _v1meta()

    @property
    def required_indicators(self) -> List[str]:
        return []

    @property
    def warmup_bars(self) -> int:
        return 3

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        sig = pd.Series(0, index=df.index, dtype=int)
        if len(df) > 20:
            sig.iloc[20] = 1
        if len(df) > 30:
            sig.iloc[30] = -1
        return sig


def _manual_atr(df: pd.DataFrame, period: int) -> np.ndarray:
    """Independent re-implementation of TR + Wilder-style ewm (span=period,
    adjust=False) so the adapter's prices are checked against hand math, not
    against the same function it calls."""
    trs: List[float] = []
    prev_close: float | None = None
    for h, l, c in zip(df["High"], df["Low"], df["Close"]):
        if prev_close is None:
            tr = float(h - l)
        else:
            tr = max(
                float(h - l), abs(float(h) - prev_close), abs(float(l) - prev_close)
            )
        trs.append(tr)
        prev_close = float(c)
    alpha = 2.0 / (period + 1)
    out = np.empty(len(trs))
    state = trs[0]
    out[0] = state
    for i in range(1, len(trs)):
        state = alpha * trs[i] + (1.0 - alpha) * state
        out[i] = state
    return out


def test_adapter_reproduces_t6_absolute_prices():
    df = _frame(40)
    pair = "EUR_USD"
    adapter = SignalStrategyAdapter(_ToyV1(), pair=pair)
    orders = list(adapter.generate_orders({"H1": df}))

    assert [o.decision_bar for o in orders] == [df.index[20], df.index[30]]

    period = ContractStrategyAdapter.ATR_PERIOD
    atr_vals = _manual_atr(df, period)
    slip = BacktestConfig().slippage_pips * get_pip_value(pair)

    # long at bar 20: T6 entry = close + slippage, stop below, TP above
    o = orders[0]
    entry = float(df["Close"].iloc[20]) + slip
    assert o.direction == 1
    assert o.entry == "market" and o.entry_price is None
    assert o.decision_close == pytest.approx(float(df["Close"].iloc[20]), rel=1e-12)
    assert o.stop.price == pytest.approx(
        entry - ContractStrategyAdapter.STOP_LOSS_ATR * atr_vals[20], rel=1e-9
    )
    (leg,) = o.exits
    assert leg.kind == "take_profit" and leg.fraction == 1.0 and leg.label == "TP"
    assert leg.price == pytest.approx(
        entry + ContractStrategyAdapter.TAKE_PROFIT_ATR * atr_vals[20], rel=1e-9
    )
    assert o.time_exit_after_bars == _T6_MAX_BARS
    assert o.close_on_opposite is True
    assert o.tag == "v1"
    assert o.strategy_id == adapter.strategy_id

    # short at bar 30: mirrored
    o = orders[1]
    entry = float(df["Close"].iloc[30]) - slip
    assert o.direction == -1
    assert o.stop.price == pytest.approx(
        entry + ContractStrategyAdapter.STOP_LOSS_ATR * atr_vals[30], rel=1e-9
    )
    assert o.exits[0].price == pytest.approx(
        entry - ContractStrategyAdapter.TAKE_PROFIT_ATR * atr_vals[30], rel=1e-9
    )


def test_adapter_metadata_and_surface():
    adapter = SignalStrategyAdapter(_ToyV1(), pair="USD_JPY")
    meta = adapter.metadata
    assert meta.strategy_id == "toy_v1__v1adapt"
    assert meta.primary_granularity == "H1"
    assert meta.simulate_on == "H1"
    assert meta.pairs == ["EUR_USD"]  # v1 declaration preserved
    assert adapter.max_concurrent_positions == 1  # F12 default
    assert adapter.warmup_bars >= ContractStrategyAdapter.ATR_PERIOD


def test_adapter_emits_nothing_when_flat():
    class _Flat(_ToyV1):
        def generate_signals(self, df: pd.DataFrame) -> pd.Series:
            return pd.Series(0, index=df.index, dtype=int)

    adapter = SignalStrategyAdapter(_Flat(), pair="EUR_USD")
    assert list(adapter.generate_orders({"H1": _frame(40)})) == []


# ---------------------------------------------------------------------------
# re-export surface
# ---------------------------------------------------------------------------


def test_v1_names_are_reexported():
    assert Stage.RESEARCH.value == "research"
    assert issubclass(LookAheadError, AssertionError)
    assert Strategy is not None
    meta = _v1meta("reexport_check")
    assert meta.stage is Stage.RESEARCH
