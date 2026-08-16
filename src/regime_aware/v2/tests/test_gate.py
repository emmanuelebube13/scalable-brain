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
