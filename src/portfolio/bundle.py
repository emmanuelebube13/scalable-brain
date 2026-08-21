"""Pair-keyed frame bundles — the input a cross-sectional strategy needs.

``v2_harness.build_frames`` loops over ``metadata.pairs`` and calls a strategy once per
pair, so a strategy can never see two pairs at the same time. This module loads all
pairs at once and aligns them onto one calendar, which is the precondition for ranking
them against each other.

Alignment policy (deliberate, and the reason this is not a one-liner)
--------------------------------------------------------------------
Different pairs have slightly different bar counts — a pair can be missing a bar the
others have. Two wrong answers are available:

* ``dropna()`` across the whole matrix throws away every timestamp where *any* pair is
  missing, silently shortening the sample and biasing it toward quiet periods.
* Unrestricted forward-fill invents prices during genuine market closure and makes a
  stale price look like a flat return.

What we do instead: build the union calendar, forward-fill each pair by at most
``max_staleness_bars`` bars, and record per-pair staleness counts in the returned
``BundleReport`` so the caller can see how much filling happened rather than trusting
it blindly. A pair still missing after the bounded fill is left as NaN and every
downstream consumer must treat NaN as "no position", never as "zero return".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Mapping, Optional, Sequence

import pandas as pd
from sqlalchemy import bindparam, text

from src.common.db import get_engine

logger = logging.getLogger("system1.portfolio.bundle")

#: Columns every frame in a bundle carries, in this order.
FRAME_COLUMNS: Sequence[str] = (
    "Open",
    "high",
    "low",
    "Close",
    "volume",
    "bid_close",
    "ask_close",
)

#: A D1 bar is missing for at most a long weekend plus a holiday before we stop
#: pretending the last price is still good.
DEFAULT_MAX_STALENESS_BARS = 3


@dataclass(frozen=True)
class BundleReport:
    """What the loader had to do to make the pairs line up.

    ``rows_per_pair`` is the raw count from the database; ``filled_per_pair`` counts
    bars that exist only because of the bounded forward-fill; ``dropped_per_pair``
    counts bars left NaN because the gap exceeded ``max_staleness_bars``.
    """

    granularity: str
    calendar_start: pd.Timestamp
    calendar_end: pd.Timestamp
    calendar_bars: int
    rows_per_pair: Dict[str, int] = field(default_factory=dict)
    filled_per_pair: Dict[str, int] = field(default_factory=dict)
    dropped_per_pair: Dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        parts = [
            f"{p}: {self.rows_per_pair.get(p, 0)} rows"
            f" (+{self.filled_per_pair.get(p, 0)} filled,"
            f" {self.dropped_per_pair.get(p, 0)} NaN)"
            for p in sorted(self.rows_per_pair)
        ]
        return (
            f"{self.granularity} calendar {self.calendar_start:%Y-%m-%d}"
            f" -> {self.calendar_end:%Y-%m-%d} ({self.calendar_bars} bars) | "
            + "; ".join(parts)
        )


_QUERY = text("""
    SELECT a.symbol           AS symbol,
           p."timestamp"      AS ts,
           p."Open"           AS "Open",
           p.high             AS high,
           p.low              AS low,
           p."Close"          AS "Close",
           p.volume           AS volume,
           p.bid_close        AS bid_close,
           p.ask_close        AS ask_close
      FROM fact_market_prices p
      JOIN dim_asset a ON a.asset_id = p.asset_id
     WHERE p.granularity = :granularity
       AND a.symbol IN :symbols
       AND (:start_ts IS NULL OR p."timestamp" >= :start_ts)
       AND (:end_ts   IS NULL OR p."timestamp" <= :end_ts)
     ORDER BY a.symbol, p."timestamp"
    """).bindparams(bindparam("symbols", expanding=True))


def load_frames(
    pairs: Sequence[str],
    granularity: str = "D1",
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Dict[str, pd.DataFrame]:
    """Load one OHLC frame per pair, indexed by UTC timestamp, sorted ascending.

    Pairs with no rows are omitted from the result rather than returned empty — a
    caller that silently evaluates a 4-pair universe as if it were 5 would be
    computing a different strategy from the one it thinks it is, so
    :func:`build_bundle` raises on the difference instead.
    """
    if not pairs:
        raise ValueError("load_frames: no pairs requested")

    params = {
        "granularity": granularity,
        "symbols": list(pairs),
        "start_ts": start,
        "end_ts": end,
    }
    with get_engine().connect() as conn:
        raw = pd.read_sql(_QUERY, conn, params=params, parse_dates=["ts"])

    frames: Dict[str, pd.DataFrame] = {}
    for symbol, group in raw.groupby("symbol", sort=True):
        frame = group.drop(columns=["symbol"]).set_index("ts").sort_index()
        frame.index.name = "timestamp"
        # A duplicated (timestamp, pair) would double-count a bar in every downstream
        # return calculation; the DB's natural key should prevent it, so treat any
        # survivor as a data fault rather than quietly de-duplicating.
        duplicates = int(frame.index.duplicated().sum())
        if duplicates:
            raise ValueError(
                f"load_frames: {symbol} {granularity} has {duplicates} duplicate "
                f"timestamps; the natural key should make this impossible"
            )
        frames[str(symbol)] = frame[list(FRAME_COLUMNS)]
    return frames


def align_closes(
    frames: Mapping[str, pd.DataFrame],
    max_staleness_bars: int = DEFAULT_MAX_STALENESS_BARS,
) -> tuple[pd.DataFrame, BundleReport]:
    """Put every pair's close on one calendar with a *bounded* forward-fill.

    Returns ``(closes, report)`` where ``closes`` is indexed by the union calendar with
    one column per pair. NaN survives where a gap was longer than
    ``max_staleness_bars``; callers must read NaN as "no position", not "zero return".
    """
    if not frames:
        raise ValueError("align_closes: empty bundle")
    if max_staleness_bars < 0:
        raise ValueError("align_closes: max_staleness_bars must be >= 0")

    calendar = pd.DatetimeIndex(
        sorted(set().union(*(f.index for f in frames.values())))
    )
    columns: Dict[str, pd.Series] = {}
    rows_per_pair: Dict[str, int] = {}
    filled_per_pair: Dict[str, int] = {}
    dropped_per_pair: Dict[str, int] = {}

    for pair, frame in frames.items():
        raw = frame["Close"].reindex(calendar)
        rows_per_pair[pair] = int(frame["Close"].notna().sum())
        filled = raw.ffill(limit=max_staleness_bars) if max_staleness_bars else raw
        filled_per_pair[pair] = int((filled.notna() & raw.isna()).sum())
        dropped_per_pair[pair] = int(filled.isna().sum())
        columns[pair] = filled

    closes = pd.DataFrame(columns, index=calendar).sort_index()
    closes.index.name = "timestamp"
    report = BundleReport(
        granularity="",
        calendar_start=calendar[0],
        calendar_end=calendar[-1],
        calendar_bars=len(calendar),
        rows_per_pair=rows_per_pair,
        filled_per_pair=filled_per_pair,
        dropped_per_pair=dropped_per_pair,
    )
    return closes, report


def build_bundle(
    pairs: Sequence[str],
    granularity: str = "D1",
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    max_staleness_bars: int = DEFAULT_MAX_STALENESS_BARS,
) -> tuple[Dict[str, pd.DataFrame], pd.DataFrame, BundleReport]:
    """Load and align in one call. Raises if any requested pair has no data.

    Returns ``(frames, closes, report)``.
    """
    frames = load_frames(pairs, granularity, start, end)
    missing: List[str] = [p for p in pairs if p not in frames]
    if missing:
        raise ValueError(
            f"build_bundle: no {granularity} rows for {missing}. A cross-sectional "
            f"universe silently shrinking changes the strategy; fix the data or pass "
            f"the reduced universe explicitly."
        )
    closes, report = align_closes(frames, max_staleness_bars)
    report = BundleReport(
        granularity=granularity,
        calendar_start=report.calendar_start,
        calendar_end=report.calendar_end,
        calendar_bars=report.calendar_bars,
        rows_per_pair=report.rows_per_pair,
        filled_per_pair=report.filled_per_pair,
        dropped_per_pair=report.dropped_per_pair,
    )
    logger.info("bundle | %s", report.summary())
    return frames, closes, report
