"""Smash Days Strategy."""

from __future__ import annotations

from typing import List, Mapping, Sequence

import numpy as np
import pandas as pd

from ..contract_v2 import (
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)


class SmashDays(StrategyV2):
    """Smash Days in Forex."""

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="smash_days",
            name="Smash Days",
            version="0.1.0",
            author="wave2-fleet",
            hypothesis=(
                "A day whose close exceeds both the previous close and the highs of "
                "the preceding five sessions marks terminal exhaustion of a short-term "
                "upleg: late momentum buyers have chased price to a multi-day extreme "
                "and there is no residual bid left above them, so the path of least "
                "resistance on the following session is a snapback through the prior "
                "day's low as trapped longs liquidate and short-term mean-reversion flow dominates."
            ),
            granularities=["D1"],
            pairs=["AUD_USD", "USD_CAD", "EUR_USD", "GBP_USD", "USD_JPY"],
            primary_granularity="D1",
            context_granularities=(),
            simulate_on="H1",
            source_row=35,
            source_url="https://www.trade2win.com/threads/smash-days-in-forex.242994/",
        )

    @property
    def required_indicators(self) -> List[str]:
        return []

    @property
    def warmup_bars(self) -> int:
        # We need 5 prior bars, plus the shift of 1, so 6 bars.
        return 6

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        d1 = frames["D1"]
        close = d1["Close"].to_numpy(dtype=float)
        high = d1["High"].to_numpy(dtype=float)
        low = d1["Low"].to_numpy(dtype=float)

        # PRIOR5_HIGH[t] = max(High[t-5..t-1])
        # We use pandas shift(1).rolling(5).max() to precisely match this definition.
        prior_5_high = d1["High"].shift(1).rolling(5).max().to_numpy()

        orders: List[OrderIntent] = []
        for i in range(self.warmup_bars, len(d1)):
            close_t = close[i]
            close_t_minus_1 = close[i - 1]
            prior5 = float(prior_5_high[i])

            if np.isnan(prior5):
                continue

            # Smash-up day condition
            if close_t > close_t_minus_1 and close_t > prior5:
                entry_level = float(low[i])
                stop_level = float(high[i])

                # NOTE 3 check: sell stop must sit BELOW the market close.
                # If the level is already at or above the close, it's an instant fill in disguise.
                if entry_level >= close_t:
                    continue

                risk = stop_level - entry_level
                if risk <= 0:
                    continue

                orders.append(
                    OrderIntent(
                        decision_bar=d1.index[i],
                        direction=-1,
                        entry="sell_stop",
                        entry_price=entry_level,
                        decision_close=close_t,
                        stop=StopRule(price=stop_level),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="time",
                                bars=5,
                                label="T_TIME5",
                            )
                        ],
                        expires_after_bars=1,
                        tag="smash_days",
                        strategy_id=self.strategy_id,
                    )
                )
        return orders
