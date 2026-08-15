"""ema_cross_h4_filter_bot — H1 EMA9/21 cross gated by an H4 EMA200 regime.

Spec: ``task/2026-August-week1/fleet/upload/wave2/specs/SPEC-ema_cross_h4_filter_bot.md``
(row 41 of ``forex_swing_strategies.csv``).

Shape and conventions follow ``reference_pullback_continuation.py``. Its four
numbered NOTES were checked against this spec; why each does or does not bind is
recorded here so a reviewer need not re-derive it:

* **NOTE 1 (causal MTF join)** — **binds.** Spec §2 declares an H4 context frame
  and §9 fixes the join rule: an H4 bar stamped ``T`` may inform the H1 decision
  on bar ``t`` only when ``T + 4h <= t``. That is implemented by re-stamping the
  H4 frame at its CLOSE (``index + GRANULARITY_INTERVAL["H4"]``) and
  ``merge_asof(direction="backward")`` onto the H1 index — the vectorised form of
  ``contract_v2.closed_context_frame(h4, "H4", t)``. The naive
  ``h4.loc[h4.index <= t]`` would admit the H4 bar that is still forming and is
  the 108-phantom-order bug.
* **NOTE 2 (causal swing structure)** — does not bind. Spec §3 states no
  swing/ZigZag/pivot/fractal construct is used anywhere, so nothing from
  ``causal_structure`` is needed and ``detect_swing_points`` is not imported.
* **NOTE 3 (pending entry on the right side of the close)** — does not bind.
  Spec §4/§5 emit ``market`` entries only, so there is no pending level to
  validate. ``decision_close`` is still carried for the engine's records.
* **NOTE 4 (breakeven names an existing leg)** — does not bind. Spec §6 declares
  ``move_to_breakeven_on: none`` and ``trail: none`` — a static stop.

One documented spec inconsistency (see REPORT Uncertainties): §9's *mechanical*
footnote suggests ``merge_asof(..., allow_exact_matches=False)``, which would
demand ``T + 4h < t`` and so discard the H4 bar that closes exactly as the H1
decision bar opens — one bar in four. The normative rule ``T + 4h <= t`` is
stated four times (§4.2, §5.2, §8, §9) and is what is implemented here, matching
``closed_context_frame`` exactly.
"""

from __future__ import annotations

from typing import List, Mapping, Sequence

import numpy as np
import pandas as pd

from ..contract_v2 import (
    GRANULARITY_INTERVAL,
    Direction,
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)
from ...data_access.indicators import ema, get_pip_value

#: Quotes at or above this level are JPY-quoted (USD_JPY ~110, EUR_USD ~1.10).
#: Same convention as ``amazing_crossover`` / ``holy_grail_pullback``.
_JPY_QUOTE_THRESHOLD = 20.0


def _pip_size_from_price(price: float) -> float:
    """Pip size for the instrument whose quote is ``price`` (spec §3).

    Spec §3 says ``pip = get_pip_value(pair)``. The v2 contract never passes the
    pair to the strategy (``generate_orders`` receives frames only), so the pair
    name is not available where the geometry is built; taking
    ``metadata.pairs[0]`` would apply a 0.0001 pip to USD_JPY and turn the
    50-pip stop into a 0.5-pip stop. The pip *magnitudes* still come from the
    inventory ``get_pip_value``; only the quote convention is inferred, from one
    completed bar's close, which keeps this causal and pure.
    """
    pair = "USD_JPY" if price >= _JPY_QUOTE_THRESHOLD else "EUR_USD"
    return float(get_pip_value(pair))


class EmaCrossH4FilterBot(StrategyV2):
    """Take fresh H1 EMA9/21 crosses only in the direction of the H4 EMA200 regime."""

    EMA_FAST_PERIOD = 9  # §3 — EMA(H1 close, 9)
    EMA_SLOW_PERIOD = 21  # §3 — EMA(H1 close, 21)
    EMA_REGIME_PERIOD = 200  # §3 — EMA(H4 close, 200)
    STOP_PIPS = 50.0  # §6 — hard stop, 50 pips from C
    TP_PIPS = 100.0  # §7 — hard target, 100 pips from C (1:2 RR)
    SESSION_START_HOUR = 7  # §4.3 / §8 — decision instant in [07:00, 21:00) UTC
    SESSION_END_HOUR = 21  # §4.3 / §8 — exclusive upper bound
    EXPIRY_BARS = 1  # §4 — a market intent fills at the next open or dies

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="ema_cross_h4_filter_bot",
            name="EMA Cross with H4 Filter Bot",
            version="0.1.0",
            author="wave2-fleet",
            hypothesis=(
                "Fast/slow EMA crosses on H1 capture the early phase of "
                "short-horizon momentum bursts, and requiring price to be on the "
                "correct side of the H4 EMA200 suppresses the counter-trend "
                "whipsaws that destroy naked crossover systems. The claimed "
                "persistence mechanism is behavioural: medium-horizon "
                "trend-following profits from the under-reaction and herding of "
                "market participants around established H4 regimes, so H1 crosses "
                "aligned with the dominant regime should have positive expectancy "
                "at a 1:2 reward-to-risk bracket, while crosses against the regime "
                "are mostly noise and are skipped."
            ),
            granularities=["H1", "H4"],
            # §2 pairs_available, LIVE only. The five "pending" Wave-1 additions
            # (USD_CHF, NZD_USD, EUR_GBP, EUR_JPY, GBP_JPY) are excluded per the
            # run brief: never declare a pair the spec lists as pending.
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "USD_CAD", "AUD_USD"],
            primary_granularity="H1",
            context_granularities=("H4",),  # §2 — EMA200 regime filter only
            simulate_on="H1",
            source_row=41,
            source_url=(
                "https://github.com/igormoondev/forex-meta-trader-trading-bot"
            ),
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["ema"]

    @property
    def warmup_bars(self) -> int:
        """Derived, not chosen, and counted in H1 bars (the primary frame).

        The deepest chain is the H4 EMA200: ``EMA_REGIME_PERIOD`` H4 bars, each
        four H1 bars long, so ``4 * EMA_REGIME_PERIOD`` H1 bars must elapse
        before the regime value carries its full window. The H1 EMA21 needs far
        less; ``3 * EMA_SLOW_PERIOD`` is the usual ewm settling allowance. The
        larger of the two governs.
        """
        return max(4 * self.EMA_REGIME_PERIOD, 3 * self.EMA_SLOW_PERIOD)

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def _regime_sign(
        self, h1_index: pd.Index, h4: pd.DataFrame
    ) -> "np.ndarray[object, np.dtype[np.float64]]":
        """§4.2 / §5.2 / §8: +1 bullish, -1 bearish, 0 flat, NaN unknown.

        The H4 frame is re-stamped at each bar's CLOSE and joined backward, so
        the value attached to H1 bar ``t`` comes from the last H4 bar ``T`` with
        ``T + 4h <= t`` (§9). See NOTE 1 in the module docstring.
        """
        regime_ema = ema(h4["Close"], self.EMA_REGIME_PERIOD)
        sign = np.sign(h4["Close"].to_numpy(dtype=float) - regime_ema.to_numpy(dtype=float))
        h4_at_close = pd.DataFrame(
            {"regime": sign},
            index=pd.DatetimeIndex(h4.index) + GRANULARITY_INTERVAL["H4"],
        )
        joined = pd.merge_asof(
            pd.DataFrame(index=h1_index),
            h4_at_close,
            left_index=True,
            right_index=True,
            direction="backward",
        )
        return joined["regime"].to_numpy(dtype=float)

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h1 = frames["H1"]
        h4 = frames["H4"]

        fast = ema(h1["Close"], self.EMA_FAST_PERIOD).to_numpy(dtype=float)
        slow = ema(h1["Close"], self.EMA_SLOW_PERIOD).to_numpy(dtype=float)
        regime = self._regime_sign(h1.index, h4)

        # §4.3 / §8: the decision instant is the CLOSE of H1 bar t, i.e. one full
        # H1 interval after the open-stamped index label.
        decision_instant = pd.DatetimeIndex(h1.index) + GRANULARITY_INTERVAL["H1"]
        decision_hour = np.asarray(decision_instant.hour, dtype=int)

        close = h1["Close"].to_numpy(dtype=float)
        index = h1.index

        orders: List[OrderIntent] = []
        # warmup_bars >= 1 by construction, so index i-1 always exists.
        for i in range(max(self.warmup_bars, 1), len(h1)):
            # §4.3 / §5.3 — session gate first; it is the cheapest test.
            if not (
                self.SESSION_START_HOUR <= decision_hour[i] < self.SESSION_END_HOUR
            ):
                continue

            direction: Direction
            if fast[i] > slow[i] and fast[i - 1] <= slow[i - 1]:  # §4.1 fresh cross up
                if regime[i] != 1.0:  # §4.2 H4 close > H4 EMA200
                    continue
                direction = 1
            elif fast[i] < slow[i] and fast[i - 1] >= slow[i - 1]:  # §5.1 cross down
                if regime[i] != -1.0:  # §5.2 H4 close < H4 EMA200
                    continue
                direction = -1
            else:
                continue

            # §6 / §10 #2: all geometry is anchored to the decision-bar close;
            # the market fill price is unknowable at emission.
            anchor = float(close[i])
            pip = _pip_size_from_price(anchor)

            orders.append(
                OrderIntent(
                    decision_bar=index[i],
                    direction=direction,
                    entry="market",  # §4/§5 — fills at the open of t+1 (F1/F2)
                    entry_price=None,
                    decision_close=anchor,
                    # §6: static 50-pip stop, no breakeven move, no trail.
                    stop=StopRule(price=anchor - direction * self.STOP_PIPS * pip),
                    exits=[
                        # §7: one full-size leg at 100 pips (1:2 RR). The source's
                        # opposite-cross exit is a SIGNAL exit and is inexpressible
                        # in contract v2; it is rejected, not approximated (§10 #1).
                        ExitLeg(
                            fraction=1.0,
                            kind="take_profit",
                            price=anchor + direction * self.TP_PIPS * pip,
                            label="TP1",
                        )
                    ],
                    expires_after_bars=self.EXPIRY_BARS,  # §4
                    tag="ema_cross_h4_filter_bot",
                    strategy_id=self.strategy_id,
                )
            )
        return orders
