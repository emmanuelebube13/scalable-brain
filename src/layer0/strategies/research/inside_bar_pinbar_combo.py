"""inside_bar_pinbar_combo strategy."""

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
from ...data_access.indicators import atr, ema, get_pip_value


class InsideBarPinbarCombo(StrategyV2):
    """Inside bar pinbar combo strategy."""

    EMA_PERIOD = 50
    ATR_PERIOD = 14
    SWING_PERIOD = 5
    RECENCY_WINDOW = 250
    EXPIRY_BARS = 2

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="inside_bar_pinbar_combo",
            name="Inside Bar Pin Bar Combo",
            version="0.1.0",
            author="wave2-fleet",
            hypothesis=(
                "A two-bar exhaustion sequence — an inside bar immediately followed by a pin bar with a "
                "pronounced rejection tail — occurring at a confirmed structural level after an extended "
                "trend leg, marks the point where the final momentum traders are trapped on the wrong "
                "side. Entering on a 50% retracement of the pin bar monetises the post-signal profit-taking "
                "dip of the trapped side before the reversal resumes."
            ),
            granularities=["D1"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="D1",
            context_granularities=(),
            simulate_on="H1",
            source_row=31,
            source_url="https://dailypriceaction.com/blog/forex-pin-bar-trading-strategy/",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["ema", "atr", "confirmed_swing_points"]

    @property
    def warmup_bars(self) -> int:
        return (
            max(self.EMA_PERIOD, self.ATR_PERIOD, self.SWING_PERIOD * 3)
            + self.RECENCY_WINDOW
        )

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        d1 = frames["D1"]

        ema50 = ema(d1["Close"], self.EMA_PERIOD).to_numpy(dtype=float)
        atr14 = atr(d1["High"], d1["Low"], d1["Close"], self.ATR_PERIOD).to_numpy(
            dtype=float
        )

        highs = last_n_confirmed_highs(
            d1["High"], d1["Low"], n=50, period=self.SWING_PERIOD
        )
        lows = last_n_confirmed_lows(
            d1["High"], d1["Low"], n=50, period=self.SWING_PERIOD
        )

        orders: List[OrderIntent] = []
        n_bars = len(d1)

        high = d1["High"].to_numpy(dtype=float)
        low = d1["Low"].to_numpy(dtype=float)
        close = d1["Close"].to_numpy(dtype=float)
        open_ = d1["Open"].to_numpy(dtype=float)

        for i in range(self.warmup_bars, n_bars):
            # We need bar t, t-1, t-2
            t = i
            t_1 = i - 1
            t_2 = i - 2

            # Condition 1: Inside bar at t-1
            if not (high[t_1] <= high[t_2] and low[t_1] >= low[t_2]):
                continue

            r_t = high[t] - low[t]
            if r_t <= 0:
                continue

            lower_tail = min(open_[t], close[t]) - low[t]
            upper_tail = high[t] - max(open_[t], close[t])

            # Check pin bar conditions
            is_bullish_pin = (lower_tail >= 0.60 * r_t) and (upper_tail <= 0.25 * r_t)
            is_bearish_pin = (upper_tail >= 0.60 * r_t) and (lower_tail <= 0.25 * r_t)

            if not (is_bullish_pin or is_bearish_pin):
                continue

            # Condition 3: Close inside the inside bar's range
            if not (low[t_1] <= close[t] <= high[t_1]):
                continue

            is_strong_bullish = (close[t] - low[t]) > 0.60 * r_t
            is_strong_bearish = (high[t] - close[t]) > 0.60 * r_t

            if is_bullish_pin and is_strong_bullish and close[t] < ema50[t]:
                # Bullish setup (Long)
                # Check condition 6: At confirmed support
                found_support = False
                for j in range(1, 51):
                    lvl = (
                        highs[f"level_{j}"].iloc[t]
                        if f"level_{j}" in highs.columns
                        else np.nan
                    )
                    # wait, support is swing low
                    lvl = (
                        lows[f"level_{j}"].iloc[t]
                        if f"level_{j}" in lows.columns
                        else np.nan
                    )
                    if np.isnan(lvl):
                        break

                    occur_ts = lows[f"occur_{j}"].iloc[t]
                    if pd.isnull(occur_ts):
                        break

                    # Calculate how many bars ago the occurrence was
                    occur_idx = d1.index.get_loc(occur_ts)
                    if t - occur_idx <= self.RECENCY_WINDOW:
                        if abs(low[t] - lvl) <= 0.25 * atr14[t]:
                            found_support = True
                            break

                if not found_support:
                    continue

                entry = (high[t] + low[t]) / 2.0

                # Condition 7: Take-profit level exists (swing high above entry)
                tp_level = None
                tp_dist = float("inf")
                for j in range(1, 51):
                    lvl = (
                        highs[f"level_{j}"].iloc[t]
                        if f"level_{j}" in highs.columns
                        else np.nan
                    )
                    if np.isnan(lvl):
                        break

                    occur_ts = highs[f"occur_{j}"].iloc[t]
                    if pd.isnull(occur_ts):
                        break

                    occur_idx = d1.index.get_loc(occur_ts)
                    if t - occur_idx <= self.RECENCY_WINDOW:
                        if lvl > entry:
                            if lvl - entry < tp_dist:
                                tp_dist = lvl - entry
                                tp_level = lvl

                if tp_level is None:
                    continue

                if entry >= close[t]:
                    continue

                stop_price = low[t] - 0.10 * atr14[t]
                if stop_price >= entry:
                    continue

                orders.append(
                    OrderIntent(
                        decision_bar=d1.index[t],
                        direction=1,
                        entry="buy_limit",
                        entry_price=entry,
                        decision_close=close[t],
                        stop=StopRule(price=stop_price),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="take_profit",
                                price=tp_level,
                                label="TP1",
                            )
                        ],
                        expires_after_bars=self.EXPIRY_BARS,
                        tag="inside_bar_pinbar_combo",
                        strategy_id=self.metadata.strategy_id,
                    )
                )

            elif is_bearish_pin and is_strong_bearish and close[t] > ema50[t]:
                # Bearish setup (Short)
                # Check condition 6: At confirmed resistance
                found_resistance = False
                for j in range(1, 51):
                    lvl = (
                        highs[f"level_{j}"].iloc[t]
                        if f"level_{j}" in highs.columns
                        else np.nan
                    )
                    if np.isnan(lvl):
                        break

                    occur_ts = highs[f"occur_{j}"].iloc[t]
                    if pd.isnull(occur_ts):
                        break

                    occur_idx = d1.index.get_loc(occur_ts)
                    if t - occur_idx <= self.RECENCY_WINDOW:
                        if abs(high[t] - lvl) <= 0.25 * atr14[t]:
                            found_resistance = True
                            break

                if not found_resistance:
                    continue

                entry = (high[t] + low[t]) / 2.0

                # Condition 7: Take-profit level exists (swing low below entry)
                tp_level = None
                tp_dist = float("inf")
                for j in range(1, 51):
                    lvl = (
                        lows[f"level_{j}"].iloc[t]
                        if f"level_{j}" in lows.columns
                        else np.nan
                    )
                    if np.isnan(lvl):
                        break

                    occur_ts = lows[f"occur_{j}"].iloc[t]
                    if pd.isnull(occur_ts):
                        break

                    occur_idx = d1.index.get_loc(occur_ts)
                    if t - occur_idx <= self.RECENCY_WINDOW:
                        if lvl < entry:
                            if entry - lvl < tp_dist:
                                tp_dist = entry - lvl
                                tp_level = lvl

                if tp_level is None:
                    continue

                if entry <= close[t]:
                    continue

                stop_price = high[t] + 0.10 * atr14[t]
                if stop_price <= entry:
                    continue

                orders.append(
                    OrderIntent(
                        decision_bar=d1.index[t],
                        direction=-1,
                        entry="sell_limit",
                        entry_price=entry,
                        decision_close=close[t],
                        stop=StopRule(price=stop_price),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="take_profit",
                                price=tp_level,
                                label="TP1",
                            )
                        ],
                        expires_after_bars=self.EXPIRY_BARS,
                        tag="inside_bar_pinbar_combo",
                        strategy_id=self.metadata.strategy_id,
                    )
                )

        return orders
