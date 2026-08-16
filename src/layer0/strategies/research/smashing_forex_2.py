"""Smashing Forex 2 strategy."""

from __future__ import annotations

from typing import List, Mapping, Sequence
import numpy as np
import pandas as pd

from ..contract_v2 import ExitLeg, OrderIntent, StopRule, StrategyMetadataV2, StrategyV2
from ...data_access.indicators import ema, cci, get_pip_value


class SmashingForex2(StrategyV2):
    """When price closes beyond its 60-period EMA while the 14-period CCI simultaneously exceeds ±100, an established directional move with above-average displacement is already underway, and trend-following entries taken at that point capture continuation because CCI ±100 filters out weak, mean-reverting drifts that a bare EMA cross would accept. The edge should persist because it exploits herding behaviour in sustained order flow: the first lot banks a fixed 200-pip profit to de-risk the trade, and the breakeven-protected runner monetises the fat right tail of trend days that fixed-target systems forfeit. The system survives on asymmetry — many small scratches and 1R-ish wins, occasional large runner gains."""

    EMA_PERIOD = 60
    CCI_PERIOD = 14
    TARGET_PIPS = 200.0
    STOP_CAP_PIPS = 200.0
    BUFFER_PIPS = 5.0

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="smashing_forex_2",
            name="Smashing Forex 2",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "When price closes beyond its 60-period EMA while the 14-period CCI "
                "simultaneously exceeds ±100, an established directional move with "
                "above-average displacement is already underway, and trend-following "
                "entries taken at that point capture continuation because CCI ±100 "
                "filters out weak, mean-reverting drifts that a bare EMA cross would "
                "accept. The edge should persist because it exploits herding behaviour "
                "in sustained order flow: the first lot banks a fixed 200-pip profit "
                "to de-risk the trade, and the breakeven-protected runner monetises "
                "the fat right tail of trend days that fixed-target systems forfeit. "
                "The system survives on asymmetry — many small scratches and 1R-ish "
                "wins, occasional large runner gains."
            ),
            granularities=["H4", "D1"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="H4",
            simulate_on="H1",
            source_row=7,
            source_url="https://www.forexstrategiesresources.com/trend-following-forex-strategies/63-smashing-forex-system-2/",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["ema", "cci"]

    @property
    def warmup_bars(self) -> int:
        return 120

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        primary = frames[self.metadata.primary_granularity]
        pip = float(get_pip_value(self.metadata.pairs[0]))

        close = primary["Close"].to_numpy(dtype=float)
        ema60 = ema(primary["Close"], self.EMA_PERIOD).to_numpy(dtype=float)
        cci14 = cci(
            primary["High"], primary["Low"], primary["Close"], period=self.CCI_PERIOD
        ).to_numpy(dtype=float)

        long_cond = (close > ema60) & (cci14 > 100.0)
        short_cond = (close < ema60) & (cci14 < -100.0)

        orders: List[OrderIntent] = []
        for i in range(self.warmup_bars, len(primary)):
            if (
                np.isnan(ema60[i])
                or np.isnan(cci14[i])
                or np.isnan(ema60[i - 1])
                or np.isnan(cci14[i - 1])
            ):
                continue

            c_t = float(close[i])
            is_long = long_cond[i]
            is_short = short_cond[i]

            if is_long and not long_cond[i - 1]:
                dist_ema = (c_t - float(ema60[i])) + self.BUFFER_PIPS * pip
                dist_cap = self.STOP_CAP_PIPS * pip
                dist = min(dist_ema, dist_cap)
                if dist <= 0:
                    continue

                orders.append(
                    OrderIntent(
                        decision_bar=primary.index[i],
                        direction=1,
                        entry="market",
                        entry_price=None,
                        decision_close=c_t,
                        stop=StopRule(
                            price=c_t - dist,
                            move_to_breakeven_on="TP1",
                            breakeven_offset_pips=0.0,
                            trail_atr_multiple=None,
                        ),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="take_profit",
                                price=c_t + self.TARGET_PIPS * pip,
                                label="TP1",
                            ),
                        ],
                        expires_after_bars=None,
                        size_fraction=1.0,
                        tag="smashing2_long",
                        strategy_id=self.strategy_id,
                    )
                )
            elif is_short and not short_cond[i - 1]:
                dist_ema = (float(ema60[i]) - c_t) + self.BUFFER_PIPS * pip
                dist_cap = self.STOP_CAP_PIPS * pip
                dist = min(dist_ema, dist_cap)
                if dist <= 0:
                    continue

                orders.append(
                    OrderIntent(
                        decision_bar=primary.index[i],
                        direction=-1,
                        entry="market",
                        entry_price=None,
                        decision_close=c_t,
                        stop=StopRule(
                            price=c_t + dist,
                            move_to_breakeven_on="TP1",
                            breakeven_offset_pips=0.0,
                            trail_atr_multiple=None,
                        ),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="take_profit",
                                price=c_t - self.TARGET_PIPS * pip,
                                label="TP1",
                            ),
                        ],
                        expires_after_bars=None,
                        size_fraction=1.0,
                        tag="smashing2_short",
                        strategy_id=self.strategy_id,
                    )
                )

        return orders
