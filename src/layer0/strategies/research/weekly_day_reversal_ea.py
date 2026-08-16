from typing import List, Mapping, Sequence

import numpy as np
import pandas as pd

from ..contract_v2 import (
    Direction,
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)


class WeeklyDayReversalEa(StrategyV2):
    """Weekly Day Reversal EA."""

    ADR_PERIOD = 14
    TARGET_DOW = 1  # Tuesday
    FILTER_MULTIPLE = 1.5
    STOP_MULTIPLE = 0.5
    TIME_LEG_BARS = 23

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="weekly_day_reversal_ea",
            name="Weekly Day Reversal EA",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "FX majors exhibit a weekday-calendar reversal anomaly: after a directional day, "
                "the following configured weekday tends to retrace part of that move rather than continue it, "
                "because short-horizon positioning built up during the prior session is unwound by mean-reverting "
                "flow (profit-taking, liquidity rebalancing at the start of a new trading day) before fresh information arrives."
            ),
            granularities=["D1"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="D1",
            context_granularities=(),
            simulate_on="H1",
            source_row=40,
            source_url="https://www.mql5.com/en/code/74137",
        )

    @property
    def required_indicators(self) -> List[str]:
        return []

    @property
    def warmup_bars(self) -> int:
        return 15

    def _adr14(self, df: pd.DataFrame) -> pd.Series:
        return (df["High"] - df["Low"]).rolling(self.ADR_PERIOD).mean()

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        d1 = frames["D1"]

        open_arr = d1["Open"].to_numpy(dtype=float)
        high_arr = d1["High"].to_numpy(dtype=float)
        low_arr = d1["Low"].to_numpy(dtype=float)
        close_arr = d1["Close"].to_numpy(dtype=float)

        adr = self._adr14(d1).to_numpy(dtype=float)

        # d1 index timestamps are open-stamps. D's stamp + 1 day = next bar's stamp (T)
        next_dow = (d1.index + pd.Timedelta(days=1)).dayofweek.to_numpy()

        orders: List[OrderIntent] = []
        for i in range(self.warmup_bars, len(d1)):
            if np.isnan(adr[i]):
                continue

            if next_dow[i] != self.TARGET_DOW:
                continue

            close_d = close_arr[i]
            open_d = open_arr[i]
            high_d = high_arr[i]
            low_d = low_arr[i]

            if (high_d - low_d) < self.FILTER_MULTIPLE * adr[i]:
                continue

            if close_d < open_d:
                direction: Direction = 1
            elif close_d > open_d:
                direction = -1
            else:
                continue

            stop_distance = self.STOP_MULTIPLE * adr[i]
            stop_price = (
                close_d - stop_distance if direction == 1 else close_d + stop_distance
            )

            orders.append(
                OrderIntent(
                    decision_bar=d1.index[i],
                    direction=direction,
                    entry="market",
                    entry_price=None,
                    stop=StopRule(
                        price=float(stop_price),
                    ),
                    exits=[
                        ExitLeg(
                            fraction=1.0,
                            kind="time",
                            bars=self.TIME_LEG_BARS,
                            label="TIME_CLOSE",
                        )
                    ],
                    expires_after_bars=None,
                    tag="weekly_day_reversal_ea",
                )
            )
        return orders
