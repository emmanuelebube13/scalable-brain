"""Advanced OutSide with HMA and Klinger Forex Swing strategy."""

from __future__ import annotations

from typing import List, Mapping, Sequence

import numpy as np
import pandas as pd

from ..contract_v2 import ExitLeg, OrderIntent, StopRule, StrategyMetadataV2, StrategyV2


def _wma(series: pd.Series, period: int) -> pd.Series:
    weights = np.arange(1, period + 1)
    return series.rolling(period).apply(
        lambda x: np.dot(x, weights) / weights.sum(), raw=True
    )


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=True).mean()


def _hma(series: pd.Series, period: int) -> pd.Series:
    half_period = int(np.floor(period / 2))
    sqrt_period = int(np.floor(np.sqrt(period)))
    w1 = _wma(series, half_period)
    w2 = _wma(series, period)
    raw = 2 * w1 - w2
    return _wma(raw, sqrt_period)


class OutsideHmaKlinger(StrategyV2):
    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="outside_hma_klinger",
            name="Advanced OutSide with HMA and Klinger Forex Swing strategy",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "An outside bar that engulfs the prior bar's entire range and then closes bullish is a two-sided liquidity sweep resolved in favour of buyers: both sides' stops have been triggered, the losing side is trapped, and the bar's close reveals which side won the auction. Requiring price above the Hull MA (a low-lag trend proxy) restricts entries to the direction of the prevailing multi-day drift, and requiring the Klinger oscillator positive demands that tick-activity flow — a proxy for real volume flow — confirms that participation, not just price, supports the move. (The short side mirrors this on inside bars — see §10, row 3, for the documented asymmetry.)"
            ),
            granularities=["H4"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="H4",
            context_granularities=(),
            simulate_on="H1",
            source_row=20,
            source_url="https://www.tradingview.com/script/v5vo0vNc-Advanced-OutSide-with-HMA-and-Klinger-Forex-Swing-strategy/",
        )

    @property
    def required_indicators(self) -> List[str]:
        return []

    @property
    def warmup_bars(self) -> int:
        return 60

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h4 = frames["H4"]

        high = h4["High"].to_numpy(dtype=float)
        low = h4["Low"].to_numpy(dtype=float)
        close = h4["Close"].to_numpy(dtype=float)
        open_ = h4["Open"].to_numpy(dtype=float)
        volume = h4["Volume"].to_numpy(dtype=float)

        close_s = h4["Close"]
        prev_close_s = close_s.shift(1)

        # Signed volume: SV[t] = +Volume[t] if Close[t] >= Close[t-1], else -Volume[t]
        sv = pd.Series(
            np.where(close_s >= prev_close_s, volume, -volume), index=h4.index
        )

        # KVO = ema(SV, 34) - ema(SV, 55)
        kvo = _ema(sv, 34) - _ema(sv, 55)
        kvo_np = kvo.to_numpy(dtype=float)

        # HMA(27)
        hma = _hma(close_s, 27)
        hma_np = hma.to_numpy(dtype=float)

        orders: List[OrderIntent] = []
        for i in range(self.warmup_bars, len(h4)):
            # Conditions long
            long_cond = False
            # 1. Outside bar: High[t] > High[t-1] AND Low[t] < Low[t-1]
            if high[i] > high[i - 1] and low[i] < low[i - 1]:
                # 2. Bullish close
                if close[i] > open_[i]:
                    # 3. KVO > 0
                    if not np.isnan(kvo_np[i]) and kvo_np[i] > 0:
                        # 4. Close[t] > HMA[t]
                        if not np.isnan(hma_np[i]) and close[i] > hma_np[i]:
                            long_cond = True

            # Conditions short
            short_cond = False
            # 1. Inside bar: High[t] < High[t-1] AND Low[t] > Low[t-1]
            if high[i] < high[i - 1] and low[i] > low[i - 1]:
                # 2. Bearish close
                if close[i] < open_[i]:
                    # 3. KVO < 0
                    if not np.isnan(kvo_np[i]) and kvo_np[i] < 0:
                        # 4. Close[t] < HMA[t]
                        if not np.isnan(hma_np[i]) and close[i] < hma_np[i]:
                            short_cond = True

            if long_cond:
                a = close[i]
                sl_long = a * 0.9880
                tp_long = a * 1.0060

                orders.append(
                    OrderIntent(
                        decision_bar=h4.index[i],
                        direction=1,
                        entry="market",
                        entry_price=None,
                        stop=StopRule(
                            price=sl_long,
                            move_to_breakeven_on=None,
                            breakeven_offset_pips=0.0,
                        ),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="take_profit",
                                price=tp_long,
                                label="TP1",
                            )
                        ],
                        expires_after_bars=None,
                        tag="outside_hma_klinger_long",
                    )
                )
            elif short_cond:
                a = close[i]
                sl_short = a * 1.0150
                tp_short = a * 0.9925

                orders.append(
                    OrderIntent(
                        decision_bar=h4.index[i],
                        direction=-1,
                        entry="market",
                        entry_price=None,
                        stop=StopRule(
                            price=sl_short,
                            move_to_breakeven_on=None,
                            breakeven_offset_pips=0.0,
                        ),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="take_profit",
                                price=tp_short,
                                label="TP1",
                            )
                        ],
                        expires_after_bars=None,
                        tag="outside_hma_klinger_short",
                    )
                )

        return orders
