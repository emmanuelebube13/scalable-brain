"""Causal structural regime labels (CSRM) — the label that routes live signals.

Why this file exists here
-------------------------
This code was written during the R3 regime-aware trial and lived in
``src/regime_aware/context.py``. That trial **concluded negative** and the package was
removed. But ``task/OPEN.md`` §8 is explicit that the outcome was mixed, not uniform:

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

What the R3 trial actually found (CORRECTED 2026-09-05)
-------------------------------------------------------
This docstring used to say the trial produced "no statistically significant uplift (OOS
p-values 0.199 and 0.262 out of 126 comparisons)". Three things were wrong with that
sentence, and together they let a null result read as an inconclusive one:

1. The figures were **0.202 and 0.263**, not 0.199 and 0.262.
2. They are **bootstrap P(Δ≤0)**, not p-values.
3. They were the **best 2 of 126**, selected after the fact. Quoting the two most
   favourable numbers from 126 comparisons and calling the result "not significant"
   understates it considerably.

The whole-filter result from run ``65000002`` is the honest summary:

    **129 comparisons across three label sources. 27 better on point estimate.
    ZERO with a 95% confidence interval clear of zero.**

The unclassified null control no-ops in 11/11 cells, so the apparatus manufactures no
differences of its own — meaning the zero is a real zero, not an insensitive test.

This is not "inconclusive, needs more data". It is evidence of no effect. The label math
is retained because it is needed for *routing*, not because it was shown to add edge.

Causality
---------
Every label is ``shift(1)``-ed before it is returned, and the first 252 bars are forced
to ``UNKNOWN`` to cover the one-year rolling z-score warm-up. A label attached to bar
``t`` is therefore computed only from bars strictly before ``t``.

Preconditions (enforced, not assumed)
-------------------------------------
``.shift(1)``, ``.rolling()``, ``.ewm()`` and the ``.iloc`` warm-up mask are all
**positional**. If the frame is unsorted, has duplicate timestamps, is timezone-naive, or
contains more than one instrument concatenated together, every value silently comes out
wrong — no exception, just bad labels. ``build_structural_labels`` therefore validates all
four and raises. ``hmm_regime.py`` has always handled this correctly (it groups by
``asset_id`` throughout); the two modules had different robustness contracts for the same
kind of input, and only one of them was on the live path.
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

#: Identifies the labelling RULE that produced a given label, so a stored label can be
#: attributed to the exact code that made it.
#:
#: Bump this on any change that alters output. It is written into
#: ``fact_regime_structural`` / ``fact_regime_structural_live`` and into the regime map
#: header, which is what makes "was this label produced by the labeller we think it was?"
#: an answerable question rather than an assumption.
#:
#: Not a package version — it versions the *output*, not the module. Two builds of this
#: file that produce identical labels share a version; one whitespace change does not.
LABELLER_VERSION = "structural-v1.1.0"

#: No label could be formed — inside warm-up, or an indicator was NaN. Callers must treat
#: this as "do not route", never as a tradable regime.
UNKNOWN = "UNKNOWN"

#: The four structural regimes plus the refusal value.
ALL_REGIMES = ("Trending-Up", "Trending-Down", "Ranging", "High-Vol", UNKNOWN)

#: ADX above this is "trending"; at or below is "not trending".
ADX_TREND_THRESHOLD = 25.0

#: One trading year for the ATR-percent z-score.
VOL_ZSCORE_WINDOW = 252

#: EMA spans for the trend-direction test.
EMA_FAST_SPAN = 50
EMA_SLOW_SPAN = 200


def _seeded_ema(series: pd.Series, span: int) -> pd.Series:
    """EMA seeded with the SMA of the first ``span`` observations.

    ``pandas.ewm(adjust=False)`` seeds on the **first observation**, so a recursive EMA
    keeps a weight of ``(1 - 2/(span+1))**n`` on that one arbitrary price after *n* bars.
    For span=200 that is roughly **8% at bar 252, 2% at bar 400, and under 1% only past
    bar 600** — while the warm-up mask is 252 bars, sized for the z-score, not for the EMA.

    So for about a year and a half past each instrument's mask, the Up/Down direction call
    was partly determined by *where that instrument's data happens to begin*. Two runs over
    different lookback windows produced different labels for the same bar, which is why the
    live label was not reproducible from an archival rebuild.

    EMA50 was never affected (residual seed weight ~5e-5 by bar 252). This is an
    EMA200-only problem.

    Seeding with SMA(span) makes the series valid from bar ``span - 1`` with no residual
    dependence on the start of the frame, and costs nothing — the alternative, extending
    the mask to 600 bars, would discard ~1.4 years of history per instrument.

    Values before index ``span - 1`` are NaN, which falls through to UNKNOWN.
    """
    alpha = 2.0 / (span + 1.0)
    vals = series.to_numpy(dtype="float64")
    n = len(vals)
    out = np.full(n, np.nan, dtype="float64")
    if n < span:
        return pd.Series(out, index=series.index)
    out[span - 1] = vals[:span].mean()
    for i in range(span, n):
        out[i] = alpha * vals[i] + (1.0 - alpha) * out[i - 1]
    return pd.Series(out, index=series.index)


def _validate_frame(d1: pd.DataFrame) -> None:
    """Enforce the positional-operation preconditions. Raises, or passes silently.

    These guards do not change a single value on well-formed input. They exist because
    every operation downstream is positional, so malformed input produces confidently
    wrong labels rather than an error.
    """
    if not isinstance(d1.index, pd.DatetimeIndex):
        raise TypeError("build_structural_labels requires a DatetimeIndex")

    if d1.index.tz is None:
        raise ValueError(
            "d1.index is tz-naive. Localize or convert to UTC before calling; "
            "pd.to_datetime(..., utc=True) would LABEL naive timestamps as UTC "
            "rather than converting them, silently shifting every bar."
        )

    if not d1.index.is_monotonic_increasing:
        raise ValueError(
            "d1.index is not sorted ascending; positional ops would be wrong"
        )

    if d1.index.has_duplicates:
        dupes = d1.index[d1.index.duplicated()].unique()[:5].tolist()
        raise ValueError(f"d1.index has duplicate timestamps, e.g. {dupes}")

    # Single-instrument contract. Every rolling window, EMA, the .iloc warm-up mask and
    # the shift(1) would silently bleed across instrument boundaries otherwise.
    for col in ("asset_id", "instrument", "symbol"):
        if col in d1.columns and d1[col].nunique(dropna=True) > 1:
            raise ValueError(
                f"build_structural_labels received {d1[col].nunique()} instruments in one "
                f"frame (column '{col}'). It labels ONE instrument. Call per instrument."
            )


def build_structural_labels(
    d1: pd.DataFrame, return_indicators: bool = False
) -> pd.DataFrame:
    """A causal structural regime labeller for ONE instrument.

    Uses ADX(14) for bounded trend strength and a one-year rolling z-score of ATR-percent
    (ATR / Close) for normalised volatility.

    **Only the volatility leg is cross-asset normalised.** The docstring here used to
    claim the thresholds "mean the same thing on a 0.7 AUD_USD and a 159 USD_JPY". That is
    true of the ATR% z-score, which is unit-free by construction, and false of the other
    two tests: ``ADX > 25`` is a raw, identical cut for every pair, and the EMA50/EMA200
    comparison is a raw price comparison. The claim overstated what the labeller does and
    has been relied on; corrected 2026-09-05.

    ``return_indicators=True`` additionally returns the indicator values at each bar
    (``adx``, ``ema_fast``, ``ema_slow``, ``atr_pct``, ``vol_zscore``) and
    ``source_bar_time`` — the bar each label was DERIVED from, i.e. one bar back. Existing
    callers are unaffected: the default return shape is unchanged.

    Preconditions: sorted, tz-aware, no duplicate timestamps, exactly one instrument.
    All four are enforced; see :func:`_validate_frame`.

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

    _validate_frame(d1)

    close = d1["Close"]
    high = d1["High"]
    low = d1["Low"]

    # SMA-seeded, not ewm(adjust=False) — see _seeded_ema for why the old seeding made the
    # direction call depend on where each instrument's history happens to start.
    ema_fast = _seeded_ema(close, EMA_FAST_SPAN)
    ema_slow = _seeded_ema(close, EMA_SLOW_SPAN)

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

    # tz_convert, NOT pd.to_datetime(..., utc=True). The guard above has already
    # established the index is tz-aware, so this CONVERTS to UTC. `to_datetime(utc=True)`
    # would RELABEL a naive index as UTC, silently shifting every bar by the local offset
    # — on this host, three hours.
    bar_time = d1.index.tz_convert("UTC")
    out = pd.DataFrame({"bar_time": bar_time, "regime": shifted.to_numpy()})

    if return_indicators:
        # The bar each label was DERIVED from: one back, because of the shift(1). Stored
        # so the shift is auditable from the data rather than inferred from the code.
        out["source_bar_time"] = pd.Series(bar_time).shift(1).to_numpy()
        for name, series in (
            ("adx", adx),
            ("ema_fast", ema_fast),
            ("ema_slow", ema_slow),
            ("atr_pct", atr_pct),
            ("vol_zscore", vol_zscore),
        ):
            # Shifted alongside the label so each row's indicators are the ones that
            # PRODUCED that row's label, not the ones on the bar it is attached to.
            out[name] = series.shift(1).to_numpy()

    return out.reset_index(drop=True)


def regime_coverage(df: pd.DataFrame) -> Dict[str, float]:
    """Share of bars per regime, as percentages. Diagnostic only."""
    counts = df["regime"].value_counts(normalize=True)
    return {str(k): round(float(v) * 100, 2) for k, v in counts.items()}
