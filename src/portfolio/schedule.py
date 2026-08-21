"""Cross-sectional weight schedules — the mechanism the single-pair harness cannot reach.

This module does not reimplement the ranking rule. ``currency_momentum_factor`` already
contains it as pure functions pinned by a golden fixture, written specifically so that
"a multi-pair harness can call them unchanged". We call them unchanged. If the numbers
here disagree with that module's fixture, the fixture wins.

Causality
---------
Two rules, both load-bearing, both tested by truncation:

1. **Rebalance cadence** is ``month(index[i]) != month(index[i-1])`` — the first bar of
   a new calendar month. Not "the last bar of the month", which is undecidable at bar
   ``i`` without reading ``index[i+1]``. This mirrors NOTE 2 in
   ``currency_momentum_factor`` and fires exactly once per calendar month.
2. **Signal inputs** at rebalance bar ``i`` are ``close[i]`` and ``close[i - 252]``,
   both closed bars at or before ``i``.

The weights this produces are *decided at the close of bar i*. Applying them to bar
``i``'s own return would be look-ahead; :mod:`src.portfolio.evaluate` is responsible for
the one-bar shift and tests it.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Mapping, Sequence

import numpy as np
import pandas as pd

from src.layer0.strategies.research.currency_momentum_factor import (
    USD_BASE_PAIRS,
    USD_QUOTE_PAIRS,
    currency_momentum,
    net_tercile_weights,
)

logger = logging.getLogger("system1.portfolio.schedule")

#: §3, §10 row 9: the source's ``pct_change(252)`` on D1 bars — 12 months of trading days.
LOOKBACK_BARS = 252

#: Every pair this module knows how to attribute to a currency.
PAIR_TO_CURRENCY: Dict[str, str] = {**USD_QUOTE_PAIRS, **USD_BASE_PAIRS}


def pair_is_usd_base(pair: str) -> bool:
    """True when buying the pair is *short* the non-dollar currency (e.g. USD_JPY)."""
    if pair in USD_BASE_PAIRS:
        return True
    if pair in USD_QUOTE_PAIRS:
        return False
    raise ValueError(f"pair_is_usd_base: {pair!r} is not a USD major in the universe")


def rebalance_bars(
    index: pd.DatetimeIndex, warmup_bars: int = LOOKBACK_BARS
) -> List[int]:
    """Positional indices of the first bar of each calendar month, after warmup.

    Uses only ``index[i]`` and ``index[i-1]``, so truncating the series cannot change
    which earlier bars are rebalance bars — the property ``assert_no_lookahead_v2``
    checks for order emission, applied here to cadence.
    """
    if warmup_bars < 0:
        raise ValueError("rebalance_bars: warmup_bars must be >= 0")
    # Month key as an integer rather than to_period(), which drops tz and warns. The
    # bars are tz-aware UTC and must stay that way: a naive conversion would shift
    # the 21:00 UTC D1 stamps across a month boundary.
    periods = np.asarray(index.year) * 12 + np.asarray(index.month)
    bars: List[int] = []
    for i in range(max(warmup_bars, 1), len(index)):
        if periods[i] != periods[i - 1]:
            bars.append(i)
    return bars


def currency_weights_at(
    closes: pd.DataFrame, i: int, lookback_bars: int = LOOKBACK_BARS
) -> Dict[str, float]:
    """Net tercile weights per *currency* using closes at ``i`` and ``i - lookback``.

    A pair whose close is missing at either end is dropped from the universe for this
    rebalance rather than imputed — a currency ranked on a fabricated price would
    reorder the whole cross-section.
    """
    if i < lookback_bars:
        raise ValueError(
            f"currency_weights_at: bar {i} is inside the {lookback_bars} warmup"
        )

    mom: Dict[str, float] = {}
    for pair in closes.columns:
        currency = PAIR_TO_CURRENCY.get(str(pair))
        if currency is None:
            continue
        close_now = float(closes.iloc[i][pair])
        close_then = float(closes.iloc[i - lookback_bars][pair])
        if not np.isfinite(close_now) or not np.isfinite(close_then):
            continue
        if close_now <= 0.0 or close_then <= 0.0:
            continue
        mom[currency] = currency_momentum(
            close_then, close_now, usd_base=pair_is_usd_base(str(pair))
        )

    if len(mom) < 2:
        return {}
    return net_tercile_weights(mom)


def build_weight_schedule(
    closes: pd.DataFrame, lookback_bars: int = LOOKBACK_BARS
) -> pd.DataFrame:
    """Monthly pair-weight schedule. Index = rebalance timestamps, columns = pairs.

    A currency weight becomes a *pair* weight by the §4.4/§5.4 convention: long the
    currency means buying a USD-quote pair and selling a USD-base pair, so a USD-base
    pair's weight is the negated currency weight. ``direction_for_currency_weight``
    encodes the same rule for the discrete case and the tests assert the two agree.
    """
    unknown = [str(p) for p in closes.columns if str(p) not in PAIR_TO_CURRENCY]
    if unknown:
        raise ValueError(f"build_weight_schedule: pairs outside the universe {unknown}")

    bars = rebalance_bars(closes.index, warmup_bars=lookback_bars)
    if not bars:
        raise ValueError(
            f"build_weight_schedule: no rebalance bars after a {lookback_bars}-bar "
            f"warmup in {len(closes)} bars"
        )

    rows: List[Dict[str, float]] = []
    stamps: List[pd.Timestamp] = []
    for i in bars:
        cw = currency_weights_at(closes, i, lookback_bars)
        if not cw:
            continue
        row = {
            str(pair): (
                -cw.get(PAIR_TO_CURRENCY[str(pair)], 0.0)
                if pair_is_usd_base(str(pair))
                else cw.get(PAIR_TO_CURRENCY[str(pair)], 0.0)
            )
            for pair in closes.columns
        }
        rows.append(row)
        stamps.append(closes.index[i])

    schedule = pd.DataFrame(rows, index=pd.DatetimeIndex(stamps, name="timestamp"))
    schedule = schedule[[str(p) for p in closes.columns]]
    logger.info(
        "weight schedule | %d rebalances %s -> %s | gross exposure mean %.3f",
        len(schedule),
        schedule.index[0].date() if len(schedule) else "-",
        schedule.index[-1].date() if len(schedule) else "-",
        float(schedule.abs().sum(axis=1).mean()) if len(schedule) else 0.0,
    )
    return schedule
