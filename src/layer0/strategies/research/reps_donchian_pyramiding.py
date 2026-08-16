"""REPS Donchian Pyramiding — implementation of SPEC-reps_donchian_pyramiding.

Weekly (derived) Donchian close-breakouts open a directional *series*; D1 and H4
breakout events inside that series emit pyramid add-ons. Every intent is a market
order carrying a static H4-channel stop and a single 6xATR trailing exit leg.

Three places where the obvious implementation is wrong, and what is done instead:

* **The weekly frame is derived from D1, never loaded** (spec §10 #3): the native
  W1 feed is ~8 weeks stale, which would silently freeze signals at the end of every
  OOS window. Weeks are the broker week Sun 21:00Z -> Fri 21:00Z; D1 bars are stamped
  at their open, so adding 3h maps every session onto its own calendar day and the
  ISO week of that day is the trading week.
* **Context is consumed at the decision bar's OPEN, not its close.** The look-ahead
  probe truncates a context frame to the bars that closed by the *open* of the last
  surviving primary bar, so a strategy that reads H4 bars from inside the decision
  bar's own session emits an order the truncated re-run cannot reproduce. Both the
  stop level (§6) and the H4 add-on pattern (§4) are therefore anchored one D1 bar
  earlier than the spec's literal wording. Recorded as a deviation in the report.
* **Every Donchian channel is shifted one bar** (§3), so a breakout is never measured
  against a channel that contains the bar doing the breaking.

The state machines, the pyramid-into-strength proxy and the once-per-weekly-event
rule are all functions of bar data and the strategy's own prior emissions only — a
v2 strategy never observes a fill, so nothing here depends on one (§10 #8/#11).
"""

from __future__ import annotations

from typing import List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from ...data_access.indicators import donchian_channel
from ..contract_v2 import (
    GRANULARITY_INTERVAL,
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)


class RepsDonchianPyramiding(StrategyV2):
    """Turtle-style weekly Donchian breakouts, pyramided on D1 and H4 continuation."""

    CHANNEL_PERIOD = 20  # §3: all three Donchian channels
    TRAIL_ATR_MULTIPLE = 6.0  # §7: the SERIES_EXIT leg
    H4_WINDOW_BARS = 12  # §4: "up to 12 H4 bars" = two D1 sessions
    SESSION_OFFSET_HOURS = 3  # 21:00/22:00Z open -> the session's own calendar day

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="reps_donchian_pyramiding",
            name="REPS Donchian Pyramiding",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "Turtle-style Donchian breakouts on the weekly chart capture the birth "
                "of large multi-month FX trends, which persist because macro divergences "
                "(rates, growth, capital flows) reprice currencies slowly and "
                "herding/underreaction extends the move; pyramiding into confirmed "
                "strength then concentrates exposure in the small number of trends that "
                "pay for the many false breakouts, so expectancy is carried by a fat "
                "right tail rather than by win rate."
            ),
            granularities=["D1", "H4"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="D1",
            # W1 is DERIVED from D1 (§10 #3) and is deliberately NOT declared: a
            # declared context frame is mandatory data to the harness, and making the
            # measurement depend on a feed the strategy never reads would be false.
            context_granularities=("H4",),
            simulate_on="H1",
            source_row=14,
            source_url=(
                "https://www.forexfactory.com/thread/"
                "552483-reverse-engineering-a-profitable-system-reps"
            ),
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["donchian_channel", "atr"]

    @property
    def warmup_bars(self) -> int:
        # 20 weekly bars + the 1-bar shift ~= 105 D1 sessions; 150 leaves margin for
        # holiday-shortened weeks.
        return 150

    @property
    def max_concurrent_positions(self) -> int:
        """§2 / §10 #2 (F12): 1 initial + at most 3 add-ons, per Turtle convention."""
        return 4

    # ------------------------------------------------------------------
    # Derived weekly frame (§3, §10 #3)
    # ------------------------------------------------------------------

    def _weekly_frame(self, d1: pd.DataFrame) -> pd.DataFrame:
        """Aggregate D1 bars into broker weeks, indexed at the week's first D1 open."""
        session = d1.index + pd.Timedelta(hours=self.SESSION_OFFSET_HOURS)
        week_start = session.normalize() - pd.to_timedelta(session.weekday, unit="D")
        grouped = d1.groupby(week_start)
        return pd.DataFrame(
            {
                "High": grouped["High"].max(),
                "Low": grouped["Low"].min(),
                "Close": grouped["Close"].last(),
            }
        )

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        d1 = frames["D1"]
        h4 = frames["H4"]
        if len(d1) <= self.warmup_bars or h4.empty:
            return []

        # -- weekly channel, causally attached to the D1 decision frame ----------
        # The weekly bar is stamped at its own open and shifted forward one full
        # weekly interval, then asof-merged with allow_exact_matches=False: exactly
        # the mechanics spec §3 prescribes. A week is therefore first usable on the
        # Monday-stamped D1 bar of the following week.
        w1 = self._weekly_frame(d1)
        w_hi, _, w_lo = donchian_channel(w1["High"], w1["Low"], self.CHANNEL_PERIOD)
        weekly = pd.DataFrame(
            {
                "w_hi": w_hi.shift(1).to_numpy(dtype=float),
                "w_lo": w_lo.shift(1).to_numpy(dtype=float),
                "w_close": w1["Close"].to_numpy(dtype=float),
                "w_start": w1.index.to_numpy(),
            },
            index=w1.index + GRANULARITY_INTERVAL["W1"],
        )
        joined = pd.merge_asof(
            pd.DataFrame(index=d1.index),
            weekly,
            left_index=True,
            right_index=True,
            direction="backward",
            allow_exact_matches=False,
        )

        # -- D1 channel (§3) ----------------------------------------------------
        d_hi_s, _, d_lo_s = donchian_channel(d1["High"], d1["Low"], self.CHANNEL_PERIOD)
        d_hi = d_hi_s.shift(1).to_numpy(dtype=float)
        d_lo = d_lo_s.shift(1).to_numpy(dtype=float)

        # -- H4 channel, and the last H4 bar closed by each D1 bar's open --------
        h_hi_s, _, h_lo_s = donchian_channel(h4["High"], h4["Low"], self.CHANNEL_PERIOD)
        h_hi = h_hi_s.shift(1).to_numpy(dtype=float)
        h_lo = h_lo_s.shift(1).to_numpy(dtype=float)
        h4_close_at = (h4.index + GRANULARITY_INTERVAL["H4"]).to_numpy()
        anchor = (
            np.searchsorted(h4_close_at, d1.index.to_numpy(), side="right") - 1
        ).astype(int)

        h4_close = h4["Close"].to_numpy(dtype=float)
        # Breakout flags per H4 bar, both directions (§4.3 / §5).
        h4_below = h4_close < h_lo
        h4_above = h4_close > h_hi

        d1_close = d1["Close"].to_numpy(dtype=float)
        w_hi_a = joined["w_hi"].to_numpy(dtype=float)
        w_lo_a = joined["w_lo"].to_numpy(dtype=float)
        w_close_a = joined["w_close"].to_numpy(dtype=float)
        w_start_a = joined["w_start"].to_numpy()
        index = d1.index

        orders: List[OrderIntent] = []
        long_active = False
        short_active = False
        last_long_close: Optional[float] = None
        last_short_close: Optional[float] = None
        long_week_used: object = None
        short_week_used: object = None

        def emit(i: int, direction: int, stop_price: float, tag: str) -> None:
            orders.append(
                OrderIntent(
                    decision_bar=index[i],
                    direction=1 if direction > 0 else -1,
                    entry="market",
                    entry_price=None,
                    decision_close=float(d1_close[i]),
                    stop=StopRule(price=stop_price),
                    exits=[
                        ExitLeg(
                            fraction=1.0,
                            kind="trailing",
                            atr_multiple=self.TRAIL_ATR_MULTIPLE,
                            label="SERIES_EXIT",
                        )
                    ],
                    expires_after_bars=1,
                    tag=tag,
                    strategy_id=self.strategy_id,
                )
            )

        for i in range(self.warmup_bars, len(d1)):
            a = anchor[i]
            if a < 0 or np.isnan(d_hi[i]) or np.isnan(d_lo[i]):
                continue
            stop_long = h_lo[a]
            stop_short = h_hi[a]
            if np.isnan(stop_long) or np.isnan(stop_short):
                continue
            close_t = float(d1_close[i])
            lo = max(0, a - self.H4_WINDOW_BARS + 1)

            # -- series resets (§4/§5): a full D1 close through the opposing band --
            if long_active and close_t <= d_lo[i]:
                long_active = False
            if short_active and close_t >= d_hi[i]:
                short_active = False

            # -- INITIAL_LONG (§4) --------------------------------------------
            if not long_active and not np.isnan(w_hi_a[i]):
                if w_close_a[i] > w_hi_a[i] and w_start_a[i] != long_week_used:
                    long_week_used = w_start_a[i]
                    if stop_long < close_t:  # §4 guard
                        long_active = True
                        last_long_close = close_t
                        emit(i, 1, float(stop_long), "INITIAL_LONG")

            # -- ADDON_LONG_D1 (§4): fresh crossover of the shifted D1 channel ---
            if (
                long_active
                and last_long_close is not None
                and close_t > d_hi[i]
                and d1_close[i - 1] <= d_hi[i - 1]
                and close_t > last_long_close
                and stop_long < close_t
            ):
                last_long_close = close_t
                emit(i, 1, float(stop_long), "ADDON_LONG_D1")

            # -- ADDON_LONG_H4 (§4): counter-move then reversal, one per D1 bar --
            if (
                long_active
                and last_long_close is not None
                and close_t > last_long_close
                and stop_long < close_t
                and self._counter_then_with(h4_below, h4_above, lo, a)
            ):
                last_long_close = close_t
                emit(i, 1, float(stop_long), "ADDON_LONG_H4")

            # -- INITIAL_SHORT (§5) -------------------------------------------
            if not short_active and not np.isnan(w_lo_a[i]):
                if w_close_a[i] < w_lo_a[i] and w_start_a[i] != short_week_used:
                    short_week_used = w_start_a[i]
                    if stop_short > close_t:
                        short_active = True
                        last_short_close = close_t
                        emit(i, -1, float(stop_short), "INITIAL_SHORT")

            # -- ADDON_SHORT_D1 (§5) ------------------------------------------
            if (
                short_active
                and last_short_close is not None
                and close_t < d_lo[i]
                and d1_close[i - 1] >= d_lo[i - 1]
                and close_t < last_short_close
                and stop_short > close_t
            ):
                last_short_close = close_t
                emit(i, -1, float(stop_short), "ADDON_SHORT_D1")

            # -- ADDON_SHORT_H4 (§5) ------------------------------------------
            if (
                short_active
                and last_short_close is not None
                and close_t < last_short_close
                and stop_short > close_t
                and self._counter_then_with(h4_above, h4_below, lo, a)
            ):
                last_short_close = close_t
                emit(i, -1, float(stop_short), "ADDON_SHORT_H4")

        return orders

    @staticmethod
    def _counter_then_with(
        counter: np.ndarray, with_trend: np.ndarray, lo: int, hi: int
    ) -> bool:
        """True when a counter-move break is followed by a with-trend break in [lo, hi].

        §4.3/§5: an H4 bar *u1* closes through the band opposite the series direction
        and a strictly later bar *u2* in the same window closes through the band in the
        series direction. Both flags are computed from shifted channels, so neither bar
        is measured against a channel containing itself.
        """
        for u1 in range(lo, hi + 1):
            if counter[u1]:
                return bool(with_trend[u1 + 1 : hi + 1].any())
        return False
