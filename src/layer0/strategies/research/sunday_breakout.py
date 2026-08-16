"""Sunday Breakout — SPEC-sunday_breakout.md (CSV row 4).

At the close of the week's first H4 bar (the "Sunday candle"), place a buy stop 10
pips above its high and a sell stop 10 pips below its low, stop at the opposite end
of that candle, target half a weekly ATR, and let both pendings live until the
Friday close.

NOTE 1 — WHICH BAR IS THE SUNDAY CANDLE (§9). The market reopens Sunday 21:00 UTC
    and H4 bars are stamped at their open, so exactly one H4 bar starts on a Sunday.
    It is identified structurally rather than by clock arithmetic: bar *i* is the
    Sunday candle when its FX week differs from bar *i-1*'s. Adding 3h to a bar's
    open stamp moves every session onto its own calendar day, and the ISO week of
    that day is the FX week — which survives the 21:00/22:00 DST shift that a
    literal "hour == 21 and weekday == Sunday" test does not. Its high and low are
    knowable only at its close (Monday 01:00 UTC), which is why the decision bar is
    the Sunday candle itself and the orders fill from the next bar onward (F1).

NOTE 2 — THE WEEKLY ATR IS SHIFTED A FULL WEEK (§3, §10 #2). The W1 index is moved
    forward by one weekly interval and asof-merged with ``allow_exact_matches=False``,
    so only fully completed weeks can enter the ATR whatever the feed's stamp
    convention is. The strict inequality costs one extra week of freshness at exactly
    the Sunday-candle bar (the week that ended at that bar's open is excluded); §3
    mandates those mechanics and the direction is conservative.

NOTE 3 — THE BREAKEVEN TRIGGER IS A REAL LEG (§6, §10 #3). ``move_to_breakeven_on``
    accepts only an ``ExitLeg`` label and ``ExitLeg.fraction`` must be > 0, so the
    source's "move the stop to breakeven at +2R" is expressed as a 1%-size take
    profit at exactly +2R named ``BE_2R``. Two honest mismatches follow: the trigger
    is not zero-size, and per F8 the stop moves at the CLOSE of the bar that reaches
    +2R rather than intrabar. Both are pessimistic relative to the live rule.

NOTE 4 — NO OCO EXISTS (§8, §10 #8). The long and short pendings are independent.
    F12 (``max_concurrent_positions = 1``) stops them being open at the same time,
    but nothing cancels the survivor when its sibling fills, so a mid-week stop-out
    can be followed by the opposite order filling in the same week — one more trade
    than the CSV intends. Shortening the expiry to prevent it would amputate the
    documented week-long setup horizon, so the faithful expiry is kept and the
    residual risk is reported.

NOTE 5 — the pair is never passed to a v2 strategy, so the 10-pip offset infers its
    quote convention from the decision bar's own close, as ``amazing_crossover`` and
    ``ema_cross_h4_filter_bot`` already do. The magnitudes come from the inventory
    ``get_pip_value``.
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

#: Above this quote level an instrument is JPY-quoted (EUR_JPY ~ 160, GBP_USD ~ 1.3).
_JPY_QUOTE_THRESHOLD = 20.0


def _pip_size_from_price(price: float) -> float:
    """Pip size for the instrument whose quote is ``price`` (NOTE 5)."""
    pair = "USD_JPY" if price >= _JPY_QUOTE_THRESHOLD else "EUR_USD"
    return float(get_pip_value(pair))


class SundayBreakout(StrategyV2):
    """Break the week's opening H4 range by 10 pips; target half a weekly ATR."""

    BREAK_PIPS = 10.0  # §4.2: the decisive-break buffer
    ATR_PERIOD = 14  # §3: weekly ATR(14)
    TARGET_ATR_FRACTION = 0.5  # §7: TP at half a weekly ATR
    BE_TRIGGER_R = 2.0  # §6/§7: the breakeven trigger sits at +2R
    BE_TRIGGER_FRACTION = 0.01  # §10 #3: smallest expressible trigger leg
    EXPIRES_AFTER_BARS = 29  # §4.6: Monday 01:00 -> Friday 17:00 inclusive
    SESSION_OFFSET_HOURS = 3  # 21:00/22:00Z open -> the session's own calendar day

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="sunday_breakout",
            name="Sunday Breakout (opening-range break, weekly-ATR target)",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "The weekend close interrupts price discovery while news and "
                "positioning accumulate; when the market reopens, the first hours of "
                "the week form an initial balance whose range encodes the opening "
                "week's unresolved order flow. A decisive break of that range by ten "
                "pips signals that opening-week momentum is resolving in one direction, "
                "and the move tends to extend a meaningful fraction of the week's "
                "normal travel. The edge should persist because it is structural — it "
                "rests on the fixed weekly close and reopen cycle of the FX market and "
                "on the tendency of opening-range resolution to attract follow-through "
                "— rather than on any fitted parameter."
            ),
            granularities=["H4", "W1"],
            # §2: GBP_USD is the only requested pair that exists; EUR_JPY was a
            # Wave-1 addition that never landed.
            pairs=["GBP_USD"],
            primary_granularity="H4",
            context_granularities=("W1",),
            simulate_on="H1",
            source_row=4,
            source_url="https://forums.babypips.com/t/sunday-breakout-strategy/23165",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["atr", "get_pip_value"]

    @property
    def warmup_bars(self) -> int:
        # 14 weekly bars for the ATR; a trading week is 30 H4 bars.
        return self.ATR_PERIOD * 30

    @property
    def max_concurrent_positions(self) -> int:
        """§8 (F12): the two weekly pendings can never be open at the same time."""
        return 1

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h4 = frames["H4"]
        w1 = frames["W1"]
        if len(h4) <= self.warmup_bars or w1.empty:
            return []

        # NOTE 2: only fully completed weeks may inform a decision.
        weekly_atr = atr(w1["High"], w1["Low"], w1["Close"], period=self.ATR_PERIOD)
        w1_at_close = pd.DataFrame(
            {"atr_w": weekly_atr.to_numpy(dtype=float)},
            index=w1.index + GRANULARITY_INTERVAL["W1"],
        )
        atr_w = pd.merge_asof(
            pd.DataFrame(index=h4.index),
            w1_at_close,
            left_index=True,
            right_index=True,
            direction="backward",
            allow_exact_matches=False,
        )["atr_w"].to_numpy(dtype=float)

        # NOTE 1: the Sunday candle is the first H4 bar of an FX week.
        session = h4.index + pd.Timedelta(hours=self.SESSION_OFFSET_HOURS)
        week_key = (
            session.normalize() - pd.to_timedelta(session.weekday, unit="D")
        ).to_numpy()

        high = h4["High"].to_numpy(dtype=float)
        low = h4["Low"].to_numpy(dtype=float)
        close = h4["Close"].to_numpy(dtype=float)
        index = h4.index

        orders: List[OrderIntent] = []
        for i in range(max(self.warmup_bars, 1), len(h4)):
            if week_key[i] == week_key[i - 1]:
                continue  # not the week's opening bar
            atr_t = float(atr_w[i])
            if not np.isfinite(atr_t) or atr_t <= 0.0:
                continue

            sun_high = float(high[i])
            sun_low = float(low[i])
            close_t = float(close[i])
            pip10 = self.BREAK_PIPS * _pip_size_from_price(close_t)
            target_distance = self.TARGET_ATR_FRACTION * atr_t
            # §6: R is measured from the DECLARED entry level, the only price
            # knowable at emission, and is identical for both directions.
            risk = (sun_high - sun_low) + pip10
            if risk <= 0.0 or target_distance <= 0.0:
                continue

            for direction, entry_kind, entry_price, stop_price in (
                (1, "buy_stop", sun_high + pip10, sun_low),
                (-1, "sell_stop", sun_low - pip10, sun_high),
            ):
                orders.append(
                    OrderIntent(
                        decision_bar=index[i],
                        direction=1 if direction > 0 else -1,
                        entry=entry_kind,  # type: ignore[arg-type]
                        entry_price=entry_price,
                        decision_close=close_t,
                        # NOTE 3: the breakeven move is triggered by the BE_2R leg.
                        stop=StopRule(
                            price=stop_price,
                            move_to_breakeven_on="BE_2R",
                            breakeven_offset_pips=0.0,
                        ),
                        exits=[
                            ExitLeg(
                                fraction=self.BE_TRIGGER_FRACTION,
                                kind="take_profit",
                                price=entry_price
                                + direction * self.BE_TRIGGER_R * risk,
                                label="BE_2R",
                            ),
                            ExitLeg(
                                fraction=1.0 - self.BE_TRIGGER_FRACTION,
                                kind="take_profit",
                                price=entry_price + direction * target_distance,
                                label="TP",
                            ),
                        ],
                        expires_after_bars=self.EXPIRES_AFTER_BARS,  # §4.6
                        tag="sunday_break",
                        strategy_id=self.strategy_id,
                    )
                )
        return orders
