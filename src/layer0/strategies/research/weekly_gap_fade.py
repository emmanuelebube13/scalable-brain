"""Weekly Gap Fade — SPEC-weekly_gap_fade.md (CSV row 3).

Fade the weekend gap: at the close of the week's first H1 bar, if the week opened at
least 5 pips away from the prior Friday's close, take the opposite side and hold
until Friday evening. No take profit, no tactical stop — the exit is time.

NOTE 1 — THE DECISION FRAME IS H1, NOT W1 (§2, §10 #3). The gap is first knowable at
    the close of the week's opening H1 bar; a W1 decision close (Friday 21:00 UTC)
    predates the open being measured, and a D1 decision would arrive ~24h late.

NOTE 2 — THE WEEK BOUNDARY IS DETECTED STRUCTURALLY, NOT BY CLOCK (§4 step 1). §4
    describes the week-opening bar as "stamped Sunday 21:00 UTC" and its predecessor
    as "Friday 20:00 UTC". In this feed those stamps move an hour with DST: 68 of the
    108 week openings in the last two years are stamped 21:00 and 40 are stamped
    22:00. A literal stamp test would therefore veto every winter week — roughly 37%
    of the sample — silently. The check implemented is the pattern §4 step 1 exists to
    assert: the bar opens a new session (its predecessor is more than one H1 bar
    behind), the bar falls on a Sunday, and its predecessor falls on the preceding
    Friday. Holiday-shortened weeks and data holes still fail it, which is the
    intended veto (§10 #7).

NOTE 3 — THE STOP IS CATASTROPHIC, NOT TACTICAL (§6, §10 #1). The source declares no
    stop at all, but ``OrderIntent`` requires one and it is the r-multiple
    denominator. 5 x D1 ATR(14) from the decision close is rarely touched inside a
    five-day hold. Consequence a reviewer must carry into the gate reading: the risk
    unit here is roughly 3-5x wider than an ATR-harness strategy's, so |r| values are
    compressed and are not comparable across strategies without that adjustment.

NOTE 4 — THE TIME EXIT IS COMPUTED FROM THE CALENDAR, NEVER FROM THE FRAME (§7). The
    leg count must not depend on which later bars happen to exist in the frame: that
    is future information, and the truncation probe would (correctly) reject it. The
    count is pure timestamp arithmetic from the decision bar to the coming Friday
    19:00 UTC — 117 bars in a standard 21:00-open week, 116 in a 22:00-open one.

NOTE 5 — the 5-pip threshold is a proxy for "5 x average spread" (§8, §10 #5). No
    spread series exists, so the F10 cost model's 1.0 pip is used. This is LOOSER
    than the author's 2010 GBP/JPY reality (2-4 pip spreads => a 10-20 pip
    threshold), so this implementation trades more, smaller gaps than the documented
    sample. It is the one place where conservatism and the no-invented-data rule
    conflict, and the rule wins.
"""

from __future__ import annotations

from typing import List, Mapping, Sequence

import numpy as np
import pandas as pd

from ...data_access.indicators import atr, get_pip_value
from ..contract_v2 import (
    GRANULARITY_INTERVAL,
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)

#: Above this quote level an instrument is JPY-quoted (USD_JPY ~ 150, majors ~ 1).
_JPY_QUOTE_THRESHOLD = 20.0

_SUNDAY = 6
_FRIDAY = 4


def _pip_size_from_price(price: float) -> float:
    """Pip size for the instrument whose quote is ``price`` (§3, `calculate_pips`).

    The v2 contract never passes the pair to a strategy, so the quote convention is
    inferred from the decision bar's own close; the magnitudes still come from the
    inventory ``get_pip_value``. Same treatment as ``amazing_crossover``.
    """
    pair = "USD_JPY" if price >= _JPY_QUOTE_THRESHOLD else "EUR_USD"
    return float(get_pip_value(pair))


class WeeklyGapFade(StrategyV2):
    """Fade a >= 5 pip weekend gap; exit at the Friday 19:00 UTC bar close."""

    MIN_GAP_PIPS = 5.0  # §4.5/§5.4: 5 x the 1.0-pip spread proxy (NOTE 5)
    ATR_PERIOD = 14  # §3: D1 ATR(14)
    STOP_ATR_MULTIPLE = 5.0  # §6: catastrophic, not tactical
    EXIT_WEEKDAY_OFFSET = 5  # §7: Sunday + 5 days = the coming Friday
    EXIT_HOUR_UTC = 19  # §7/§10 #4: the last H1 close before the author's exit

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="weekly_gap_fade",
            name="Weekly Gap Fade (weekend gap reversion, time exit)",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "When the forex market reopens after the weekend the opening price "
                "sometimes gaps away from the prior Friday's close, and these gaps are "
                "frequently faded because the weekend produces no new fundamental flow "
                "proportionate to the price jump — the gap is largely an artefact of "
                "thin Sunday-night liquidity, retail order imbalances accumulating over "
                "the close, and dealers re-quoting spreads at the open. Mean reversion "
                "should persist because the gap is not information-driven in most "
                "weeks: once normal weekday liquidity returns, price gravitates back "
                "toward the pre-weekend consensus, and the strictly mechanical time "
                "exit removes the discretionary stop placement that gap-fade traders "
                "are typically stop-hunted on."
            ),
            granularities=["H1", "D1"],
            # §2 pairs_available, live subset. GBP_JPY — the author's preferred and
            # only documented pair — is not in this database.
            pairs=["USD_JPY", "EUR_USD", "GBP_USD", "AUD_USD", "USD_CAD"],
            primary_granularity="H1",
            context_granularities=("D1",),
            simulate_on="H1",
            source_row=3,
            source_url="https://www.earnforex.com/forex-strategy/forex-gap-strategy",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["atr", "calculate_pips"]

    @property
    def warmup_bars(self) -> int:
        return self.ATR_PERIOD * 24  # 14 D1 bars' worth of H1 bars

    @property
    def max_concurrent_positions(self) -> int:
        """§4: one position per pair; across pairs the source trades simultaneously."""
        return 1

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h1 = frames["H1"]
        d1 = frames["D1"]
        if len(h1) <= self.warmup_bars or d1.empty:
            return []

        # §2/§6: the D1 ATR, shifted one full interval so only a CLOSED daily bar can
        # inform the decision. At a Sunday decision that is the Thursday-stamped bar,
        # which closed at Friday 21:00 UTC.
        atr_d1 = atr(d1["High"], d1["Low"], d1["Close"], period=self.ATR_PERIOD)
        d1_at_close = pd.DataFrame(
            {"atr_d1": atr_d1.to_numpy(dtype=float)},
            index=d1.index + GRANULARITY_INTERVAL["D1"],
        )
        joined = pd.merge_asof(
            pd.DataFrame(index=h1.index),
            d1_at_close,
            left_index=True,
            right_index=True,
            direction="backward",
            allow_exact_matches=False,
        )["atr_d1"].to_numpy(dtype=float)

        index = h1.index
        open_ = h1["Open"].to_numpy(dtype=float)
        close = h1["Close"].to_numpy(dtype=float)
        step = GRANULARITY_INTERVAL["H1"]

        orders: List[OrderIntent] = []
        for i in range(max(self.warmup_bars, 1), len(h1)):
            # NOTE 2: the structural week-boundary check (§4 step 1).
            bar_ts = index[i]
            prev_ts = index[i - 1]
            if bar_ts - prev_ts <= step:
                continue  # inside a session, not a week opening
            if bar_ts.weekday() != _SUNDAY or prev_ts.weekday() != _FRIDAY:
                continue  # holiday-shortened week or data hole -> no trade

            atr_t = float(joined[i])
            if not np.isfinite(atr_t) or atr_t <= 0.0:
                continue

            close_t = float(close[i])
            pip = _pip_size_from_price(close_t)
            gap_pips = (float(open_[i]) - float(close[i - 1])) / pip
            if abs(gap_pips) < self.MIN_GAP_PIPS:
                continue
            direction = 1 if gap_pips <= -self.MIN_GAP_PIPS else -1

            # NOTE 4: the time leg, from the calendar alone.
            exit_ts = (
                bar_ts.normalize()
                + pd.Timedelta(days=self.EXIT_WEEKDAY_OFFSET)
                + pd.Timedelta(hours=self.EXIT_HOUR_UTC)
            )
            hold_bars = int((exit_ts - (bar_ts + step)) / step)
            if hold_bars <= 0:
                continue

            orders.append(
                OrderIntent(
                    decision_bar=bar_ts,
                    direction=1 if direction > 0 else -1,
                    entry="market",  # §4: fills at the next H1 open (F1/F2)
                    entry_price=None,
                    decision_close=close_t,
                    # NOTE 3: catastrophic stop, decision-close anchored (§10 #8).
                    stop=StopRule(
                        price=close_t - direction * self.STOP_ATR_MULTIPLE * atr_t
                    ),
                    exits=[
                        ExitLeg(
                            fraction=1.0,
                            kind="time",
                            bars=hold_bars,
                            label="W-END",
                        )
                    ],
                    expires_after_bars=1,  # §4: defensive only for a market intent
                    tag="weekly_gap_fade",
                    strategy_id=self.strategy_id,
                )
            )
        return orders
