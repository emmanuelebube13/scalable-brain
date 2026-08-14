"""Amazing Crossover — EMA(5)/EMA(10) cross confirmed by RSI(10, median) at 50.

Source: row 34 of ``forex_swing_strategies.csv`` ·
https://forums.babypips.com/t/amazing-crossover-system-100-pips-per-day/19403
Spec: ``task/2026-W32/fleet/upload/wave2/specs/SPEC-amazing_crossover.md``.

Single-frame H1 strategy (spec §2: ``context_granularities: none``), so there is
no context frame to join and NOTE 1 of the reference strategy does not apply
here — nothing in this module reads any frame other than the primary H1 one.
No swing structure, ZigZag, pivots or fractals are used anywhere (spec §3), so
``detect_swing_points`` is not merely avoided, it has no role to play.

Shape notes, mapped to the spec:

* §4/§5 — the entry is a **strict same-bar conjunction**: the EMA cross and the
  RSI-50 cross must both occur at decision bar ``t``. Two conditions that
  merely both *hold* at ``t`` are not enough; each must have flipped between
  ``t-1`` and ``t``.
* §3 — RSI is computed on the **median price** ``(High + Low) / 2``, not on
  Close. That derivation is the only "new" maths in the file and is done
  inline from the frame the strategy is handed (never written back to it).
* §6/§7 — every level is anchored to ``C_t``, the close of the decision bar,
  because the entry is a market order whose fill price (open of ``t+1``) is
  unknowable at emission.
"""

from __future__ import annotations

from typing import List, Mapping, Optional, Sequence

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


class AmazingCrossover(StrategyV2):
    """H1 EMA5/EMA10 cross that must be confirmed by RSI(10, median) crossing 50."""

    EMA_FAST_PERIOD = 5  # spec §3 — EMA on Close, period 5
    EMA_SLOW_PERIOD = 10  # spec §3 — EMA on Close, period 10
    RSI_PERIOD = 10  # spec §3 — RSI on the median price, period 10
    RSI_LEVEL = 50.0  # spec §3/§4.2 — the midline that must be crossed
    STOP_PIPS = 100.0  # spec §6 — initial stop, 100 pips from C_t
    BE_TRIGGER_PIPS = 20.0  # spec §7 — first rung: +20 pips
    BE_TRIGGER_FRACTION = 0.10  # spec §7/§10 #5 — declared interpretive choice
    TP1_PIPS = 50.0  # spec §7/§10 #2 — lower bound of the "50-100 pip" band
    TP1_FRACTION = 0.90  # 0.10 + 0.90 = 1.0 exactly
    BE_LABEL = "BE_TRIGGER"  # named by StopRule.move_to_breakeven_on (§6)
    TP1_LABEL = "TP1"

    def __init__(self, pair: Optional[str] = None) -> None:
        """``pair`` only selects the pip size (``0.0001`` vs ``0.01`` for JPY).

        The v2 harness does not pass the pair into the strategy, and the
        registry instantiates with no arguments, so the default reproduces the
        reference strategy's behaviour (``metadata.pairs[0]``). It is a
        constructor argument so a pair-aware caller can size a USD_JPY stop in
        yen pips rather than in EUR_USD pips — see the report's Uncertainties.
        """
        self._pair = pair or self.metadata.pairs[0]

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
            # Spec §2 pairs_available (live only). USD_CHF and NZD_USD are
            # declared PENDING backfill there and so are deliberately omitted.
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="H1",
            context_granularities=(),  # spec §2 — single-frame strategy
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
        # Spec §3: RSI(10) needs >= 11 bars and EMA(10) ~10 to stabilise; the
        # spec declares a 50-bar warmup so every input is fully formed.
        return 50

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h1 = frames["H1"]
        pip = float(get_pip_value(self._pair))

        close = h1["Close"]
        # Spec §3: the RSI input is the median price of each bar. Both High and
        # Low belong to bar t and are complete at its close, so this is trailing
        # data. A new Series is built; the frame handed in is never written to.
        median_price = (h1["High"] + h1["Low"]) / 2.0

        ema_fast = ema(close, self.EMA_FAST_PERIOD).to_numpy(dtype=float)
        ema_slow = ema(close, self.EMA_SLOW_PERIOD).to_numpy(dtype=float)
        rsi_med = rsi(median_price, self.RSI_PERIOD).to_numpy(dtype=float)
        close_values = close.to_numpy(dtype=float)
        index = h1.index

        orders: List[OrderIntent] = []
        for i in range(max(self.warmup_bars, 1), len(h1)):
            # Bar t-1 is needed for both crosses, so a NaN there is not a
            # "condition false" — it is an unknowable condition. Skip.
            if (
                np.isnan(ema_fast[i])
                or np.isnan(ema_slow[i])
                or np.isnan(ema_fast[i - 1])
                or np.isnan(ema_slow[i - 1])
                or np.isnan(rsi_med[i])
                or np.isnan(rsi_med[i - 1])
            ):
                continue

            # §4.1 / §5.1 — the EMA cross must happen AT bar i (equality on the
            # prior bar counts as not-yet-crossed).
            ema_cross_up = (
                ema_fast[i] > ema_slow[i] and ema_fast[i - 1] <= ema_slow[i - 1]
            )
            ema_cross_down = (
                ema_fast[i] < ema_slow[i] and ema_fast[i - 1] >= ema_slow[i - 1]
            )
            # §4.2 / §5.2 / §10 #7 — strict two-sided cross of the 50 midline.
            rsi_cross_up = (
                rsi_med[i] > self.RSI_LEVEL and rsi_med[i - 1] <= self.RSI_LEVEL
            )
            rsi_cross_down = (
                rsi_med[i] < self.RSI_LEVEL and rsi_med[i - 1] >= self.RSI_LEVEL
            )

            # Strict same-bar conjunction (§4, §5, §10 #1).
            if ema_cross_up and rsi_cross_up:
                direction: Direction = 1
            elif ema_cross_down and rsi_cross_down:
                direction = -1
            else:
                continue

            decision_close = float(close_values[i])

            # §6/§7 — all geometry anchored to C_t. `direction` flips every leg,
            # so the short plan is the exact mirror of the long plan.
            stop_price = decision_close - direction * self.STOP_PIPS * pip
            be_price = decision_close + direction * self.BE_TRIGGER_PIPS * pip
            tp1_price = decision_close + direction * self.TP1_PIPS * pip

            orders.append(
                OrderIntent(
                    decision_bar=index[i],
                    direction=direction,
                    # §4/§5 — market entry; the fill is the open of bar t+1
                    # (F1/F2) and its price is unknowable here, hence
                    # entry_price=None and no pending-order side check.
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
                        # inexpressible; no ATR trail is invented in its place.
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
                    # §4 — a market order is not pending, so there is no
                    # expiry to run down.
                    expires_after_bars=None,
                    tag="amazing_crossover",
                    strategy_id=self.metadata.strategy_id,
                )
            )
        return orders
