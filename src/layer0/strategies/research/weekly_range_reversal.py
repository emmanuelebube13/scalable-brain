"""Weekly Range Reversal — SPEC-weekly_range_reversal.md (CSV row 27).

Fade the outer eighth of a trailing two-week H1 range when an ultra-slow CCI(2000)
turns back from a washed-out extreme, targeting the middle of that range, with a
stop one pip beyond the extreme and at most one setup per pair per FX week.

Everything is computed on the single H1 decision frame: the "two weeks" of the
source is 336 H1 bars (2 x 168), not a W1 context frame, so no multi-timeframe
alignment is involved (§2, §10 #10).

NOTE 1 — the range levels are a TRAILING window, not swing structure. `lo2w[t]`
    may move as new lows print; that is causal (a trailing extremum) and needs no
    confirmation lag, which is exactly why §10 #1 rejects the source's
    discretionary "trendline across the last two CCI peaks" in favour of the
    pseudocode's 10/90 cross. No swing/pivot/fractal construct appears here.

NOTE 2 — the CCI arming window is `CCI[t-24 … t-1]`, strictly BEFORE the decision
    bar (§4.4, §10 #9). It is built as `cci.shift(1).rolling(24)`, so the touch can
    never be satisfied by the same bar that produced the cross — which is the
    logically impossible reading §10 #9 rejects.

NOTE 3 — the weekly throttle (§4.5, §10 #7) is one slot per FX week per pair,
    shared by both directions, and is consumed only by an intent that is actually
    emitted. The FX week opens Sunday 21:00 UTC; bars are stamped at their open, so
    adding 3h maps every bar onto its own trading day and the ISO week of that day
    is the FX week. This is strategy-internal state derived from its own prior
    emissions — never from fills, which a v2 strategy cannot observe.

NOTE 4 — the pair is never passed to a v2 strategy, so the 1-pip stop buffer (§6)
    infers its quote convention from the decision bar's own close, the way
    ``amazing_crossover`` and ``ema_cross_h4_filter_bot`` already do. The pip
    magnitudes still come from the inventory ``get_pip_value``.

NOTE 5 — §4.6/§5.6's reward:risk floor is a HARD GATE, not a target adjustment: a
    setup whose 50%-of-range target does not pay at least 2x the distance to the
    zone-edge stop is dropped (§10 #4). Stretching the target until it passes is
    exactly the curve-fit that rule exists to forbid.
"""

from __future__ import annotations

from typing import List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from ...data_access.indicators import cci, get_pip_value
from ..contract_v2 import (
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)

#: Above this quote level an instrument is JPY-quoted (USD_JPY ~ 150, majors ~ 1).
_JPY_QUOTE_THRESHOLD = 20.0


def _pip_size_from_price(price: float) -> float:
    """Pip size for the instrument whose quote is ``price`` (NOTE 4)."""
    pair = "USD_JPY" if price >= _JPY_QUOTE_THRESHOLD else "EUR_USD"
    return float(get_pip_value(pair))


class WeeklyRangeReversal(StrategyV2):
    """Fade the outer eighth of a trailing two-week H1 range on a CCI turn."""

    CCI_PERIOD = 2000  # §3, §10 #2: midpoint of the author's 1800-2200 band
    RANGE_BARS = 336  # §3: two weeks of H1 bars (2 x 168)
    TOUCH_LOOKBACK = 24  # §4.4/§5.4, §10 #9: one trading day of arming
    ZONE_FRACTION = 0.125  # §3: the outer eighth of the range
    TARGET_FRACTION = 0.50  # §7, §10 #3: 50% of the range, not 62.5%
    LONG_CROSS = 10.0  # §4.3
    LONG_TOUCH = 5.0  # §4.4
    SHORT_CROSS = 90.0  # §5.3
    SHORT_TOUCH = 95.0  # §5.4
    STOP_BUFFER_PIPS = 1.0  # §6, §10 #5: "just beyond", tightest reading
    MIN_REWARD_RISK = 2.0  # §4.6/§5.6, §10 #4

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="weekly_range_reversal",
            name="Weekly Range Reversal (2-week zone fade, CCI 2000)",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "On a two-week horizon FX prices spend most of their time ranging, so "
                "when price reaches the outer eighth of its trailing two-week range "
                "while the ultra-long CCI(2000) shows momentum has washed out to a "
                "stretched extreme and is now turning back, the odds favour reversion "
                "toward the middle of that range rather than an immediate breakout. "
                "Breakout attempts at fortnightly extremes fail more often than they "
                "succeed in non-trending regimes, the 2000-period CCI filters out "
                "noise-level dips so only genuinely stretched moves are faded, and the "
                "enforced minimum 1:2 reward-to-risk means the strategy can be wrong "
                "more often than right and still profit."
            ),
            granularities=["H1"],
            # §2 pairs_available, live subset: GBP_USD is the author's tradeable
            # headline pair; GBP_CAD (his first choice) does not exist here.
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="H1",
            context_granularities=(),  # §2: the two-week range is an H1 window
            simulate_on="H1",
            source_row=27,
            source_url="https://forex-station.com/simple-trading-system-t8476248.html",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["cci", "get_pip_value"]

    @property
    def warmup_bars(self) -> int:
        # §4.1: CCI(2000) dominates the 336-bar range window.
        return self.CCI_PERIOD

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h1 = frames[self.metadata.primary_granularity]
        if len(h1) <= self.warmup_bars:
            return []

        high = h1["High"]
        low = h1["Low"]
        hi2w = high.rolling(self.RANGE_BARS).max().to_numpy(dtype=float)
        lo2w = low.rolling(self.RANGE_BARS).min().to_numpy(dtype=float)

        cci_series = cci(high, low, h1["Close"], period=self.CCI_PERIOD)
        cci_values = cci_series.to_numpy(dtype=float)
        # NOTE 2: the arming window ends one bar BEFORE the decision bar.
        prior = cci_series.shift(1).rolling(self.TOUCH_LOOKBACK)
        touch_low = prior.min().to_numpy(dtype=float)
        touch_high = prior.max().to_numpy(dtype=float)

        # NOTE 3: FX week (opens Sunday 21:00 UTC) as a comparable timestamp.
        session = h1.index + pd.Timedelta(hours=3)
        week_key = (
            session.normalize() - pd.to_timedelta(session.weekday, unit="D")
        ).to_numpy()

        close = h1["Close"].to_numpy(dtype=float)
        index = h1.index

        orders: List[OrderIntent] = []
        week_used: object = None

        for i in range(max(self.warmup_bars, 1), len(h1)):
            if week_key[i] == week_used:  # §4.5/§5.5: one setup per week per pair
                continue
            top = hi2w[i]
            bottom = lo2w[i]
            cci_t = cci_values[i]
            cci_prev = cci_values[i - 1]
            if not (np.isfinite(top) and np.isfinite(bottom)):
                continue
            if not (np.isfinite(cci_t) and np.isfinite(cci_prev)):
                continue
            span = float(top - bottom)
            if span <= 0.0:
                continue

            close_t = float(close[i])
            pip = _pip_size_from_price(close_t)
            target = float(bottom) + self.TARGET_FRACTION * span  # §7: the mid
            zone_low = float(bottom) + self.ZONE_FRACTION * span
            zone_high = float(bottom) + (1.0 - self.ZONE_FRACTION) * span

            intent: Optional[OrderIntent] = None

            # -- §4 long: bottom eighth of the range, CCI crossing back up ------
            if (
                close_t <= zone_low
                and cci_t > self.LONG_CROSS
                and cci_prev <= self.LONG_CROSS
                and np.isfinite(touch_low[i])
                and touch_low[i] <= self.LONG_TOUCH
            ):
                stop_price = float(bottom) - self.STOP_BUFFER_PIPS * pip
                # NOTE 5: §4.6 reward:risk floor, a gate rather than a nudge.
                if target - close_t >= self.MIN_REWARD_RISK * (close_t - stop_price):
                    intent = self._intent(index[i], 1, close_t, stop_price, target)

            # -- §5 short: the exact mirror at the top eighth --------------------
            elif (
                close_t >= zone_high
                and cci_t < self.SHORT_CROSS
                and cci_prev >= self.SHORT_CROSS
                and np.isfinite(touch_high[i])
                and touch_high[i] >= self.SHORT_TOUCH
            ):
                stop_price = float(top) + self.STOP_BUFFER_PIPS * pip
                if close_t - target >= self.MIN_REWARD_RISK * (stop_price - close_t):
                    intent = self._intent(index[i], -1, close_t, stop_price, target)

            if intent is not None:
                orders.append(intent)
                week_used = week_key[i]
        return orders

    def _intent(
        self,
        decision_bar: pd.Timestamp,
        direction: int,
        decision_close: float,
        stop_price: float,
        target: float,
    ) -> OrderIntent:
        return OrderIntent(
            decision_bar=decision_bar,
            direction=1 if direction > 0 else -1,
            entry="market",  # §4/§5: fills at the open of bar t+1 (F1/F2)
            entry_price=None,
            decision_close=decision_close,
            stop=StopRule(price=stop_price),  # §6: static, no breakeven, no trail
            exits=[
                ExitLeg(
                    fraction=1.0,
                    kind="take_profit",
                    price=target,
                    label="TP1",
                )
            ],
            expires_after_bars=None,  # §4/§5: a market intent is never pending
            tag="range_fade",
            strategy_id=self.strategy_id,
        )
