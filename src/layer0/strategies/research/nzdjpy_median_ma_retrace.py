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
from ...data_access.indicators import sma


class NzdjpyMedianMaRetrace(StrategyV2):
    """Counter-trend-within-strength edge: when the fast median-price average dips below the slow median-price average (a short-term retrace) during the London morning window, price is statistically more likely to resume the prevailing direction than to keep falling, because London session open flow concentrates institutional continuation orders at round hours and the (H+L)/2 median filters out wick noise that fakes genuine weakness. The claimed persistence is behavioural — session-timed liquidity and round-hour order clustering — not a pure curve pattern; however the source's own evidence (backtest 2013–2020 plus a 2020-onward forward test) exists only as chart images in the thread and is not machine-verifiable, and the below-1:1 reward:risk means the edge must rest on a high win rate that the rules alone do not guarantee."""

    FAST_PERIOD = 5
    SLOW_PERIOD = 50

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="nzdjpy_median_ma_retrace",
            name="NZDJPY Median MA Retrace",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "Counter-trend-within-strength edge: when the fast median-price average dips below the slow median-price average (a short-term retrace) during the London morning window, price is statistically more likely to resume the prevailing direction than to keep falling, because London session open flow concentrates institutional continuation orders at round hours and the (H+L)/2 median filters out wick noise that fakes genuine weakness. The claimed persistence is behavioural — session-timed liquidity and round-hour order clustering — not a pure curve pattern; however the source's own evidence (backtest 2013–2020 plus a 2020-onward forward test) exists only as chart images in the thread and is not machine-verifiable, and the below-1:1 reward:risk means the edge must rest on a high win rate that the rules alone do not guarantee."
            ),
            granularities=["H1"],
            pairs=["NZD_JPY"],
            primary_granularity="H1",
            context_granularities=(),
            simulate_on="H1",
            source_row=37,
            source_url="https://www.trade2win.com/threads/trading-strategy-advice.241661/",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["sma"]

    @property
    def warmup_bars(self) -> int:
        return self.SLOW_PERIOD

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h1 = frames["H1"]

        med = (h1["High"] + h1["Low"]) / 2.0
        ma5_s = sma(med, self.FAST_PERIOD).to_numpy(dtype=float)
        ma50_s = sma(med, self.SLOW_PERIOD).to_numpy(dtype=float)
        close = h1["Close"].to_numpy(dtype=float)
        hours = h1.index.hour.to_numpy()
        minutes = h1.index.minute.to_numpy()

        orders: List[OrderIntent] = []
        for i in range(self.warmup_bars, len(h1)):
            hour_ok = (7 <= hours[i] <= 13) and (minutes[i] == 0)
            if not hour_ok:
                continue

            c5 = ma5_s[i]
            c50 = ma50_s[i]
            p5 = ma5_s[i - 1]
            p50 = ma50_s[i - 1]

            if np.isnan(c5) or np.isnan(c50) or np.isnan(p5) or np.isnan(p50):
                continue

            buy_signal = (c5 < c50) and (p5 >= p50)
            sell_signal = (c5 > c50) and (p5 <= p50)

            if not buy_signal and not sell_signal:
                continue

            close_price = float(close[i])

            if buy_signal:
                stop_price = close_price * (1.0 - 0.005)
                tp_price = close_price * (1.0 + 0.004)

                orders.append(
                    OrderIntent(
                        decision_bar=h1.index[i],
                        direction=1,
                        entry="market",
                        entry_price=None,
                        stop=StopRule(
                            price=stop_price,
                            move_to_breakeven_on=None,
                            breakeven_offset_pips=0.0,
                        ),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="take_profit",
                                price=tp_price,
                                label="TP",
                            ),
                        ],
                        expires_after_bars=None,
                        tag="nzdjpy_median_ma_retrace",
                    )
                )
            elif sell_signal:
                stop_price = close_price * (1.0 + 0.005)
                tp_price = close_price * (1.0 - 0.004)

                orders.append(
                    OrderIntent(
                        decision_bar=h1.index[i],
                        direction=-1,
                        entry="market",
                        entry_price=None,
                        stop=StopRule(
                            price=stop_price,
                            move_to_breakeven_on=None,
                            breakeven_offset_pips=0.0,
                        ),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="take_profit",
                                price=tp_price,
                                label="TP",
                            ),
                        ],
                        expires_after_bars=None,
                        tag="nzdjpy_median_ma_retrace",
                    )
                )

        return orders
