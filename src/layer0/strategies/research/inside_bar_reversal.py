"""inside_bar_reversal — counter-trend inside-bar reversal off the nearest confirmed swing.

Spec: ``task/2026-August-week1/fleet/upload/wave2/specs/SPEC-inside_bar_reversal.md`` (source row 25,
https://www.earnforex.com/forex-strategy/inside-bar-strategy).

Single-timeframe strategy — ``context_granularities`` is empty (spec §2). Everything is
read off the primary D1 frame; there is no multi-timeframe join to get wrong, so reference
NOTE 1 (``closed_context_frame`` / ``merge_asof``) does not apply here.

The pattern (spec §4 long / §5 short), evaluated at the close of decision bar ``t`` (the
"container bar" is ``t-1``):

1. Trend precondition on ``tr = close.diff(10).rolling(5).mean()`` (spec §3) — a private,
   fully specified formula, not part of the shared indicator inventory.
2. Container bar (``t-1``) colour opposite to the reversal direction.
3. Strict inside bar: ``High[t] < High[t-1] and Low[t] > Low[t-1]`` (equal extremes fail
   the pattern — spec §10 #6). Identical for both directions.
4. Inside bar colour matches the reversal direction.
5. A TP-existence gate (the "declarability gate", spec §4 cond. 5 / §5 cond. 5): at least
   one confirmed swing extreme (``causal_structure.confirmed_swing_points``, period=5)
   strictly beyond the decision close, in the trade direction. No such level -> no order
   is emitted (spec §10 #5); a fallback exit is never invented.

Entry is ``market`` (fills at the open of bar ``t+1``, F1/F2 — the intent carries no entry
price). Stop and the single take-profit leg are absolute levels fully knowable at the close
of ``t`` (spec §6/§7): stop = the container bar's extreme, TP = the nearest confirmed swing
extreme beyond the close. No breakeven, no trail (spec §6), no minimum reward:risk filter
(spec §10 #3) — reference NOTE 4's "fill-anchored R is inexpressible" reasoning is exactly
why the stop/TP are anchored to decision-bar-knowable prices instead of the (unknown) fill.

NOTE (nearest confirmed level, not most-recent): ``causal_structure.last_n_confirmed_highs``
/ ``last_n_confirmed_lows`` give the *n most recently confirmed* levels — not the level
*nearest a price*. In a trend, the most recently confirmed extreme is not always the
nearest one beyond the current close (an older, larger swing can still be the closest one
on the correct side of price). ``_nearest_confirmed_above`` / ``_nearest_confirmed_below``
below track the running set of every level confirmed so far and binary-search it, so
"nearest" is computed exactly as spec §4/§5/§7 state it, rather than approximated by
"most recently confirmed". Both helpers only ever insert ``confirmed[t]`` before querying
row ``t``, so recomputing on a truncated prefix reproduces every row up to the truncation
identically (required by ``assert_no_lookahead_v2``).
"""

from __future__ import annotations

import bisect
from typing import List, Mapping, Sequence

import numpy as np
import pandas as pd

from ..causal_structure import confirmed_swing_points
from ..contract_v2 import ExitLeg, OrderIntent, StopRule, StrategyMetadataV2, StrategyV2


def _trend_slope(close: pd.Series, diff_period: int, ma_period: int) -> pd.Series:
    """Spec §3: ``tr[t] = mean(close[i] - close[i-10] for i in [t-4 .. t])``.

    Exactly ``close.diff(diff_period).rolling(ma_period).mean()`` — the CSV's own
    pseudocode, reproduced verbatim. Causal: ``tr[t]`` depends only on
    ``close[t - diff_period - ma_period + 1 .. t]``; no future bar is consulted.
    """
    return close.diff(diff_period).rolling(ma_period).mean()


def _nearest_confirmed_above(confirmed: pd.Series, reference: pd.Series) -> np.ndarray:
    """Spec §4 cond. 5 / §7 TP1 (long): the nearest confirmed level strictly ABOVE
    ``reference[t]``, using only levels whose confirmation bar is ``<= t``.

    ``confirmed`` carries a level at its CONFIRMATION bar (NaN elsewhere) — the
    ``causal_structure.confirmed_swing_points`` convention. At each bar ``t`` this
    inserts ``confirmed[t]`` (if any) into a running sorted set *before* querying it, so
    a level confirming exactly at ``t`` (occurrence ``k`` with ``k + period == t``) is
    included — matching the spec's ``k + 5 <= t``. Row ``t`` only ever consults
    ``confirmed[0 .. t]``, so recomputing on a truncated prefix reproduces every row up
    to the truncation identically.
    """
    values = confirmed.to_numpy(dtype=float)
    ref = reference.to_numpy(dtype=float)
    out = np.full(len(values), np.nan, dtype=float)
    levels: List[float] = []
    for t in range(len(values)):
        level = values[t]
        if not np.isnan(level):
            bisect.insort(levels, float(level))
        if levels:
            idx = bisect.bisect_right(levels, float(ref[t]))
            if idx < len(levels):
                out[t] = levels[idx]
    return out


def _nearest_confirmed_below(confirmed: pd.Series, reference: pd.Series) -> np.ndarray:
    """Mirror of :func:`_nearest_confirmed_above` for swing lows (spec §5 cond. 5 / §7
    TP1 short): the nearest confirmed level strictly BELOW ``reference[t]``."""
    values = confirmed.to_numpy(dtype=float)
    ref = reference.to_numpy(dtype=float)
    out = np.full(len(values), np.nan, dtype=float)
    levels: List[float] = []
    for t in range(len(values)):
        level = values[t]
        if not np.isnan(level):
            bisect.insort(levels, float(level))
        if levels:
            idx = bisect.bisect_left(levels, float(ref[t]))
            if idx > 0:
                out[t] = levels[idx - 1]
    return out


class InsideBarReversal(StrategyV2):
    """Counter-trend inside bar; target the nearest confirmed swing extreme (spec §1)."""

    TREND_DIFF_PERIOD = 10  # spec §3: close.diff(10)
    TREND_MA_PERIOD = 5  # spec §3: .rolling(5).mean()
    SWING_PERIOD = 5  # spec §3/§9: swing definition AND confirmation lag

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="inside_bar_reversal",
            name="Inside Bar Reversal",
            version="0.1.0",
            author="wave2-fleet",
            hypothesis=(
                "An inside bar that forms against the prevailing trend, after a mature "
                "directional move, marks a volatility contraction and order-flow "
                "exhaustion: the counter-trend container bar has spent the last "
                "directional push, and the inside bar's failure to make a new trend "
                "extreme shows the dominant side can no longer attract follow-through. "
                "Traders positioned with the trend take profits and late entrants are "
                "trapped, so price mean-reverts toward the nearest structural level (the "
                "last confirmed swing in the reversal direction) more often than chance. "
                "The edge should persist because it rests on durable behavioural "
                "mechanics — profit-taking after extended moves and the informational "
                "content of range contraction — rather than on any fragile parameter."
            ),
            granularities=["D1"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="D1",
            context_granularities=(),
            simulate_on="H1",
            source_row=25,
            source_url="https://www.earnforex.com/forex-strategy/inside-bar-strategy",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["confirmed_swing_points", "trend_slope_diff10_roll5"]

    @property
    def warmup_bars(self) -> int:
        # tr needs TREND_DIFF_PERIOD + TREND_MA_PERIOD - 1 = 14 trailing closes; a few
        # extra bars give the swing structure a realistic chance to have confirmed at
        # least once before the first decision is trusted.
        return 20

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        d1 = frames[self.metadata.primary_granularity]

        open_ = d1["Open"].to_numpy(dtype=float)
        high = d1["High"].to_numpy(dtype=float)
        low = d1["Low"].to_numpy(dtype=float)
        close = d1["Close"].to_numpy(dtype=float)

        tr = _trend_slope(
            d1["Close"], self.TREND_DIFF_PERIOD, self.TREND_MA_PERIOD
        ).to_numpy(dtype=float)

        swing_highs, swing_lows = confirmed_swing_points(
            d1["High"], d1["Low"], period=self.SWING_PERIOD
        )
        tp_long = _nearest_confirmed_above(swing_highs, d1["Close"])
        tp_short = _nearest_confirmed_below(swing_lows, d1["Close"])

        orders: List[OrderIntent] = []
        for i in range(self.warmup_bars, len(d1)):
            if np.isnan(tr[i]):
                continue
            # -- condition 3 (spec §4/§5): strict inside bar, shared by both directions.
            if not (high[i] < high[i - 1] and low[i] > low[i - 1]):
                continue

            container_bearish = close[i - 1] < open_[i - 1]
            container_bullish = close[i - 1] > open_[i - 1]
            inside_bullish = close[i] > open_[i]
            inside_bearish = close[i] < open_[i]

            if tr[i] < 0.0 and container_bearish and inside_bullish:
                # -- condition 5 (spec §4): TP-existence gate for the long side.
                tp = tp_long[i]
                if np.isnan(tp):
                    continue  # spec §10 #5: no confirmed level -> no order, ever
                orders.append(
                    OrderIntent(
                        decision_bar=d1.index[i],
                        direction=1,
                        entry="market",
                        entry_price=None,
                        stop=StopRule(price=float(low[i - 1])),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="take_profit",
                                price=float(tp),
                                label="TP1",
                            )
                        ],
                        expires_after_bars=None,
                        size_fraction=1.0,
                        tag="inside_bar_reversal_long",
                        strategy_id=self.strategy_id,
                    )
                )
            elif tr[i] > 0.0 and container_bullish and inside_bearish:
                # -- condition 5 (spec §5): TP-existence gate for the short side.
                tp = tp_short[i]
                if np.isnan(tp):
                    continue  # spec §10 #5: no confirmed level -> no order, ever
                orders.append(
                    OrderIntent(
                        decision_bar=d1.index[i],
                        direction=-1,
                        entry="market",
                        entry_price=None,
                        stop=StopRule(price=float(high[i - 1])),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="take_profit",
                                price=float(tp),
                                label="TP1",
                            )
                        ],
                        expires_after_bars=None,
                        size_fraction=1.0,
                        tag="inside_bar_reversal_short",
                        strategy_id=self.strategy_id,
                    )
                )
        return orders
