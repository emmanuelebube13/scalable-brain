from typing import List, Mapping, Sequence

import numpy as np
import pandas as pd

from ..contract_v2 import ExitLeg, OrderIntent, StopRule, StrategyMetadataV2, StrategyV2
from ...data_access.indicators import get_pip_value


class ThreeCandleSwingReversal(StrategyV2):
    """Daily Chart 3-Candle Swing Reversal Strategy."""

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="three_candle_swing_reversal",
            name="Three Candle Swing Reversal",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "After a sustained multi-day decline, a three-bar pattern of ascending lows "
                "culminating in a close back through the first bar's body marks seller exhaustion: "
                "the marginal seller has been absorbed at successively higher lows and trapped "
                "shorts must cover, producing a multi-session counter-swing worth roughly 100 pips. "
                "The edge persists because daily-bar participants (the last timeframe dominated "
                "by discretionary position traders rather than HFT) anchor on prior-day bodies as "
                "reference levels, so a reclaim of the pattern's origin level triggers mechanical "
                "short-covering and fresh dip-buying. The author's MODERATE conviction is honest: "
                "win rate was never measured."
            ),
            granularities=["D1"],
            pairs=["EUR_USD", "USD_CAD", "USD_JPY"],
            primary_granularity="D1",
            context_granularities=(),
            simulate_on="H1",
            source_row=15,
            source_url="https://www.forexfactory.com/thread/759887-daily-chart-3-candle",
        )

    @property
    def required_indicators(self) -> List[str]:
        return []

    @property
    def warmup_bars(self) -> int:
        return 6

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        d1 = frames["D1"]
        pip = float(get_pip_value(self.metadata.pairs[0]))

        high = d1["High"].to_numpy(dtype=float)
        low = d1["Low"].to_numpy(dtype=float)
        close = d1["Close"].to_numpy(dtype=float)
        open_ = d1["Open"].to_numpy(dtype=float)

        orders: List[OrderIntent] = []
        last_long_signal_idx = -999
        last_short_signal_idx = -999

        for i in range(self.warmup_bars, len(d1)):
            # Check suppression
            can_long = (i - last_long_signal_idx) > 2
            can_short = (i - last_short_signal_idx) > 2

            if not (can_long or can_short):
                continue

            # Trend filter
            downtrend = (
                high[i - 3] < high[i - 4]
                and high[i - 4] < high[i - 5]
                and low[i - 3] < low[i - 4]
                and low[i - 4] < low[i - 5]
            )
            uptrend = (
                high[i - 3] > high[i - 4]
                and high[i - 4] > high[i - 5]
                and low[i - 3] > low[i - 4]
                and low[i - 4] > low[i - 5]
            )

            # Long rules
            if can_long and downtrend:
                if low[i - 1] > low[i - 2] and low[i] > low[i - 1]:
                    trig = min(open_[i - 2], close[i - 2])
                    if close[i] > trig:
                        # Ensure buy_limit is valid (E <= close[i])
                        # The condition above guarantees trig < close[i], so buy_limit is valid.
                        stop = min(
                            trig - 50 * pip, min(low[i - 2], low[i - 1]) - 15 * pip
                        )
                        orders.append(
                            OrderIntent(
                                decision_bar=d1.index[i],
                                direction=1,
                                entry="buy_limit",
                                entry_price=trig,
                                stop=StopRule(
                                    price=stop,
                                ),
                                exits=[
                                    ExitLeg(
                                        fraction=1.0,
                                        kind="take_profit",
                                        price=trig + 100 * pip,
                                        label="TP1",
                                    )
                                ],
                                expires_after_bars=2,
                                tag="three_candle_long",
                            )
                        )
                        last_long_signal_idx = i
                        continue  # Long and short are mutually exclusive anyway

            # Short rules
            if can_short and uptrend:
                if high[i - 1] < high[i - 2] and high[i] < high[i - 1]:
                    trig_s = max(open_[i - 2], close[i - 2])
                    if close[i] < trig_s:
                        stop = max(
                            trig_s + 50 * pip, max(high[i - 2], high[i - 1]) + 15 * pip
                        )
                        orders.append(
                            OrderIntent(
                                decision_bar=d1.index[i],
                                direction=-1,
                                entry="sell_limit",
                                entry_price=trig_s,
                                stop=StopRule(
                                    price=stop,
                                ),
                                exits=[
                                    ExitLeg(
                                        fraction=1.0,
                                        kind="take_profit",
                                        price=trig_s - 100 * pip,
                                        label="TP1",
                                    )
                                ],
                                expires_after_bars=2,
                                tag="three_candle_short",
                            )
                        )
                        last_short_signal_idx = i

        return orders
