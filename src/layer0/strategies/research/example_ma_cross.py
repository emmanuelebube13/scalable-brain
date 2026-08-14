"""Example research strategy: trailing-only MA crossover.

A minimal contract-compliant strategy so the registry has a real
research-stage entry to discover and the promotion pipeline has something
concrete to refuse/evaluate in tests.
"""

from __future__ import annotations

from typing import List

import pandas as pd

from ..contract import Stage, Strategy, StrategyMetadata


class ExampleMaCross(Strategy):
    """Fast/SMA crossover over a slow SMA, trailing data only."""

    FAST = 10
    SLOW = 50

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id="example_ma_cross",
            name="Example MA Crossover",
            version="0.1.0",
            author="wave1 skeleton",
            hypothesis=(
                "When the fast moving average crosses above the slow moving "
                "average, short-term momentum persists long enough to reach "
                "an ATR-based profit target before reverting."
            ),
            granularities=["H1"],
            pairs=["EUR_USD"],
            stage=Stage.RESEARCH,
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["sma"]

    @property
    def warmup_bars(self) -> int:
        return self.SLOW

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        fast = df["Close"].rolling(self.FAST, min_periods=self.FAST).mean()
        slow = df["Close"].rolling(self.SLOW, min_periods=self.SLOW).mean()
        cross_up = (fast > slow) & (fast.shift(1) <= slow.shift(1))
        cross_down = (fast < slow) & (fast.shift(1) >= slow.shift(1))
        signals = pd.Series(0, index=df.index, dtype=int)
        signals[cross_up.fillna(False)] = 1
        signals[cross_down.fillna(False)] = -1
        return signals
