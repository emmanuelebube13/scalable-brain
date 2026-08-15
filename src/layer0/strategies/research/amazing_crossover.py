"""Amazing Crossover — EMA(5)/EMA(10) cross confirmed by RSI(10, median) at 50.

Source: row 34 of ``forex_swing_strategies.csv`` ·
https://forums.babypips.com/t/amazing-crossover-system-100-pips-per-day/19403
Spec: ``task/2026-August-week1/fleet/upload/wave2/specs/SPEC-amazing_crossover.md``.

Single-frame H1 strategy (spec §2: ``context_granularities: none``), so there is
no context frame to join and NOTE 1 of the reference strategy does not apply:
nothing in this module reads any frame other than the primary H1 one, and no
``closed_context_frame`` call is needed because there is no context bar that
could be admitted early. No swing structure, ZigZag, pivots or fractals are used
anywhere (spec §3), so the banned centred swing detector in ``indicators`` — and
``causal_structure`` too — has no role to play here.

Shape notes, mapped to the spec:

* §4/§5 — the entry is a **strict same-bar conjunction**: the EMA cross and the
  RSI-50 cross must both *happen* at decision bar ``t``. Two conditions that
  merely both *hold* at ``t`` are not enough; each must have flipped between
  ``t-1`` and ``t``.
* §3 — RSI is computed on the **median price** ``(High + Low) / 2``, not on
  Close. That derivation is the only arithmetic in this file that is not an
  inventory indicator; it is done from the frame the strategy is handed and is
  never written back to it.
* §6/§7 — every level is anchored to ``C_t``, the close of the decision bar,
  because the entry is a market order whose fill price (open of ``t+1``, F1/F2)
  is unknowable at emission.
* §6 — the pip size is derived from the decision bar's own price level rather
  than from a pair name, because ``StrategyV2`` is never told which pair it is
  running on. See ``_pip_size_from_price``.
"""

from __future__ import annotations

from typing import List, Mapping, Sequence

import numpy as np
import pandas as pd

from ..contract_v2 import (
    Direction,
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)
from ...data_access.indicators import ema, get_pip_value, rsi

#: A quote above this level can only be a JPY-quoted pair. Every non-JPY major
#: this strategy declares trades in the 0.4–2.2 range; USD_JPY has traded 75–160
#: over the whole history. The gap is two orders of magnitude, so the test is
#: not a tuned threshold.
_JPY_QUOTE_THRESHOLD = 20.0


def _pip_size_from_price(price: float) -> float:
    """Pip size for the instrument whose quote is ``price`` (spec §6).

    Spec §6 says ``pip = get_pip_value(pair)`` — 0.0001 for the non-JPY majors,
    0.01 for USD_JPY. The v2 contract, however, never passes the pair to the
    strategy (``generate_orders`` receives frames only, and the harness
    instantiates strategies with no arguments), so the pair name is not
    available at the point the geometry is built. Taking ``metadata.pairs[0]``
    the way the reference strategy does would apply a 0.0001 pip to USD_JPY and
    turn the 100-pip stop into a 1-pip stop.

    The pip *magnitudes* still come from the inventory ``get_pip_value``; only
    the identification of the quote convention is inferred, from the decision
    bar's own close. That keeps the function causal (it reads one completed bar)
    and pure. Recorded as an interface gap in the report.
    """
    pair = "USD_JPY" if price >= _JPY_QUOTE_THRESHOLD else "EUR_USD"
    return float(get_pip_value(pair))


class AmazingCrossover(StrategyV2):
    """H1 EMA5/EMA10 cross that must be confirmed by RSI(10, median) crossing 50."""

    EMA_FAST_PERIOD = 5  # §3 — EMA on Close, period 5
    EMA_SLOW_PERIOD = 10  # §3 — EMA on Close, period 10
    RSI_PERIOD = 10  # §3 — RSI on the median price, period 10
    RSI_LEVEL = 50.0  # §3/§4.2/§5.2 — the midline that must be crossed
    STOP_PIPS = 100.0  # §6 — initial stop, 100 pips from C_t
    BE_TRIGGER_PIPS = 20.0  # §7 — first ladder rung, +20 pips
    BE_TRIGGER_FRACTION = 0.10  # §7/§10 #5 — declared interpretive decision
    TP1_PIPS = 50.0  # §7/§10 #2 — lower bound of the "50–100 pip" band
    TP1_FRACTION = 0.90  # 0.10 + 0.90 = 1.0 exactly
    BE_LABEL = "BE_TRIGGER"  # named by StopRule.move_to_breakeven_on (§6)
    TP1_LABEL = "TP1"

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="amazing_crossover",
            name="Amazing Crossover — EMA5/EMA10 + RSI(10, median) 50-cross",
            version="0.1.0",
            author="wave2-fleet",
            hypothesis=(
                "The claimed edge is dual-confirmed short-term momentum ignition "
                "on H1: a fast/slow EMA cross marks a shift in the intraday "
                "order-flow balance, and requiring RSI(10) on the median price to "
                "cross 50 on the same bar demands that the shift is visible in the "
                "bar's central tendency (not merely a close-price artifact) at the "
                "same moment. The behavioural reason it could persist is herding: "
                "intraday breakout/momentum followers on the most liquid retail "
                "timeframe pile in once a fast trend signal and a momentum midline "
                "agree, extending the move for a few bars to a few hours; the "
                "strict same-bar conjunction exists to filter the chop that kills "
                "naked EMA crosses in ranging sessions."
            ),
            granularities=["H1"],
            # §2 pairs_available, live only. USD_CHF and NZD_USD are declared
            # PENDING backfill there and so are deliberately omitted.
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="H1",
            context_granularities=(),  # §2 — single-frame strategy
            simulate_on="H1",
            source_row=34,
            source_url=(
                "https://forums.babypips.com/t/"
                "amazing-crossover-system-100-pips-per-day/19403"
            ),
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["ema", "rsi"]

    @property
    def warmup_bars(self) -> int:
        # §3: RSI(10) needs >= 11 bars and EMA(10) ~10 bars to stabilise; the
        # spec declares a 50-bar warmup so every input is fully formed before
        # the first decision bar.
        return 50

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h1 = frames[self.metadata.primary_granularity]

        close = h1["Close"]
        # §3: the RSI input is the median price of each bar. High and Low both
        # belong to bar t and are complete at its close, so this is trailing
        # data. A new Series is built; the frame handed in is never written to.
        median_price = (h1["High"] + h1["Low"]) / 2.0

        ema_fast = ema(close, self.EMA_FAST_PERIOD).to_numpy(dtype=float)
        ema_slow = ema(close, self.EMA_SLOW_PERIOD).to_numpy(dtype=float)
        rsi_median = rsi(median_price, self.RSI_PERIOD).to_numpy(dtype=float)
        close_values = close.to_numpy(dtype=float)
        index = h1.index

        orders: List[OrderIntent] = []
        for i in range(max(self.warmup_bars, 1), len(h1)):
            # Bar t-1 is needed by both crosses, so a NaN there is not a
            # "condition is false" — it is an unknowable condition. Skip it.
            # (indicators.rsi is NaN on the first bar of any series.)
            if (
                np.isnan(ema_fast[i])
                or np.isnan(ema_slow[i])
                or np.isnan(ema_fast[i - 1])
                or np.isnan(ema_slow[i - 1])
                or np.isnan(rsi_median[i])
                or np.isnan(rsi_median[i - 1])
            ):
                continue

            # §4.1 / §5.1 — the EMA cross must happen AT bar i. Equality on the
            # prior bar counts as not-yet-crossed, so it still admits a cross.
            ema_cross_up = (
                ema_fast[i] > ema_slow[i] and ema_fast[i - 1] <= ema_slow[i - 1]
            )
            ema_cross_down = (
                ema_fast[i] < ema_slow[i] and ema_fast[i - 1] >= ema_slow[i - 1]
            )
            # §4.2 / §5.2 / §10 #7 — strict two-sided cross of the 50 midline,
            # with `<= 50` / `>= 50` on the prior bar (matches the pseudocode's
            # `shift() <= 50`).
            rsi_cross_up = (
                rsi_median[i] > self.RSI_LEVEL and rsi_median[i - 1] <= self.RSI_LEVEL
            )
            rsi_cross_down = (
                rsi_median[i] < self.RSI_LEVEL and rsi_median[i - 1] >= self.RSI_LEVEL
            )

            # Strict same-bar conjunction (§4, §5, §10 #1).
            if ema_cross_up and rsi_cross_up:
                direction: Direction = 1
            elif ema_cross_down and rsi_cross_down:
                direction = -1
            else:
                continue

            decision_close = float(close_values[i])
            pip = _pip_size_from_price(decision_close)

            # §6/§7 — all geometry anchored to C_t. `direction` flips every
            # level, so the short plan is the exact mirror of the long plan.
            stop_price = decision_close - direction * self.STOP_PIPS * pip
            be_price = decision_close + direction * self.BE_TRIGGER_PIPS * pip
            tp1_price = decision_close + direction * self.TP1_PIPS * pip

            orders.append(
                OrderIntent(
                    decision_bar=index[i],
                    direction=direction,
                    # §4/§5 — market entry; the fill is the open of bar t+1
                    # (F1/F2) and its price is unknowable here, hence
                    # entry_price=None and no pending-side check to make.
                    entry="market",
                    entry_price=None,
                    decision_close=decision_close,
                    stop=StopRule(
                        price=stop_price,
                        # §6 — names the leg defined below; the contract rejects
                        # a breakeven trigger with no matching label.
                        move_to_breakeven_on=self.BE_LABEL,
                        breakeven_offset_pips=0.0,
                        # §6/§10 #4 — the author's open-ended P&L ladder is
                        # inexpressible in contract v2; no ATR trail is invented
                        # in its place, so the stop stays at breakeven.
                        trail_atr_multiple=None,
                    ),
                    exits=[
                        ExitLeg(
                            fraction=self.BE_TRIGGER_FRACTION,
                            kind="take_profit",
                            price=be_price,
                            label=self.BE_LABEL,
                        ),
                        ExitLeg(
                            fraction=self.TP1_FRACTION,
                            kind="take_profit",
                            price=tp1_price,
                            label=self.TP1_LABEL,
                        ),
                    ],
                    # §4 — a market order is not pending, so there is no expiry
                    # to run down (spec: expires_after_bars = null).
                    expires_after_bars=None,
                    tag="amazing_crossover",
                    strategy_id=self.metadata.strategy_id,
                )
            )
        return orders
