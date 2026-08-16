"""ma_crossover_swing strategy."""

from __future__ import annotations

from typing import List, Mapping, Sequence

import numpy as np
import pandas as pd

from ..contract_v2 import ExitLeg, OrderIntent, StopRule, StrategyMetadataV2, StrategyV2
from ...data_access.indicators import atr, ema, macd, sma


class MaCrossoverSwing(StrategyV2):
    """MA Crossover Swing Strategy."""

    FAST_EMA = 5
    SLOW_EMA = 10
    REGIME_SMA = 200
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9
    ATR_PERIOD = 14

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="ma_crossover_swing",
            name="MA Crossover Swing",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "Trend-following edge: when a fast moving average crosses a slower one "
                "and price is simultaneously on the trend side of the 200-day mean with "
                "MACD momentum agreeing, the market is in the early phase of a multi-day "
                "directional move driven by herding of momentum participants and the slow "
                "re-pricing of drift; entering at the next open with a wide ATR bracket "
                "(1:2.3 reward-to-risk) and an 8-bar time stop harvests the continuation "
                "while cutting trades where the move fails to materialise promptly. The "
                "dual confirmation exists because raw MA crosses are whipsaw-prone in "
                "ranges — the edge should persist because regime (SMA200) and momentum "
                "(MACD) agreement filters out the low-quality crossings that erode the raw signal."
            ),
            granularities=["D1"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY"],
            primary_granularity="D1",
            context_granularities=(),
            simulate_on="H1",
            source_row=18,
            source_url="https://www.tradingview.com/script/uNIA4siU-Moving-Average-Crossover-Swing-Strategy/",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["ema", "sma", "macd", "atr"]

    @property
    def warmup_bars(self) -> int:
        return 200

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        d1 = frames["D1"]

        ema5 = ema(d1["Close"], self.FAST_EMA).to_numpy(dtype=float)
        ema10 = ema(d1["Close"], self.SLOW_EMA).to_numpy(dtype=float)
        sma200 = sma(d1["Close"], self.REGIME_SMA).to_numpy(dtype=float)

        macd_line, macd_signal, _ = macd(
            d1["Close"], self.MACD_FAST, self.MACD_SLOW, self.MACD_SIGNAL
        )
        macd_line_np = macd_line.to_numpy(dtype=float)
        macd_signal_np = macd_signal.to_numpy(dtype=float)

        atr14 = atr(d1["High"], d1["Low"], d1["Close"], self.ATR_PERIOD).to_numpy(
            dtype=float
        )
        close = d1["Close"].to_numpy(dtype=float)

        orders: List[OrderIntent] = []

        for i in range(self.warmup_bars, len(d1)):
            if (
                np.isnan(sma200[i])
                or np.isnan(macd_line_np[i])
                or np.isnan(macd_signal_np[i])
                or np.isnan(atr14[i])
            ):
                continue

            is_bullish_cross = ema5[i] > ema10[i] and ema5[i - 1] <= ema10[i - 1]
            is_bearish_cross = ema5[i] < ema10[i] and ema5[i - 1] >= ema10[i - 1]

            close_t = close[i]
            atr_t = atr14[i]

            # Long rules
            if (
                is_bullish_cross
                and close_t > sma200[i]
                and macd_line_np[i] > macd_signal_np[i]
            ):
                stop = close_t - 1.4 * atr_t
                tp = close_t + 3.2 * atr_t

                orders.append(
                    OrderIntent(
                        decision_bar=d1.index[i],
                        direction=1,
                        entry="market",
                        entry_price=None,
                        decision_close=close_t,
                        stop=StopRule(price=stop),
                        exits=[
                            ExitLeg(
                                fraction=0.5,
                                kind="take_profit",
                                price=tp,
                                label="TP",
                            ),
                            ExitLeg(
                                fraction=0.5,
                                kind="time",
                                bars=8,
                                label="TIME",
                            ),
                        ],
                        expires_after_bars=None,
                        tag="ma_crossover_swing",
                        strategy_id=self.strategy_id,
                    )
                )

            # Short rules
            elif (
                is_bearish_cross
                and close_t < sma200[i]
                and macd_line_np[i] < macd_signal_np[i]
            ):
                stop = close_t + 1.4 * atr_t
                tp = close_t - 3.2 * atr_t

                orders.append(
                    OrderIntent(
                        decision_bar=d1.index[i],
                        direction=-1,
                        entry="market",
                        entry_price=None,
                        decision_close=close_t,
                        stop=StopRule(price=stop),
                        exits=[
                            ExitLeg(
                                fraction=0.5,
                                kind="take_profit",
                                price=tp,
                                label="TP",
                            ),
                            ExitLeg(
                                fraction=0.5,
                                kind="time",
                                bars=8,
                                label="TIME",
                            ),
                        ],
                        expires_after_bars=None,
                        tag="ma_crossover_swing",
                        strategy_id=self.strategy_id,
                    )
                )

        return orders
