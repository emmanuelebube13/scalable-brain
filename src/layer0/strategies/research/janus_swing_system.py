import numpy as np
import pandas as pd
from typing import List, Sequence, Mapping

from ..contract_v2 import (
    StrategyV2,
    StrategyMetadataV2,
    OrderIntent,
    StopRule,
    ExitLeg,
)
from ...data_access.indicators import get_pip_value
from ..causal_structure import (
    last_n_confirmed_highs,
    last_n_confirmed_lows,
)


def _pip_size_from_price(price: float) -> float:
    pair = "USD_JPY" if price >= 20.0 else "EUR_USD"
    return float(get_pip_value(pair))


class JanusSwingSystem(StrategyV2):
    SWING_PERIOD = 5

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="janus_swing_system",
            name="Forex Swing System",
            version="1.0.0",
            author="forexstrategiesresources",
            hypothesis="After a multi-day decline into a well-tested demand zone, a strong-bodied bullish day (a 'straight bar' closing in its upper half) marks the point where momentum sellers are exhausted and value buyers defending the level take control; entering on a retracement to that day's midpoint captures the mean-reversion swing back away from support.",
            granularities=["D1"],
            pairs=[
                "EUR_USD",
                "EUR_CAD",
                "EUR_AUD",
                "EUR_JPY",
                "AUD_USD",
                "AUD_NZD",
                "USD_CAD",
                "GBP_USD",
                "GBP_JPY",
                "USD_JPY",
                "NZD_USD",
            ],
            primary_granularity="D1",
            simulate_on="H1",
            source_url="https://www.forexstrategiesresources.com/trend-following-forex-strategies/109-forex-swing-system/",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["confirmed_swing_points"]

    @property
    def warmup_bars(self) -> int:
        return 100

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        d1 = frames[self.metadata.primary_granularity]
        n = len(d1)
        if n < self.warmup_bars:
            return []

        open_s = d1["Open"].to_numpy(dtype=float)
        high_s = d1["High"].to_numpy(dtype=float)
        low_s = d1["Low"].to_numpy(dtype=float)
        close_s = d1["Close"].to_numpy(dtype=float)

        sh = last_n_confirmed_highs(
            d1["High"], d1["Low"], n=1, period=self.SWING_PERIOD
        ).to_numpy()
        sl = last_n_confirmed_lows(
            d1["High"], d1["Low"], n=1, period=self.SWING_PERIOD
        ).to_numpy()

        orders: List[OrderIntent] = []
        last_emission_idx = -100

        for i in range(self.warmup_bars, n):
            O_t, H_t, L_t, C_t = open_s[i], high_s[i], low_s[i], close_s[i]
            mid_t = (H_t + L_t) / 2.0

            C_t1 = close_s[i - 1]
            C_t2 = close_s[i - 2]
            C_t3 = close_s[i - 3]
            C_t4 = close_s[i - 4]

            pip = _pip_size_from_price(C_t)

            # LONG rules
            bullish_straight = (O_t > mid_t) and (C_t > O_t)
            three_down = (C_t1 < C_t2) and (C_t2 < C_t3) and (C_t3 < C_t4)
            L_sl = sl[i, 0]
            at_support = not np.isnan(L_sl) and abs(L_t - L_sl) <= 10.0 * pip

            can_emit = (i - last_emission_idx) >= 4

            if can_emit and bullish_straight and three_down and at_support:
                stop_price = L_t - 5.0 * pip
                risk = mid_t - stop_price
                risk_pips = risk / pip

                orders.append(
                    OrderIntent(
                        decision_bar=d1.index[i],
                        direction=1,
                        entry="buy_limit",
                        entry_price=mid_t,
                        decision_close=C_t,
                        stop=StopRule(price=stop_price),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="trailing",
                                pips=risk_pips,
                                label="TRAIL",
                            )
                        ],
                        expires_after_bars=72,
                        strategy_id=self.strategy_id,
                    )
                )
                last_emission_idx = i
                continue

            # SHORT rules
            bearish_straight = (O_t < mid_t) and (C_t < O_t)
            three_up = (C_t1 > C_t2) and (C_t2 > C_t3) and (C_t3 > C_t4)
            L_sh = sh[i, 0]
            at_resistance = not np.isnan(L_sh) and abs(H_t - L_sh) <= 10.0 * pip

            if can_emit and bearish_straight and three_up and at_resistance:
                stop_price = H_t + 5.0 * pip
                risk = stop_price - mid_t
                risk_pips = risk / pip

                orders.append(
                    OrderIntent(
                        decision_bar=d1.index[i],
                        direction=-1,
                        entry="sell_limit",
                        entry_price=mid_t,
                        decision_close=C_t,
                        stop=StopRule(price=stop_price),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="trailing",
                                pips=risk_pips,
                                label="TRAIL",
                            )
                        ],
                        expires_after_bars=72,
                        strategy_id=self.strategy_id,
                    )
                )
                last_emission_idx = i

        return orders
