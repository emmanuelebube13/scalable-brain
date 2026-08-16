from __future__ import annotations

from typing import List, Mapping, Sequence

import numpy as np
import pandas as pd

from ..causal_structure import (
    confirmed_swing_points,
    last_n_confirmed_highs,
    last_n_confirmed_lows,
)
from ..contract_v2 import (
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)
from ...data_access.indicators import macd


class MacdDivergence(StrategyV2):
    """MACD Divergence strategy: Buy lower lows in price with higher lows in MACD."""

    SWING_PERIOD = 5
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="macd_divergence",
            name="MACD Divergence",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "Momentum leads price: when price prints a lower low but the MACD line "
                "prints a higher low, the selling pressure behind the down-leg is genuinely "
                "exhausting — fewer participants are willing to push each successive low — "
                "so the probability of a reversal or deep pullback rises. This should persist "
                "because it rests on a behavioural mechanism (crowd conviction decaying into "
                "the tail of a trend leg, visible in smoothed momentum before it is visible "
                "in price) rather than on a data-mined pattern, and because divergence "
                "failure is slow enough that a stop at the divergence low caps the loss "
                "when the trend instead continues."
            ),
            granularities=["H4"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="H4",
            context_granularities=(),
            simulate_on="H1",
            source_row=24,
            source_url="https://www.earnforex.com/forex-strategy/macd-divergence-strategy",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["macd", "confirmed_swing_points"]

    @property
    def warmup_bars(self) -> int:
        return 60

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h4 = frames["H4"]

        # MACD
        macd_line, _, _ = macd(
            h4["Close"],
            fast=self.MACD_FAST,
            slow=self.MACD_SLOW,
            signal=self.MACD_SIGNAL,
        )
        macd_arr = macd_line.to_numpy(dtype=float)

        # Confirmed swing points (for R* and S* and tracking last 2)
        conf_highs, conf_lows = confirmed_swing_points(
            h4["High"], h4["Low"], period=self.SWING_PERIOD
        )
        conf_highs_arr = conf_highs.to_numpy(dtype=float)
        conf_lows_arr = conf_lows.to_numpy(dtype=float)

        highs = last_n_confirmed_highs(
            h4["High"], h4["Low"], n=2, period=self.SWING_PERIOD
        )
        lows = last_n_confirmed_lows(
            h4["High"], h4["Low"], n=2, period=self.SWING_PERIOD
        )

        l_level_1 = lows["level_1"].to_numpy(dtype=float)
        l_level_2 = lows["level_2"].to_numpy(dtype=float)
        l_occur_1 = lows["occur_1"]
        l_occur_2 = lows["occur_2"]

        h_level_1 = highs["level_1"].to_numpy(dtype=float)
        h_level_2 = highs["level_2"].to_numpy(dtype=float)
        h_occur_1 = highs["occur_1"]
        h_occur_2 = highs["occur_2"]

        close = h4["Close"].to_numpy(dtype=float)
        high = h4["High"].to_numpy(dtype=float)
        low = h4["Low"].to_numpy(dtype=float)

        time_to_idx = {t: i for i, t in enumerate(h4.index)}

        known_highs = set()
        known_lows = set()

        orders: List[OrderIntent] = []

        for t in range(len(h4)):
            if not np.isnan(conf_highs_arr[t]):
                known_highs.add(conf_highs_arr[t])
            if not np.isnan(conf_lows_arr[t]):
                known_lows.add(conf_lows_arr[t])

            if t < self.warmup_bars:
                continue

            # LONG SETUP
            if not (np.isnan(l_level_1[t]) or np.isnan(l_level_2[t])):
                k1 = time_to_idx.get(l_occur_2.iloc[t])
                k2 = time_to_idx.get(l_occur_1.iloc[t])
                if k1 is not None and k2 is not None:
                    c = k2 + self.SWING_PERIOD

                    if c <= t <= c + 10:
                        L1 = l_level_2[t]
                        L2 = l_level_1[t]

                        if L2 < L1:
                            if macd_arr[k2] > macd_arr[k1]:
                                if macd_arr[k1] < 0 and macd_arr[k2] < 0:
                                    if close[t] > high[c]:
                                        # Must be the first close above High[c]
                                        first_trigger = True
                                        for x in range(c + 1, t):
                                            if close[x] > high[c]:
                                                first_trigger = False
                                                break
                                        if first_trigger:
                                            valid_highs = [
                                                h for h in known_highs if h > close[t]
                                            ]
                                            if valid_highs:
                                                r_star = min(valid_highs)
                                                orders.append(
                                                    OrderIntent(
                                                        decision_bar=h4.index[t],
                                                        direction=1,
                                                        entry="market",
                                                        entry_price=None,
                                                        stop=StopRule(price=L2),
                                                        exits=[
                                                            ExitLeg(
                                                                fraction=1.0,
                                                                kind="take_profit",
                                                                price=r_star,
                                                                label="TP1",
                                                            )
                                                        ],
                                                        expires_after_bars=None,
                                                        tag="macd_div_long",
                                                    )
                                                )

            # SHORT SETUP
            if not (np.isnan(h_level_1[t]) or np.isnan(h_level_2[t])):
                j1 = time_to_idx.get(h_occur_2.iloc[t])
                j2 = time_to_idx.get(h_occur_1.iloc[t])
                if j1 is not None and j2 is not None:
                    c = j2 + self.SWING_PERIOD

                    if c <= t <= c + 10:
                        H1 = h_level_2[t]
                        H2 = h_level_1[t]

                        if H2 > H1:
                            if macd_arr[j2] < macd_arr[j1]:
                                if macd_arr[j1] > 0 and macd_arr[j2] > 0:
                                    if close[t] < low[c]:
                                        # Must be the first close below Low[c]
                                        first_trigger = True
                                        for x in range(c + 1, t):
                                            if close[x] < low[c]:
                                                first_trigger = False
                                                break
                                        if first_trigger:
                                            valid_lows = [
                                                l for l in known_lows if l < close[t]
                                            ]
                                            if valid_lows:
                                                s_star = max(valid_lows)
                                                orders.append(
                                                    OrderIntent(
                                                        decision_bar=h4.index[t],
                                                        direction=-1,
                                                        entry="market",
                                                        entry_price=None,
                                                        stop=StopRule(price=H2),
                                                        exits=[
                                                            ExitLeg(
                                                                fraction=1.0,
                                                                kind="take_profit",
                                                                price=s_star,
                                                                label="TP1",
                                                            )
                                                        ],
                                                        expires_after_bars=None,
                                                        tag="macd_div_short",
                                                    )
                                                )

        return orders
