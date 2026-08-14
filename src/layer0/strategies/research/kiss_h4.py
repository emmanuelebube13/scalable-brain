import numpy as np
import pandas as pd
from typing import List, Sequence, Mapping

from src.layer0.strategies.contract_v2 import (
    StrategyV2,
    StrategyMetadataV2,
    OrderIntent,
    StopRule,
    ExitLeg,
    Direction,
)
from src.layer0.data_access.indicators import atr, macd, get_pip_value
from src.layer0.strategies.causal_structure import (
    last_n_confirmed_highs,
    last_n_confirmed_lows,
)


def _pip_size_from_price(price: float) -> float:
    pair = "USD_JPY" if price >= 20.0 else "EUR_USD"
    return float(get_pip_value(pair))


def _tp_from_price(price: float) -> float:
    if price >= 20.0:
        return 75.0
    if price > 1.15:
        return 75.0
    return 50.0


class KissH4(StrategyV2):
    # Extracted parameters to allow shrinking in test fixtures
    LWMA_PERIOD = 20
    ATR_PERIOD = 14
    MACD_FAST = 24
    MACD_SLOW = 52
    MACD_SIGNAL = 18
    SWING_PERIOD = 5
    SWING_COUNT = 2

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="kiss_h4",
            name="4H KISS",
            version="1.0.0",
            author="forexstrategiesresources",
            hypothesis="In an established H4 trend, pullbacks to a rising/falling 20 LWMA attract trend followers. PA signals + MACD filter out reversals.",
            granularities=["H4"],
            pairs=["GBP_USD", "EUR_JPY", "GBP_JPY", "EUR_USD", "AUD_USD"],
            primary_granularity="H4",
            simulate_on="H1",
            source_url="https://www.forexstrategiesresources.com/trend-following-forex-strategies/90-4h-kiss/",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["atr", "macd", "confirmed_swing_points"]

    @property
    def warmup_bars(self) -> int:
        return 100

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h4 = frames[self.metadata.primary_granularity]
        n = len(h4)
        if n < self.warmup_bars:
            return []

        open_s = h4["Open"].to_numpy(dtype=float)
        high_s = h4["High"].to_numpy(dtype=float)
        low_s = h4["Low"].to_numpy(dtype=float)
        close_s = h4["Close"].to_numpy(dtype=float)

        weights = np.arange(1, self.LWMA_PERIOD + 1, dtype=float)
        weight_sum = weights.sum()
        lwma_s = (
            h4["Close"]
            .rolling(self.LWMA_PERIOD)
            .apply(lambda x: np.dot(x, weights) / weight_sum, raw=True)
            .to_numpy(dtype=float)
        )

        atr_s = atr(h4["High"], h4["Low"], h4["Close"], self.ATR_PERIOD).to_numpy(
            dtype=float
        )

        _, _, hist_series = macd(
            h4["Close"],
            fast=self.MACD_FAST,
            slow=self.MACD_SLOW,
            signal=self.MACD_SIGNAL,
        )
        hist_s = hist_series.to_numpy(dtype=float)

        sh = last_n_confirmed_highs(
            h4["High"], h4["Low"], n=self.SWING_COUNT, period=self.SWING_PERIOD
        ).to_numpy()
        sl = last_n_confirmed_lows(
            h4["High"], h4["Low"], n=self.SWING_COUNT, period=self.SWING_PERIOD
        ).to_numpy()

        orders: List[OrderIntent] = []

        start_idx = max(self.warmup_bars, self.LWMA_PERIOD + 1)
        for i in range(start_idx, n):
            if not (
                np.isfinite(lwma_s[i])
                and np.isfinite(lwma_s[i - 1])
                and np.isfinite(atr_s[i])
                and np.isfinite(atr_s[i - 1])
                and np.isfinite(hist_s[i])
                and np.isfinite(hist_s[i - 1])
            ):
                continue

            O_t, H_t, L_t, C_t = open_s[i], high_s[i], low_s[i], close_s[i]
            O_t1, H_t1, L_t1, C_t1 = (
                open_s[i - 1],
                high_s[i - 1],
                low_s[i - 1],
                close_s[i - 1],
            )

            lwma_t, lwma_t1 = lwma_s[i], lwma_s[i - 1]
            atr_t = atr_s[i]
            hist_t, hist_t1 = hist_s[i], hist_s[i - 1]

            recent_sh, prior_sh = sh[i, 0], sh[i, 1]
            recent_sl, prior_sl = sl[i, 0], sl[i, 1]

            pip = _pip_size_from_price(C_t)
            tol = 0.25 * atr_t
            body_t = abs(C_t - O_t)
            lower_wick_t = min(O_t, C_t) - L_t
            upper_wick_t = H_t - max(O_t, C_t)

            # LONG
            uptrend = (
                not np.isnan(recent_sh)
                and not np.isnan(prior_sh)
                and recent_sh > prior_sh
                and not np.isnan(recent_sl)
                and not np.isnan(prior_sl)
                and recent_sl > prior_sl
            )
            rising_lwma = lwma_t > lwma_t1
            support = (L_t <= lwma_t + tol) and (C_t > lwma_t)

            bull_engulfing = (
                (C_t > O_t) and (C_t1 < O_t1) and (O_t <= C_t1) and (C_t >= O_t1)
            )
            bull_pin_bar = (
                (C_t > O_t)
                and (lower_wick_t >= 2 * body_t)
                and (upper_wick_t <= 0.5 * lower_wick_t)
                and ((H_t - L_t) >= tol)
            )
            bull_tweezer = (
                (C_t1 < O_t1) and (C_t > O_t) and (abs(L_t - L_t1) <= 0.1 * atr_t)
            )
            bull_pa = bull_engulfing or bull_pin_bar or bull_tweezer
            macd_up = (hist_t > hist_t1) and (hist_t > 0)

            if uptrend and rising_lwma and support and bull_pa and macd_up:
                stop_price = C_t - 100 * pip
                tp_dist = _tp_from_price(C_t) * pip
                tp_price = C_t + tp_dist

                orders.append(
                    OrderIntent(
                        decision_bar=h4.index[i],
                        direction=1,
                        entry="market",
                        entry_price=None,
                        decision_close=C_t,
                        stop=StopRule(price=stop_price),
                        exits=[
                            ExitLeg(
                                fraction=0.5,
                                kind="take_profit",
                                price=tp_price,
                                label="TP1",
                            ),
                            ExitLeg(fraction=0.5, kind="time", bars=12, label="TIME1"),
                        ],
                        expires_after_bars=None,
                        strategy_id=self.strategy_id,
                    )
                )
                continue

            # SHORT
            downtrend = (
                not np.isnan(recent_sh)
                and not np.isnan(prior_sh)
                and recent_sh < prior_sh
                and not np.isnan(recent_sl)
                and not np.isnan(prior_sl)
                and recent_sl < prior_sl
            )
            falling_lwma = lwma_t < lwma_t1
            resistance = (H_t >= lwma_t - tol) and (C_t < lwma_t)

            bear_engulfing = (
                (C_t < O_t) and (C_t1 > O_t1) and (O_t >= C_t1) and (C_t <= O_t1)
            )
            bear_pin_bar = (
                (C_t < O_t)
                and (upper_wick_t >= 2 * body_t)
                and (lower_wick_t <= 0.5 * upper_wick_t)
                and ((H_t - L_t) >= tol)
            )
            bear_tweezer = (
                (C_t1 > O_t1) and (C_t < O_t) and (abs(H_t - H_t1) <= 0.1 * atr_t)
            )
            bear_pa = bear_engulfing or bear_pin_bar or bear_tweezer
            macd_down = (hist_t < hist_t1) and (hist_t < 0)

            if downtrend and falling_lwma and resistance and bear_pa and macd_down:
                stop_price = C_t + 100 * pip
                tp_dist = _tp_from_price(C_t) * pip
                tp_price = C_t - tp_dist

                orders.append(
                    OrderIntent(
                        decision_bar=h4.index[i],
                        direction=-1,
                        entry="market",
                        entry_price=None,
                        decision_close=C_t,
                        stop=StopRule(price=stop_price),
                        exits=[
                            ExitLeg(
                                fraction=0.5,
                                kind="take_profit",
                                price=tp_price,
                                label="TP1",
                            ),
                            ExitLeg(fraction=0.5, kind="time", bars=12, label="TIME1"),
                        ],
                        expires_after_bars=None,
                        strategy_id=self.strategy_id,
                    )
                )

        return orders
