from __future__ import annotations

from typing import List, Mapping, Sequence

import numpy as np
import pandas as pd

from ..contract_v2 import (
    GRANULARITY_INTERVAL,
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)
from ...data_access.indicators import ema, rsi


class MtfSwingWeeklyPivots(StrategyV2):
    """Trend-aligned pullback entry using D1 regime and H4 EMA pullbacks."""

    D1_EMA_FAST = 50
    D1_EMA_SLOW = 200
    H4_EMA = 21
    H4_RSI = 14
    STOP_WINDOW = 5

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="mtf_swing_weekly_pivots",
            name="MTF Swing Weekly Pivots",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "The edge is a trend-aligned pullback entry: when the daily chart is in an "
                "established regime (price above a rising-stacked EMA50/EMA200), intraday "
                "dips back toward the 21-period EMA are more likely to be profit-taking "
                "pauses than trend reversals, so buying a confirmed bullish rejection candle "
                'at that "value" line with a fixed 1:2 reward-to-risk harvests the behavioural '
                "tendency of trend-following flows to re-enter after shallow retracements. "
                "The daily regime gate exists to keep the strategy out of ranging markets where "
                "EMA pullbacks have no follow-through; persistence rests on the well-documented "
                "medium-term momentum/trend premium in FX majors rather than on any microstructural "
                "quirk that arbitrage would quickly erase."
            ),
            granularities=["H4"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="H4",
            context_granularities=("D1",),
            simulate_on="H1",
            source_row=19,
            source_url="https://www.tradingview.com/script/oXYuZB8v-Swing-Strategy-MTF-with-Auto-SL-TP-Weekly-Pivots/",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["ema", "rsi"]

    @property
    def warmup_bars(self) -> int:
        return 1200

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h4 = frames["H4"]
        d1 = frames["D1"]

        # 1. D1 regime (context)
        d1_ema_50 = ema(d1["Close"], self.D1_EMA_FAST)
        d1_ema_200 = ema(d1["Close"], self.D1_EMA_SLOW)

        d1_trend_up = (d1["Close"] > d1_ema_50) & (d1_ema_50 > d1_ema_200)
        d1_trend_down = (d1["Close"] < d1_ema_50) & (d1_ema_50 < d1_ema_200)

        d1_at_close = pd.DataFrame(
            {
                "trend_up": d1_trend_up.astype(float).to_numpy(),
                "trend_down": d1_trend_down.astype(float).to_numpy(),
            },
            index=d1.index + GRANULARITY_INTERVAL["D1"],
        )

        trend = pd.merge_asof(
            pd.DataFrame(index=h4.index),
            d1_at_close,
            left_index=True,
            right_index=True,
            direction="backward",
        )

        trend_up = trend["trend_up"].to_numpy(dtype=float)
        trend_down = trend["trend_down"].to_numpy(dtype=float)

        # 2. H4 indicators
        h4_ema_21 = ema(h4["Close"], self.H4_EMA).to_numpy(dtype=float)
        h4_rsi_14 = rsi(h4["Close"], self.H4_RSI).to_numpy(dtype=float)

        close = h4["Close"].to_numpy(dtype=float)
        open_ = h4["Open"].to_numpy(dtype=float)
        high = h4["High"].to_numpy(dtype=float)
        low = h4["Low"].to_numpy(dtype=float)

        # Rolling minimum over the last 5 bars (inclusive of current bar)
        s_long = h4["Low"].rolling(self.STOP_WINDOW).min().to_numpy(dtype=float)
        s_short = h4["High"].rolling(self.STOP_WINDOW).max().to_numpy(dtype=float)

        orders: List[OrderIntent] = []

        start_idx = max(self.warmup_bars, self.STOP_WINDOW, 1)

        for t in range(start_idx, len(h4)):
            # LONG RULES
            if trend_up[t] == 1.0 and h4_rsi_14[t] > 50:
                if (
                    0 <= h4_ema_21[t] - close[t]
                    and (h4_ema_21[t] - close[t]) / h4_ema_21[t] < 0.01
                ):
                    if close[t] > open_[t] and close[t] > high[t - 1]:
                        if close[t] - s_long[t] > 0:
                            orders.append(
                                OrderIntent(
                                    decision_bar=h4.index[t],
                                    direction=1,
                                    entry="market",
                                    entry_price=None,
                                    stop=StopRule(
                                        price=float(s_long[t]),
                                    ),
                                    exits=[
                                        ExitLeg(
                                            fraction=1.0,
                                            kind="take_profit",
                                            price=float(
                                                close[t] + 2.0 * (close[t] - s_long[t])
                                            ),
                                            label="TP1",
                                        )
                                    ],
                                    expires_after_bars=None,
                                    tag="long_pullback",
                                )
                            )
                            continue

            # SHORT RULES
            if trend_down[t] == 1.0 and h4_rsi_14[t] < 50:
                if (
                    0 <= close[t] - h4_ema_21[t]
                    and (close[t] - h4_ema_21[t]) / h4_ema_21[t] < 0.01
                ):
                    if close[t] < open_[t] and close[t] < low[t - 1]:
                        if s_short[t] - close[t] > 0:
                            orders.append(
                                OrderIntent(
                                    decision_bar=h4.index[t],
                                    direction=-1,
                                    entry="market",
                                    entry_price=None,
                                    stop=StopRule(
                                        price=float(s_short[t]),
                                    ),
                                    exits=[
                                        ExitLeg(
                                            fraction=1.0,
                                            kind="take_profit",
                                            price=float(
                                                close[t] - 2.0 * (s_short[t] - close[t])
                                            ),
                                            label="TP1",
                                        )
                                    ],
                                    expires_after_bars=None,
                                    tag="short_pullback",
                                )
                            )

        return orders
