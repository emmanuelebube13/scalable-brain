"""REFERENCE STRATEGY — the shape every Wave-2 strategy should copy.

This is **not** one of the 51 CSV strategies. It is a deliberately synthetic
example that exercises every hard feature the real ones need, so there is one
correct pattern to imitate instead of 51 inventions:

* a **multi-timeframe filter** (D1 trend gating H4 entries) done *causally*
* **causal swing structure** ("the second consecutive higher high")
* a **pending stop entry** placed above a confirmed level
* a **three-leg scale-out** whose fractions sum to 1.0
* a **breakeven move** triggered by a named leg

Read the four numbered notes below before writing your own. Each one marks a
place where the obvious implementation is wrong.

Author's guide: `docs/design/CONTRACT_V2_AND_POSITION_ENGINE.md`.
"""

from __future__ import annotations

from typing import List, Mapping, Sequence

import numpy as np
import pandas as pd

from ..causal_structure import last_n_confirmed_highs, last_n_confirmed_lows
from ..contract_v2 import (
    GRANULARITY_INTERVAL,
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)
from ...data_access.indicators import get_pip_value, sma


class ReferencePullbackContinuation(StrategyV2):
    """Buy the resumption of a D1 uptrend on a confirmed H4 higher-high break."""

    TREND_PERIOD = 50  # D1 SMA defining the trend
    SWING_PERIOD = 5  # swing definition AND confirmation lag
    ENTRY_BUFFER_PIPS = 2.0  # stop order sits this far above the level
    STOP_BUFFER_PIPS = 5.0  # stop sits this far below the confirmed swing low
    EXPIRY_BARS = 6  # cancel the pending order if it never triggers

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="reference_pullback_continuation",
            name="Reference — Pullback Continuation",
            version="1.0.0",
            author="wave1-reference",
            hypothesis=(
                "In an established daily uptrend, a pullback that fails to take out "
                "the prior swing low and then breaks the most recent confirmed swing "
                "high marks the resumption of that trend, because the traders who "
                "faded the pullback are forced to cover above the level."
            ),
            granularities=["H4"],
            pairs=["EUR_USD", "GBP_USD"],
            primary_granularity="H4",
            context_granularities=("D1",),
            simulate_on="H1",
            source_row=None,  # a real strategy sets its CSV row here
            source_url="",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["sma", "confirmed_swing_points"]

    @property
    def warmup_bars(self) -> int:
        # Enough H4 bars for the D1 SMA to exist and for swings to confirm.
        return 300

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h4 = frames["H4"]
        d1 = frames["D1"]
        pip = float(get_pip_value(self.metadata.pairs[0]))

        # -- NOTE 1 --------------------------------------------------------
        # The causal multi-timeframe join. Bars are stamped at their OPEN, so a
        # D1 bar at 21:00 Monday is not knowable until 21:00 Tuesday. Shifting
        # the D1 index forward by one full interval re-stamps each bar at its
        # CLOSE; merge_asof(direction="backward") then attaches, to every H4
        # bar, the most recent D1 bar that had actually finished.
        #
        # Writing `d1.loc[d1.index <= ts]` instead admits the still-forming
        # daily bar and is look-ahead. That exact mistake produced 108 phantom
        # orders during the Wave-1 review. If you prefer the explicit form,
        # `contract_v2.closed_context_frame(d1, "D1", ts)` is the same rule.
        d1_trend_up = (d1["Close"] > sma(d1["Close"], self.TREND_PERIOD)).astype(float)
        d1_at_close = pd.DataFrame(
            {"trend_up": d1_trend_up.to_numpy()},
            index=d1.index + GRANULARITY_INTERVAL["D1"],
        )
        trend = pd.merge_asof(
            pd.DataFrame(index=h4.index),
            d1_at_close,
            left_index=True,
            right_index=True,
            direction="backward",
        )["trend_up"]

        # -- NOTE 2 --------------------------------------------------------
        # Swing structure, causally. `last_n_confirmed_highs` gives, at every
        # bar t, the levels of the last n swing highs that have CONFIRMED by t.
        # A swing high occurring at bar k only confirms at k+SWING_PERIOD.
        # Never import `indicators.detect_swing_points` — it uses center=True
        # and reads the future. It is what contaminated the only strategy that
        # ever reached production.
        highs = last_n_confirmed_highs(
            h4["High"], h4["Low"], n=2, period=self.SWING_PERIOD
        )
        lows = last_n_confirmed_lows(
            h4["High"], h4["Low"], n=1, period=self.SWING_PERIOD
        )

        level_1 = highs["level_1"].to_numpy(dtype=float)  # most recent confirmed
        level_2 = highs["level_2"].to_numpy(dtype=float)  # the one before it
        swing_low = lows["level_1"].to_numpy(dtype=float)
        trend_up = trend.to_numpy(dtype=float)
        close = h4["Close"].to_numpy(dtype=float)

        orders: List[OrderIntent] = []
        for i in range(self.warmup_bars, len(h4)):
            if trend_up[i] != 1.0:
                continue
            if np.isnan(level_1[i]) or np.isnan(level_2[i]) or np.isnan(swing_low[i]):
                continue
            # "the SECOND consecutive higher high" — both levels known at bar i.
            if not level_1[i] > level_2[i]:
                continue

            entry = float(level_1[i]) + self.ENTRY_BUFFER_PIPS * pip
            stop = float(swing_low[i]) - self.STOP_BUFFER_PIPS * pip

            # -- NOTE 3 ----------------------------------------------------
            # A buy stop must sit ABOVE the market at the decision bar; if the
            # level is already below the close it is a market order wearing a
            # disguise, and OrderIntent rejects it. Skipping is correct — the
            # break already happened and this setup is gone.
            if entry <= close[i]:
                continue
            risk = entry - stop
            if risk <= 0:
                continue

            orders.append(
                OrderIntent(
                    decision_bar=h4.index[i],
                    direction=1,
                    entry="buy_stop",
                    entry_price=entry,
                    # -- NOTE 4 --------------------------------------------
                    # The breakeven trigger names a leg by LABEL. The label
                    # must exist among the exits or the contract rejects the
                    # intent. The stop then moves at the CLOSE of the bar in
                    # which TP2 fills (F8) — never intrabar, because bar data
                    # cannot tell us the within-bar sequence.
                    stop=StopRule(
                        price=stop,
                        move_to_breakeven_on="TP2",
                        breakeven_offset_pips=0.0,
                    ),
                    exits=[
                        ExitLeg(
                            fraction=0.333,
                            kind="take_profit",
                            price=entry + 1.0 * risk,
                            label="TP1",
                        ),
                        ExitLeg(
                            fraction=0.333,
                            kind="take_profit",
                            price=entry + 2.0 * risk,
                            label="TP2",
                        ),
                        ExitLeg(
                            fraction=0.334,
                            kind="take_profit",
                            price=entry + 3.0 * risk,
                            label="TP3",
                        ),
                    ],
                    expires_after_bars=self.EXPIRY_BARS,
                    tag="reference",
                )
            )
        return orders
