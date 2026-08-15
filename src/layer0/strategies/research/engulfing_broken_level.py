"""SPEC-engulfing_broken_level — daily engulfing candle at a broken confirmed level.

Source: row 32 of forex_swing_strategies.csv ·
https://dailypriceaction.com/blog/how-to-trade-the-bearish-engulfing-pattern/

Full mechanization: ``task/2026-August-week1/fleet/upload/wave2/specs/SPEC-engulfing_broken_level.md``.
Summary (D1-only, single timeframe — the source's optional H4 pin-bar retest
entry is rejected, spec §10 #5):

- A bullish (bearish) engulfing candle at bar *t* that both range-engulfs and
  body-engulfs bar *t-1* and closes beyond bar *t-1*'s opposite extreme
  (spec §4/§5 conditions 1-4).
- ... whose low (high) touches/undercuts (exceeds) the most recently
  CONFIRMED swing low (high), confirmation bar <= t-1 (condition 5).
- ... and whose CLOSE breaks the nearest confirmed swing high (low) above
  (below) the candle's low (high), confirmation bar <= t-1 (condition 6).
- ... provided a confirmed swing level beyond the 50%-retracement entry price
  exists to serve as the take-profit target, confirmation bar <= t
  (condition 7).

Entry is a 50% retracement limit order of the engulfing candle's range;
the stop sits 0.5xATR(14) beyond the candle's extreme (spec §6, §10 #7); the
sole exit leg (fraction 1.0) targets the nearest confirmed swing level beyond
the entry price (spec §7). Pending lifetime is exactly one D1 bar in
H1-simulation terms (spec §4/§5, §10 #8), which the causality audit (spec §9)
shows makes consecutive-signal pending overlap impossible.

``detect_swing_points`` is never used (it is look-ahead, see
``causal_structure`` module docstring); all swing levels come from
:func:`causal_structure.confirmed_swing_points`, which stamps a swing at its
CONFIRMATION bar (occurrence bar + period) while carrying the level set at
the occurrence bar.
"""

from __future__ import annotations

import bisect
import math
from typing import List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from ..causal_structure import confirmed_swing_points
from ..contract_v2 import (
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)
from ...data_access.indicators import atr


class EngulfingBrokenLevel(StrategyV2):
    """D1 engulfing candle at a confirmed swing extreme that breaks a nearby
    confirmed swing level by close — the "trapped trader" reversal (spec §1)."""

    SWING_PERIOD = 5  # confirmed_swing_points period AND confirmation lag (spec §3)
    ATR_PERIOD = 14  # spec §3
    STOP_ATR_MULTIPLE = 0.5  # spec §6, §10 #7
    EXPIRY_BARS = 24  # H1 simulation bars = exactly one D1 bar (spec §4/§5, §10 #8)

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="engulfing_broken_level",
            name="Engulfing Candle at a Broken Confirmed Level",
            version="0.1.0",
            author="wave2-fleet",
            hypothesis=(
                "When a daily bearish (or bullish) engulfing candle forms at a "
                "previously confirmed swing extreme and closes through a nearby "
                "key level, it marks the point where the last group of "
                "breakout/trend-continuation traders is trapped on the wrong "
                "side of a level that has already proven itself. The edge "
                "claimed is that large-range daily engulfing candles at "
                "well-tested levels represent genuine institutional "
                "order-flow reversal rather than noise: daily candles "
                "aggregate a full session of participation, so a range that "
                "swallows the prior day's range and closes through a level "
                "forces a broad cohort of positions underwater, whose exits "
                "fuel the move toward the next level. It should persist "
                "because level memories and trapped-trader liquidation are "
                "structural features of how FX flow works, not an "
                "arbitrageable micro-pattern; the D1-only restriction is the "
                "author's explicit defence against the noise that swamps the "
                "pattern on lower timeframes."
            ),
            granularities=["D1"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="D1",
            context_granularities=(),
            simulate_on="H1",
            source_row=32,
            source_url=(
                "https://dailypriceaction.com/blog/"
                "how-to-trade-the-bearish-engulfing-pattern/"
            ),
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["confirmed_swing_points", "atr"]

    @property
    def warmup_bars(self) -> int:
        # Room for at least one swing high AND one swing low to have
        # confirmed before the decision bar, plus the ATR lookback.
        return max(self.SWING_PERIOD * 4, self.ATR_PERIOD) + 5

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        d1 = frames["D1"]
        n = len(d1)

        open_arr = d1["Open"].to_numpy(dtype=float)
        high_arr = d1["High"].to_numpy(dtype=float)
        low_arr = d1["Low"].to_numpy(dtype=float)
        close_arr = d1["Close"].to_numpy(dtype=float)

        swing_highs, swing_lows = confirmed_swing_points(
            d1["High"], d1["Low"], period=self.SWING_PERIOD
        )
        sh = swing_highs.to_numpy(dtype=float)
        sl = swing_lows.to_numpy(dtype=float)

        atr_series = atr(d1["High"], d1["Low"], d1["Close"], period=self.ATR_PERIOD)
        atr_arr = atr_series.to_numpy(dtype=float)

        # Two causal views of confirmed-swing history, maintained
        # incrementally as the loop advances (spec §9):
        #  - `last_high` / `last_low`: the level of the MOST RECENTLY
        #    confirmed swing (by confirmation order) -- H_swing / L_swing.
        #  - `highs_sorted` / `lows_sorted`: every confirmed level seen so
        #    far, kept sorted, for the "nearest level above/below a price"
        #    queries (R_break/S_break and the take-profit set).
        # `added_through` is the highest bar position already folded in.
        highs_sorted: List[float] = []
        lows_sorted: List[float] = []
        last_high: float = math.nan
        last_low: float = math.nan
        added_through = -1

        def add_position(p: int) -> None:
            nonlocal last_high, last_low
            if not np.isnan(sh[p]):
                level = float(sh[p])
                bisect.insort(highs_sorted, level)
                last_high = level
            if not np.isnan(sl[p]):
                level = float(sl[p])
                bisect.insort(lows_sorted, level)
                last_low = level

        def nearest_above(levels: List[float], threshold: float) -> Optional[float]:
            idx = bisect.bisect_right(levels, threshold)
            return levels[idx] if idx < len(levels) else None

        def nearest_below(levels: List[float], threshold: float) -> Optional[float]:
            idx = bisect.bisect_left(levels, threshold)
            return levels[idx - 1] if idx > 0 else None

        orders: List[OrderIntent] = []

        for i in range(max(self.warmup_bars, 1), n):
            # Fold in every confirmation with position <= i - 1: this is the
            # state that conditions 5/6 (L_swing/H_swing, R_break/S_break)
            # are entitled to see (spec §9: confirmation bar <= t-1).
            while added_through < i - 1:
                added_through += 1
                add_position(added_through)

            o_t, h_t, l_t, c_t = (
                float(open_arr[i]),
                float(high_arr[i]),
                float(low_arr[i]),
                float(close_arr[i]),
            )
            o_p, h_p, l_p, c_p = (
                float(open_arr[i - 1]),
                float(high_arr[i - 1]),
                float(low_arr[i - 1]),
                float(close_arr[i - 1]),
            )

            range_engulf = h_t >= h_p and l_t <= l_p  # spec §4.2 / §5.2

            order: Optional[OrderIntent] = None

            if (
                c_t > o_t  # §4.1 bullish
                and range_engulf  # §4.2
                and c_t >= o_p
                and o_t <= c_p  # §4.3 body engulf
                and c_t > h_p  # §4.4 closes beyond prior high
            ):
                l_swing = last_low  # confirmation bar <= i-1
                r_break = nearest_above(highs_sorted, l_t)  # confirmation bar <= i-1
                if (
                    not math.isnan(l_swing)
                    and r_break is not None
                    and l_t <= l_swing  # §4.5 forms at the confirmed swing low
                    and c_t > r_break  # §4.6 breaks resistance by close
                ):
                    entry_price = l_t + 0.5 * (h_t - l_t)  # §4 midpoint, §10 #10
                    # Fold in bar i's own confirmation before the take-profit
                    # search: §7 allows confirmation bar <= t (not <= t-1).
                    if added_through < i:
                        added_through = i
                        add_position(i)
                    take_profit = nearest_above(highs_sorted, entry_price)
                    if (
                        take_profit is not None  # §4.7 valid target exists
                        and entry_price < c_t  # buy_limit below the close (NOTE 3)
                    ):
                        stop_price = l_t - self.STOP_ATR_MULTIPLE * atr_arr[i]
                        order = OrderIntent(
                            decision_bar=d1.index[i],
                            direction=1,
                            entry="buy_limit",
                            entry_price=entry_price,
                            stop=StopRule(price=stop_price),
                            exits=[
                                ExitLeg(
                                    fraction=1.0,
                                    kind="take_profit",
                                    price=take_profit,
                                    label="TP1",
                                )
                            ],
                            expires_after_bars=self.EXPIRY_BARS,
                            tag="engulfing_broken_level",
                            strategy_id=self.strategy_id,
                        )
            elif (
                c_t < o_t  # §5.1 bearish
                and range_engulf  # §5.2
                and c_t <= o_p
                and o_t >= c_p  # §5.3 body engulf
                and c_t < l_p  # §5.4 closes beyond prior low
            ):
                h_swing = last_high  # confirmation bar <= i-1
                s_break = nearest_below(lows_sorted, h_t)  # confirmation bar <= i-1
                if (
                    not math.isnan(h_swing)
                    and s_break is not None
                    and h_t >= h_swing  # §5.5 forms at the confirmed swing high
                    and c_t < s_break  # §5.6 breaks support by close
                ):
                    entry_price = h_t - 0.5 * (h_t - l_t)  # §5 midpoint, §10 #10
                    if added_through < i:
                        added_through = i
                        add_position(i)
                    take_profit = nearest_below(lows_sorted, entry_price)
                    if (
                        take_profit is not None  # §5.7 valid target exists
                        and entry_price > c_t  # sell_limit above the close (NOTE 3)
                    ):
                        stop_price = h_t + self.STOP_ATR_MULTIPLE * atr_arr[i]
                        order = OrderIntent(
                            decision_bar=d1.index[i],
                            direction=-1,
                            entry="sell_limit",
                            entry_price=entry_price,
                            stop=StopRule(price=stop_price),
                            exits=[
                                ExitLeg(
                                    fraction=1.0,
                                    kind="take_profit",
                                    price=take_profit,
                                    label="TP1",
                                )
                            ],
                            expires_after_bars=self.EXPIRY_BARS,
                            tag="engulfing_broken_level",
                            strategy_id=self.strategy_id,
                        )

            # Whether or not an order was built, make sure bar i's own
            # confirmation is folded in for the NEXT bar's <= t-1 view.
            if added_through < i:
                added_through = i
                add_position(i)

            if order is not None:
                orders.append(order)

        return orders
