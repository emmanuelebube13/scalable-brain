"""T6 — adapt a contract `Strategy` to the legacy backtest engine.

The contract is deliberately smaller than `StrategyBase`: it is the *promotion*
surface (identity, hypothesis, signals) while `StrategyBase` is the *execution*
surface the engine drives (indicators, stops, targets, entry/exit descriptions).

Keeping them separate is the point. A research author writes ~30 lines against
the contract and cannot accidentally reach execution concerns; this adapter
supplies the engine's requirements using the standard cost model and ATR-based
stops, so every research strategy is backtested under *identical* execution
assumptions. A strategy cannot flatter itself with bespoke stop logic.
"""

from __future__ import annotations

from typing import Dict

import pandas as pd

from ..core_engine.strategy_base import StrategyBase, StrategyConfig
from ..data_access.indicators import atr
from .contract import Strategy


class ContractStrategyAdapter(StrategyBase):
    """Drive a contract `Strategy` through the legacy `BacktestEngine`."""

    # Uniform execution assumptions for every research strategy.
    ATR_PERIOD = 14
    STOP_LOSS_ATR = 1.0
    TAKE_PROFIT_ATR = 3.0  # matches the live DEFAULT_RR_RATIO of 3.0

    def __init__(self, strategy: Strategy) -> None:
        meta = strategy.metadata
        super().__init__(
            StrategyConfig(
                name=meta.name,
                description=meta.hypothesis,
                version=meta.version,
                author=meta.author,
                assets=list(meta.pairs),
                granularities=list(meta.granularities),
                atr_period=self.ATR_PERIOD,
                stop_loss_atr=self.STOP_LOSS_ATR,
                take_profit_atr=self.TAKE_PROFIT_ATR,
                # Explicitly off. The config default is True, but the filter
                # was always inert here: it no-ops when "ATR" is absent, and
                # before FIX-S1-021 the adapter wrote "atr" (lower case).
                # Fixing the casing would otherwise silently activate it and
                # change every research strategy's trade set — a semantics
                # change far beyond the stop-source defect being fixed.
                volatility_filter=False,
            )
        )
        self._strategy = strategy

    def calculate_indicators(
        self, df: pd.DataFrame, asset: str, granularity: str
    ) -> pd.DataFrame:
        """Only ATR — stops and targets are uniform across research strategies.

        Strategy-specific indicators are the strategy's own business, computed
        inside `generate_signals` from trailing data.
        """
        # NOTE: the column MUST be upper-case "ATR" — that is the casing
        # `StrategyBase.calculate_stop_loss` / `calculate_take_profit` and
        # `multi_timeframe.generate_mtf_signals` read. Writing "atr" (lower
        # case) made every lookup miss, so stops were recomputed per-entry on
        # a data prefix and became warmup-dependent (FIX-S1-021 / O-12).
        df["ATR"] = atr(df["High"], df["Low"], df["Close"], period=self.ATR_PERIOD)
        return df

    def generate_signals(
        self, df: pd.DataFrame, asset: str, granularity: str
    ) -> pd.Series:
        signals = self._strategy.generate_signals(df)
        return signals.reindex(df.index).fillna(0).astype(int)

    def get_entry_conditions(self) -> Dict[str, str]:
        return {"hypothesis": self._strategy.metadata.hypothesis}

    def get_exit_conditions(self) -> Dict[str, str]:
        return {
            "stop_loss": f"{self.STOP_LOSS_ATR} x ATR({self.ATR_PERIOD})",
            "take_profit": f"{self.TAKE_PROFIT_ATR} x ATR({self.ATR_PERIOD})",
        }

    def get_required_warmup_bars(self) -> int:
        return max(self._strategy.warmup_bars, self.ATR_PERIOD * 3)
