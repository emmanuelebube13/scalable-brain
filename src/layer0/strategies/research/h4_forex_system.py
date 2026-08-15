"""h4_forex_system — 6 EMA / 13 SMA cross confirmed by a same-bar MACD cross and
Parabolic SAR position, on H4 GBP pairs.

Spec: ``task/2026-August-week1/fleet/upload/wave2/specs/SPEC-h4_forex_system.md``
(row 8 of ``forex_swing_strategies.csv``) ·
https://www.forexstrategiesresources.com/trend-following-forex-strategies/44-4h-system/

Scope note (spec §2): the source page describes the same system on H4 *and* D1,
each with its own SL/TP table, run as two separate (strategy, pair, granularity)
cells (spec §10 #6). This module's ``strategy_id`` is ``h4_forex_system`` and
spec §2 states its ``primary_granularity`` is **H4**; only the H4 cell is
implemented here. The D1 cell is a distinct cell with its own SL/TP row and, per
this fleet's one-id-one-file assignment, is out of scope for this deliverable —
recorded under Uncertainties in the report rather than resolved silently.

Shape and NOTE checks, following ``reference_pullback_continuation.py``:

* **NOTE 1 (causal MTF join)** — does not bind. Spec §2 declares
  ``context_granularities: none``: this is a single-frame H4 strategy (spec §9
  row "D1 cell vs H4 cell": "No multi-timeframe interaction exists in either
  cell"). No context frame is read, so neither ``closed_context_frame`` nor the
  ``merge_asof`` form is needed.
* **NOTE 2 (causal swing structure)** — does not bind. Spec §9 states explicitly:
  "This strategy uses no swing/pivot/ZigZag/fractal construct" — neither
  ``causal_structure`` nor the banned ``indicators.detect_swing_points`` is
  imported.
* **NOTE 3 (pending entry on the right side of the close)** — does not bind.
  Spec §4/§5 declare ``market`` entries only (``entry_price=None``), so there is
  no pending level to validate against the decision close.
* **NOTE 4 (breakeven names an existing leg)** — does not bind. Spec §6 declares
  ``move_to_breakeven_on: none`` and ``trail_atr_multiple: none`` — the stop is
  static and no leg label is ever referenced by it.

**Parabolic SAR is private** (spec §3): ``indicators.py`` has no PSAR
implementation, so the Wilder (1978) recursion the spec writes out in full is
implemented here as a module-level helper, never added to ``indicators.py``.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Sequence

import numpy as np
import pandas as pd

from ..contract_v2 import (
    Direction,
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)
from ...data_access.indicators import ema, get_pip_value, macd, sma


def _parabolic_sar(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    step: float = 0.02,
    max_af: float = 0.20,
) -> pd.Series:
    """Wilder (1978) Parabolic SAR, exactly per spec §3. Strictly causal.

    State per bar: ``trend`` (+1 long / -1 short), ``sar``, ``ep`` (extreme
    point), ``af`` (acceleration factor). Bar 0 has no SAR (NaN). Bar 1 seeds
    the recursion (spec §3 "Initialisation"): long if ``Close[1] >= Close[0]``
    with ``SAR = Low[0]``, ``EP = High[1]``; short otherwise with
    ``SAR = High[0]``, ``EP = Low[1]``; ``AF = step`` in both cases.

    From bar 2 onward (spec §3 "Recursion"), each bar:
      1. ``sar_raw = sar[t-1] + af * (ep - sar[t-1])``.
      2. Clamp: long -> ``min(sar_raw, Low[t-1], Low[t-2])``;
         short -> ``max(sar_raw, High[t-1], High[t-2])``.
      3. Reversal: long and ``Low[t] < clamped`` -> flip to short,
         ``sar[t] = ep`` (the extreme reached during the prior leg),
         ``ep = Low[t]``, ``af = step`` (mirrored for short).
      4. Otherwise: update ``ep``/``af`` if a new extreme in the trend
         direction was made this bar (``af`` capped at ``max_af``).

    Only bars ``<= t`` are ever read — no repaint, no centred window.
    """
    n = int(len(close))
    highs = high.to_numpy(dtype=float)
    lows = low.to_numpy(dtype=float)
    closes = close.to_numpy(dtype=float)
    out = np.full(n, np.nan, dtype=float)
    if n < 2:
        return pd.Series(out, index=close.index)

    trend: int
    if closes[1] >= closes[0]:
        trend = 1
        sar_val = float(lows[0])
        ep = float(highs[1])
    else:
        trend = -1
        sar_val = float(highs[0])
        ep = float(lows[1])
    af = step
    out[1] = sar_val

    for t in range(2, n):
        sar_raw = sar_val + af * (ep - sar_val)
        if trend == 1:
            clamped = min(sar_raw, lows[t - 1], lows[t - 2])
        else:
            clamped = max(sar_raw, highs[t - 1], highs[t - 2])

        if trend == 1 and lows[t] < clamped:
            sar_val = ep  # highest high of the prior long leg
            trend = -1
            ep = float(lows[t])
            af = step
        elif trend == -1 and highs[t] > clamped:
            sar_val = ep  # lowest low of the prior short leg
            trend = 1
            ep = float(highs[t])
            af = step
        else:
            sar_val = clamped
            if trend == 1 and highs[t] > ep:
                ep = float(highs[t])
                af = min(af + step, max_af)
            elif trend == -1 and lows[t] < ep:
                ep = float(lows[t])
                af = min(af + step, max_af)
        out[t] = sar_val

    return pd.Series(out, index=close.index)


class H4ForexSystem(StrategyV2):
    """6 EMA / 13 SMA cross, confirmed by a same-bar MACD cross and PSAR position."""

    EMA_FAST_PERIOD = 6  # §3 EMA(close, 6)
    SMA_SLOW_PERIOD = 13  # §3 SMA(close, 13)
    MACD_FAST = 12  # §3 macd(close, 12, 26, 9)
    MACD_SLOW = 26
    MACD_SIGNAL = 9
    PSAR_STEP = 0.02  # §3 Parabolic SAR step
    PSAR_MAX_AF = 0.20  # §3 Parabolic SAR max acceleration
    WARMUP = 27  # §3: slow EMA 26 + signal seed

    # §6 / §7 H4 rows only (this module implements the H4 cell — see module
    # docstring "Scope note"). GBP_JPY is documented for completeness even
    # though it is not in ``metadata.pairs`` (spec §2: pending Wave-1 backfill).
    SL_PIPS: Dict[str, float] = {"GBP_USD": 70.0, "GBP_JPY": 90.0}
    TP_PIPS: Dict[str, float] = {"GBP_USD": 60.0, "GBP_JPY": 80.0}

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="h4_forex_system",
            name="4H System",
            version="0.1.0",
            author="wave2-fleet",
            hypothesis=(
                "A fast/slow moving-average crossover (6 EMA vs 13 SMA) on H4/D1 "
                "captures the early phase of short-term trend persistence in GBP "
                "pairs, and requiring simultaneous MACD-momentum agreement plus "
                "Parabolic SAR position filters out the whipsaw crosses that "
                "dominate in range-bound regimes. The claimed edge rests on the "
                "well-documented behavioural tendency of FX trends to persist over "
                "multi-bar horizons (herding, staggered information diffusion, and "
                "central-bank policy cycles that unfold over days), so that a "
                "confirmed momentum cross is more likely than chance to be followed "
                "by continuation far enough to reach a fixed pip target before a "
                "fixed stop."
            ),
            granularities=["H4"],
            # §2 pairs_available: GBP_USD only. GBP_JPY is pending Wave-1 backfill
            # and is deliberately excluded per the run brief.
            pairs=["GBP_USD"],
            primary_granularity="H4",
            context_granularities=(),
            simulate_on="H1",
            source_row=8,
            source_url=(
                "https://www.forexstrategiesresources.com/"
                "trend-following-forex-strategies/44-4h-system/"
            ),
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["ema", "sma", "macd", "parabolic_sar"]

    @property
    def warmup_bars(self) -> int:
        return self.WARMUP

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h4 = frames[self.metadata.primary_granularity]

        pair = self.metadata.pairs[0]
        pip = float(get_pip_value(pair))
        sl_pips = self.SL_PIPS[pair]
        tp_pips = self.TP_PIPS[pair]

        close_s = h4["Close"]
        ema6_s = ema(close_s, self.EMA_FAST_PERIOD)
        sma13_s = sma(close_s, self.SMA_SLOW_PERIOD)
        macd_line_s, signal_line_s, _hist_s = macd(
            close_s, self.MACD_FAST, self.MACD_SLOW, self.MACD_SIGNAL
        )
        psar_s = _parabolic_sar(
            h4["High"], h4["Low"], close_s, self.PSAR_STEP, self.PSAR_MAX_AF
        )

        high = h4["High"].to_numpy(dtype=float)
        low = h4["Low"].to_numpy(dtype=float)
        close = close_s.to_numpy(dtype=float)
        ema6 = ema6_s.to_numpy(dtype=float)
        sma13 = sma13_s.to_numpy(dtype=float)
        macd_line = macd_line_s.to_numpy(dtype=float)
        signal_line = signal_line_s.to_numpy(dtype=float)
        psar = psar_s.to_numpy(dtype=float)
        index = h4.index

        orders: List[OrderIntent] = []
        for i in range(max(self.warmup_bars, 1), len(h4)):
            # Spec §3 warmup: emit only where every input is defined at bar i
            # AND at bar i-1 (both are read by the cross conditions §4/§5).
            if not (
                np.isfinite(ema6[i])
                and np.isfinite(ema6[i - 1])
                and np.isfinite(sma13[i])
                and np.isfinite(sma13[i - 1])
                and np.isfinite(macd_line[i])
                and np.isfinite(macd_line[i - 1])
                and np.isfinite(signal_line[i])
                and np.isfinite(signal_line[i - 1])
                and np.isfinite(psar[i])
            ):
                continue

            ma_cross_up = ema6[i] > sma13[i] and ema6[i - 1] <= sma13[i - 1]
            ma_cross_down = ema6[i] < sma13[i] and ema6[i - 1] >= sma13[i - 1]
            macd_cross_up = (
                macd_line[i] > signal_line[i] and macd_line[i - 1] <= signal_line[i - 1]
            )
            macd_cross_down = (
                macd_line[i] < signal_line[i] and macd_line[i - 1] >= signal_line[i - 1]
            )
            # §3 "PSAR dot below/above the candle" — a raw comparison of the
            # causal psar[i] value against Low[i]/High[i] (spec §3 last bullet).
            psar_below = psar[i] < low[i]  # §4.3
            psar_above = psar[i] > high[i]  # §5.3

            direction: Direction
            if ma_cross_up and macd_cross_up and psar_below:  # §4 conjunction
                direction = 1
            elif ma_cross_down and macd_cross_down and psar_above:  # §5 conjunction
                direction = -1
            else:
                continue

            # §6/§7: geometry anchored to the decision-bar close C = Close[t]
            # (fleet rule 8 — the t+1 fill price is unknowable at emission).
            c = float(close[i])
            if direction == 1:
                stop_price = c - sl_pips * pip
                tp_price = c + tp_pips * pip
            else:
                stop_price = c + sl_pips * pip
                tp_price = c - tp_pips * pip

            orders.append(
                OrderIntent(
                    decision_bar=index[i],
                    direction=direction,
                    entry="market",  # §4/§5: market, entry_price=None
                    entry_price=None,
                    decision_close=c,
                    stop=StopRule(
                        price=stop_price,
                        move_to_breakeven_on=None,  # §6: none
                        trail_atr_multiple=None,  # §6: static stop, never moves
                    ),
                    exits=[
                        ExitLeg(
                            fraction=1.0,  # §7: single leg, fractions sum to 1.0
                            kind="take_profit",
                            price=tp_price,
                            label="TP1",
                        )
                    ],
                    expires_after_bars=None,  # §4/§5: market entry, no pending order
                    tag="h4_forex_system",
                    strategy_id=self.strategy_id,
                )
            )
        return orders
