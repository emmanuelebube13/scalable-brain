"""bb_midline_break — Bollinger 2σ excursion, then a decisive midline break.

Spec: ``task/2026-W32/fleet/upload/wave2/specs/SPEC-bb_midline_break.md``
(row 28 of ``forex_swing_strategies.csv``).

Shape and conventions follow ``reference_pullback_continuation.py``. Three of its
four NOTES do not bind here and the reason is recorded so a reviewer does not
have to re-derive it:

* **NOTE 1 (causal MTF join)** — not applicable. Spec §2 declares
  ``context_granularities: none``; this is a single-frame H4 strategy, so no
  context frame is read at all and ``closed_context_frame`` is not needed.
* **NOTE 2 (causal swing structure)** — not applicable. Spec §3 states that no
  swing/ZigZag/pivot/fractal detection is used anywhere, so neither
  ``causal_structure`` nor the banned ``indicators.detect_swing_points`` is
  imported.
* **NOTE 3 (pending entry on the right side of the close)** — not applicable.
  Spec §4/§5 emit ``market`` entries only (``entry_price=None``), so there is no
  pending level to validate and no pending-overlap risk (§10 #7).
* **NOTE 4 (breakeven names an existing leg)** — spec §6 declares
  ``move_to_breakeven_on: none``, so the stop is static and no label is named.

The only causality subtlety that *does* bind is the band-touch state: the touch
must occur on one of bars t−5 … t−1, never on bar t itself (§9, §10 #2). That is
expressed as a rolling 5-bar OR **shifted one bar**, mirroring the source
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
    """Fade a 2σ Bollinger excursion once a large candle closes back across the mean."""

    BB_PERIOD = 20  # §3 Bollinger Bands period
    BB_STD = 2.0  # §3 Bollinger Bands std_dev
    BODY_PERIOD = 20  # §3 avg_body = sma(body, 20), window INCLUDES bar t (§10 #10)
    BODY_MULTIPLE = 1.5  # §4.3 / §5.3 body[t] > 1.5 x avg_body[t]
    CLOSE_QUARTILE = 0.25  # §4.4 / §5.4 close in the extreme quarter of the range
    TOUCH_LOOKBACK = 5  # §4.1 / §5.1 touch on one of bars t-5 ... t-1 (§10 #1)
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
                "After price stretches to or beyond a 2-sigma Bollinger Band — a "
                "statistically extreme excursion relative to the last 20 bars — and "
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
            # §2 pairs_available, live only. The eight Wave-1 "pending" additions
            # are deliberately excluded (see REPORT Uncertainties).
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
        # The deepest chain is the band-touch state: bands need BB_PERIOD closes
        # (valid from index BB_PERIOD-1) and the touch window reaches back
        # TOUCH_LOOKBACK bars from t-1, so the first fully-defined decision bar is
        # BB_PERIOD - 1 + TOUCH_LOOKBACK = 24. Doubling the band period leaves
        # comfortable margin without being a tuned quantity.
        return 2 * self.BB_PERIOD

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h4 = frames[self.metadata.primary_granularity]

        upper_s, mid_s, lower_s = bollinger_bands(
            h4["Close"], period=self.BB_PERIOD, std_dev=self.BB_STD
        )

        # §3 / §4.3: body and its 20-bar mean, the window INCLUDING bar t.
        body_s = (h4["Close"] - h4["Open"]).abs()
        avg_body_s = sma(body_s, self.BODY_PERIOD)

        # §4.1 / §5.1: each bar j is judged against its OWN contemporaneous band,
        # then the 5-bar OR is shifted one bar so bar t can never be its own touch
        # bar (§9, §10 #2). NaN bands compare False and never create a touch.
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
        upper = upper_s.to_numpy(dtype=float)
        mid = mid_s.to_numpy(dtype=float)
        lower = lower_s.to_numpy(dtype=float)
        body = body_s.to_numpy(dtype=float)
        avg_body = avg_body_s.to_numpy(dtype=float)
        prior_low_touch = prior_low_touch_s.to_numpy(dtype=float)
        prior_high_touch = prior_high_touch_s.to_numpy(dtype=float)
        index = h4.index

        orders: List[OrderIntent] = []
        for i in range(max(self.warmup_bars, 1), len(h4)):
            # Every comparison below is False when an input is NaN, so warmup and
            # data gaps suppress signals rather than inventing them.
            body_ok = body[i] > self.BODY_MULTIPLE * avg_body[i]
            if not body_ok:
                continue
            bar_range = high[i] - low[i]

            direction: Direction
            if (
                prior_low_touch[i] == 1.0  # §4.1 lower-band touch on t-5 ... t-1
                and close[i] > mid[i]  # §4.2 cross-up, part 1
                and close[i - 1] <= mid[i - 1]  # §4.2 cross-up, part 2
                and close[i]
                >= high[i] - self.CLOSE_QUARTILE * bar_range  # §4.4 top quartile
                and close[i] > open_[i]  # §4.5 bullish candle
            ):
                direction = 1
                stop_price = low[i]  # §6 exact low of the breakout candle
            elif (
                prior_high_touch[i] == 1.0  # §5.1 upper-band touch on t-5 ... t-1
                and close[i] < mid[i]  # §5.2 cross-down, part 1
                and close[i - 1] >= mid[i - 1]  # §5.2 cross-down, part 2
                and close[i]
                <= low[i] + self.CLOSE_QUARTILE * bar_range  # §5.4 bottom quartile
                and close[i] < open_[i]  # §5.5 bearish candle
            ):
                direction = -1
                stop_price = high[i]  # §6 exact high of the breakout candle
            else:
                continue

            # §6: R is declared from the anchor C = close[t] (the fill price at the
            # t+1 open is unknowable at emission). The quartile conditions make
            # R >= 0.75 x range, but a degenerate bar is still skipped rather than
            # emitted with a non-positive R.
            anchor = close[i]
            risk = abs(anchor - stop_price)
            if not risk > 0.0:
                continue

            orders.append(
                OrderIntent(
                    decision_bar=index[i],
                    direction=direction,
                    # §4/§5: "buy at the close of that breakout candle" is realised
                    # as a market intent decided at close[t] and filled at the open
                    # of t+1 per F1/F2 (§10 #8).
                    entry="market",
                    entry_price=None,
                    decision_close=anchor,
                    # §6: static stop at the candle extreme, zero buffer (§10 #5),
                    # no breakeven move and no trail.
                    stop=StopRule(price=stop_price),
                    exits=[
                        # §7: single full-size leg at 1.5R. This is a SUBSTITUTE for
                        # the documented midline-crossback exit, which is
                        # inexpressible in contract v2 (§10 #4).
                        ExitLeg(
                            fraction=1.0,
                            kind="take_profit",
                            price=anchor + direction * self.TP_R_MULTIPLE * risk,
                            label="TP1",
                        )
                    ],
                    # §4/§5: N/A for market entries.
                    expires_after_bars=None,
                    tag="bb_midline_break",
                    strategy_id=self.strategy_id,
                )
            )
        return orders
