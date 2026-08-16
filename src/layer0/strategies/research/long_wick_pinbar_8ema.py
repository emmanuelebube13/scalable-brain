from __future__ import annotations

from typing import List, Mapping, Sequence

import numpy as np
import pandas as pd

from ..contract_v2 import (
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)
from ...data_access.indicators import ema, get_pip_value


def _calc_lower_wick(
    open_p: np.ndarray, close_p: np.ndarray, low_p: np.ndarray
) -> np.ndarray:
    return np.minimum(open_p, close_p) - low_p


def _calc_upper_wick(
    open_p: np.ndarray, close_p: np.ndarray, high_p: np.ndarray
) -> np.ndarray:
    return high_p - np.maximum(open_p, close_p)


class LongWickPinbar8Ema(StrategyV2):
    """Long Wick Pinbar 8 EMA Strategy."""

    FAST_EMA = 8
    SLOW_EMA = 16
    WICK_FRACTION = 2.0 / 3.0
    STOP_BUFFER_PIPS = 2.0
    TP_MULTIPLE = 2.0

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="long_wick_pinbar_8ema",
            name="Long Wick Pinbar 8 EMA",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "In a persistent trend, a pullback to the fast EMA that is rejected — "
                "evidenced by a daily candle whose dominant feature is a long wick probing "
                "through value and being refused — marks the point where counter-trend "
                "liquidity has been absorbed and trend-following participants reassert control. "
                "The edge is behavioural: the long wick is the footprint of trapped "
                'counter-trend traders and defended resting orders at the EMA8 "dynamic '
                'support/resistance" zone, so price should resume in the trend direction '
                "with a favourable 2:1 payoff. It should persist as long as FX trends exhibit "
                "pullback-continuation structure and traders anchor on short EMAs as reference levels."
            ),
            granularities=["D1"],
            pairs=["EUR_USD", "GBP_USD", "AUD_USD"],
            primary_granularity="D1",
            context_granularities=(),
            simulate_on="H1",
            source_row=2,
            source_url="https://www.forexfactory.com/thread/175346-swing-trades-using-price-action",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["ema"]

    @property
    def warmup_bars(self) -> int:
        return self.SLOW_EMA + 10

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        d1 = frames["D1"]
        pip = float(get_pip_value(self.metadata.pairs[0]))

        close = d1["Close"].to_numpy(dtype=float)
        open_p = d1["Open"].to_numpy(dtype=float)
        high = d1["High"].to_numpy(dtype=float)
        low = d1["Low"].to_numpy(dtype=float)

        ema8 = ema(d1["Close"], self.FAST_EMA).to_numpy(dtype=float)
        ema16 = ema(d1["Close"], self.SLOW_EMA).to_numpy(dtype=float)
        rng = high - low

        lower_wick = _calc_lower_wick(open_p, close, low)
        upper_wick = _calc_upper_wick(open_p, close, high)
        min_oc = np.minimum(open_p, close)
        max_oc = np.maximum(open_p, close)

        orders: List[OrderIntent] = []
        for i in range(self.warmup_bars, len(d1)):
            if rng[i] <= 0:
                continue

            ema8_val = float(ema8[i])
            ema16_val = float(ema16[i])
            close_val = float(close[i])

            # Long rules
            # 1. EMA8 > EMA16
            # 3. lower_wick >= 2/3 rng
            # 4. Low <= EMA8 <= min(Open, Close)
            if ema8_val > ema16_val:
                if lower_wick[i] >= self.WICK_FRACTION * rng[i]:
                    if low[i] <= ema8_val <= min_oc[i]:
                        stop = float(low[i]) - self.STOP_BUFFER_PIPS * pip
                        risk = close_val - stop

                        orders.append(
                            OrderIntent(
                                decision_bar=d1.index[i],
                                direction=1,
                                entry="market",
                                entry_price=None,
                                decision_close=close_val,
                                stop=StopRule(price=stop),
                                exits=[
                                    ExitLeg(
                                        fraction=1.0,
                                        kind="take_profit",
                                        price=close_val + self.TP_MULTIPLE * risk,
                                        label="TP1",
                                    )
                                ],
                                expires_after_bars=None,
                                tag="long_wick",
                            )
                        )
                        continue

            # Short rules
            if ema8_val < ema16_val:
                if upper_wick[i] >= self.WICK_FRACTION * rng[i]:
                    if max_oc[i] <= ema8_val <= high[i]:
                        stop = float(high[i]) + self.STOP_BUFFER_PIPS * pip
                        risk = stop - close_val

                        orders.append(
                            OrderIntent(
                                decision_bar=d1.index[i],
                                direction=-1,
                                entry="market",
                                entry_price=None,
                                decision_close=close_val,
                                stop=StopRule(price=stop),
                                exits=[
                                    ExitLeg(
                                        fraction=1.0,
                                        kind="take_profit",
                                        price=close_val - self.TP_MULTIPLE * risk,
                                        label="TP1",
                                    )
                                ],
                                expires_after_bars=None,
                                tag="short_wick",
                            )
                        )

        return orders
