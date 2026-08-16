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
from ...data_access.indicators import get_pip_value


class LiquiditySweepOb(StrategyV2):
    """liquidity_sweep_ob strategy from howtotrade."""

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="liquidity_sweep_ob",
            name="Liquidity Sweep Order Block",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "In a trending market, institutional order flow clusters at the origin of a break-of-structure move "
                '(the "order block"), and stop orders accumulate just beyond obvious swing highs/lows ("liquidity"). '
                "Price frequently runs those stops — sweeping the swing level — before resuming the trend, because large "
                "participants need counter-side liquidity to fill size. Entering at the order block only after a confirmed "
                "stop-run therefore buys the trend's continuation at the exact point where weak hands were just forced out, "
                "giving a structural stop location and asymmetric reward. The edge should persist because stop-clustering at "
                "round swing levels is a stable, mechanically driven feature of leveraged FX markets, not a sentiment anomaly."
            ),
            granularities=["H4"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="H4",
            context_granularities=(),
            simulate_on="H1",
            source_row=45,
            source_url="https://howtotrade.com/blog/liquidity-sweep/",
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

        highs = last_n_confirmed_highs(h4["High"], h4["Low"], n=1, period=5)
        lows = last_n_confirmed_lows(h4["High"], h4["Low"], n=1, period=5)

        csh = highs["level_1"].to_numpy(dtype=float)
        csl = lows["level_1"].to_numpy(dtype=float)

        open_arr = h4["Open"].to_numpy(dtype=float)
        high_arr = h4["High"].to_numpy(dtype=float)
        low_arr = h4["Low"].to_numpy(dtype=float)
        close_arr = h4["Close"].to_numpy(dtype=float)

        orders: List[OrderIntent] = []

        trend_state = 0  # 1 = UP, -1 = DOWN, 0 = NONE
        episode_b = -1
        ob_high = np.nan
        ob_low = np.nan
        sweep_occurred = False
        episode_emitted = False

        for t in range(self.warmup_bars, len(h4)):
            csh_prev = csh[t - 1]
            csl_prev = csl[t - 1]

            is_bull_bos = (not np.isnan(csh_prev)) and (close_arr[t] > csh_prev)
            is_bear_bos = (not np.isnan(csl_prev)) and (close_arr[t] < csl_prev)

            if is_bull_bos:
                trend_state = 1
                episode_b = t
                episode_emitted = False
                sweep_occurred = False

                ob_k = -1
                start_j = max(0, t - 20)
                for j in range(t - 1, start_j - 1, -1):
                    if close_arr[j] < open_arr[j]:
                        ob_k = j
                        break

                if ob_k != -1:
                    ob_high = high_arr[ob_k]
                    ob_low = low_arr[ob_k]
                else:
                    ob_high = np.nan
                    ob_low = np.nan

            elif is_bear_bos:
                trend_state = -1
                episode_b = t
                episode_emitted = False
                sweep_occurred = False

                ob_k = -1
                start_j = max(0, t - 20)
                for j in range(t - 1, start_j - 1, -1):
                    if close_arr[j] > open_arr[j]:
                        ob_k = j
                        break

                if ob_k != -1:
                    ob_high = high_arr[ob_k]
                    ob_low = low_arr[ob_k]
                else:
                    ob_high = np.nan
                    ob_low = np.nan

            if trend_state == 0:
                continue

            if np.isnan(ob_high) or np.isnan(ob_low):
                continue

            if episode_emitted:
                continue

            if not sweep_occurred and episode_b != -1 and t > episode_b:
                if trend_state == 1:
                    L = csl[t]
                    if not np.isnan(L) and low_arr[t] < L and close_arr[t] > L:
                        sweep_occurred = True
                elif trend_state == -1:
                    L = csh[t]
                    if not np.isnan(L) and high_arr[t] > L and close_arr[t] < L:
                        sweep_occurred = True

            if not sweep_occurred:
                continue

            if trend_state == 1 and np.isnan(csl[t]):
                continue
            if trend_state == -1 and np.isnan(csh[t]):
                continue

            if trend_state == 1:
                if close_arr[t] > ob_high:
                    entry_price = ob_high
                    stop_price = ob_low - 4.0 * pip

                    l_tp = csh[t]
                    if np.isnan(l_tp) or l_tp <= entry_price:
                        continue

                    risk = entry_price - stop_price
                    reward = l_tp - entry_price
                    if risk <= 0:
                        continue

                    rr = reward / risk
                    if rr < 2.0:
                        continue

                    orders.append(
                        OrderIntent(
                            decision_bar=h4.index[t],
                            direction=1,
                            entry="buy_limit",
                            entry_price=entry_price,
                            stop=StopRule(
                                price=stop_price,
                                move_to_breakeven_on=None,
                                breakeven_offset_pips=0.0,
                            ),
                            exits=[
                                ExitLeg(
                                    fraction=1.0,
                                    kind="take_profit",
                                    price=l_tp,
                                    label="TP1",
                                )
                            ],
                            expires_after_bars=12,
                            tag="liquidity_sweep_ob",
                        )
                    )
                    episode_emitted = True

            elif trend_state == -1:
                if close_arr[t] < ob_low - 1.0 * pip:
                    entry_price = ob_low - 1.0 * pip
                    stop_price = ob_high + 4.0 * pip

                    l_tp = csl[t]
                    if np.isnan(l_tp) or l_tp >= entry_price:
                        continue

                    risk = stop_price - entry_price
                    reward = entry_price - l_tp
                    if risk <= 0:
                        continue

                    rr = reward / risk
                    if rr < 2.0:
                        continue

                    orders.append(
                        OrderIntent(
                            decision_bar=h4.index[t],
                            direction=-1,
                            entry="sell_limit",
                            entry_price=entry_price,
                            stop=StopRule(
                                price=stop_price,
                                move_to_breakeven_on=None,
                                breakeven_offset_pips=0.0,
                            ),
                            exits=[
                                ExitLeg(
                                    fraction=1.0,
                                    kind="take_profit",
                                    price=l_tp,
                                    label="TP1",
                                )
                            ],
                            expires_after_bars=12,
                            tag="liquidity_sweep_ob",
                        )
                    )
                    episode_emitted = True

        return orders
