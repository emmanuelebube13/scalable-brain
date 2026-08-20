"""Walk-forward fold generation + out-of-sample (OOS) labelling — FIX-S1-002.

Background
----------
System-1 strategy parameters are **fixed full-history**; there is no per-fold refit at
qualification time. "Out-of-sample" therefore means the subset of a cell's trades whose
metrics were *not* used in the selection decision. Concretely: we anchor a training window
at the per-granularity series start, reserve ``min_train`` months for in-sample, and tile
the remaining history into contiguous ``oos_window``-month OOS folds stepping forward by
``step`` months. A trade is OOS iff its **entry time** falls at or after the first OOS
window's start (``cutoff = series_start + min_train``); its ``fold_id`` is the 1-based index
of the contiguous OOS window that contains the entry time. In-sample trades get
``is_oos = False`` / ``fold_id = NULL``.

This module is deliberately a **reusable component**: FIX-S1-005 will share the same fold
generator to drive a walk-forward HMM refit. It contains *no* DB or metric logic — only
calendar math — so it stays unit-testable and pure.

Locked design parameters (do NOT change without a new fix):
    anchor       = per-granularity min entry_time (``series_bounds``)
    min_train    = 36 months   (expanding/anchored train window minimum)
    step         = 6 months    (how far the train_end / OOS window advances per fold)
    oos_window   = 6 months    (length of each OOS window; == step => contiguous tiling)
    mode         = "anchored"  (train_start fixed at series_start; "rolling" also supported)

All datetimes are tz-aware UTC throughout. Month arithmetic uses
``dateutil.relativedelta`` so "36 months" lands on a real calendar boundary rather than a
day-count approximation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

# --- Locked validation-design constants (see module docstring) ---------------------------
MIN_TRAIN_MONTHS = 36
STEP_MONTHS = 6
OOS_WINDOW_MONTHS = 6
MODE = "anchored"

# Average days per calendar month — matches the financial-metrics skill's oos_month_span spec.
_DAYS_PER_MONTH = 30.44


@dataclass(frozen=True)
class Fold:
    """One walk-forward fold.

    Attributes:
        fold_id: 1-based index of the fold (and of its OOS window).
        train_start: Inclusive start of the in-sample/training window (tz-aware UTC).
        train_end: Exclusive end of training == ``oos_start`` (tz-aware UTC).
        oos_start: Inclusive start of the out-of-sample window (tz-aware UTC).
        oos_end: Exclusive end of the OOS window, clamped to ``series_end`` (tz-aware UTC).
    """

    fold_id: int
    train_start: datetime
    train_end: datetime
    oos_start: datetime
    oos_end: datetime


def generate_folds(
    series_start: datetime,
    series_end: datetime,
    min_train: int = MIN_TRAIN_MONTHS,
    step: int = STEP_MONTHS,
    oos_window: Optional[int] = None,
    mode: str = MODE,
) -> List[Fold]:
    """Generate walk-forward folds over ``[series_start, series_end)``.

    The first OOS window opens at ``cutoff = series_start + min_train`` months; subsequent
    windows step forward by ``step`` months. With the locked ``step == oos_window`` the OOS
    windows tile the post-train history contiguously and without overlap. The final window
    is clamped to ``series_end`` (a possibly-partial trailing fold).

    Args:
        series_start: Anchor (per-granularity min entry_time), tz-aware UTC.
        series_end: End of available history (per-granularity max entry_time), tz-aware UTC.
        min_train: Minimum training span in months before the first OOS window.
        step: Months between consecutive OOS window starts.
        oos_window: OOS window length in months. Defaults to ``step`` (contiguous tiling).
        mode: ``"anchored"`` (train_start fixed at ``series_start``, expanding train) or
            ``"rolling"`` (train_start slides so the train window stays ``min_train`` long).

    Returns:
        Folds in chronological order. Empty when ``cutoff >= series_end`` (i.e.
        ``min_train`` covers the whole series — there is no out-of-sample period).

    Raises:
        ValueError: If ``step`` is non-positive or ``mode`` is unrecognised.
    """
    if step <= 0:
        raise ValueError(f"step must be positive, got {step}")
    if mode not in ("anchored", "rolling"):
        raise ValueError(f"mode must be 'anchored' or 'rolling', got {mode!r}")
    window = step if oos_window is None else oos_window
    if window <= 0:
        raise ValueError(f"oos_window must be positive, got {window}")

    cutoff = series_start + relativedelta(months=min_train)
    folds: List[Fold] = []
    k = 0
    while True:
        oos_start = cutoff + relativedelta(months=step * k)
        if oos_start >= series_end:
            break
        oos_end = min(oos_start + relativedelta(months=window), series_end)
        if mode == "anchored":
            train_start = series_start
        else:  # rolling
            train_start = oos_start - relativedelta(months=min_train)
        folds.append(
            Fold(
                fold_id=len(folds) + 1,
                train_start=train_start,
                train_end=oos_start,
                oos_start=oos_start,
                oos_end=oos_end,
            )
        )
        k += 1
    return folds


def default_folds(series_start: datetime, series_end: datetime) -> List[Fold]:
    """Folds for the locked System-1 design (min_train=36, step=6, oos_window=6, anchored)."""
    return generate_folds(
        series_start,
        series_end,
        min_train=MIN_TRAIN_MONTHS,
        step=STEP_MONTHS,
        oos_window=OOS_WINDOW_MONTHS,
        mode=MODE,
    )


def series_bounds(entry_times: pd.Series) -> Tuple[pd.Timestamp, pd.Timestamp]:
    """Return ``(min, max)`` of a tz-aware (UTC) entry-time series, ignoring NaT.

    This is the canonical ``series_start(g)`` / ``series_end(g)`` anchor: the per-granularity
    minimum and maximum trade entry time.
    """
    et = pd.to_datetime(entry_times, utc=True)
    return et.min(), et.max()


def assign_oos(
    entry_times: pd.Series, folds: Sequence[Fold]
) -> Tuple[pd.Series, pd.Series]:
    """Label trades in-sample vs out-of-sample by **entry time**.

    A trade is OOS iff ``entry_time >= folds[0].oos_start`` (the cutoff). Its ``fold_id`` is
    the 1-based index of the contiguous OOS window containing the entry time — assigned by
    the OOS-window start boundaries, so the final window catches any trade at/after the last
    ``oos_start`` (including one landing exactly at ``series_end``). A trade exactly at the
    cutoff is OOS in fold 1; a trade one instant earlier is in-sample.

    Args:
        entry_times: Trade entry times (tz-aware UTC or coercible).
        folds: Folds from :func:`generate_folds` (chronological, contiguous tiling).

    Returns:
        ``(is_oos, fold_id)`` aligned to ``entry_times.index``. ``is_oos`` is a bool Series;
        ``fold_id`` is a nullable ``Int64`` Series (``<NA>`` for in-sample / NaT rows).
    """
    idx = entry_times.index
    n = len(entry_times)
    if not folds:
        return (
            pd.Series(np.zeros(n, dtype=bool), index=idx),
            pd.Series([pd.NA] * n, index=idx, dtype="Int64"),
        )

    et = pd.to_datetime(entry_times, utc=True)
    # Use POSIX seconds for a numpy-vectorised boundary search (avoids tz int64 pitfalls).
    et_ts = np.array(
        [t.timestamp() if pd.notna(t) else np.nan for t in et], dtype="float64"
    )
    starts_ts = np.array([f.oos_start.timestamp() for f in folds], dtype="float64")

    # bisect_right - 1: the last OOS window whose start is <= entry_time. -1 => in-sample.
    pos = np.searchsorted(starts_ts, et_ts, side="right") - 1
    nan_mask = np.isnan(et_ts)
    is_oos_arr = pos >= 0
    is_oos_arr[nan_mask] = False

    fold_vals: List[object] = [
        int(pos[i]) + 1 if is_oos_arr[i] else pd.NA for i in range(n)
    ]
    return (
        pd.Series(is_oos_arr, index=idx),
        pd.Series(fold_vals, index=idx, dtype="Int64"),
    )


def oos_month_span(folds: Sequence[Fold]) -> float:
    """Total calendar months spanned by the **union** of the folds' OOS windows.

    Overlapping/adjacent OOS windows are merged, then the merged spans' whole-day lengths are
    summed and divided by the average days-per-month (matches the financial-metrics skill).
    Returns ``0.0`` for an empty fold list.
    """
    if not folds:
        return 0.0
    intervals = sorted(((f.oos_start, f.oos_end) for f in folds), key=lambda iv: iv[0])
    merged: List[Tuple[datetime, datetime]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    total_days = sum((end - start).days for start, end in merged)
    return total_days / _DAYS_PER_MONTH
