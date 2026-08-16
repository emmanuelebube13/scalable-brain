"""The contract-v2 regime gate."""

import pandas as pd
from typing import Sequence, Mapping, Dict, List
from src.layer0.strategies.contract_v2 import (
    StrategyV2,
    StrategyMetadataV2,
    OrderIntent,
)
from src.regime_aware.contract import ParamBlock
from src.regime_aware.context import UNKNOWN

class RegimeGateV2(StrategyV2):
    """
    A wrapper implementing StrategyV2 that holds an inner strategy plus a mask.
    Filters the yielded intents from the inner strategy based on the regime label
    at the intent's decision_bar.
    """

    def __init__(self, inner: StrategyV2, labels: pd.Series, mask: Dict[str, ParamBlock]):
        self._inner = inner
        self._labels = labels
        self._mask = mask
        self.intents_dropped: int = 0
        self.dropped_by_regime: Dict[str, int] = {}
        self.intents_passed: int = 0

    @property
    def metadata(self) -> StrategyMetadataV2:
        return self._inner.metadata

    @property
    def required_indicators(self) -> List[str]:
        return self._inner.required_indicators

    @property
    def warmup_bars(self) -> int:
        return self._inner.warmup_bars

    def generate_orders(self, frames: Mapping[str, pd.DataFrame]) -> Sequence[OrderIntent]:
        # Reset counters per run so that `assert_no_lookahead_v2` probes
        # or multiple calls do not accumulate stale counts from previous runs.
        # The final full run will leave the counters in the correct state for the caller.
        self.intents_dropped = 0
        self.dropped_by_regime = {}
        self.intents_passed = 0

        intents = self._inner.generate_orders(frames)
        filtered: List[OrderIntent] = []
        
        for intent in intents:
            decision_time = intent.decision_bar
            
            if decision_time in self._labels.index:
                label = self._labels.loc[decision_time]
            else:
                label = UNKNOWN
            
            # UNKNOWN always means do not trade. Never treat it as permissive.
            if label == UNKNOWN:
                enabled = False
            else:
                block = self._mask.get(str(label))
                enabled = block.enabled if block else False
            
            if enabled:
                filtered.append(intent)
                self.intents_passed += 1
            else:
                self.intents_dropped += 1
                label_str = str(label)
                self.dropped_by_regime[label_str] = self.dropped_by_regime.get(label_str, 0) + 1
                
        return filtered
