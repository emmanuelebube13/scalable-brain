"""Riding Trend Retracement Strategy."""

from __future__ import annotations

from typing import List, Mapping, Sequence

import numpy as np
import pandas as pd

from ..causal_structure import (
    last_n_confirmed_highs,
    last_n_confirmed_lows,
    zigzag_swings,
)
from ..contract_v2 import (
    GRANULARITY_INTERVAL,
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)
from ...data_access.indicators import get_pip_value, sma


class RidingTrendRetracement(StrategyV2):
    """Buy the resumption of a D1 uptrend on a confirmed H4 higher-high break."""

    TREND_PERIOD = 200
    TREND_SLOPE_PERIOD = 5
    ZIGZAG_DEPTH = 3
    ZIGZAG_DEVIATION = 0.5
    ZIGZAG_BACKSTEP = 3
    ENTRY_BUFFER_PIPS = 3.0
    STOP_SWING_BUFFER_PIPS = 20.0
    STOP_MAX_PIPS = 100.0
    EXPIRY_BARS = 1

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="riding_trend_retracement",
            name="Riding Trend Retracement",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "Established trends, as measured by price holding above a rising 200-day SMA, "
                "persist because the dominant order flow in the market is aligned with the prevailing direction; "
                "counter-trend retracements are profit-taking pauses, not reversals, and they tend to resolve "
                "back in the trend direction. A buy stop placed beyond the second consecutive higher swing high "
                "demands that the market prove resumption twice before capital is committed, filtering out the deep "
                "pullbacks that become genuine reversals. The edge should persist because it is the behavioural "
                "signature of trend-following: late, confirmed entries in exchange for a higher win rate on "
                "continuation, monetised by asymmetric scale-outs (1:2 / 1:4 / 1:6) that let the surviving third "
                "of the position harvest the tail of the move."
            ),
            granularities=["H4"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="H4",
            context_granularities=("D1",),
            simulate_on="H1",
            source_row=1,
            source_url="https://www.forexstrategiesresources.com/trend-following-forex-strategies/88-riding-the-trend-after-retracement/",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["sma", "confirmed_swing_points", "zigzag_swings"]

    @property
    def warmup_bars(self) -> int:
        return 1300

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h4 = frames["H4"]
        d1 = frames["D1"]
        pip = float(get_pip_value(self.metadata.pairs[0]))

        # 1. D1 Trend Filter
        sma200 = sma(d1["Close"], self.TREND_PERIOD)
        sma200_slope = sma200.diff(self.TREND_SLOPE_PERIOD)
        d1_bullish = (d1["Close"] > sma200) & (sma200_slope > 0)
        d1_bearish = (d1["Close"] < sma200) & (sma200_slope < 0)

        d1_at_close = pd.DataFrame(
            {
                "bullish": d1_bullish.astype(float).to_numpy(),
                "bearish": d1_bearish.astype(float).to_numpy(),
            },
            index=d1.index + GRANULARITY_INTERVAL["D1"],
        )
        trend = pd.merge_asof(
            pd.DataFrame(index=h4.index),
            d1_at_close,
            left_index=True,
            right_index=True,
            direction="backward",
        )
        bullish_h4 = trend["bullish"].fillna(0.0).to_numpy(dtype=float)
        bearish_h4 = trend["bearish"].fillna(0.0).to_numpy(dtype=float)

        # 2. H4 Causal ZigZag & Swings
        zz = zigzag_swings(
            h4["High"],
            h4["Low"],
            depth=self.ZIGZAG_DEPTH,
            deviation_pips=self.ZIGZAG_DEVIATION,
            backstep=self.ZIGZAG_BACKSTEP,
            pip_value=pip,
        )

        sl_conf_long = last_n_confirmed_lows(
            h4["High"], h4["Low"], n=1, period=self.ZIGZAG_DEPTH
        )["level_1"].to_numpy(dtype=float)
        sl_conf_short = last_n_confirmed_highs(
            h4["High"], h4["Low"], n=1, period=self.ZIGZAG_DEPTH
        )["level_1"].to_numpy(dtype=float)

        orders: List[OrderIntent] = []
        long_highs: List[float] = []
        short_lows: List[float] = []

        zz_idx = 0
        zz_confirms = zz["confirm_time"].to_numpy()
        zz_kinds = zz["kind"].to_numpy()
        zz_levels = zz["level"].to_numpy()

        close = h4["Close"].to_numpy(dtype=float)

        for i in range(self.warmup_bars, len(h4)):
            current_time = h4.index[i]

            if bullish_h4[i] != 1.0:
                long_highs.clear()
            if bearish_h4[i] != 1.0:
                short_lows.clear()

            while zz_idx < len(zz) and zz_confirms[zz_idx] <= current_time:
                kind = zz_kinds[zz_idx]
                level = zz_levels[zz_idx]
                if kind == "high":
                    if len(long_highs) > 0 and level <= long_highs[-1]:
                        long_highs = [level]
                    else:
                        long_highs.append(level)
                else:
                    if len(short_lows) > 0 and level >= short_lows[-1]:
                        short_lows = [level]
                    else:
                        short_lows.append(level)
                zz_idx += 1

            if bullish_h4[i] != 1.0:
                long_highs.clear()
            if bearish_h4[i] != 1.0:
                short_lows.clear()

            if bullish_h4[i] == 1.0 and len(long_highs) >= 3:
                h3 = long_highs[-1]
                entry = h3 + self.ENTRY_BUFFER_PIPS * pip

                if entry > close[i]:
                    sl_conf = sl_conf_long[i]
                    if np.isnan(sl_conf):
                        sl = entry - self.STOP_MAX_PIPS * pip
                    else:
                        sl = max(
                            entry - self.STOP_MAX_PIPS * pip,
                            sl_conf - self.STOP_SWING_BUFFER_PIPS * pip,
                        )

                    risk = entry - sl
                    if risk > 0:
                        orders.append(
                            OrderIntent(
                                decision_bar=current_time,
                                direction=1,
                                entry="buy_stop",
                                entry_price=entry,
                                stop=StopRule(
                                    price=sl,
                                    move_to_breakeven_on="TP2",
                                    breakeven_offset_pips=0.0,
                                ),
                                exits=[
                                    ExitLeg(
                                        fraction=0.333,
                                        kind="take_profit",
                                        price=entry + 200.0 * pip,
                                        label="TP1",
                                    ),
                                    ExitLeg(
                                        fraction=0.333,
                                        kind="take_profit",
                                        price=entry + 400.0 * pip,
                                        label="TP2",
                                    ),
                                    ExitLeg(
                                        fraction=0.334,
                                        kind="take_profit",
                                        price=entry + 600.0 * pip,
                                        label="TP3",
                                    ),
                                ],
                                expires_after_bars=self.EXPIRY_BARS,
                                tag="riding_trend_long",
                            )
                        )

            if bearish_h4[i] == 1.0 and len(short_lows) >= 3:
                l3 = short_lows[-1]
                entry = l3 - self.ENTRY_BUFFER_PIPS * pip

                if entry < close[i]:
                    sh_conf = sl_conf_short[i]
                    if np.isnan(sh_conf):
                        sl = entry + self.STOP_MAX_PIPS * pip
                    else:
                        sl = min(
                            entry + self.STOP_MAX_PIPS * pip,
                            sh_conf + self.STOP_SWING_BUFFER_PIPS * pip,
                        )

                    risk = sl - entry
                    if risk > 0:
                        orders.append(
                            OrderIntent(
                                decision_bar=current_time,
                                direction=-1,
                                entry="sell_stop",
                                entry_price=entry,
                                stop=StopRule(
                                    price=sl,
                                    move_to_breakeven_on="TP2",
                                    breakeven_offset_pips=0.0,
                                ),
                                exits=[
                                    ExitLeg(
                                        fraction=0.333,
                                        kind="take_profit",
                                        price=entry - 200.0 * pip,
                                        label="TP1",
                                    ),
                                    ExitLeg(
                                        fraction=0.333,
                                        kind="take_profit",
                                        price=entry - 400.0 * pip,
                                        label="TP2",
                                    ),
                                    ExitLeg(
                                        fraction=0.334,
                                        kind="take_profit",
                                        price=entry - 600.0 * pip,
                                        label="TP3",
                                    ),
                                ],
                                expires_after_bars=self.EXPIRY_BARS,
                                tag="riding_trend_short",
                            )
                        )

        return orders
