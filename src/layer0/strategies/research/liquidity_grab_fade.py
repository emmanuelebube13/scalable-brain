"""
liquidity_grab_fade strategy

Source: row 46 of forex_swing_strategies.csv
"""

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
from ...data_access.indicators import get_pip_value


class LiquidityGrabFade(StrategyV2):
    """Liquidity Grab Fade"""

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="liquidity_grab_fade",
            name="Liquidity Grab Fade",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "In a trending market, stop orders cluster just beyond obvious structural zones "
                "— in this strategy's framing, the far edge of an order block — and large participants "
                "deliberately push price through those clusters to source counter-side liquidity before "
                "the trend resumes. A price excursion through the order block that fails to hold (a "
                '"liquidity grab") is therefore evidence of forced weak-hand liquidation, not genuine '
                "reversal: once the grab completes and price closes back beyond the order block's near "
                "edge, the path of least resistance is again with the trend. Entering on that recapture "
                "close buys/sells the exact moment the trapped breakout traders must unwind, with "
                "invalidation defined by the grab extreme itself."
            ),
            granularities=["H4"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="H4",
            context_granularities=(),
            simulate_on="H1",
            source_row=46,
            source_url="https://howtotrade.com/blog/liquidity-grab/",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["confirmed_swing_points"]

    @property
    def warmup_bars(self) -> int:
        return 30

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h4 = frames["H4"]
        pip = float(get_pip_value(self.metadata.pairs[0]))

        high = h4["High"]
        low = h4["Low"]
        close = h4["Close"]
        open_ = h4["Open"]
        index = h4.index

        swing_highs, swing_lows = confirmed_swing_points(high, low, period=5)
        sh_vals = swing_highs.to_numpy(dtype=float)
        sl_vals = swing_lows.to_numpy(dtype=float)

        highs_n1 = last_n_confirmed_highs(high, low, n=1, period=5)
        lows_n1 = last_n_confirmed_lows(high, low, n=1, period=5)

        csh_arr = highs_n1["level_1"].to_numpy(dtype=float)
        csl_arr = lows_n1["level_1"].to_numpy(dtype=float)

        high_arr = high.to_numpy(dtype=float)
        low_arr = low.to_numpy(dtype=float)
        close_arr = close.to_numpy(dtype=float)
        open_arr = open_.to_numpy(dtype=float)

        orders: List[OrderIntent] = []
        confirmed_highs_list: List[float] = []
        confirmed_lows_list: List[float] = []

        trend_state = 0
        episode_b = -1
        ob_high = np.nan
        ob_low = np.nan
        grab_j0 = -1
        grab_extreme = np.nan

        for i in range(self.warmup_bars, len(h4)):
            if not np.isnan(sh_vals[i]):
                confirmed_highs_list.append(sh_vals[i])
            if not np.isnan(sl_vals[i]):
                confirmed_lows_list.append(sl_vals[i])

            prev_csh = csh_arr[i - 1]
            prev_csl = csl_arr[i - 1]

            is_bullish_bos = (
                close_arr[i] > prev_csh if not np.isnan(prev_csh) else False
            )
            is_bearish_bos = (
                close_arr[i] < prev_csl if not np.isnan(prev_csl) else False
            )

            if is_bullish_bos:
                trend_state = 1
                episode_b = i
                start_j = max(0, i - 20)
                ob_j = -1
                for j in range(i - 1, start_j - 1, -1):
                    if close_arr[j] < open_arr[j]:
                        ob_j = j
                        break
                if ob_j != -1:
                    ob_high = high_arr[ob_j]
                    ob_low = low_arr[ob_j]
                else:
                    ob_high = np.nan
                    ob_low = np.nan
                grab_j0 = -1
                grab_extreme = np.nan
                continue

            elif is_bearish_bos:
                trend_state = -1
                episode_b = i
                start_j = max(0, i - 20)
                ob_j = -1
                for j in range(i - 1, start_j - 1, -1):
                    if close_arr[j] > open_arr[j]:
                        ob_j = j
                        break
                if ob_j != -1:
                    ob_high = high_arr[ob_j]
                    ob_low = low_arr[ob_j]
                else:
                    ob_high = np.nan
                    ob_low = np.nan
                grab_j0 = -1
                grab_extreme = np.nan
                continue

            if trend_state == 1 and not np.isnan(ob_high):
                if grab_j0 == -1:
                    if i >= episode_b + 1:
                        if low_arr[i] < ob_low:
                            grab_j0 = i
                            grab_extreme = low_arr[i]
                        elif i - episode_b >= 24:
                            ob_high = np.nan
                            ob_low = np.nan

                if grab_j0 != -1:
                    if i > grab_j0:
                        grab_extreme = min(grab_extreme, low_arr[i])

                    if i >= grab_j0 + 1:
                        if close_arr[i] > ob_high:
                            valid_highs = [
                                h for h in confirmed_highs_list if h > close_arr[i]
                            ]
                            tp_level = min(valid_highs) if valid_highs else np.nan

                            if not np.isnan(tp_level):
                                stop_level = grab_extreme - 4.0 * pip
                                if stop_level < close_arr[i]:
                                    orders.append(
                                        OrderIntent(
                                            decision_bar=index[i],
                                            direction=1,
                                            entry="market",
                                            entry_price=None,
                                            stop=StopRule(price=stop_level),
                                            exits=[
                                                ExitLeg(
                                                    fraction=1.0,
                                                    kind="take_profit",
                                                    price=tp_level,
                                                    label="TP1",
                                                )
                                            ],
                                            expires_after_bars=None,
                                            tag="liquidity_grab_fade_long",
                                        )
                                    )
                            ob_high = np.nan
                            ob_low = np.nan
                            grab_j0 = -1

            elif trend_state == -1 and not np.isnan(ob_low):
                if grab_j0 == -1:
                    if i >= episode_b + 1:
                        if high_arr[i] > ob_high:
                            grab_j0 = i
                            grab_extreme = high_arr[i]
                        elif i - episode_b >= 24:
                            ob_high = np.nan
                            ob_low = np.nan

                if grab_j0 != -1:
                    if i > grab_j0:
                        grab_extreme = max(grab_extreme, high_arr[i])

                    if i >= grab_j0 + 1:
                        if close_arr[i] < ob_low:
                            valid_lows = [
                                l for l in confirmed_lows_list if l < close_arr[i]
                            ]
                            tp_level = max(valid_lows) if valid_lows else np.nan

                            if not np.isnan(tp_level):
                                stop_level = grab_extreme + 4.0 * pip
                                if stop_level > close_arr[i]:
                                    orders.append(
                                        OrderIntent(
                                            decision_bar=index[i],
                                            direction=-1,
                                            entry="market",
                                            entry_price=None,
                                            stop=StopRule(price=stop_level),
                                            exits=[
                                                ExitLeg(
                                                    fraction=1.0,
                                                    kind="take_profit",
                                                    price=tp_level,
                                                    label="TP1",
                                                )
                                            ],
                                            expires_after_bars=None,
                                            tag="liquidity_grab_fade_short",
                                        )
                                    )
                            ob_high = np.nan
                            ob_low = np.nan
                            grab_j0 = -1

        return orders
