import pytest
import pandas as pd
from typing import Sequence, Mapping, List
from src.layer0.strategies.contract_v2 import (
    StrategyV2,
    StrategyMetadataV2,
    OrderIntent,
    StopRule,
    ExitLeg,
    assert_no_lookahead_v2,
)
from src.regime_aware.contract import ParamBlock
from src.regime_aware.context import UNKNOWN
from src.regime_aware.v2.gate import RegimeGateV2

class DummyStrategy(StrategyV2):
    def __init__(self, intents: List[OrderIntent]):
        self._intents = intents
        self._metadata = StrategyMetadataV2(
            strategy_id="dummy_strategy",
            name="Dummy",
            version="1.0",
            author="Test",
            hypothesis="Test hypothesis with enough words to satisfy the length requirement which is at least twenty words long so I keep typing until it is long enough to pass validation.",
            granularities=["H1"],
            pairs=["EUR_USD"],
            primary_granularity="H1",
            stage="research",
        )

    @property
    def metadata(self) -> StrategyMetadataV2:
        return self._metadata

    @property
    def required_indicators(self) -> List[str]:
        return []

    @property
    def warmup_bars(self) -> int:
        return 10

    def generate_orders(self, frames: Mapping[str, pd.DataFrame]) -> Sequence[OrderIntent]:
        # Return all intents whose decision bar is in the primary frame index
        idx = frames["H1"].index
        return [i for i in self._intents if i.decision_bar in idx]

def make_intent(decision_bar: pd.Timestamp) -> OrderIntent:
    return OrderIntent(
        decision_bar=decision_bar,
        direction=1,
        entry="market",
        entry_price=None,
        stop=StopRule(price=1.0),
        exits=[ExitLeg(fraction=1.0, kind="take_profit", price=2.0, label="TP")],
        strategy_id="dummy_strategy"
    )

def test_delegation():
    inner = DummyStrategy([])
    gate = RegimeGateV2(inner, pd.Series(dtype=object), {})
    assert gate.metadata == inner.metadata
    assert gate.warmup_bars == inner.warmup_bars
    assert gate.required_indicators == inner.required_indicators

def test_identity():
    ts1 = pd.Timestamp("2026-08-01 10:00:00+00:00")
    ts2 = pd.Timestamp("2026-08-01 11:00:00+00:00")
    intents = [make_intent(ts1), make_intent(ts2)]
    inner = DummyStrategy(intents)
    
    labels = pd.Series(["Trending-Up", "Ranging"], index=[ts1, ts2])
    mask = {
        "Trending-Up": ParamBlock(enabled=True),
        "Ranging": ParamBlock(enabled=True),
    }
    
    gate = RegimeGateV2(inner, labels, mask)
    frames = {"H1": pd.DataFrame(index=[ts1, ts2])}
    
    result = list(gate.generate_orders(frames))
    assert result == intents
    assert gate.intents_passed == 2
    assert gate.intents_dropped == 0

def test_full_suppression():
    ts1 = pd.Timestamp("2026-08-01 10:00:00+00:00")
    intents = [make_intent(ts1)]
    inner = DummyStrategy(intents)
    
    labels = pd.Series(["Trending-Up"], index=[ts1])
    mask = {
        "Trending-Up": ParamBlock(enabled=False),
    }
    
    gate = RegimeGateV2(inner, labels, mask)
    frames = {"H1": pd.DataFrame(index=[ts1])}
    
    result = list(gate.generate_orders(frames))
    assert result == []
    assert gate.intents_passed == 0
    assert gate.intents_dropped == 1
    assert gate.dropped_by_regime == {"Trending-Up": 1}

def test_decision_bar_not_fill_bar():
    decision_ts = pd.Timestamp("2026-08-01 10:00:00+00:00")
    fill_ts = pd.Timestamp("2026-08-01 11:00:00+00:00")  # The gate has no knowledge of this
    
    intent = make_intent(decision_ts)
    inner = DummyStrategy([intent])
    
    labels = pd.Series(["Trending-Up", "Ranging"], index=[decision_ts, fill_ts])
    mask = {
        "Trending-Up": ParamBlock(enabled=False),
        "Ranging": ParamBlock(enabled=True),
    }
    
    gate = RegimeGateV2(inner, labels, mask)
    frames = {"H1": pd.DataFrame(index=[decision_ts, fill_ts])}
    
    result = list(gate.generate_orders(frames))
    # It should be filtered because decision_bar is Trending-Up (disabled)
    assert result == []

def test_unknown_is_always_filtered():
    ts1 = pd.Timestamp("2026-08-01 10:00:00+00:00")
    intents = [make_intent(ts1)]
    inner = DummyStrategy(intents)
    
    labels = pd.Series([UNKNOWN], index=[ts1])
    # Even if we maliciously try to enable UNKNOWN in the mask:
    mask = {
        UNKNOWN: ParamBlock(enabled=True),
    }
    
    gate = RegimeGateV2(inner, labels, mask)
    frames = {"H1": pd.DataFrame(index=[ts1])}
    
    result = list(gate.generate_orders(frames))
    assert result == []

def test_warmup_bars_are_unknown():
    ts1 = pd.Timestamp("2026-08-01 10:00:00+00:00")
    intents = [make_intent(ts1)]
    inner = DummyStrategy(intents)
    
    # Missing from labels series -> UNKNOWN
    labels = pd.Series(dtype=object)
    mask = {
        "Trending-Up": ParamBlock(enabled=True),
    }
    
    gate = RegimeGateV2(inner, labels, mask)
    frames = {"H1": pd.DataFrame(index=[ts1])}
    
    result = list(gate.generate_orders(frames))
    assert result == []

def test_assert_no_lookahead_v2():
    idx = pd.date_range("2026-08-01", periods=100, freq="1h", tz="UTC")
    intents = [make_intent(idx[20]), make_intent(idx[50]), make_intent(idx[80])]
    inner = DummyStrategy(intents)
    
    # Random labels
    labels = pd.Series(["Trending-Up"] * 50 + ["Ranging"] * 50, index=idx)
    mask = {
        "Trending-Up": ParamBlock(enabled=True),
        "Ranging": ParamBlock(enabled=False),
    }
    
    gate = RegimeGateV2(inner, labels, mask)
    
    # Create valid frame
    df = pd.DataFrame({"Close": [1.0] * 100}, index=idx)
    frames = {"H1": df}
    
    # This will raise LookAheadError if it fails
    assert_no_lookahead_v2(gate, frames, probes=5)


# ---------------------------------------------------------------------------
# Real-data invariants
#
# `test_identity` above uses a two-bar toy series in which every bar carries a
# label. It passes trivially and does NOT establish the property the trial
# depends on. On real data the d1_trend label has a 200-day EMA warm-up
# (~7.8% of bars are UNKNOWN), and UNKNOWN is always dropped — so an
# all-permissive mask does NOT reproduce the raw ungated strategy. That is
# correct behaviour, and it is exactly why the runner's blind arm is itself
# gated with the permissive mask. These tests pin that down.
# ---------------------------------------------------------------------------


def test_permissive_gate_drops_exactly_the_unknown_bars():
    """An all-permissive mask filters UNKNOWN and nothing else."""
    ts = [pd.Timestamp("2026-08-01 10:00:00+00:00") + pd.Timedelta(hours=i)
          for i in range(4)]
    intents = [make_intent(t) for t in ts]
    labels = pd.Series(["Trending-Up", UNKNOWN, "Ranging", UNKNOWN], index=ts)
    permissive = {
        "Trending-Up": ParamBlock(enabled=True),
        "Trending-Down": ParamBlock(enabled=True),
        "Ranging": ParamBlock(enabled=True),
        "High-Vol": ParamBlock(enabled=True),
        UNKNOWN: ParamBlock(enabled=True),  # even so, UNKNOWN must drop
    }
    gate = RegimeGateV2(DummyStrategy(intents), labels, permissive)
    out = list(gate.generate_orders({"H1": pd.DataFrame(index=ts)}))

    assert out == [intents[0], intents[2]]
    assert gate.intents_dropped == 2
    assert gate.dropped_by_regime == {UNKNOWN: 2}


def test_aware_is_a_subset_of_the_permissive_blind_arm():
    """The masked arm may only ever remove intents the blind arm kept.

    This is the invariant that makes the A/B interpretable: both arms share one
    evaluable window, and every difference is attributable to the mask.
    """
    ts = [pd.Timestamp("2026-08-01 10:00:00+00:00") + pd.Timedelta(hours=i)
          for i in range(4)]
    intents = [make_intent(t) for t in ts]
    labels = pd.Series(
        ["Trending-Up", UNKNOWN, "Ranging", "Trending-Down"], index=ts
    )
    permissive = {r: ParamBlock(enabled=True)
                  for r in ("Trending-Up", "Trending-Down", "Ranging", "High-Vol", UNKNOWN)}
    trend_mask = dict(permissive)
    trend_mask["Ranging"] = ParamBlock(enabled=False)

    frames = {"H1": pd.DataFrame(index=ts)}
    blind = list(RegimeGateV2(DummyStrategy(intents), labels, permissive)
                 .generate_orders(frames))
    aware = list(RegimeGateV2(DummyStrategy(intents), labels, trend_mask)
                 .generate_orders(frames))

    assert set(id(i) for i in aware) <= set(id(i) for i in blind)
    # the only removal is the Ranging bar, never the warm-up bar
    assert [i for i in blind if i not in aware] == [intents[2]]
