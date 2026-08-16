from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Mapping, Sequence, List

from src.layer0.strategies.causal_structure import (
    last_n_confirmed_highs,
    last_n_confirmed_lows,
)
from src.layer0.strategies.contract_v2 import (
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)
from src.layer0.data_access.indicators import ema, atr


class PrecisionSwing(StrategyV2):
    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="precision_swing",
            name="precision_swing",
            version="1.0.0",
            author="wave2",
            hypothesis="When four independent trend/momentum lenses — price vs. a fast/slow EMA pair, the EMA pair's own ordering, the Parabolic SAR's trailing point, and a detrended oscillator — all agree on direction on the H4 frame, the market is in a persistent institutional-order-flow regime rather than noise, and continuation is more likely than reversal.",
            granularities=["H4"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="H4",
            context_granularities=(),
            simulate_on="H1",
            source_row=10,
            source_url="https://www.forexstrategiesresources.com/trend-following-forex-strategies-ii/214-precision-swing-strategy/",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["ema", "atr", "confirmed_swing_points"]

    @property
    def warmup_bars(self) -> int:
        return 55

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h4 = frames["H4"]

        close = h4["Close"].to_numpy(dtype=float)
        high = h4["High"].to_numpy(dtype=float)
        low = h4["Low"].to_numpy(dtype=float)

        ema14 = ema(h4["Close"], 14).to_numpy(dtype=float)
        ema34 = ema(h4["Close"], 34).to_numpy(dtype=float)
        atr14 = atr(h4["High"], h4["Low"], h4["Close"], 14).to_numpy(dtype=float)

        # Swings
        highs = last_n_confirmed_highs(h4["High"], h4["Low"], n=1, period=5)
        lows = last_n_confirmed_lows(h4["High"], h4["Low"], n=1, period=5)
        level_high = highs["level_1"].to_numpy(dtype=float)
        level_low = lows["level_1"].to_numpy(dtype=float)

        # Private PSAR
        psar = np.full(len(h4), np.nan)
        if len(h4) > 1:
            if close[1] >= close[0]:
                tdir = 1
                cur_sar = low[0]
                ep = high[1]
            else:
                tdir = -1
                cur_sar = high[0]
                ep = low[1]
            af = 0.02

            for t in range(2, len(h4)):
                # 1. SAR[t]
                sar_t = cur_sar + af * (ep - cur_sar)

                # 2. Clamp
                if tdir == 1:
                    sar_t = min(sar_t, low[t - 1], low[t - 2])
                else:
                    sar_t = max(sar_t, high[t - 1], high[t - 2])

                # 3. Reversal test
                if tdir == 1 and low[t] < sar_t:
                    tdir = -1
                    sar_t = ep
                    ep = low[t]
                    af = 0.02
                elif tdir == -1 and high[t] > sar_t:
                    tdir = 1
                    sar_t = ep
                    ep = high[t]
                    af = 0.02
                else:
                    # 4. No reversal
                    if tdir == 1:
                        if high[t] > ep:
                            ep = high[t]
                            af = min(af + 0.02, 0.02)
                    else:
                        if low[t] < ep:
                            ep = low[t]
                            af = min(af + 0.02, 0.02)

                psar[t] = sar_t
                cur_sar = sar_t

        # Private DPO
        # DPO[t] = Close[t-11] - SMA(Close, 21)[t] = close.shift(11) - close.rolling(21).mean()
        shifted_close = h4["Close"].shift(11)
        sma21 = h4["Close"].rolling(21).mean()
        dpo = (shifted_close - sma21).to_numpy(dtype=float)

        orders: List[OrderIntent] = []
        prev_long_cond = False
        prev_short_cond = False

        for t in range(self.warmup_bars, len(h4)):
            # Long conditions
            long_cond = (
                close[t] > ema14[t]
                and close[t] > ema34[t]
                and ema14[t] > ema34[t]
                and psar[t] < low[t]
                and dpo[t] > 0
                and dpo[t] >= 0.25 * atr14[t]
                and not np.isnan(level_low[t])
                and level_low[t] < close[t]
            )

            # Short conditions
            short_cond = (
                close[t] < ema14[t]
                and close[t] < ema34[t]
                and ema14[t] < ema34[t]
                and psar[t] > high[t]
                and dpo[t] < 0
                and dpo[t] <= -0.25 * atr14[t]
                and not np.isnan(level_high[t])
                and level_high[t] > close[t]
            )

            if long_cond and not prev_long_cond:
                d = close[t]
                sl_level = float(level_low[t])
                tp = d + 1.25 * (d - sl_level)
                orders.append(
                    OrderIntent(
                        decision_bar=h4.index[t],
                        direction=1,
                        entry="market",
                        entry_price=None,
                        stop=StopRule(price=sl_level),
                        exits=[
                            ExitLeg(
                                fraction=1.0, kind="take_profit", price=tp, label="TP1"
                            )
                        ],
                        expires_after_bars=None,
                        tag="precision_swing",
                    )
                )

            elif short_cond and not prev_short_cond:
                d = close[t]
                sl_level = float(level_high[t])
                tp = d - 1.25 * (sl_level - d)
                orders.append(
                    OrderIntent(
                        decision_bar=h4.index[t],
                        direction=-1,
                        entry="market",
                        entry_price=None,
                        stop=StopRule(price=sl_level),
                        exits=[
                            ExitLeg(
                                fraction=1.0, kind="take_profit", price=tp, label="TP1"
                            )
                        ],
                        expires_after_bars=None,
                        tag="precision_swing",
                    )
                )

            prev_long_cond = long_cond
            prev_short_cond = short_cond

        return orders
