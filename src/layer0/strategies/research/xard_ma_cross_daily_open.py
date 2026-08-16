"""
Xard MA Cross Daily Open strategy.
"""

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
from ...data_access.indicators import get_pip_value, sma


class XardMaCrossDailyOpen(StrategyV2):
    """Xard MA Cross Daily Open Strategy"""

    SMA_FAST = 13
    SMA_SLOW1 = 55
    SMA_SLOW2 = 89
    ADR_PERIOD = 5
    ADR_DISP_THRESHOLD = 0.15
    STOP_BUFFER_PIPS = 5.0
    RR_RATIO = 2.0

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="xard_ma_cross_daily_open",
            name="Xard MA Cross Daily Open",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "A fresh fast/slow moving-average cross on H1, taken only when price has "
                "already established a same-direction displacement of at least 15% of the "
                "average daily range away from the daily open, captures intraday "
                "trend-continuation flow: once the market has committed to one side of the "
                "day's opening reference (the level at which overnight positioning is marked) "
                "with meaningful range behind it, stop-running and session momentum tend to "
                "extend the move further in that direction, so a 2:1 reward:risk target is "
                "reached more often than chance. The edge should persist because daily opens "
                "and MA crosses are universally watched, self-reinforcing reference points for "
                "intraday FX participants, and the 15%-ADR displacement gate filters the "
                "flat-open chop in which MA crosses whipsaw."
            ),
            granularities=["H1"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="H1",
            context_granularities=(),
            simulate_on="H1",
            source_row=26,
            source_url="https://forex-station.com/xard-simple-trend-following-trading-system-t8416709-15170.html",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["sma"]

    @property
    def warmup_bars(self) -> int:
        return 200

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h1 = frames["H1"]
        pip = float(get_pip_value(self.metadata.pairs[0]))

        sma_fast = sma(h1["Close"], self.SMA_FAST)
        sma_slow1 = sma(h1["Close"], self.SMA_SLOW1)
        sma_slow2 = sma(h1["Close"], self.SMA_SLOW2)

        sma_fast_prev = sma_fast.shift(1)
        sma_slow1_prev = sma_slow1.shift(1)
        sma_slow2_prev = sma_slow2.shift(1)

        cross_up_1 = (sma_fast > sma_slow1) & (sma_fast_prev <= sma_slow1_prev)
        cross_up_2 = (sma_fast > sma_slow2) & (sma_fast_prev <= sma_slow2_prev)
        cross_up = cross_up_1 | cross_up_2

        cross_down_1 = (sma_fast < sma_slow1) & (sma_fast_prev >= sma_slow1_prev)
        cross_down_2 = (sma_fast < sma_slow2) & (sma_fast_prev >= sma_slow2_prev)
        cross_down = cross_down_1 | cross_down_2

        # DO and ADR
        df_helper = pd.DataFrame(
            {"trading_day": (h1.index - pd.Timedelta(hours=21)).floor("D")},
            index=h1.index,
        )

        daily_open = h1.groupby(df_helper["trading_day"])["Open"].first()
        do_t_series = df_helper["trading_day"].map(daily_open)

        daily_high = h1.groupby(df_helper["trading_day"])["High"].max()
        daily_low = h1.groupby(df_helper["trading_day"])["Low"].min()
        dr = daily_high - daily_low
        adr_series = dr.shift(1).rolling(self.ADR_PERIOD).mean()
        adr_t_series = df_helper["trading_day"].map(adr_series)

        close = h1["Close"].to_numpy(dtype=float)
        do_t = do_t_series.to_numpy(dtype=float)
        adr_t = adr_t_series.to_numpy(dtype=float)

        cross_up = cross_up.to_numpy(dtype=bool)
        cross_down = cross_down.to_numpy(dtype=bool)

        orders: List[OrderIntent] = []

        for i in range(self.warmup_bars, len(h1)):
            if not (cross_up[i] or cross_down[i]):
                continue

            c = float(close[i])
            daily_open_price = float(do_t[i])
            adr = float(adr_t[i])

            if np.isnan(c) or np.isnan(daily_open_price) or np.isnan(adr) or adr <= 0:
                continue

            disp = (c - daily_open_price) / adr

            # Long entry
            if cross_up[i]:
                if c <= daily_open_price:
                    continue
                if disp < self.ADR_DISP_THRESHOLD:
                    continue

                stop_price = daily_open_price - self.STOP_BUFFER_PIPS * pip
                if stop_price >= c:
                    continue

                risk = c - stop_price
                tp_price = c + self.RR_RATIO * risk

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
                                label="TP1",
                            )
                        ],
                        expires_after_bars=None,
                        tag="xard_long",
                    )
                )

            # Short entry
            if cross_down[i]:
                if c >= daily_open_price:
                    continue
                if disp > -self.ADR_DISP_THRESHOLD:
                    continue

                stop_price = daily_open_price + self.STOP_BUFFER_PIPS * pip
                if stop_price <= c:
                    continue

                risk = stop_price - c
                tp_price = c - self.RR_RATIO * risk

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
                                label="TP1",
                            )
                        ],
                        expires_after_bars=None,
                        tag="xard_short",
                    )
                )

        return orders
