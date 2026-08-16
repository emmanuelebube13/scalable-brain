from __future__ import annotations

from typing import List, Mapping, Sequence

import numpy as np
import pandas as pd

from ..causal_structure import last_n_confirmed_highs, last_n_confirmed_lows
from ..contract_v2 import (
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)
from ...data_access.indicators import atr


class PinbarKeyLevel50pct(StrategyV2):
    """Pin-bar key level 50% retracement strategy."""

    SWING_PERIOD = 5
    ATR_PERIOD = 14
    CONFLUENCE_ATR_MULTIPLIER = 0.25
    STOP_ATR_MULTIPLIER = 0.10
    EXPIRY_BARS = 24

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="pinbar_key_level_50pct",
            name="Pinbar Key Level 50% Retracement",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                'A long-tailed rejection candle ("pin bar") printing at a well-tested horizontal '
                "support or resistance level signals that larger participants aggressively absorbed one "
                "side of the market within a single day, leaving the losing side trapped; the edge persists "
                "because trapped traders must exit (fueling the reversal) and because the 50%-retracement "
                "limit entry buys into the residual stop-run at a discount, converting a visually obvious "
                "pattern into a structurally favourable reward-to-risk profile (minimum 2R) where even a "
                "modest win rate is profitable."
            ),
            granularities=["D1"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="D1",
            context_granularities=(),
            simulate_on="H1",
            source_row=30,
            source_url="https://dailypriceaction.com/blog/forex-pin-bar-trading-strategy/",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["atr", "confirmed_swing_points"]

    @property
    def warmup_bars(self) -> int:
        return 150

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        d1 = frames["D1"]

        highs = last_n_confirmed_highs(
            d1["High"], d1["Low"], n=6, period=self.SWING_PERIOD
        )
        lows = last_n_confirmed_lows(
            d1["High"], d1["Low"], n=6, period=self.SWING_PERIOD
        )

        atr14 = atr(d1["High"], d1["Low"], d1["Close"], self.ATR_PERIOD)

        highs_arr = highs[[f"level_{i}" for i in range(1, 7)]].to_numpy(dtype=float)
        lows_arr = lows[[f"level_{i}" for i in range(1, 7)]].to_numpy(dtype=float)

        o = d1["Open"].to_numpy(dtype=float)
        h = d1["High"].to_numpy(dtype=float)
        l = d1["Low"].to_numpy(dtype=float)
        c = d1["Close"].to_numpy(dtype=float)
        atr_arr = atr14.to_numpy(dtype=float)

        rng = h - l
        body = np.abs(c - o)
        tail_dn = np.minimum(o, c) - l
        tail_up = h - np.maximum(o, c)

        orders: List[OrderIntent] = []
        for i in range(self.warmup_bars, len(d1)):
            if rng[i] <= 0 or np.isnan(atr_arr[i]):
                continue

            entry_price = (h[i] + l[i]) / 2.0

            # Entry Long
            long_cond = (
                tail_dn[i] >= 0.67 * rng[i]
                and body[i] <= 0.33 * rng[i]
                and c[i] >= o[i]
            )

            # Entry Short
            short_cond = (
                tail_up[i] >= 0.67 * rng[i]
                and body[i] <= 0.33 * rng[i]
                and c[i] <= o[i]
            )

            if long_cond:
                confluence_threshold = self.CONFLUENCE_ATR_MULTIPLIER * atr_arr[i]
                valid_lows = lows_arr[i][~np.isnan(lows_arr[i])]
                if len(valid_lows) > 0 and np.any(
                    np.abs(l[i] - valid_lows) <= confluence_threshold
                ):
                    valid_highs = highs_arr[i][~np.isnan(highs_arr[i])]
                    valid_highs = valid_highs[valid_highs > entry_price]
                    if len(valid_highs) > 0:
                        tp = float(np.min(valid_highs))
                        stop = float(l[i] - self.STOP_ATR_MULTIPLIER * atr_arr[i])
                        if stop < entry_price and (tp - entry_price) >= 2.0 * (
                            entry_price - stop
                        ):
                            orders.append(
                                OrderIntent(
                                    decision_bar=d1.index[i],
                                    direction=1,
                                    entry="buy_limit",
                                    entry_price=float(entry_price),
                                    stop=StopRule(price=stop),
                                    exits=[
                                        ExitLeg(
                                            fraction=1.0,
                                            kind="take_profit",
                                            price=tp,
                                            label="TP1",
                                        )
                                    ],
                                    expires_after_bars=self.EXPIRY_BARS,
                                    tag="pinbar_key_level_50pct",
                                )
                            )
                            continue

            if short_cond:
                confluence_threshold = self.CONFLUENCE_ATR_MULTIPLIER * atr_arr[i]
                valid_highs = highs_arr[i][~np.isnan(highs_arr[i])]
                if len(valid_highs) > 0 and np.any(
                    np.abs(h[i] - valid_highs) <= confluence_threshold
                ):
                    valid_lows = lows_arr[i][~np.isnan(lows_arr[i])]
                    valid_lows = valid_lows[valid_lows < entry_price]
                    if len(valid_lows) > 0:
                        tp = float(np.max(valid_lows))
                        stop = float(h[i] + self.STOP_ATR_MULTIPLIER * atr_arr[i])
                        if stop > entry_price and (entry_price - tp) >= 2.0 * (
                            stop - entry_price
                        ):
                            orders.append(
                                OrderIntent(
                                    decision_bar=d1.index[i],
                                    direction=-1,
                                    entry="sell_limit",
                                    entry_price=float(entry_price),
                                    stop=StopRule(price=stop),
                                    exits=[
                                        ExitLeg(
                                            fraction=1.0,
                                            kind="take_profit",
                                            price=tp,
                                            label="TP1",
                                        )
                                    ],
                                    expires_after_bars=self.EXPIRY_BARS,
                                    tag="pinbar_key_level_50pct",
                                )
                            )

        return orders
