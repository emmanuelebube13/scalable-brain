"""Pilot research strategy — RSI mean reversion.

Deliberately a *plain* idea, chosen so the pipeline is demonstrated on something
whose verdict is not pre-ordained. Its purpose is to exercise the machinery
end-to-end; whether it qualifies is the pipeline's answer, not the author's.

The `mean_reversion/` folder held only a README. This gives that family an actual
implementation to be judged.
"""

from __future__ import annotations

from typing import List

import pandas as pd

from ..contract import Stage, Strategy, StrategyMetadata


class RSIMeanReversion(Strategy):
    """Fade RSI extremes, exit on reversion to the midline."""

    def __init__(
        self, period: int = 14, oversold: float = 30.0, overbought: float = 70.0
    ) -> None:
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id="rsi_mean_reversion",
            name="RSI Mean Reversion",
            version="0.1.0",
            author="T6 pilot",
            hypothesis=(
                "In ranging conditions short-horizon RSI extremes reflect temporary "
                "order-flow imbalance rather than information, so fading a reading "
                "below 30 or above 70 captures the reversion to fair value once the "
                "imbalance clears. The edge should weaken or invert in trending "
                "regimes, where an extreme reading indicates continuation."
            ),
            granularities=["H1", "H4"],
            pairs=["EUR_USD", "GBP_USD"],
            stage=Stage.RESEARCH,
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["rsi", "atr"]

    @property
    def warmup_bars(self) -> int:
        return max(100, self.period * 5)

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """+1 / -1 / 0 per bar. Every operation is trailing-only by construction."""
        close = df["Close"]
        delta = close.diff()
        gain = (
            delta.clip(lower=0.0).rolling(self.period, min_periods=self.period).mean()
        )
        loss = (
            (-delta.clip(upper=0.0))
            .rolling(self.period, min_periods=self.period)
            .mean()
        )
        rs = gain / loss.replace(0.0, pd.NA)
        rsi = 100.0 - (100.0 / (1.0 + rs))

        signals = pd.Series(0, index=df.index, dtype=int)
        signals[rsi < self.oversold] = 1
        signals[rsi > self.overbought] = -1
        signals.iloc[: self.warmup_bars] = 0
        return signals
