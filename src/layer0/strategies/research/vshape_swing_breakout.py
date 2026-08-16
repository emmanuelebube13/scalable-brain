"""vshape_swing_breakout strategy."""

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
from ...data_access.indicators import atr, get_pip_value, sma


class VshapeSwingBreakout(StrategyV2):
    """V-shape Swing Breakout strategy."""

    SWING_PERIOD = 5
    WINDOW_SIZE = 20
    ATR_PERIOD = 14
    SMA_PERIOD = 20
    TRAIL_ATR_MULTIPLE = 3.0

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="vshape_swing_breakout",
            name="V-shape Swing Breakout",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "A sharp, V-shaped reversal marks a point where one side of the market was forced to liquidate in a hurry "
                "and the other side absorbed that flow aggressively; the extreme of that flush and the origin of the selloff "
                "become reference levels that subsequent order flow respects. When price later breaks back through the origin "
                "of the flush on a candle that is both unusually large and unusually active, it signals that the absorbing "
                "side has taken control with conviction rather than drift, so continuation in the breakout direction is more "
                "likely than chance. The edge should persist because breakout confirmation (range expansion plus activity "
                "surge) systematically filters out the low-participation pokes that produce most false breakouts — a "
                "behavioural asymmetry (committed vs. uncommitted flows) rather than a data-mined pattern."
            ),
            granularities=["H4"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="H4",
            context_granularities=(),
            simulate_on="H1",
            source_row=33,
            source_url="https://tradingstrategyguides.com/best-breakout-trading-strategy/",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["atr", "sma", "confirmed_swing_points"]

    @property
    def warmup_bars(self) -> int:
        return max(self.ATR_PERIOD, self.SMA_PERIOD, 100)

    def _get_v_legs_and_level(
        self, high: np.ndarray, low: np.ndarray, k: int, is_long: bool
    ):
        if is_long:
            pre_high = np.max(high[k - 5 : k + 1])
            post_high = np.max(high[k + 1 : k + 6])
            down_leg = pre_high - low[k]
            up_leg = post_high - low[k]
            level = pre_high
            return down_leg, up_leg, level
        else:
            pre_low = np.min(low[k - 5 : k + 1])
            post_low = np.min(low[k + 1 : k + 6])
            up_leg = high[k] - pre_low
            down_leg = high[k] - post_low
            level = pre_low
            return up_leg, down_leg, level

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h4 = frames["H4"]
        pip = float(get_pip_value(self.metadata.pairs[0]))

        open_arr = h4["Open"].to_numpy(dtype=float)
        high_arr = h4["High"].to_numpy(dtype=float)
        low_arr = h4["Low"].to_numpy(dtype=float)
        close_arr = h4["Close"].to_numpy(dtype=float)
        vol_arr = h4["Volume"].to_numpy(dtype=float)

        atr_arr = atr(h4["High"], h4["Low"], h4["Close"], self.ATR_PERIOD).to_numpy(
            dtype=float
        )
        body_abs = np.abs(close_arr - open_arr)
        sma_body = sma(pd.Series(body_abs), self.SMA_PERIOD).to_numpy(dtype=float)
        sma_vol = sma(h4["Volume"], self.SMA_PERIOD).to_numpy(dtype=float)

        highs = last_n_confirmed_highs(
            h4["High"], h4["Low"], n=1, period=self.SWING_PERIOD
        )
        lows = last_n_confirmed_lows(
            h4["High"], h4["Low"], n=1, period=self.SWING_PERIOD
        )

        high_occur = highs["occur_1"]
        low_occur = lows["occur_1"]

        orders: List[OrderIntent] = []

        active_long_setup_c = -1
        active_long_k = -1
        active_long_L = np.nan

        active_short_setup_c = -1
        active_short_k = -1
        active_short_L = np.nan

        last_confirmed_low_k = -1
        last_confirmed_high_k = -1

        for i in range(self.warmup_bars, len(h4)):
            ts_low = low_occur.iloc[i]
            if pd.notna(ts_low):
                k = h4.index.get_loc(ts_low)
                if k != last_confirmed_low_k and i == k + self.SWING_PERIOD:
                    last_confirmed_low_k = k
                    if k >= 5:
                        down_leg, up_leg, L = self._get_v_legs_and_level(
                            high_arr, low_arr, k, is_long=True
                        )
                        if down_leg >= 1.5 * atr_arr[k] and up_leg >= 1.0 * atr_arr[k]:
                            active_long_setup_c = i
                            active_long_k = k
                            active_long_L = L

            ts_high = high_occur.iloc[i]
            if pd.notna(ts_high):
                k = h4.index.get_loc(ts_high)
                if k != last_confirmed_high_k and i == k + self.SWING_PERIOD:
                    last_confirmed_high_k = k
                    if k >= 5:
                        up_leg, down_leg, L = self._get_v_legs_and_level(
                            high_arr, low_arr, k, is_long=False
                        )
                        if up_leg >= 1.5 * atr_arr[k] and down_leg >= 1.0 * atr_arr[k]:
                            active_short_setup_c = i
                            active_short_k = k
                            active_short_L = L

            if (
                active_long_setup_c != -1
                and active_long_setup_c <= i <= active_long_setup_c + 19
            ):
                if close_arr[i] > active_long_L:
                    body_signed = close_arr[i] - open_arr[i]
                    if body_signed > 1.5 * sma_body[i]:
                        if vol_arr[i] > sma_vol[i]:
                            stop_price = low_arr[active_long_k] - 1.0 * pip
                            orders.append(
                                OrderIntent(
                                    decision_bar=h4.index[i],
                                    direction=1,
                                    entry="market",
                                    entry_price=None,
                                    stop=StopRule(
                                        price=stop_price,
                                        move_to_breakeven_on=None,
                                        trail_atr_multiple=self.TRAIL_ATR_MULTIPLE,
                                    ),
                                    exits=[
                                        ExitLeg(
                                            fraction=1.0,
                                            kind="trailing",
                                            atr_multiple=self.TRAIL_ATR_MULTIPLE,
                                            label="TRAIL",
                                        )
                                    ],
                                    expires_after_bars=None,
                                    tag="vshape_long",
                                )
                            )
                            active_long_setup_c = -1

            if (
                active_short_setup_c != -1
                and active_short_setup_c <= i <= active_short_setup_c + 19
            ):
                if close_arr[i] < active_short_L:
                    body_signed = open_arr[i] - close_arr[i]
                    if body_signed > 1.5 * sma_body[i]:
                        if vol_arr[i] > sma_vol[i]:
                            stop_price = high_arr[active_short_k] + 1.0 * pip
                            orders.append(
                                OrderIntent(
                                    decision_bar=h4.index[i],
                                    direction=-1,
                                    entry="market",
                                    entry_price=None,
                                    stop=StopRule(
                                        price=stop_price,
                                        move_to_breakeven_on=None,
                                        trail_atr_multiple=self.TRAIL_ATR_MULTIPLE,
                                    ),
                                    exits=[
                                        ExitLeg(
                                            fraction=1.0,
                                            kind="trailing",
                                            atr_multiple=self.TRAIL_ATR_MULTIPLE,
                                            label="TRAIL",
                                        )
                                    ],
                                    expires_after_bars=None,
                                    tag="vshape_short",
                                )
                            )
                            active_short_setup_c = -1

        return orders
