"""h4_box_breakout — weekly opening-range ("box") breakout on JPY crosses.

Spec: ``task/2026-August-week1/fleet/upload/wave2/specs/SPEC-h4_box_breakout.md``
Source: row 36 of ``forex_swing_strategies.csv`` ·
https://www.trade2win.com/threads/4h-box-breakout.63584/

Mechanics, one paragraph: the *box* is the single H4 bar that opens the feed week
(stamped **Sunday 21:00 UTC**). At that bar's close — Monday 01:00 UTC, which is
therefore the decision bar — the strategy declares two pending stop orders, one
either side of the box, offset by a 21-pip noise buffer, each stopped at the
opposite box edge and scaled out in four equal quarters at 1/2/3/4 box heights.
Both pendings live 29 H4 bars, which kills them at Friday 17:00 UTC — before the
next week's box bar can exist.

Notes on the parts where the obvious implementation is wrong:

* **NOTE A — the box needs no lookback and no context frame.** ``context_granularities``
  is empty (spec §2): the "weekly" grouping is a *calendar partition of H4 bars*, not a
  W1 frame read. There is deliberately no ``closed_context_frame`` call here, because
  there is no context frame to read. The box is one already-completed H4 bar, so the
  decision bar IS the box bar and the confirmation lag is zero (spec §9).
* **NOTE B — the week-open bar is identified by its stamp, never by position.**
  "First bar of the week" implemented as "first row after a gap" would silently
  re-anchor the box onto a holiday Monday. Spec §3.2 / §10 row 8 require the literal
  Sunday-21:00-UTC stamp and require the *whole week to be skipped* when it is absent.
  See the ``_week_open_box_positions`` docstring for the DST caveat this creates.
* **NOTE C — both sides are emitted, and neither cancels the other.** Contract v2 has
  no OCO (spec §10 row 5). Within one whipsaw week both pendings can fill; that is a
  recorded, accepted, conservative consequence, not something to patch here.
* **NOTE D — the take-profit ladder is anchored to the DECLARED entry level**, not to
  the eventual fill, because the fill price is unknowable at emission (spec §10 row 4).
  Declared risk is ``H + 21 pips`` while TP1 sits at ``+1 H``, so TP1 is slightly under
  1R by construction. That is the spec's arithmetic (§7) and is kept as written.

No indicators beyond pip-size conversion; the source explicitly states "no indicators".
``detect_swing_points`` is irrelevant here — no swing, pivot or fractal is used.
"""

from __future__ import annotations

from typing import List, Mapping, Sequence, Tuple

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
from ...data_access.indicators import get_pip_value

#: pandas weekday numbering: Monday = 0 … Sunday = 6.
_BOX_WEEKDAY = 6
#: The feed's week-open hour in UTC (market reopens Sunday 21:00 UTC).
_BOX_HOUR = 21


def _week_open_box_positions(index: pd.Index) -> np.ndarray:
    """Positional indices of the H4 bars stamped **Sunday 21:00 UTC** (spec §3, step 2).

    Private module-level helper: the "weekly box" is a mechanical construct that the
    indicator inventory does not carry, and the spec specifies it in full, so it is
    defined here rather than added to a shared module (fleet hard rule 3).

    The stamp is matched literally. Consequences, both intended by spec §3.2/§10 row 8:

    * A week whose Sunday-21:00 bar is missing (holiday) is **skipped entirely** — the
      next bar is never substituted, because "opening range" would stop meaning
      anything.
    * The match is on 21:00 **UTC**, not on a DST-following local week open. If the
      feed's winter week-open bar is stamped 22:00 UTC rather than 21:00, those weeks
      produce no box and no setup. The spec fixes the boundary at 21:00 UTC and
      explicitly rejects a DST-drifting boundary (§10 row 1); this is recorded as an
      uncertainty in the report rather than silently generalised here.

    Tz-naive indices are read as UTC; tz-aware indices are converted to UTC first, so
    the calendar test cannot be fooled by the frame's presentation timezone.
    """
    stamps = pd.DatetimeIndex(index)
    utc = stamps.tz_localize("UTC") if stamps.tz is None else stamps.tz_convert("UTC")
    mask = (
        (np.asarray(utc.dayofweek) == _BOX_WEEKDAY)
        & (np.asarray(utc.hour) == _BOX_HOUR)
        & (np.asarray(utc.minute) == 0)
        & (np.asarray(utc.second) == 0)
    )
    return np.flatnonzero(mask)


class H4BoxBreakout(StrategyV2):
    """Break the first H4 bar of the feed week by 21 pips; hold for 1–4 box heights."""

    # -- spec §4.2 / §8: the only filter in the source is the noise buffer -----
    NOISE_BUFFER_PIPS = 20.0  # conservative end of the source's "10-20 pip" range
    SPREAD_PROXY_PIPS = 1.0  # F10 cost-model constant standing in for "+ spread"

    # -- spec §7: four equal take-profit legs at 1/2/3/4 box heights -----------
    TP_MULTIPLES: Tuple[float, ...] = (1.0, 2.0, 3.0, 4.0)
    LEG_FRACTION = 0.25  # 0.25 x 4 == 1.0 exactly (0.25 is exact in binary)

    # -- spec §4.3: 30-bar feed week, box bar = bar 0, order dies after bar 29 -
    EXPIRY_BARS = 29

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="h4_box_breakout",
            name="H4 Weekly Box Breakout",
            version="0.1.0",
            author="wave2-fleet",
            hypothesis=(
                "The first 4-hour range of a trading week on volatile JPY crosses "
                "marks the market's initial equilibrium after the weekend close; a "
                "decisive break of that range, beyond a noise buffer, signals that "
                "the week's dominant directional flow (institutional "
                "position-building, weekend news resolution, Asian-session JPY "
                "repricing) has committed, and that commitment tends to persist for "
                "one to four box-heights because early-week positioning is not yet "
                "profitable enough to unwind. The edge should persist as long as JPY "
                "crosses concentrate weekly range-expansion into their opening "
                "sessions and breakout-following flows outnumber faders."
            ),
            granularities=["H4"],
            # Spec §2: the only two named pairs that exist at all in this feed are the
            # Wave-1 additions GBP_JPY and EUR_JPY, both still backfilling. The spec
            # instructs "declare, harness skips if backfill incomplete"; AUD_JPY,
            # CHF_JPY and CAD_JPY are absent entirely and are NOT declared.
            pairs=["GBP_JPY", "EUR_JPY"],
            primary_granularity="H4",
            context_granularities=(),  # NOTE A — no context frame is read
            simulate_on="H1",
            source_row=36,
            source_url="https://www.trade2win.com/threads/4h-box-breakout.63584/",
        )

    @property
    def required_indicators(self) -> List[str]:
        # Pip-size conversion only; the source explicitly states "no indicators".
        return ["get_pip_value"]

    @property
    def warmup_bars(self) -> int:
        """One bar.

        The box is a single completed H4 bar, so there is genuinely no indicator
        lookback to warm (spec §9: zero confirmation lag). Bar 0 is still discarded:
        it is the frame's boundary bar and a load window can slice into it, which
        would give a truncated High/Low and therefore a wrong box.
        """
        return 1

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h4 = frames["H4"]
        pip = float(get_pip_value(self.metadata.pairs[0]))
        # Spec §4.2 / §8: B = 20 pips + 1.0-pip spread proxy = 21 pips.
        buffer_price = (self.NOISE_BUFFER_PIPS + self.SPREAD_PROXY_PIPS) * pip

        high = h4["High"].to_numpy(dtype=float)
        low = h4["Low"].to_numpy(dtype=float)
        close = h4["Close"].to_numpy(dtype=float)
        index = h4.index

        orders: List[OrderIntent] = []
        for position in _week_open_box_positions(index):
            i = int(position)
            if i < self.warmup_bars:
                continue

            box_high = float(high[i])
            box_low = float(low[i])
            decision_close = float(close[i])
            if np.isnan(box_high) or np.isnan(box_low) or np.isnan(decision_close):
                continue

            # Spec §3, step 3: a flat/degenerate box means the week is skipped.
            height = box_high - box_low
            if height <= 0.0:
                continue

            decision_bar = pd.Timestamp(index[i])
            long_entry = box_high + buffer_price
            short_entry = box_low - buffer_price

            # NOTE C — one weekly setup, two pendings, no OCO available.
            # A buy stop must sit above and a sell stop below the decision-bar close
            # or the contract (rightly) rejects it as an instant fill in disguise.
            # With High >= Close >= Low and a positive buffer this always holds; the
            # guards stay because a malformed bar must skip, never be clamped legal.
            if long_entry > decision_close:
                orders.append(
                    self._intent(
                        decision_bar=decision_bar,
                        direction=1,
                        entry="buy_stop",
                        entry_price=long_entry,
                        stop_price=box_low,  # spec §6: opposite box edge, no buffer
                        height=height,
                        decision_close=decision_close,
                        tag="box_break_long",
                    )
                )
            if short_entry < decision_close:
                orders.append(
                    self._intent(
                        decision_bar=decision_bar,
                        direction=-1,
                        entry="sell_stop",
                        entry_price=short_entry,
                        stop_price=box_high,  # spec §6: opposite box edge, no buffer
                        height=height,
                        decision_close=decision_close,
                        tag="box_break_short",
                    )
                )
        return orders

    # ------------------------------------------------------------------
    # Trade-plan construction (spec §6 + §7)
    # ------------------------------------------------------------------

    def _intent(
        self,
        *,
        decision_bar: pd.Timestamp,
        direction: Direction,
        entry: EntryKind,
        entry_price: float,
        stop_price: float,
        height: float,
        decision_close: float,
        tag: str,
    ) -> OrderIntent:
        """Assemble one side of the weekly setup.

        NOTE D — every take-profit level is ``declared entry ± k x H``. The stop is the
        opposite box edge exactly (spec §6, §10 row 7): no buffer, no breakeven move,
        no trail. Adding any of those would flatter the results.
        """
        exits = [
            ExitLeg(
                fraction=self.LEG_FRACTION,
                kind="take_profit",
                price=entry_price + direction * multiple * height,
                label=f"TP{leg_number}",
            )
            for leg_number, multiple in enumerate(self.TP_MULTIPLES, start=1)
        ]
        return OrderIntent(
            decision_bar=decision_bar,
            direction=direction,
            entry=entry,
            entry_price=entry_price,
            decision_close=decision_close,
            stop=StopRule(
                price=stop_price,
                move_to_breakeven_on=None,  # spec §6: the source never moves the stop
                trail_atr_multiple=None,  # spec §6: static for the life of the trade
            ),
            exits=exits,
            expires_after_bars=self.EXPIRY_BARS,
            tag=tag,
            strategy_id=self.strategy_id,
        )
