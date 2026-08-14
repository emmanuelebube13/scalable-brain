"""bb_midline_break — Bollinger 2-sigma excursion, then a decisive midline break.

Spec: ``task/2026-W32/fleet/upload/wave2/specs/SPEC-bb_midline_break.md``
(row 28 of ``forex_swing_strategies.csv``).

Shape and conventions follow ``reference_pullback_continuation.py``. All four of
its numbered NOTES were checked against this spec; the reason each one does or
does not bind is recorded here so a reviewer does not have to re-derive it:

* **NOTE 1 (causal MTF join)** — does not bind. Spec §2 declares
  ``context_granularities: none``: this is a single-frame H4 strategy, no context
  frame is read at all, so neither ``closed_context_frame`` nor the
  ``merge_asof`` form is needed. D1/W1 are sanctioned *alternative primaries*
  (§10 #9), never context frames.
* **NOTE 2 (causal swing structure)** — does not bind. Spec §3 states that no
  swing/ZigZag/pivot/fractal detection is used anywhere, so neither
  ``causal_structure`` nor the banned ``indicators.detect_swing_points`` is
  imported, and §9 declares no confirmation lag.
* **NOTE 3 (pending entry on the right side of the close)** — does not bind.
  Spec §4/§5 emit ``market`` entries only (``entry_price=None``), so there is no
  pending level to validate against the decision close and no pending-overlap
  risk (§10 #7). ``decision_close`` is still carried for the engine's records.
* **NOTE 4 (breakeven names an existing leg)** — does not bind. Spec §6 declares
  ``move_to_breakeven_on: none`` and ``trail: none``, so the stop is static and
  no leg label is referenced.

The one causality subtlety that *does* bind is the band-touch state: the touch
must occur on one of bars t-5 … t-1 and never on bar t itself (§9, §10 #2). That
is expressed as a rolling 5-bar OR **shifted one bar**, mirroring the source
pseudocode's ``(low <= lower).rolling(5).max().shift(1)``.
"""

from __future__ import annotations

from typing import List, Mapping, Sequence

import pandas as pd

from ..contract_v2 import (
    Direction,
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)
from ...data_access.indicators import bollinger_bands, sma


class BollingerMidlineBreak(StrategyV2):
    """Fade a 2-sigma Bollinger excursion once a big candle closes back over the mean."""

    BB_PERIOD = 20  # §3 Bollinger Bands period
    BB_STD = 2.0  # §3 Bollinger Bands std_dev
    BODY_PERIOD = 20  # §3 avg_body = sma(body, 20); window INCLUDES bar t (§10 #10)
    BODY_MULTIPLE = 1.5  # §4.3 / §5.3 body[t] > 1.5 x avg_body[t]
    CLOSE_QUARTILE = 0.25  # §4.4 / §5.4 close in the extreme quarter of the range
    TOUCH_LOOKBACK = 5  # §4.1 / §5.1 touch on one of bars t-5 … t-1 (§10 #1)
    TP_R_MULTIPLE = 1.5  # §7 single take-profit leg at 1.5R

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="bb_midline_break",
            name="Bollinger Midline Break",
            version="0.1.0",
            author="wave2-fleet",
            hypothesis=(
                "After price stretches to or beyond a 2-sigma Bollinger Band - a "
                "statistically extreme excursion relative to the last 20 bars - and "
                "then a large-bodied candle closes back across the 20-bar mean with "
                "its close at the candle's extreme, the move marks exhaustion of the "
                "band-side move and the start of a momentum swing away from the band. "
                "The edge should persist because Bollinger extremes are where "
                "short-term mean-reversion flow (profit-taking from the prior move, "
                "plus breakout-fade orders resting at round statistical levels) meets "
                "stopped-out late entrants; a decisive close back through the widely "
                "watched 20-period mean forces the band-side crowd to unwind "
                "simultaneously, giving the reversal follow-through rather than a "
                "one-bar blip. The author rates it MODERATE: the rules are fully "
                "mechanical but no backtest is documented on the source page."
            ),
            granularities=["H4"],
            # §2 pairs_available, LIVE only. The eight Wave-1 "pending" additions are
            # deliberately excluded per the run brief ("never a pair the spec lists as
            # missing/pending"); see REPORT Uncertainties.
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="H4",
            context_granularities=(),  # §2: none — single-frame strategy
            simulate_on="H1",  # §2 / contract Part D
            source_row=28,
            source_url="https://tradingstrategyguides.com/swing-trading-strategy/",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["bollinger_bands", "sma"]

    @property
    def warmup_bars(self) -> int:
        """Derived, not chosen.

        The deepest input chain is the band-touch state. The bands need
        ``BB_PERIOD`` closes, so they are first defined at index ``BB_PERIOD - 1``;
        the touch window reaches back ``TOUCH_LOOKBACK`` bars from ``t-1``, so the
        first decision bar whose every input is defined is
        ``BB_PERIOD - 1 + TOUCH_LOOKBACK``. Discarding ``BB_PERIOD + TOUCH_LOOKBACK``
        bars starts one bar past that, which is the conservative side.
        """
        return self.BB_PERIOD + self.TOUCH_LOOKBACK

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h4 = frames[self.metadata.primary_granularity]

        # §3: the inventory Bollinger implementation, used as-is including its std
        # convention (§10 #6) — no private reimplementation.
        upper_s, mid_s, lower_s = bollinger_bands(
            h4["Close"], period=self.BB_PERIOD, std_dev=self.BB_STD
        )

        # §3 / §4.3: body and its 20-bar mean, the window INCLUDING bar t (§10 #10).
        # Self-inclusion is causal (known at t's close) and conservative: a big bar
        # raises its own threshold.
        body_s = (h4["Close"] - h4["Open"]).abs()
        avg_body_s = sma(body_s, self.BODY_PERIOD)

        # §4.1 / §5.1: each bar j is judged against its OWN contemporaneous band
        # value, then the 5-bar OR is shifted one bar so bar t can never serve as its
        # own touch bar (§9, §10 #2). A NaN band compares False, so warmup bars never
        # manufacture a touch.
        prior_low_touch_s = (
            (h4["Low"] <= lower_s)
            .astype(float)
            .rolling(self.TOUCH_LOOKBACK)
            .max()
            .shift(1)
        )
        prior_high_touch_s = (
            (h4["High"] >= upper_s)
            .astype(float)
            .rolling(self.TOUCH_LOOKBACK)
            .max()
            .shift(1)
        )

        open_ = h4["Open"].to_numpy(dtype=float)
        high = h4["High"].to_numpy(dtype=float)
        low = h4["Low"].to_numpy(dtype=float)
        close = h4["Close"].to_numpy(dtype=float)
        mid = mid_s.to_numpy(dtype=float)
        body = body_s.to_numpy(dtype=float)
        avg_body = avg_body_s.to_numpy(dtype=float)
        prior_low_touch = prior_low_touch_s.to_numpy(dtype=float)
        prior_high_touch = prior_high_touch_s.to_numpy(dtype=float)
        index = h4.index

        orders: List[OrderIntent] = []
        # warmup_bars >= 1 by construction, so index i-1 always exists.
        for i in range(max(self.warmup_bars, 1), len(h4)):
            # Every comparison below is False when an input is NaN, so warmup and
            # data gaps suppress signals rather than inventing them.
            if not body[i] > self.BODY_MULTIPLE * avg_body[i]:  # §4.3 / §5.3
                continue
            bar_range = high[i] - low[i]

            direction: Direction
            stop_price: float
            if (
                prior_low_touch[i] == 1.0  # §4.1 lower-band touch on t-5 … t-1
                and close[i] > mid[i]  # §4.2 cross-up, leg 1
                and close[i - 1] <= mid[i - 1]  # §4.2 cross-up, leg 2
                and close[i]
                >= high[i] - self.CLOSE_QUARTILE * bar_range  # §4.4 top quartile
                and close[i] > open_[i]  # §4.5 bullish candle
            ):
                direction = 1
                stop_price = float(low[i])  # §6 exact low of the breakout candle
            elif (
                prior_high_touch[i] == 1.0  # §5.1 upper-band touch on t-5 … t-1
                and close[i] < mid[i]  # §5.2 cross-down, leg 1
                and close[i - 1] >= mid[i - 1]  # §5.2 cross-down, leg 2
                and close[i]
                <= low[i] + self.CLOSE_QUARTILE * bar_range  # §5.4 bottom quartile
                and close[i] < open_[i]  # §5.5 bearish candle
            ):
                direction = -1
                stop_price = float(high[i])  # §6 exact high of the breakout candle
            else:
                continue

            # §6: R is declared from the anchor C = close[t]; the t+1 fill price is
            # unknowable at emission. The quartile conditions force R >= 0.75 x range,
            # but a degenerate bar is skipped rather than emitted with R <= 0.
            anchor = float(close[i])
            risk = abs(anchor - stop_price)
            if not risk > 0.0:
                continue

            orders.append(
                OrderIntent(
                    decision_bar=index[i],
                    direction=direction,
                    # §4/§5: "buy at the close of that breakout candle" is realised as
                    # a market intent decided at close[t] and filled at the open of
                    # t+1 per F1/F2 (§10 #8).
                    entry="market",
                    entry_price=None,
                    decision_close=anchor,
                    # §6: static stop at the candle extreme, zero buffer (§10 #5); no
                    # breakeven move, no trail.
                    stop=StopRule(price=stop_price),
                    exits=[
                        # §7: one full-size leg at 1.5R. This is a SUBSTITUTE for the
                        # documented midline-crossback exit, which is inexpressible in
                        # contract v2 (§10 #4).
                        ExitLeg(
                            fraction=1.0,
                            kind="take_profit",
                            price=anchor + direction * self.TP_R_MULTIPLE * risk,
                            label="TP1",
                        )
                    ],
                    # §4/§5: expires_after_bars is N/A for a market entry.
                    expires_after_bars=None,
                    tag="bb_midline_break",
                    strategy_id=self.strategy_id,
                )
            )
        return orders
