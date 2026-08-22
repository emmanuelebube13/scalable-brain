"""Causal structural regime labels (CSRM) — the label that routes live signals.

Why this file exists here
-------------------------
This code was written during the R3 regime-aware trial and lived in
``src/regime_aware/context.py``. That trial **concluded negative** — structural
regime-filtering produced no statistically significant uplift (OOS p-values 0.199 and
0.262 out of 126 comparisons) and the package was removed. But ``task/OPEN.md`` §8 is
explicit that the outcome was mixed, not uniform:

    "The label math is a permanent addition to the project, but it does not magically
    create an edge where none exists."

Deleting the package took the live dependency out with the failed experiment:
``src/signals/run.py`` imports ``build_structural_labels`` to resolve the regime that
routes every emitted signal, and the producer crashed on import
(``ModuleNotFoundError: No module named 'src.regime_aware'``). This module restores just
the label math, in the package where regime code belongs. Nothing of the failed
experiment comes back with it.

Why the structural label and not the HMM label
----------------------------------------------
Both reasons are from ``run.py``'s own docstring and both still hold:

1. ``fact_market_regime_v2``'s **causal** label only exists for bars inside a completed
   walk-forward fold. The latest row per asset has no causal label at all, so routing on
   it returned ``None`` for every instrument, every bar was skipped, and the producer
   emitted nothing while logging only "No signals generated" — a silent stall.
2. It is the label published to ``system1/regime_status/latest.json``, so the regime
   System 3 sees on its dashboard is the one that actually routed the signal. Any other
   choice has the two disagreeing.

Being a deterministic rule over D1 closes, it is always available and never depends on a
fit having been run recently.

Causality
---------
Every label is ``shift(1)``-ed before it is returned, and the first 252 bars are forced
to ``UNKNOWN`` to cover the one-year rolling z-score warm-up. A label attached to bar
``t`` is therefore computed only from bars strictly before ``t``.
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

#: No label could be formed — inside warm-up, or an indicator was NaN. Callers must treat
#: this as "do not route", never as a tradable regime.
UNKNOWN = "UNKNOWN"

#: The four structural regimes plus the refusal value.
ALL_REGIMES = ("Trending-Up", "Trending-Down", "Ranging", "High-Vol", UNKNOWN)

#: ADX above this is "trending"; at or below is "not trending".
ADX_TREND_THRESHOLD = 25.0

#: One trading year for the ATR-percent z-score.
VOL_ZSCORE_WINDOW = 252


def build_structural_labels(d1: pd.DataFrame) -> pd.DataFrame:
    """A causal, cross-asset-normalised structural regime labeller.

    Uses ADX(14) for bounded trend strength and a one-year rolling z-score of ATR-percent
    (ATR / Close) for normalised volatility, so the same thresholds mean the same thing on
    a 0.7 AUD_USD and a 159 USD_JPY.

    Mapping:

    ===============================  ==================
    condition                        regime
    ===============================  ==================
    ADX > 25 and EMA50 > EMA200      ``Trending-Up``
    ADX > 25 and EMA50 <= EMA200     ``Trending-Down``
    ADX <= 25 and vol z-score > 0    ``High-Vol``
    ADX <= 25 and vol z-score <= 0   ``Ranging``
    ===============================  ==================

    Returns a frame of ``bar_time`` (tz-aware UTC) and ``regime``, one row per input bar.
    """
    from src.layer0.data_access.indicators import adx as calc_adx, atr as calc_atr

    close = d1["Close"]
    high = d1["High"]
    low = d1["Low"]

    ema_fast = close.ewm(span=50, adjust=False).mean()
    ema_slow = close.ewm(span=200, adjust=False).mean()

    adx = calc_adx(high, low, close, period=14)

    atr = calc_atr(high, low, close, period=14)
    atr_pct = atr / close
    roll_mean = atr_pct.rolling(
        window=VOL_ZSCORE_WINDOW, min_periods=VOL_ZSCORE_WINDOW
    ).mean()
    roll_std = atr_pct.rolling(
        window=VOL_ZSCORE_WINDOW, min_periods=VOL_ZSCORE_WINDOW
    ).std(ddof=0)
    # A flat ATR window would divide by zero and produce inf, which compares as > 0 and
    # would label a dead-quiet stretch High-Vol. NaN falls through to UNKNOWN instead.
    roll_std = roll_std.replace(0, np.nan)
    vol_zscore = (atr_pct - roll_mean) / roll_std

    label = pd.Series(UNKNOWN, index=d1.index, dtype="object")
    label[(adx > ADX_TREND_THRESHOLD) & (ema_fast > ema_slow)] = "Trending-Up"
    label[(adx > ADX_TREND_THRESHOLD) & (ema_fast <= ema_slow)] = "Trending-Down"
    label[(adx <= ADX_TREND_THRESHOLD) & (vol_zscore > 0)] = "High-Vol"
    label[(adx <= ADX_TREND_THRESHOLD) & (vol_zscore <= 0)] = "Ranging"

    # Warm-up: the z-score needs a full year before it means anything.
    label.iloc[:VOL_ZSCORE_WINDOW] = UNKNOWN

    shifted = label.shift(1).fillna(UNKNOWN)
    return pd.DataFrame(
        {
            "bar_time": pd.to_datetime(d1.index, utc=True),
            "regime": shifted.to_numpy(),
        }
    ).reset_index(drop=True)


def regime_coverage(df: pd.DataFrame) -> Dict[str, float]:
    """Share of bars per regime, as percentages. Diagnostic only."""
    counts = df["regime"].value_counts(normalize=True)
    return {str(k): round(float(v) * 100, 2) for k, v in counts.items()}
