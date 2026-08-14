"""demark_fractal_breakout — SPEC-demark_fractal_breakout (row 48).

Source: a 2007 forum thread describing a "pure mechanical" DeMark-style fractal
breakout: buy a confirmed swing-high break, sell a confirmed swing-low break,
trail the stop toward the opposite structure. LevDP (DeMark's swing-lookback
parameter) is fixed at 2, and the source's own text mandates a confirmation
lag of LevDP+1 = 3 bars, not the natural 2-bar causal confirmation.

No context frame: everything happens on the H4 decision frame (spec §2).
Decisions are taken at the close of the most recently CLOSED H4 bar `t`.

-- NOTE 1: the mandatory extra confirmation lag ------------------------------
`causal_structure.confirmed_swing_points(period=2)` stamps a swing at its
NATURAL causal confirmation bar `k+2` (the 2 right-side bars are complete).
The source explicitly requires one more bar of confirmation ("confirmed 3 bars
later" / "delayed by LevDP+1 bars, which must be modeled" — spec §3, §9, §10
#2): a swing occurring at `k` is knowable to this system only at `k+3`. That
extra bar is implemented here as a single additional `shift(1)` on the output
of `confirmed_swing_points` — still purely causal (a forward shift moves
information LATER, never earlier), never as a shorter or centred window.

-- NOTE 2: staleness is a THIRD condition, not implied by the swing detector -
`confirmed_swing_points(period=2)`'s own confirmation only checks that no bar
in `[k+1, k+2]` exceeded the level (spec's right-side, non-strict test). Once
the level is only usable from `k+3` onward (NOTE 1), bar `k+3` itself has never
been checked against the level. Spec §4.2/§5.2 is explicit that the staleness
window is `[k+1, t]` INCLUDING the confirmation bar `t` itself, so this module
computes its own rolling extremum over the trailing 3 bars ending at `t`
(`[t-2, t-1, t] == [k+1, k+2, k+3]` whenever `t` is a fresh confirmation, since
`t == k+3`) rather than trusting the swing detector's own (shorter) check.

-- NOTE 3: the stop anchor is a rolling "most recent knowable" query ---------
Spec §4.3/§5.3 need "the most recent CONFIRMED opposite-side circle as of `t`",
with no staleness requirement on that side. That is exactly a forward-fill of
the (lag-adjusted, NOTE 1) confirmed-event series: `series.ffill()` at bar `t`
holds the latest non-NaN value at or before `t`, which is causal by
construction (never looks past `t`) and requires no new shared indicator
(spec §3 says exactly this: "no new shared indicator").

-- NOTE 4: a pending entry must sit on the correct side of the decision close
Buy-stop entries must be above `Close[t]`; sell-stop entries below. Condition 2
(NOTE 2) already guarantees this algebraically (spec §4: "Condition 2
guarantees Close(t) <= High(t) < High[k] < entry_price"), but the check is
kept explicit and defensive, mirroring `REFERENCE_STRATEGY.py`'s NOTE 3: if the
guarantee were ever violated by a parameter change, this skips the bar rather
than emitting an instant fill disguised as a pending order.

-- Exit / stop structure (spec §6, §7) ---------------------------------------
The source's real management ("move the stop to each new opposite-side circle
as it appears") cannot be expressed: OrderIntents are declarative and a
strategy can never observe fills or amend a live order (spec §10 #6). The
spec's resolution is an ATR(14, H4) ratchet proxy, `trail_atr_multiple = 1.5`,
carried on `StopRule` (the ratchet itself, updated by the engine at bar close
per F9) AND on the single `ExitLeg(kind="trailing")` (spec §7's TRAIL leg,
fraction 1.0 — the whole position exits through the trailing stop; there is no
take-profit). There is no breakeven mechanism (`move_to_breakeven_on=None`).

**Reported, not worked around:** `position_engine.py` rejects any intent
carrying a fractional `ExitLeg(kind="trailing")` with `TRAILING_LEG_UNSUPPORTED`
("use StopRule.trail_atr_multiple (whole-position trailing)" — see
`position_engine.py` around the pending-fill classification step). The
contract's own `ExitLeg.__post_init__` accepts `kind="trailing"` with fraction
1.0; the engine's admission step does not. This is the exact same shared-file
conflict already discovered and documented by another Wave-2 agent against
`daily_fib_retracement.py` — not something new to fix here, not something this
module works around (fleet hard rule 3), and repeated in
`REPORT-demark_fractal_breakout.md`.

-- expires_after_bars: which frame's bars? (spec §10 #11) --------------------
Spec §2 declares `simulate_on: H1`; `position_engine.PositionEngine.run` takes
a `resolution_df` and iterates a bar index `t` OVER THAT FRAME
(`deadline = t + intent.expires_after_bars`, read directly from
`position_engine.py`), and `v2_harness.evaluate_cell` calls `engine.run` with
`resolution_df=h1_frame` for the H1-resolution measurement that matches this
strategy's declared `simulate_on`. So under the resolution mode this strategy
is meant to be measured on, the engine counts SIMULATION (H1) bars, not
decision-frame (H4) bars — the branch spec §10 #11 flags explicitly: "if the
engine counts only simulation bars, Wave 2 must emit expires_after_bars = 12
H1 bars and note the translation in its report." `EXPIRES_AFTER_BARS = 12`
below is that translation (3 H4 bars x 4 H1-bars-per-H4-bar).
"""

from __future__ import annotations

from typing import List, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd

from ..causal_structure import confirmed_swing_points
from ..contract_v2 import (
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)
from ...data_access.indicators import get_pip_value


def _confirmed_with_extra_lag(
    high: pd.Series, low: pd.Series, period: int
) -> Tuple[pd.Series, pd.Series]:
    """``confirmed_swing_points`` plus the spec's mandatory extra 1-bar lag.

    See NOTE 1. A swing occurring at bar ``k`` is naturally confirmed (causally)
    at ``k+period``; this DeMark system does not treat it as knowable until
    ``k+period+1``. Implemented as a plain forward ``shift(1)`` of the already
    causal ``confirmed_swing_points`` output — this only ever pushes a value
    LATER in the index, so it cannot introduce look-ahead.

    Returns:
        ``(red_events, blue_events)`` — float Series indexed like the inputs.
        Non-NaN only at each swing's (lag-adjusted) confirmation bar, carrying
        the level set at the occurrence bar. NaN everywhere else.
    """
    swing_high, swing_low = confirmed_swing_points(high, low, period=period)
    return swing_high.shift(1), swing_low.shift(1)


class DemarkFractalBreakout(StrategyV2):
    """Buy a confirmed LevDP=2 swing-high break; sell a confirmed swing-low break."""

    LEVDP = 2  # DeMark LevDP; the `period` fed to confirmed_swing_points (spec §3)
    CONFIRMATION_EXTRA_LAG_BARS = 1  # NOTE 1 — total lag = LEVDP + this = 3 bars
    ENTRY_BUFFER_PIPS = 4.0  # noise buffer beyond the fractal (spec §4/§5)
    SPREAD_PROXY_PIPS = 1.0  # F10 spread convention, embedded in the trigger (§8)
    STOP_BUFFER_PIPS = 3.0  # initial stop beyond the opposite anchor (spec §6)
    TRAIL_ATR_MULTIPLE = 1.5  # ATR(14, H4) ratchet proxy (spec §6/§7)
    ATR_PERIOD = 14  # spec §3; ATR itself is computed engine-side (F9), see NOTE
    DECISION_FRAME_EXPIRY_BARS = 3  # spec §4/§5: 3 H4 decision bars
    H1_BARS_PER_H4_BAR = 4
    EXPIRES_AFTER_BARS = DECISION_FRAME_EXPIRY_BARS * H1_BARS_PER_H4_BAR  # 12 (§10 #11)

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="demark_fractal_breakout",
            name="DeMark Fractal (LevDP=2) Breakout",
            version="0.1.0",
            author="wave2-fleet",
            hypothesis=(
                "When price breaks beyond a recently confirmed DeMark LevDP=2 swing "
                "point on H4, the break signals that the side which produced the "
                "last local extreme has lost control: stops clustered just beyond "
                "the fractal are triggered, short-term momentum traders pile in, "
                "and the retest-and-failure dynamic around a visible, widely-watched "
                "level propels price far enough to outrun the small structural stop "
                "behind the last opposite fractal. The edge should persist because "
                "LevDP=2 fractals are objective, identical on every trader's chart, "
                "and therefore concentrate real stop and entry orders at exactly the "
                "levels this system trades; the mandatory confirmation lag means the "
                "system buys strength after a pause rather than at the extreme "
                "itself, filtering out the noise breaks that eat naive tick-level "
                "breakout systems. It degrades in low-volatility mean-reverting "
                "regimes where every level break fails, and the 2007-era source "
                "offers no performance evidence — hence EXPERIMENTAL."
            ),
            granularities=["H4"],
            # §2 pairs_available only — the 8 Wave-1-pending pairs must not be
            # declared until their history is backfilled.
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="H4",
            context_granularities=(),  # §2: single-timeframe strategy
            simulate_on="H1",
            source_row=48,
            source_url=(
                "https://www.forexfactory.com/thread/37521-simple-pure-mechanical-"
                "h4-system-ea-needed"
            ),
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["confirmed_swing_points", "atr", "get_pip_value"]

    @property
    def warmup_bars(self) -> int:
        # No indicator here needs a long lookback (LevDP=2, a 3-bar staleness
        # window, plain forward-fills) — the binding constraint is the ATR(14)
        # the engine trails with (spec §6, F9). Matches the fleet convention
        # for ATR-trailing strategies (see inside_bar_continuation_ea.py):
        # enough bars for ATR14 to stabilise before the trail is trusted.
        return self.ATR_PERIOD * 3

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h4 = frames["H4"]
        # NOTE: pip conversion is keyed off metadata.pairs[0] because
        # generate_orders has no way to learn which pair's frames it was
        # handed (contract_v2 does not pass `pair`); this mirrors
        # REFERENCE_STRATEGY.py and every other Wave-2 strategy needing a pip
        # buffer. Flagged as an Uncertainty in the report: it means a run
        # against USD_JPY frames still converts pips at the EUR_USD rate.
        pip = float(get_pip_value(self.metadata.pairs[0]))

        entry_buffer = (self.ENTRY_BUFFER_PIPS + self.SPREAD_PROXY_PIPS) * pip
        stop_buffer = self.STOP_BUFFER_PIPS * pip

        # -- NOTE 1: fresh confirmation events, at the lag-adjusted bar ------
        red_events, blue_events = _confirmed_with_extra_lag(
            h4["High"], h4["Low"], period=self.LEVDP
        )

        # -- NOTE 2: staleness window [k+1 .. t], t == k+3 at a fresh event --
        recent_high_max3 = h4["High"].rolling(window=3, min_periods=3).max()
        recent_low_min3 = h4["Low"].rolling(window=3, min_periods=3).min()

        # -- NOTE 3: rolling "most recent knowable opposite circle" ----------
        last_red_level = red_events.ffill()
        last_blue_level = blue_events.ffill()

        close = h4["Close"].to_numpy(dtype=float)
        red_ev = red_events.to_numpy(dtype=float)
        blue_ev = blue_events.to_numpy(dtype=float)
        max3 = recent_high_max3.to_numpy(dtype=float)
        min3 = recent_low_min3.to_numpy(dtype=float)
        red_anchor = last_red_level.to_numpy(dtype=float)
        blue_anchor = last_blue_level.to_numpy(dtype=float)

        orders: List[OrderIntent] = []
        for i in range(self.warmup_bars, len(h4)):
            close_t = float(close[i])

            # ---------------- long: fresh red-circle break (spec §4) -------
            if not np.isnan(red_ev[i]):
                level = float(red_ev[i])
                # §4.2 staleness: no bar in [k+1, t] (inclusive) reached level.
                if max3[i] < level:
                    entry_price = level + entry_buffer
                    blue_level = blue_anchor[i]
                    # §4.3 stop anchor: most recent confirmed blue circle.
                    if not np.isnan(blue_level):
                        stop_price = float(blue_level) - stop_buffer
                        # §4.3(b): stop strictly below entry; NOTE 4: pending
                        # must sit above the decision close.
                        if stop_price < entry_price and entry_price > close_t:
                            orders.append(
                                OrderIntent(
                                    decision_bar=h4.index[i],
                                    direction=1,
                                    entry="buy_stop",
                                    entry_price=entry_price,
                                    decision_close=close_t,
                                    stop=StopRule(
                                        price=stop_price,
                                        move_to_breakeven_on=None,  # §6: none
                                        trail_atr_multiple=self.TRAIL_ATR_MULTIPLE,
                                    ),
                                    exits=[
                                        ExitLeg(
                                            fraction=1.0,
                                            kind="trailing",
                                            atr_multiple=self.TRAIL_ATR_MULTIPLE,
                                            label="TRAIL",
                                        )
                                    ],
                                    expires_after_bars=self.EXPIRES_AFTER_BARS,
                                    tag="red_circle_break",
                                    strategy_id=self.strategy_id,
                                )
                            )

            # ---------------- short: fresh blue-circle break (spec §5) -----
            if not np.isnan(blue_ev[i]):
                level = float(blue_ev[i])
                # §5.2 staleness: no bar in [j+1, t] (inclusive) reached level.
                if min3[i] > level:
                    entry_price = level - entry_buffer
                    red_level = red_anchor[i]
                    # §5.3 stop anchor: most recent confirmed red circle.
                    if not np.isnan(red_level):
                        stop_price = float(red_level) + stop_buffer
                        # §5.3: stop strictly above entry; NOTE 4: pending
                        # must sit below the decision close.
                        if stop_price > entry_price and entry_price < close_t:
                            orders.append(
                                OrderIntent(
                                    decision_bar=h4.index[i],
                                    direction=-1,
                                    entry="sell_stop",
                                    entry_price=entry_price,
                                    decision_close=close_t,
                                    stop=StopRule(
                                        price=stop_price,
                                        move_to_breakeven_on=None,  # §6: none
                                        trail_atr_multiple=self.TRAIL_ATR_MULTIPLE,
                                    ),
                                    exits=[
                                        ExitLeg(
                                            fraction=1.0,
                                            kind="trailing",
                                            atr_multiple=self.TRAIL_ATR_MULTIPLE,
                                            label="TRAIL",
                                        )
                                    ],
                                    expires_after_bars=self.EXPIRES_AFTER_BARS,
                                    tag="blue_circle_break",
                                    strategy_id=self.strategy_id,
                                )
                            )
        return orders
