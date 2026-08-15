"""Holy Grail Pullback — row 29 of ``forex_swing_strategies.csv``.

Spec: ``task/2026-August-week1/fleet/upload/wave2/specs/SPEC-holy_grail_pullback.md``
Source: https://tradingstrategyguides.com/professional-trading-strategies/

Single-timeframe (D1) trend-continuation pullback. On every closed D1 bar
``t`` the strategy checks (spec §4 long / §5 short, mirrored):

1. **Trend-strength breakout episode** (§4.1/§5.1): ADX(14)[t] > 30, AND the
   current above-30 run began with an *observed* upward cross (there exists a
   bar k <= t with ADX[k-1] <= 30 and ADX[k] > 30, and ADX > 30 continuously
   from k through t). If the whole available history is already above 30 with
   no observable cross, the condition fails — there is no knowable breakout.
2. **ADX rising into the pullback** (§4.2/§5.2): ADX[t-1] > 30 AND
   ADX[t-1] > ADX[t-2].
3. **Touch candle** (§4.3 long / §5.3 short): Low[t] <= SMA20[t] AND
   Close[t] > SMA20[t] for longs (mirror for shorts).
4. **Structural validity gates** (§4.7/§5.7): the most recent CONFIRMED swing
   low/high (period=5, ``causal_structure.confirmed_swing_points``) knowable
   at bar t must exist and sit on the correct side of the entry level, or the
   setup is skipped — emit nothing.

Everything is trailing-only: ADX and SMA20 are causal rolling/EWM
computations over completed bars only, and swing levels are read through
``causal_structure.last_n_confirmed_highs`` / ``last_n_confirmed_lows``, which
stamp a swing level at its CONFIRMATION bar (occurrence bar k + period), never
at occurrence. ``indicators.detect_swing_points`` (center=True) is never used.

There is no context frame (spec §2: ``context_granularities: none``) — H1 is
fill resolution only (contract §5) and is never read here.

Geometry is anchored to decision-bar-knowable levels (spec §6/§7):

* entry (long) = ``High[t] + 1 pip`` (``buy_stop``); entry (short) =
  ``Low[t] - 1 pip`` (``sell_stop``) — pseudocode's ``entry = high/low + tick``.
* stop (long) = most recent confirmed swing low, minus 1 pip; stop (short) =
  most recent confirmed swing high, plus 1 pip (spec §6, §10 #3: the source's
  "swing low formed AFTER fill" is unknowable at ``OrderIntent`` creation and
  therefore inexpressible — this is the conservative, expressible substitute).
* one take-profit leg, fraction 1.0, at the most recent confirmed swing
  high/low level exactly (spec §7, §10 #4: the trailing-stop alternative is
  rejected).
* ``expires_after_bars=1`` (spec §10 #5: source silent, conservative shortest
  non-zero lifetime).
* no breakeven move, no trailing stop — the source has neither (spec §6).

**Pip size without a pair name** (interface gap, same as
``research/amazing_crossover.py``'s ``_pip_size_from_price``): spec §3 says
``pip = get_pip_value(pair)``, but ``generate_orders`` receives frames only —
no pair identity is available at the point the geometry is built. Using
``metadata.pairs[0]`` (as the reference strategy does) would apply a 0.0001
pip to the JPY-quoted pairs in this strategy's own pair list (USD_JPY,
GBP_JPY, EUR_JPY) and shrink a 1-pip offset to 1/100th of its intended size.
Instead the pip size is inferred from the decision-bar close's own quote
magnitude — JPY-quoted pairs trade above ``_JPY_QUOTE_THRESHOLD``, every other
pair in this strategy's universe trades below it. This keeps the function
causal (reads one completed bar) and pure; recorded as an interface gap in
the report, not a shared-file fix.
"""

from __future__ import annotations

from typing import List, Mapping, Sequence

import numpy as np
import pandas as pd

from ..causal_structure import last_n_confirmed_highs, last_n_confirmed_lows
from ..contract_v2 import (
    Direction,
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)
from ...data_access.indicators import adx, get_pip_value, sma

# Same convention as research/amazing_crossover.py's `_pip_size_from_price`:
# every JPY-quoted pair in this strategy's pair list (USD_JPY, GBP_JPY,
# EUR_JPY) trades above 20; every non-JPY pair (majors and minors alike)
# trades well below it.
_JPY_QUOTE_THRESHOLD = 20.0


def _pip_size_from_price(price: float) -> float:
    """Infer the pip size from a decision-bar close (see module docstring)."""
    pair = "USD_JPY" if price >= _JPY_QUOTE_THRESHOLD else "EUR_USD"
    return float(get_pip_value(pair))


def _adx_breakout_episode(adx_values: np.ndarray, threshold: float) -> np.ndarray:
    """Spec §4.1/§5.1: is bar t inside an ADX>threshold episode that began with
    an OBSERVED upward cross?

    A run of consecutive ``adx > threshold`` bars is scanned forward once.
    Each time a new run starts at position ``k``, the cross is "observed" only
    if ``k >= 1`` and ``adx[k-1]`` is a finite, real value ``<= threshold``
    (not NaN — a value that was never computed cannot have been "observed").
    That observed-or-not flag is carried for every bar of the run; a bar that
    drops back to/below the threshold resets the run and clears the flag, so a
    fresh cross is required to re-open the gate (declining WITHIN a run is
    allowed and does not reset it, per spec §4.1).
    """
    n = int(adx_values.shape[0])
    episode_ok = np.zeros(n, dtype=bool)
    in_run = False
    cross_observed = False
    for t in range(n):
        val = adx_values[t]
        is_above = bool(np.isfinite(val) and val > threshold)
        if is_above:
            if not in_run:
                in_run = True
                if t >= 1:
                    prev = adx_values[t - 1]
                    cross_observed = bool(np.isfinite(prev) and prev <= threshold)
                else:
                    cross_observed = False
            episode_ok[t] = cross_observed
        else:
            in_run = False
            cross_observed = False
    return episode_ok


class HolyGrailPullback(StrategyV2):
    """Trade the resumption of a strong D1 trend on a 20-SMA touch-and-reject."""

    SMA_PERIOD = 20
    ADX_PERIOD = 14
    ADX_THRESHOLD = 30.0
    SWING_PERIOD = 5  # swing definition AND confirmation lag
    ENTRY_TICK_PIPS = 1.0  # spec §4.5/§5.5: entry = high/low +/- 1 pip
    STOP_BUFFER_PIPS = 1.0  # spec §6: swing level -/+ 1 pip
    EXPIRY_BARS = 1  # spec §4.6/§5.6, §10 #5
    WARMUP = 100  # SMA20 + ADX14 double-smoothing + swing confirmation, w/ margin

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="holy_grail_pullback",
            name="Holy Grail Pullback",
            version="0.1.0",
            author="wave2-fleet",
            hypothesis=(
                "When ADX(14) holds above 30 the market is in a persistent, "
                "institutionally-backed directional move; a pullback to the "
                "20-period mean is profit-taking exhaustion, not reversal, so "
                "momentum should resume once the counter-move stalls at the mean. "
                "The edge should persist because trend-following capital (CTAs, "
                "breakout systems) re-engages exactly at widely-watched mean "
                "levels in confirmed-strength regimes, and the ADX>30 gate keeps "
                "the strategy out of the ranging conditions where mean retests "
                "fail."
            ),
            granularities=["D1"],
            pairs=[
                "EUR_USD",
                "GBP_USD",
                "USD_JPY",
                "AUD_USD",
                "USD_CAD",
                "GBP_JPY",
                "EUR_JPY",
                "NZD_USD",
                "USD_CHF",
                "EUR_GBP",
                "EUR_AUD",
                "AUD_NZD",
                "EUR_CAD",
            ],
            primary_granularity="D1",
            context_granularities=(),
            simulate_on="H1",
            source_row=29,
            source_url="https://tradingstrategyguides.com/professional-trading-strategies/",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["sma", "adx", "confirmed_swing_points"]

    @property
    def warmup_bars(self) -> int:
        return self.WARMUP

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        d1 = frames["D1"]
        high = d1["High"]
        low = d1["Low"]
        close = d1["Close"]

        sma20 = sma(close, self.SMA_PERIOD)
        adx14 = adx(high, low, close, self.ADX_PERIOD)

        swing_highs = last_n_confirmed_highs(high, low, n=1, period=self.SWING_PERIOD)
        swing_lows = last_n_confirmed_lows(high, low, n=1, period=self.SWING_PERIOD)
        swing_high_level = swing_highs["level_1"].to_numpy(dtype=float)
        swing_low_level = swing_lows["level_1"].to_numpy(dtype=float)

        adx_vals = adx14.to_numpy(dtype=float)
        sma_vals = sma20.to_numpy(dtype=float)
        high_vals = high.to_numpy(dtype=float)
        low_vals = low.to_numpy(dtype=float)
        close_vals = close.to_numpy(dtype=float)
        index = d1.index
        n = len(d1)

        episode_ok = _adx_breakout_episode(adx_vals, self.ADX_THRESHOLD)

        orders: List[OrderIntent] = []
        for t in range(max(self.warmup_bars, 2), n):
            # -- §4.1/§5.1 trend-strength breakout episode --------------
            if not episode_ok[t]:
                continue

            # -- §4.2/§5.2 ADX rising into the pullback ------------------
            a1 = adx_vals[t - 1]
            a2 = adx_vals[t - 2]
            if not (np.isfinite(a1) and np.isfinite(a2)):
                continue
            if not (a1 > self.ADX_THRESHOLD and a1 > a2):
                continue

            sma_t = sma_vals[t]
            if not np.isfinite(sma_t):
                continue

            close_t = float(close_vals[t])
            high_t = float(high_vals[t])
            low_t = float(low_vals[t])
            swh = float(swing_high_level[t])
            swl = float(swing_low_level[t])
            pip = _pip_size_from_price(close_t)

            touch_long = low_t <= sma_t and close_t > sma_t
            touch_short = high_t >= sma_t and close_t < sma_t

            if touch_long:
                # §4.5: entry = High[t] + 1 pip.
                entry = high_t + self.ENTRY_TICK_PIPS * pip
                if np.isnan(swl) or np.isnan(swh):
                    continue  # §4.7: no confirmed structure known yet — skip
                stop_price = swl - self.STOP_BUFFER_PIPS * pip  # §6
                tp_price = swh  # §7: exact confirmed swing-high level
                if not stop_price < entry:
                    continue  # §4.7 gate 1: stop must sit below entry
                if not tp_price > entry:
                    continue  # §4.7 gate 2: TP must sit beyond entry
                direction: Direction = 1
                orders.append(
                    OrderIntent(
                        decision_bar=index[t],
                        direction=direction,
                        entry="buy_stop",
                        entry_price=entry,
                        decision_close=close_t,
                        stop=StopRule(
                            price=stop_price,
                            move_to_breakeven_on=None,  # §6: source has none
                            trail_atr_multiple=None,  # §6: static stop
                        ),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="take_profit",
                                price=tp_price,
                                label="TP1",
                            )
                        ],
                        expires_after_bars=self.EXPIRY_BARS,
                        tag="holy_grail_pullback",
                        strategy_id=self.strategy_id,
                    )
                )
            elif touch_short:
                # §5.5: entry = Low[t] - 1 pip.
                entry = low_t - self.ENTRY_TICK_PIPS * pip
                if np.isnan(swl) or np.isnan(swh):
                    continue  # §5.7: no confirmed structure known yet — skip
                stop_price = swh + self.STOP_BUFFER_PIPS * pip  # §6
                tp_price = swl  # §7: exact confirmed swing-low level
                if not stop_price > entry:
                    continue  # §5.7 gate 1: stop must sit above entry
                if not tp_price < entry:
                    continue  # §5.7 gate 2: TP must sit beyond entry
                direction = -1
                orders.append(
                    OrderIntent(
                        decision_bar=index[t],
                        direction=direction,
                        entry="sell_stop",
                        entry_price=entry,
                        decision_close=close_t,
                        stop=StopRule(
                            price=stop_price,
                            move_to_breakeven_on=None,
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
                        expires_after_bars=self.EXPIRY_BARS,
                        tag="holy_grail_pullback",
                        strategy_id=self.strategy_id,
                    )
                )
        return orders
