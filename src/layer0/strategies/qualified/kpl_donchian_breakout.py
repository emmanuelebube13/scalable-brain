import numpy as np
import pandas as pd
from typing import List, Sequence, Mapping

from ..contract_v2 import (
    StrategyV2,
    StrategyMetadataV2,
    OrderIntent,
    StopRule,
    ExitLeg,
)
from ...data_access.indicators import atr, donchian_channel


class KplDonchianBreakout(StrategyV2):
    DONCHIAN_PERIOD = 20
    ATR_PERIOD = 14

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="kpl_donchian_breakout",
            name="KPL Donchian Breakout",
            version="1.0.0",
            author="tradingview",
            hypothesis="A daily close beyond the extreme of the prior 20 trading days marks the start (or resumption) of a directional trend rather than random noise, because FX trends are persistent. A mechanical close-confirmed 20-day Donchian breakout with a volatility-scaled stop harvests this persistence by cutting failures quickly and letting confirmed trends run.",
            granularities=["D1"],
            pairs=[
                "EUR_USD",
                "GBP_USD",
                "USD_JPY",
                "AUD_USD",
                "USD_CAD",
                "GBP_JPY",
                "EUR_JPY",
                "NZD_USD",
                "USD_CHF",
                "EUR_GBP",
                "EUR_AUD",
                "AUD_NZD",
                "EUR_CAD",
            ],
            primary_granularity="D1",
            simulate_on="H1",
            source_url="https://www.tradingview.com/script/4mz6xvnK/",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["atr", "donchian_channel"]

    @property
    def warmup_bars(self) -> int:
        return max(self.DONCHIAN_PERIOD, self.ATR_PERIOD) + 1

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        d1 = frames[self.metadata.primary_granularity]
        n = len(d1)
        if n < self.warmup_bars:
            return []

        close_s = d1["Close"].to_numpy(dtype=float)
        atr_s = atr(d1["High"], d1["Low"], d1["Close"], self.ATR_PERIOD).to_numpy(
            dtype=float
        )

        dcu, _, dcl = donchian_channel(d1["High"], d1["Low"], self.DONCHIAN_PERIOD)
        dcu_s = dcu.shift(1).to_numpy(dtype=float)
        dcl_s = dcl.shift(1).to_numpy(dtype=float)

        orders: List[OrderIntent] = []
        start_idx = self.warmup_bars
        for i in range(start_idx, n):
            if not (
                np.isfinite(dcu_s[i])
                and np.isfinite(dcu_s[i - 1])
                and np.isfinite(dcl_s[i])
                and np.isfinite(dcl_s[i - 1])
                and np.isfinite(atr_s[i])
            ):
                continue

            C_t = close_s[i]
            C_t1 = close_s[i - 1]

            dcu_t = dcu_s[i]
            dcu_t1 = dcu_s[i - 1]
            dcl_t = dcl_s[i]
            dcl_t1 = dcl_s[i - 1]
            atr_t = atr_s[i]

            long_breakout = (C_t > dcu_t) and (C_t1 <= dcu_t1)
            if long_breakout:
                stop_price = C_t - 2.0 * atr_t
                orders.append(
                    OrderIntent(
                        decision_bar=d1.index[i],
                        direction=1,
                        entry="market",
                        entry_price=None,
                        decision_close=C_t,
                        stop=StopRule(price=stop_price, trail_atr_multiple=2.0),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="trailing",
                                atr_multiple=2.0,
                                label="TRAIL",
                            )
                        ],
                        expires_after_bars=None,
                        strategy_id=self.strategy_id,
                    )
                )
                continue

            short_breakout = (C_t < dcl_t) and (C_t1 >= dcl_t1)
            if short_breakout:
                stop_price = C_t + 2.0 * atr_t
                orders.append(
                    OrderIntent(
                        decision_bar=d1.index[i],
                        direction=-1,
                        entry="market",
                        entry_price=None,
                        decision_close=C_t,
                        stop=StopRule(price=stop_price, trail_atr_multiple=2.0),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="trailing",
                                atr_multiple=2.0,
                                label="TRAIL",
                            )
                        ],
                        expires_after_bars=None,
                        strategy_id=self.strategy_id,
                    )
                )
        return orders
