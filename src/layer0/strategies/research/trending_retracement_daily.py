import numpy as np
import pandas as pd
from typing import List, Mapping, Sequence

from ..contract_v2 import ExitLeg, OrderIntent, StopRule, StrategyMetadataV2, StrategyV2
from ..causal_structure import last_n_confirmed_highs, last_n_confirmed_lows
from ...data_access.indicators import get_pip_value


def _smma(series: pd.Series, n: int) -> pd.Series:
    """Smoothed Moving Average (SMMA)."""
    vals = series.to_numpy()
    smma_vals = np.full(len(vals), np.nan)
    if len(vals) < n:
        return pd.Series(smma_vals, index=series.index)

    smma_vals[n - 1] = np.mean(vals[:n])
    for i in range(n, len(vals)):
        smma_vals[i] = (smma_vals[i - 1] * (n - 1) + vals[i]) / n

    return pd.Series(smma_vals, index=series.index)


class TrendingRetracementDaily(StrategyV2):
    """Trading in Trending with Retracement."""

    SWING_PERIOD = 5
    ENTRY_BUFFER_PIPS = 4.0
    BREAKEVEN_OFFSET_PIPS = 25.0
    BE_PIPS = 70.0
    TP_PIPS = 150.0
    EXPIRY_BARS = 1

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="trending_retracement_daily",
            name="Trending Retracement Daily",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "After a fast smoothed-moving-average cross establishes a fresh daily trend, the first counter-trend candle that forms while price is stretched a fixed half-to-one percent beyond the smoothed mean marks a shallow pullback within an intact impulse rather than a reversal; entering on a stop order just beyond that candle's extreme captures trend resumption. The edge should persist because fast MA crosses proxy the behavioural momentum cascade — underreaction to new information followed by herding — while short-term counter-move traders provide the liquidity for continuation entries; the envelope band filters for pullbacks occurring at a consistent, moderate extension where late trend-followers re-engage and the prior swing provides a natural invalidation level."
            ),
            granularities=["D1"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="D1",
            context_granularities=(),
            simulate_on="H1",
            source_row=9,
            source_url="https://www.forexstrategiesresources.com/trend-following-forex-strategies/142-trading-in-trending-with-retracement-trading-system-daily/",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["confirmed_swing_points"]

    @property
    def warmup_bars(self) -> int:
        # Enough to warm up SMMA8 and 5-period swings
        return 20

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        d1 = frames["D1"]
        pip = float(get_pip_value(self.metadata.pairs[0]))

        close = d1["Close"].to_numpy(dtype=float)
        open_ = d1["Open"].to_numpy(dtype=float)
        high = d1["High"].to_numpy(dtype=float)
        low = d1["Low"].to_numpy(dtype=float)

        smma3 = _smma(d1["Close"], 3).to_numpy(dtype=float)
        smma8 = _smma(d1["Close"], 8).to_numpy(dtype=float)

        ui = smma8 * 1.005
        uo = smma8 * 1.010
        li = smma8 * 0.995
        lo = smma8 * 0.990

        # Bullish cross: SMMA3_c > SMMA8_c AND SMMA3_{c-1} <= SMMA8_{c-1}
        bull_cross = (smma3 > smma8) & (np.roll(smma3, 1) <= np.roll(smma8, 1))
        bull_cross[0] = False

        # Bearish cross: SMMA3_c < SMMA8_c AND SMMA3_{c-1} >= SMMA8_{c-1}
        bear_cross = (smma3 < smma8) & (np.roll(smma3, 1) >= np.roll(smma8, 1))
        bear_cross[0] = False

        highs = last_n_confirmed_highs(
            d1["High"], d1["Low"], n=1, period=self.SWING_PERIOD
        )
        lows = last_n_confirmed_lows(
            d1["High"], d1["Low"], n=1, period=self.SWING_PERIOD
        )

        swing_high = highs["level_1"].to_numpy(dtype=float)
        swing_low = lows["level_1"].to_numpy(dtype=float)

        orders: List[OrderIntent] = []
        for i in range(self.warmup_bars, len(d1)):
            if np.isnan(smma8[i]):
                continue

            # check recent crosses
            bull_cross_recent = any(bull_cross[c] for c in range(max(0, i - 4), i + 1))
            bear_cross_recent = any(bear_cross[c] for c in range(max(0, i - 4), i + 1))

            # Long Setup
            if bull_cross_recent:
                # Setup candle colour: red
                if close[i] < open_[i]:
                    # Location: UI_t <= Close_t < Open_t <= UO_t
                    if ui[i] <= close[i] and open_[i] <= uo[i]:
                        if not np.isnan(swing_low[i]):
                            entry = high[i] + self.ENTRY_BUFFER_PIPS * pip
                            stop = swing_low[i]
                            if stop < entry:
                                orders.append(
                                    OrderIntent(
                                        decision_bar=d1.index[i],
                                        direction=1,
                                        entry="buy_stop",
                                        entry_price=entry,
                                        stop=StopRule(
                                            price=stop,
                                            move_to_breakeven_on="BE_70",
                                            breakeven_offset_pips=0.0,
                                        ),
                                        exits=[
                                            ExitLeg(
                                                fraction=0.01,
                                                kind="take_profit",
                                                price=entry + self.BE_PIPS * pip,
                                                label="BE_70",
                                            ),
                                            ExitLeg(
                                                fraction=0.99,
                                                kind="take_profit",
                                                price=entry + self.TP_PIPS * pip,
                                                label="TP_150",
                                            ),
                                        ],
                                        expires_after_bars=self.EXPIRY_BARS,
                                        tag="trending_retracement_daily",
                                    )
                                )
                                continue  # One direction per bar

            # Short Setup
            if bear_cross_recent:
                # Setup candle colour: green
                if close[i] > open_[i]:
                    # Location: LO_t <= Open_t < Close_t <= LI_t
                    if lo[i] <= open_[i] and close[i] <= li[i]:
                        if not np.isnan(swing_high[i]):
                            entry = low[i] - self.ENTRY_BUFFER_PIPS * pip
                            stop = swing_high[i]
                            if stop > entry:
                                orders.append(
                                    OrderIntent(
                                        decision_bar=d1.index[i],
                                        direction=-1,
                                        entry="sell_stop",
                                        entry_price=entry,
                                        stop=StopRule(
                                            price=stop,
                                            move_to_breakeven_on="BE_70",
                                            breakeven_offset_pips=0.0,
                                        ),
                                        exits=[
                                            ExitLeg(
                                                fraction=0.01,
                                                kind="take_profit",
                                                price=entry - self.BE_PIPS * pip,
                                                label="BE_70",
                                            ),
                                            ExitLeg(
                                                fraction=0.99,
                                                kind="take_profit",
                                                price=entry - self.TP_PIPS * pip,
                                                label="TP_150",
                                            ),
                                        ],
                                        expires_after_bars=self.EXPIRY_BARS,
                                        tag="trending_retracement_daily",
                                    )
                                )

        return orders
