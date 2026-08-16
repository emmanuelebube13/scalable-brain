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
from ...data_access.indicators import atr, get_pip_value


class PinbarNoseEyes(StrategyV2):
    """Pinbar Trading System (Nose & Eyes)."""

    SWING_PERIOD = 5
    ATR_PERIOD = 14
    EXPIRY_BARS = 3
    BUFFER_PIPS = 1.0

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="pinbar_nose_eyes",
            name="Pinbar Nose Eyes",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "A pinbar (nose) that probes well beyond the prior bar's (left eye's) extreme and is rejected "
                "— closing back inside the left eye with open and close in the far quartile — marks a failed "
                "breakout and stop-run at a structural support/resistance level. The edge should persist because "
                "the protrusion flushes weak-hand stops and breakout traders beyond the level, and when that "
                "probe attracts no follow-through the trapped breakout flow must unwind, pushing price back "
                "through the left eye. Locating the pattern at a *confirmed* swing level concentrates this "
                "behaviour where resting liquidity actually sits, which is why the author insists on strong S/R "
                "and why the conservative (stop-entry beyond the nose) version demands proof that the rejection "
                "is holding before committing."
            ),
            granularities=["H4"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="H4",
            context_granularities=(),
            simulate_on="H1",
            source_row=23,
            source_url="https://www.earnforex.com/forex-strategy/pinbar-trading-system",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["atr", "confirmed_swing_points"]

    @property
    def warmup_bars(self) -> int:
        return 50

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h4 = frames["H4"]
        pip = float(get_pip_value(self.metadata.pairs[0]))

        highs = last_n_confirmed_highs(
            h4["High"], h4["Low"], n=1, period=self.SWING_PERIOD
        )
        lows = last_n_confirmed_lows(
            h4["High"], h4["Low"], n=1, period=self.SWING_PERIOD
        )
        r_level = highs["level_1"].to_numpy(dtype=float)
        s_level = lows["level_1"].to_numpy(dtype=float)

        atr14 = atr(h4["High"], h4["Low"], h4["Close"], self.ATR_PERIOD).to_numpy(
            dtype=float
        )

        open_p = h4["Open"].to_numpy(dtype=float)
        high_p = h4["High"].to_numpy(dtype=float)
        low_p = h4["Low"].to_numpy(dtype=float)
        close_p = h4["Close"].to_numpy(dtype=float)

        orders: List[OrderIntent] = []

        for i in range(self.warmup_bars, len(h4)):
            rng_le = high_p[i - 1] - low_p[i - 1]
            rng_n = high_p[i] - low_p[i]

            if rng_le <= 0 or rng_n <= 0:
                continue

            if np.isnan(atr14[i]):
                continue

            # Check long setup
            # 1. Left eye is a down bar
            is_le_down = close_p[i - 1] < open_p[i - 1]
            if is_le_down and not np.isnan(s_level[i]):
                # 2 & 3. Nose opens and closes inside left-eye body
                inside_body_open = close_p[i - 1] < open_p[i] < open_p[i - 1]
                inside_body_close = close_p[i - 1] < close_p[i] < open_p[i - 1]

                # 4. Nose low protrudes well below LE low
                protrudes_below = low_p[i] < low_p[i - 1] - 0.5 * rng_le

                # 5. Nose open AND close in top quartile
                top_quartile = min(open_p[i], close_p[i]) > low_p[i] + 0.75 * rng_n

                # 6. S/R filter
                sr_filter = abs(low_p[i] - s_level[i]) <= 0.5 * atr14[i]

                if (
                    inside_body_open
                    and inside_body_close
                    and protrudes_below
                    and top_quartile
                    and sr_filter
                ):
                    entry_price = high_p[i] + self.BUFFER_PIPS * pip
                    # 7. TP-validity guard
                    if high_p[i - 1] + self.BUFFER_PIPS * pip > entry_price:
                        # Buy stop must be above the decision bar's close
                        if entry_price > close_p[i]:
                            stop_price = (
                                min(s_level[i], low_p[i]) - self.BUFFER_PIPS * pip
                            )
                            tp_price = high_p[i - 1] + self.BUFFER_PIPS * pip

                            if entry_price - stop_price > 0:
                                orders.append(
                                    OrderIntent(
                                        decision_bar=h4.index[i],
                                        direction=1,
                                        entry="buy_stop",
                                        entry_price=entry_price,
                                        stop=StopRule(price=stop_price),
                                        exits=[
                                            ExitLeg(
                                                fraction=1.0,
                                                kind="take_profit",
                                                price=tp_price,
                                                label="TP1",
                                            )
                                        ],
                                        expires_after_bars=self.EXPIRY_BARS,
                                        tag="pinbar_nose_eyes",
                                    )
                                )

            # Check short setup
            # 1. Left eye is an up bar
            is_le_up = close_p[i - 1] > open_p[i - 1]
            if is_le_up and not np.isnan(r_level[i]):
                # 2 & 3. Nose opens and closes inside left-eye body
                inside_body_open_s = open_p[i - 1] < open_p[i] < close_p[i - 1]
                inside_body_close_s = open_p[i - 1] < close_p[i] < close_p[i - 1]

                # 4. Nose high protrudes well above LE high
                protrudes_above = high_p[i] > high_p[i - 1] + 0.5 * rng_le

                # 5. Nose open AND close in bottom quartile
                bottom_quartile = max(open_p[i], close_p[i]) < low_p[i] + 0.25 * rng_n

                # 6. S/R filter
                sr_filter_s = abs(high_p[i] - r_level[i]) <= 0.5 * atr14[i]

                if (
                    inside_body_open_s
                    and inside_body_close_s
                    and protrudes_above
                    and bottom_quartile
                    and sr_filter_s
                ):
                    entry_price_s = low_p[i] - self.BUFFER_PIPS * pip
                    # 7. TP-validity guard
                    if low_p[i - 1] - self.BUFFER_PIPS * pip < entry_price_s:
                        # Sell stop must be below the decision bar's close
                        if entry_price_s < close_p[i]:
                            stop_price_s = (
                                max(r_level[i], high_p[i]) + self.BUFFER_PIPS * pip
                            )
                            tp_price_s = low_p[i - 1] - self.BUFFER_PIPS * pip

                            if stop_price_s - entry_price_s > 0:
                                orders.append(
                                    OrderIntent(
                                        decision_bar=h4.index[i],
                                        direction=-1,
                                        entry="sell_stop",
                                        entry_price=entry_price_s,
                                        stop=StopRule(price=stop_price_s),
                                        exits=[
                                            ExitLeg(
                                                fraction=1.0,
                                                kind="take_profit",
                                                price=tp_price_s,
                                                label="TP1",
                                            )
                                        ],
                                        expires_after_bars=self.EXPIRY_BARS,
                                        tag="pinbar_nose_eyes",
                                    )
                                )

        return orders
