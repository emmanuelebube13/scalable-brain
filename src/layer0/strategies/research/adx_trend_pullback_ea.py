"""ADX Trend Pullback EA — row 38 of ``forex_swing_strategies.csv``.

Spec: ``task/2026-August-week1/fleet/upload/wave2/specs/SPEC-adx_trend_pullback_ea.md``
Source: https://www.mql5.com/en/code/73958

Single-timeframe (H1) trend-pullback entry. On every closed H1 bar ``k`` the
strategy checks five conditions (spec §4/§5):

1. ``ADX(k) > 25``                       — trend is established
2. ``ADX(k) > ADX(k-1)``                 — trend is still strengthening
3. ``dist(k-1) >= 1.0``                  — price had stretched >= 1 ATR from EMA20
4. ``dist(k) < 1.0``                     — the pullback has completed
5. ``+DI(k) > -DI(k)`` (long) / ``-DI(k) > +DI(k)`` (short)

with ``dist(j) = abs(Close(j) - EMA20(j)) / ATR14(j)``.

Everything is trailing-only: indicator values at bar ``k`` are recursions over
bars ``<= k``, condition 3 references the fully closed bar ``k-1``, and the
order is a market intent whose fill the engine resolves at the open of ``k+1``
(F1/F2). There is no context frame (spec §2: ``context_granularities: none``),
so no ``closed_context_frame`` join is needed — and none is permitted to be
faked with ``index <= ts``.

Geometry is anchored to the decision-bar close (spec §6/§7, §10 #8), because the
k+1 fill price is unknowable at emission:

* stop = ``Close(k) ∓ 2.0 × ATR14(k)``  → ``R_declared = 2.0 × ATR14(k)``
* one take-profit leg, fraction 1.0, at ``Close(k) ± 2.0 × R_declared``
  = ``Close(k) ± 4.0 × ATR14(k)``  (rr = 2.0)

No breakeven move, no trailing leg, no time stop — the source has none.

**+DI/-DI are private** (spec §3): ``indicators.adx()`` returns ADX only, and
``indicators.py`` is off-limits to this fleet, so the Wilder DMI recursion the
spec writes out in §3 is implemented here as module-level helpers.
"""

from __future__ import annotations

from typing import List, Mapping, Sequence, Tuple

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
from ...data_access.indicators import adx, atr, ema


def _wilder_running_sum(values: np.ndarray, period: int) -> np.ndarray:
    """Wilder's smoothed running sum of ``values``, exactly as spec §3 states.

    ``values[0]`` is ignored: the DM/TR series are defined only for bars
    ``j >= 1`` (they need bar ``j-1``). The sum is initialised at position
    ``period`` as the plain sum of ``values[1 : period + 1]`` and then rolled
    forward with ``S_t = S_{t-1} - S_{t-1} / period + values[t]``. Positions
    before ``period`` are NaN — the series is not yet defined there.
    """
    n = int(values.shape[0])
    out = np.full(n, np.nan, dtype=float)
    if n <= period:
        return out
    total = float(np.sum(values[1 : period + 1]))
    out[period] = total
    for i in range(period + 1, n):
        total = total - total / period + float(values[i])
        out[i] = total
    return out


def _directional_indicators(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> Tuple[pd.Series, pd.Series]:
    """Private Wilder +DI / -DI (spec §3). Strictly trailing.

    ``up(j) = High(j) - High(j-1)``, ``down(j) = Low(j-1) - Low(j)``;
    ``+DM(j) = up`` when ``up > down and up > 0`` else 0 (mirrored for ``-DM``);
    ``TR(j) = max(H-L, |H - C(j-1)|, |L - C(j-1)|)``. Each of the three series
    is Wilder-smoothed over ``period`` bars, then
    ``+DI = 100 × S(+DM) / S(TR)`` and ``-DI = 100 × S(-DM) / S(TR)``.
    """
    highs = high.to_numpy(dtype=float)
    lows = low.to_numpy(dtype=float)
    closes = close.to_numpy(dtype=float)
    n = int(highs.shape[0])

    plus_dm = np.zeros(n, dtype=float)
    minus_dm = np.zeros(n, dtype=float)
    true_range = np.zeros(n, dtype=float)
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        if up > down and up > 0.0:
            plus_dm[i] = up
        if down > up and down > 0.0:
            minus_dm[i] = down
        true_range[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    smoothed_tr = _wilder_running_sum(true_range, period)
    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di = 100.0 * _wilder_running_sum(plus_dm, period) / smoothed_tr
        minus_di = 100.0 * _wilder_running_sum(minus_dm, period) / smoothed_tr
    return (
        pd.Series(plus_di, index=high.index),
        pd.Series(minus_di, index=high.index),
    )


class AdxTrendPullbackEa(StrategyV2):
    """Buy/sell the completion of an EMA pullback inside a strengthening H1 trend."""

    # Declared parameter set (spec §3). One set, no optimisation.
    ADX_PERIOD = 14
    ADX_THRESHOLD = 25.0
    EMA_PERIOD = 20
    ATR_PERIOD = 14
    DMI_PERIOD = 14
    PULL_RATIO = 1.0
    SL_MULT = 2.0
    RR = 2.0
    WARMUP = 30  # spec §9: EMA20/ATR14/DMI14 need ~30 H1 bars of history

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="adx_trend_pullback_ea",
            name="ADX Trend Pullback EA",
            version="0.1.0",
            author="wave2-fleet",
            hypothesis=(
                "In a genuinely strengthening trend (ADX above threshold and still "
                "rising), price oscillates around its short mean: impulsive moves "
                "carry it away from the EMA, then liquidity-taking pulls it back "
                "toward the EMA before the trend resumes. Entering with the "
                "directional DMI consensus exactly when such a pullback completes — "
                "i.e. at the moment price re-approaches the EMA after having "
                "stretched at least one ATR away from it — buys the trend at a "
                "locally discounted price rather than chasing extension. The edge "
                "should persist because it is the behavioural footprint of "
                "trend-following flow (breakout chasers taking profit, value buyers "
                "re-entering at the mean) combined with a volatility-adaptive stop, "
                "so the entry is only attempted when the market has demonstrably "
                "committed to directional movement."
            ),
            granularities=["H1"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="H1",
            context_granularities=(),
            simulate_on="H1",
            source_row=38,
            source_url="https://www.mql5.com/en/code/73958",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["ema", "atr", "adx"]

    @property
    def warmup_bars(self) -> int:
        return self.WARMUP

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h1 = frames["H1"]
        close_series = h1["Close"]

        ema_series = ema(close_series, self.EMA_PERIOD)
        atr_series = atr(h1["High"], h1["Low"], close_series, self.ATR_PERIOD)
        adx_series = adx(h1["High"], h1["Low"], close_series, self.ADX_PERIOD)
        plus_di_series, minus_di_series = _directional_indicators(
            h1["High"], h1["Low"], close_series, self.DMI_PERIOD
        )

        close = close_series.to_numpy(dtype=float)
        ema20 = ema_series.to_numpy(dtype=float)
        atr14 = atr_series.to_numpy(dtype=float)
        adx14 = adx_series.to_numpy(dtype=float)
        plus_di = plus_di_series.to_numpy(dtype=float)
        minus_di = minus_di_series.to_numpy(dtype=float)
        index = h1.index

        orders: List[OrderIntent] = []
        for i in range(max(self.warmup_bars, 1), len(h1)):
            # Spec §9 warm-up: emit nothing until every input is finite at bar k
            # (and at k-1, which conditions 2 and 3 read).
            atr_k = float(atr14[i])
            atr_prev = float(atr14[i - 1])
            if not np.isfinite(atr_k) or atr_k <= 0.0:
                continue
            if not np.isfinite(atr_prev) or atr_prev <= 0.0:
                continue
            if not (np.isfinite(ema20[i]) and np.isfinite(ema20[i - 1])):
                continue
            if not (np.isfinite(adx14[i]) and np.isfinite(adx14[i - 1])):
                continue
            if not (np.isfinite(plus_di[i]) and np.isfinite(minus_di[i])):
                continue

            # §4.1 trend strength / §4.2 trend strengthening
            if not adx14[i] > self.ADX_THRESHOLD:
                continue
            if not adx14[i] > adx14[i - 1]:
                continue

            # §4.3 pullback arm (bar k-1) / §4.4 pullback release (bar k)
            dist_prev = abs(close[i - 1] - ema20[i - 1]) / atr_prev
            dist_k = abs(close[i] - ema20[i]) / atr_k
            if not dist_prev >= self.PULL_RATIO:
                continue
            if not dist_k < self.PULL_RATIO:
                continue

            # §4.5 / §5.5' directional consensus. A DMI tie is no consensus, so
            # the conservative reading is to stand aside.
            direction: Direction
            if plus_di[i] > minus_di[i]:
                direction = 1
            elif minus_di[i] > plus_di[i]:
                direction = -1
            else:
                continue

            # §6 stop and §7 take profit, anchored to the decision-bar close.
            close_k = float(close[i])
            risk = self.SL_MULT * atr_k
            stop_price = close_k - direction * risk
            take_profit = close_k + direction * self.RR * risk

            orders.append(
                OrderIntent(
                    decision_bar=index[i],
                    direction=direction,
                    entry="market",  # §4: market at the open of k+1
                    entry_price=None,
                    decision_close=close_k,
                    stop=StopRule(
                        price=stop_price,
                        move_to_breakeven_on=None,  # §6: the source has none
                        trail_atr_multiple=None,  # §6: static stop
                    ),
                    exits=[
                        ExitLeg(
                            fraction=1.0,
                            kind="take_profit",
                            price=take_profit,
                            label="TP1",
                        )
                    ],
                    expires_after_bars=None,  # §4: not a pending order
                    tag="adx_trend_pullback",
                    strategy_id=self.strategy_id,
                )
            )
        return orders
