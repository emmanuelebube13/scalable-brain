"""Strong/Weak Analysis — SPEC-strong_weak_analysis.md (CSV row 50).

Rank the 8 majors by relative strength, trade the strongest currency against the
weakest, entering on a pullback to confirmed D1 structure in the direction of the
D1 trend.

WHAT THE INTERFACE ALLOWS, AND WHERE THAT BITES — read before the code
-------------------------------------------------------------------------
``StrategyV2.generate_orders`` is handed ``Mapping[granularity -> DataFrame]`` for
**one pair at a time** (``v2_harness.build_frames`` loops over ``metadata.pairs``
and calls the strategy once per pair), and the frames carry no pair identity. The
cross-sectional part of this strategy — §3's per-currency strength sums, §3.5's
best/worst ranking and §3.6's candidate instrument — is therefore not computable
inside ``generate_orders``: the other 12 pairs' series are not reachable, and
neither is the answer to "is the pair I am holding the {best, worst} instrument?".

Consequences, all recorded in ``REPORT-strong_weak_analysis.md``:

* The **strength-rank gate is not applied**. This module emits the rest of the
  spec — §4.2/§5.2 trend filter, §4.3/§5.3 confirmed structure, §4.4/§5.4 pullback,
  §6 stop, §7 trailing leg — on whichever pair it is handed. It is a degeneration
  of the spec, not the spec: §4.1 would trade at most one instrument per bar out of
  13, this trades every pair that shows the pattern. It therefore takes *more*
  trades than the spec, on pairs the spec would not have selected, and its verdict
  is evidence about the trend-pullback skeleton only — never about the strength
  ranking, which is the part the author claimed the edge for.
* The cross-sectional rule is implemented here as three public pure functions —
  :func:`twenty_bar_return`, :func:`currency_strength` and
  :func:`candidate_instrument` — pinned by the golden fixture. A multi-pair harness
  can call them unchanged; **nothing in them is reachable from
  ``generate_orders``**, which never loads, imports or infers another pair.

This follows the precedent set by ``currency_momentum_factor`` (CSV row 43), the
other cross-sectional strategy in this fleet.

NOTE 1 — the swing level comes from ``causal_structure.confirmed_swing_points``,
    which stamps a swing at its CONFIRMATION bar (occurrence ``k``, stamped at
    ``k + period``) and carries the level set at ``k``. §4.3's staleness guard is
    expressed against the occurrence bar, so it is measured as
    ``confirmation_index - SWING_PERIOD >= t - STALENESS_BARS``. The banned
    ``indicators.detect_swing_points`` (centred window) is not used.

NOTE 2 — the stop is anchored to decision-bar values (§6, §10 #5): ``S - 1.0 x
    ATR14(t)`` for a long. Entries are ``market``, so the fill is unknowable at
    emission while ``StopRule.price`` must be an absolute float. Realised R
    therefore differs from declared R whenever price moves between the decision
    close and the fill; F3/F6 resolve that honestly.

NOTE 3 — §7 has no take-profit: the source rides trends for weeks to months and
    exits on "trend end / rank reversal", which contract v2 cannot express (exit
    kinds are take_profit | trailing | time). The single 3.0 x ATR trailing leg is
    the expressible proxy, and the fidelity loss is material (§10 #3).
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ...data_access.indicators import atr, sma
from ..causal_structure import confirmed_swing_points
from ..contract_v2 import (
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)

#: §3.1: the tradeable universe U — the 13 instruments the spec lists as available.
#: Five are live; the other eight are Wave-1 additions that never landed, so in
#: practice the strength sums would run on the five. Kept complete because these
#: helpers are the piece a multi-pair harness would call.
UNIVERSE: Tuple[str, ...] = (
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
)

#: §3.1: the currency set C.
CURRENCIES: Tuple[str, ...] = ("AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "NZD", "USD")


def twenty_bar_return(close: pd.Series, period: int = 20) -> pd.Series:
    """§3 row 4: ``ret20(t) = Close(t) / Close(t-period) - 1``.

    Trailing only — the value at *t* uses closes at *t-period* and *t*, both closed
    bars. Not reachable from :meth:`StrongWeakAnalysis.generate_orders`; it is one
    half of the cross-sectional input the single-pair interface cannot assemble.
    """
    if period <= 0:
        raise ValueError("twenty_bar_return: period must be positive")
    return close / close.shift(period) - 1.0


def currency_strength(z_by_pair: Mapping[str, float]) -> Dict[str, float]:
    """§3.3-§3.4: orient each pair's z-score onto its two currencies and sum.

    ``contrib(p -> c) = +z_p`` when *c* is the base of *p*, ``-z_p`` when it is the
    quote. A currency with no available cross at this bar is excluded from the
    result entirely (§3.4); one with a single cross is retained, which is CHF's
    normal state on the available data — a known bias recorded in §10 #7.

    Pairs outside :data:`UNIVERSE` are rejected rather than silently ignored, so a
    caller cannot widen the universe by accident. NaN z-scores are dropped: a pair
    whose 20-bar z-score has not warmed up contributes nothing.
    """
    unknown = sorted(set(z_by_pair) - set(UNIVERSE))
    if unknown:
        raise ValueError(f"currency_strength: pairs outside the universe {unknown}")
    strength: Dict[str, float] = {}
    for pair, z_value in z_by_pair.items():
        z = float(z_value)
        if not np.isfinite(z):
            continue
        base, quote = pair.split("_")
        strength[base] = strength.get(base, 0.0) + z
        strength[quote] = strength.get(quote, 0.0) - z
    return strength


def candidate_instrument(strength: Mapping[str, float]) -> Optional[Tuple[str, str]]:
    """§3.5-§3.6: pick {best, worst} and the unique instrument that expresses it.

    Returns ``(pair, best_currency)`` so the caller can tell which side of the pair
    the strong currency is on (§4.1 vs §5.1), or ``None`` when no instrument in
    :data:`UNIVERSE` joins the two currencies — §10 #4 forbids synthesising the
    position from two USD legs.

    §3.5 breaks ties by alphabetical currency code but does not say which end of a
    tie the *worst* takes. **DECISION:** one deterministic ranking is built —
    descending by strength, alphabetical within a tie — and ``best`` is its first
    entry, ``worst`` its last. So the alphabetically first of the tied maxima is
    best and the alphabetically *last* of the tied minima is worst. §3.5 calls exact
    ties measure-zero on float sums; this makes the outcome reproducible anyway.
    """
    ranked = sorted(strength.items(), key=lambda kv: (-float(kv[1]), kv[0]))
    if len(ranked) < 2:
        return None
    best = ranked[0][0]
    worst = ranked[-1][0]
    for pair in UNIVERSE:
        base, quote = pair.split("_")
        if {base, quote} == {best, worst}:
            return pair, best
    return None


class StrongWeakAnalysis(StrategyV2):
    """D1 trend + pullback to confirmed structure (strength rank not reachable)."""

    TREND_PERIOD = 50  # §3: SMA(50) trend filter
    ATR_PERIOD = 14  # §3: ATR(14), sizes the entry zone and the stop
    SWING_PERIOD = 5  # §3: confirmed_swing_points period AND confirmation lag
    STALENESS_BARS = 60  # §10 #6: swing occurrence must be within 60 D1 bars
    ZONE_ATR_MULTIPLE = 0.25  # §4.4/§5.4: depth of the entry zone around S/R
    STOP_ATR_MULTIPLE = 1.0  # §6: stop beyond the structure level
    TRAIL_ATR_MULTIPLE = 3.0  # §7: the single exit leg

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="strong_weak_analysis",
            name="Strong/Weak Analysis (trend + structure pullback)",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "Currency strength differentials driven by diverging central-bank "
                "policy, growth expectations, and the resulting institutional capital "
                "re-allocation persist for weeks to months, because large allocators "
                "cannot re-weight portfolios in a single session and because macro "
                "regimes change slowly. Ranking the 8 major currencies by recent "
                "relative performance and concentrating exposure in the single pair "
                "that combines the strongest currency against the weakest maximises "
                "the exploited differential per trade, while a D1 trend filter and "
                "entries at structural support/resistance avoid buying exhaustion. "
                "The entire edge claim rests on a proprietary strength formula the "
                "author never disclosed, so what is measured here is the reconstruction "
                "and not the author's method."
            ),
            granularities=["D1"],
            # §2 pairs_available, live subset only: the eight Wave-1 additions never
            # landed. Declaring them would only produce skipped cells.
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="D1",
            context_granularities=(),  # §2: every input is on the D1 frame
            simulate_on="H1",
            source_row=50,
            source_url=(
                "https://forums.babypips.com/t/"
                "trading-the-trend-with-strong-weak-analysis/77959"
            ),
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["sma", "atr", "zscore", "confirmed_swing_points"]

    @property
    def warmup_bars(self) -> int:
        # The binding input is SMA(50); the staleness window (60) is a guard, not a
        # requirement, and the 40-bar z-score warm-up belongs to the unreachable
        # cross-sectional path.
        return self.TREND_PERIOD + self.SWING_PERIOD

    @property
    def max_concurrent_positions(self) -> int:
        """§4 / §10 #9 (F12): one position per pair; re-emission is expected."""
        return 1

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        d1 = frames[self.metadata.primary_granularity]
        if len(d1) <= self.warmup_bars:
            return []

        close = d1["Close"].to_numpy(dtype=float)
        high = d1["High"].to_numpy(dtype=float)
        low = d1["Low"].to_numpy(dtype=float)
        trend = sma(d1["Close"], self.TREND_PERIOD).to_numpy(dtype=float)
        atr_values = atr(
            d1["High"], d1["Low"], d1["Close"], period=self.ATR_PERIOD
        ).to_numpy(dtype=float)

        # NOTE 1: levels stamped at their confirmation bar, carrying the occurrence
        # bar's price. `last_*` walks the confirmation stamps forward so that at
        # every bar t we hold the most recently CONFIRMED level and the bar it was
        # confirmed on — from which the occurrence bar is confirmation - period.
        swing_highs, swing_lows = confirmed_swing_points(
            d1["High"], d1["Low"], period=self.SWING_PERIOD
        )
        last_low_at, last_low_level = self._latest_confirmed(swing_lows)
        last_high_at, last_high_level = self._latest_confirmed(swing_highs)

        index = d1.index
        orders: List[OrderIntent] = []
        for i in range(self.warmup_bars, len(d1)):
            atr_t = float(atr_values[i])
            trend_t = float(trend[i])
            if not np.isfinite(atr_t) or atr_t <= 0.0 or not np.isfinite(trend_t):
                continue
            close_t = float(close[i])
            zone = self.ZONE_ATR_MULTIPLE * atr_t

            # -- §4 long: uptrend, price dipped into the support zone, closed above
            if close_t > trend_t and self._fresh(last_low_at[i], i):
                support = float(last_low_level[i])
                if low[i] <= support + zone and close_t > support:
                    orders.append(
                        self._intent(
                            index[i],
                            1,
                            close_t,
                            support - self.STOP_ATR_MULTIPLE * atr_t,
                        )
                    )
                    continue  # §5: at most one intent per decision bar

            # -- §5 short: the exact mirror
            if close_t < trend_t and self._fresh(last_high_at[i], i):
                resistance = float(last_high_level[i])
                if high[i] >= resistance - zone and close_t < resistance:
                    orders.append(
                        self._intent(
                            index[i],
                            -1,
                            close_t,
                            resistance + self.STOP_ATR_MULTIPLE * atr_t,
                        )
                    )
        return orders

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _latest_confirmed(confirmed: pd.Series) -> Tuple[np.ndarray, np.ndarray]:
        """Positions and levels of the most recent confirmation at or before each bar.

        ``confirmed`` is NaN except at confirmation bars. The returned position array
        holds -1 until the first confirmation, so a bar with no structure behind it
        is distinguishable from one whose structure is merely old.
        """
        values = confirmed.to_numpy(dtype=float)
        marked = np.where(np.isnan(values), -1, np.arange(len(values)))
        positions = np.maximum.accumulate(marked)
        levels = np.where(positions >= 0, values[positions], np.nan)
        return positions, levels

    def _fresh(self, confirmation_pos: int, i: int) -> bool:
        """§4.3 staleness guard, measured on the OCCURRENCE bar (NOTE 1)."""
        if confirmation_pos < 0:
            return False
        occurrence = int(confirmation_pos) - self.SWING_PERIOD
        return occurrence >= i - self.STALENESS_BARS

    def _intent(
        self,
        decision_bar: pd.Timestamp,
        direction: int,
        decision_close: float,
        stop_price: float,
    ) -> OrderIntent:
        return OrderIntent(
            decision_bar=decision_bar,
            direction=1 if direction > 0 else -1,
            entry="market",  # §4/§5: fills at the next bar's open (F1/F2)
            entry_price=None,
            decision_close=decision_close,
            stop=StopRule(price=stop_price),  # §6: no breakeven, no StopRule trail
            exits=[
                ExitLeg(
                    fraction=1.0,
                    kind="trailing",
                    atr_multiple=self.TRAIL_ATR_MULTIPLE,
                    label="TRAIL",
                )
            ],
            expires_after_bars=None,  # §4: market intents are never pending
            tag="sw_trend_pullback_norank",  # the degradation, visible per trade
            strategy_id=self.strategy_id,
        )
