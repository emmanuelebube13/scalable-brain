"""INSIDE_BAR_CONTINUATION_EA — inside-bar breakout continuation.

Source: row 39 of ``forex_swing_strategies.csv`` ·
https://www.mql5.com/en/code/73884

A large, high-commitment candle (the Main Bar: wide range relative to ATR,
body dominating its range) marks a burst of directional order flow. When the
very next bar (the Signal Bar) is fully contained inside the Main Bar and
small, the market is pausing to absorb that flow rather than reversing it, so
a breakout through the Main Bar's extreme in the direction of the original
burst is traded as a continuation. See ``SPEC-inside_bar_continuation_ea.md``
for the full derivation, the causality audit (§9) and the eleven resolved
ambiguities (§10).

Single-timeframe (H4), no context granularities. Every input the entry rules
use — the Main Bar's OHLC, the Signal Bar's OHLC, and ATR14 computed on bars
up to and including the Signal Bar — is fully known at the Signal Bar's own
close, so there is no confirmation lag to honour beyond ordinary bar-close
causality (spec §9).
"""

from __future__ import annotations

from typing import List, Mapping, Sequence

import numpy as np
import pandas as pd

from ..contract_v2 import (
    Direction,
    EntryKind,
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)
from ...data_access.indicators import atr


def _bar_range(df: pd.DataFrame) -> np.ndarray:
    """``rng[k] = High[k] - Low[k]`` (spec §3; not an inventory indicator)."""
    return (df["High"] - df["Low"]).to_numpy(dtype=float)


def _bar_body(df: pd.DataFrame) -> np.ndarray:
    """``body[k] = abs(Close[k] - Open[k])`` (spec §3; not an inventory indicator)."""
    return (df["Close"] - df["Open"]).abs().to_numpy(dtype=float)


class InsideBarContinuationEA(StrategyV2):
    """Trade the breakout of a Main Bar's extreme after a contained Signal Bar."""

    ATR_PERIOD = 14  # spec §3: ATR (Wilder) period, inventory atr(...)
    BODY_DOMINANCE_FRAC = 0.5  # spec §4.2 / §5.2
    RANGE_ATR_MULT = 1.5  # spec §4.3 / §5.3 (ATR filter ON, §10 row 3)
    INSIDE_MAX_FRAC = 0.5  # spec §4.5 / §5.5
    SL_FRACTION = 0.62  # spec §6 (§10 row 6: the only documented value)
    RR = 1.0  # spec §7 / §10 row 1 (declared RR = 1.0)
    EXPIRES_AFTER_BARS = 1  # spec §4 / §5 / §10 row 2

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="inside_bar_continuation_ea",
            name="Inside Bar Continuation EA",
            version="0.1.0",
            author="wave2-fleet",
            hypothesis=(
                "A large, high-commitment candle (the Main Bar: wide range "
                "relative to ATR, body dominating its range) marks a burst of "
                "directional order flow; when the very next bar is fully "
                "contained inside it and small (the Signal Bar), the market is "
                "pausing to absorb that flow rather than reversing it, so a "
                "breakout through the Main Bar's extreme in the direction of "
                "the original burst is a continuation with favourable odds. "
                "The edge should persist because inside bars after impulse "
                "moves are a footprint of short-term volatility compression "
                "and trapped counter-trend entries whose stops cluster just "
                "beyond the mother bar's extremes, fuelling the breakout once "
                "it triggers."
            ),
            granularities=["H4"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="H4",
            context_granularities=(),
            simulate_on="H1",
            source_row=39,
            source_url="https://www.mql5.com/en/code/73884",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["atr"]

    @property
    def warmup_bars(self) -> int:
        # Enough completed H4 bars for ATR14 to have stabilised.
        return self.ATR_PERIOD * 3

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h4 = frames["H4"]

        high = h4["High"].to_numpy(dtype=float)
        low = h4["Low"].to_numpy(dtype=float)
        open_ = h4["Open"].to_numpy(dtype=float)
        close = h4["Close"].to_numpy(dtype=float)
        rng = _bar_range(h4)
        body = _bar_body(h4)
        atr_values = atr(
            h4["High"], h4["Low"], h4["Close"], period=self.ATR_PERIOD
        ).to_numpy(dtype=float)
        index = h4.index

        orders: List[OrderIntent] = []
        start = max(self.warmup_bars, 1)
        for t in range(start, len(h4)):
            prev = t - 1

            rng_prev = rng[prev]
            body_prev = body[prev]
            rng_t = rng[t]
            atr_t = atr_values[t]
            if (
                np.isnan(rng_prev)
                or np.isnan(body_prev)
                or np.isnan(rng_t)
                or np.isnan(atr_t)
            ):
                continue

            # spec §4.4 / §5.4 — Signal Bar strictly inside the Main Bar.
            if not (high[t] < high[prev] and low[t] > low[prev]):
                continue
            # spec §4.5 / §5.5 — Signal Bar size constraint.
            if not (rng_t <= self.INSIDE_MAX_FRAC * rng_prev):
                continue
            # spec §4.2 / §5.2 — Main Bar body dominance.
            if not (body_prev >= self.BODY_DOMINANCE_FRAC * rng_prev):
                continue
            # spec §4.3 / §5.3 — Main Bar size filter (ATR filter ON).
            if not (rng_prev >= self.RANGE_ATR_MULT * atr_t):
                continue

            open_prev = open_[prev]
            close_prev = close[prev]
            if close_prev == open_prev:
                # Neither bullish (§4.1) nor bearish (§5.1); the source
                # imposes no separate doji rule, but a flat Main Bar
                # satisfies neither directional gate, so there is no setup.
                continue
            direction: Direction = 1 if close_prev > open_prev else -1

            risk = self.SL_FRACTION * rng_prev
            if risk <= 0:
                continue

            if direction == 1:
                entry_kind: EntryKind = "buy_stop"
                entry_price = float(high[prev])  # spec §4: High[t-1] exactly
                stop_price = entry_price - risk
                tp_price = entry_price + self.RR * risk
            else:
                entry_kind = "sell_stop"
                entry_price = float(low[prev])  # spec §5: Low[t-1] exactly
                stop_price = entry_price + risk
                tp_price = entry_price - self.RR * risk

            orders.append(
                OrderIntent(
                    decision_bar=index[t],
                    direction=direction,
                    entry=entry_kind,
                    entry_price=entry_price,
                    decision_close=float(close[t]),
                    stop=StopRule(
                        price=stop_price,
                        move_to_breakeven_on=None,
                        breakeven_offset_pips=0.0,
                        trail_atr_multiple=None,
                    ),
                    exits=[
                        ExitLeg(
                            fraction=1.0,
                            kind="take_profit",
                            price=tp_price,
                            label="TP1",
                        )
                    ],
                    expires_after_bars=self.EXPIRES_AFTER_BARS,
                    tag="inside_bar_continuation_ea",
                    strategy_id=self.strategy_id,
                )
            )
        return orders
