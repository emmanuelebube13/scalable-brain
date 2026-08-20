"""MODEL-001 — per-batch data-quality checks and FX-calendar-aware gap detection.

Operates on *normalized bar dicts* (one page, already filtered to complete candles):

    {
        "asset_id": int, "granularity": str, "bar_time_utc": datetime (UTC, tz-aware),
        "open": float, "high": float, "low": float, "close": float,
        "volume": int, "complete": bool,
    }

DQ checks return ``(ok_bars, quarantined)`` where ``quarantined`` is a list of
``(bar, reason_code, detail)`` — rows are quarantined, never silently dropped.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

Bar = Dict[str, object]
Quarantined = Tuple[Bar, str, str]

# Reason codes (stable; written to fact_market_prices_quarantine.quarantine_reason_code)
OHLC_SANITY = "OHLC_SANITY"
NON_POSITIVE_PRICE = "NON_POSITIVE_PRICE"
NON_MONOTONIC = "NON_MONOTONIC"
DUPLICATE = "DUPLICATE"


def _natural_key(b: Bar) -> tuple:
    return (b["asset_id"], b["granularity"], b["bar_time_utc"])


def run_dq_checks(bars: List[Bar]) -> Tuple[List[Bar], List[Quarantined]]:
    """Run pre-commit DQ checks on one page of bars.

    A bar failing any check is quarantined with the first reason it trips. Bars are
    assumed to arrive in OANDA ascending order; monotonic/duplicate checks are within
    the page only.
    """
    quarantined: List[Quarantined] = []
    bad_ids = set()  # id(bar) of any quarantined bar

    # 1. OHLC sanity + 2. non-positive price (per-bar, independent)
    for b in bars:
        o, h, l, c = b["open"], b["high"], b["low"], b["close"]
        if min(o, h, l, c) <= 0:
            quarantined.append((b, NON_POSITIVE_PRICE, f"min(OHLC)={min(o,h,l,c)} <= 0"))
            bad_ids.add(id(b))
            continue
        if l > min(o, c) or h < max(o, c) or l > h:
            quarantined.append(
                (b, OHLC_SANITY, f"O={o} H={h} L={l} C={c} violates L<=O,C<=H")
            )
            bad_ids.add(id(b))

    # 3. Monotonic bar times within the page (strictly decreasing = out of order).
    #    Equal timestamps are NOT flagged here — they are caught as DUPLICATE below so
    #    they get the more specific reason code.
    prev = None
    for b in bars:
        t = b["bar_time_utc"]
        if prev is not None and t < prev and id(b) not in bad_ids:
            quarantined.append((b, NON_MONOTONIC, f"bar_time {t} < previous {prev}"))
            bad_ids.add(id(b))
        prev = t

    # 4. Duplicate natural keys within the page
    key_counts = Counter(_natural_key(b) for b in bars)
    dup_keys = {k for k, n in key_counts.items() if n > 1}
    if dup_keys:
        seen = set()
        for b in bars:
            k = _natural_key(b)
            if k in dup_keys:
                if k in seen and id(b) not in bad_ids:
                    quarantined.append((b, DUPLICATE, f"duplicate natural key {k}"))
                    bad_ids.add(id(b))
                seen.add(k)

    ok = [b for b in bars if id(b) not in bad_ids]
    return ok, quarantined


def _is_weekend_gap(prev_t: datetime, next_t: datetime) -> bool:
    """True if the gap between two consecutive bars is an expected FX weekend gap.

    The forex market closes ~Fri 21:00 UTC and reopens ~Sun 21:00 UTC. We treat any
    gap whose missing span lies on Sat/Sun (prev bar on Fri, next bar on Sun/Mon) as
    an expected weekend gap.
    """
    # Friday == weekday 4, Saturday == 5, Sunday == 6
    if prev_t.weekday() == 4 and next_t.weekday() in (6, 0):
        return True
    # Any gap that starts Friday/Saturday and the intervening days are all weekend.
    cur = prev_t + timedelta(days=1)
    saw_weekend = False
    while cur.date() < next_t.date():
        if cur.weekday() < 5:  # a weekday is missing → not purely a weekend gap
            return False
        saw_weekend = True
        cur += timedelta(days=1)
    return saw_weekend


def detect_gaps(
    bars: List[Bar], granularity: str, interval: timedelta
) -> Dict[str, object]:
    """Detect coverage gaps over a *sorted, deduped* sequence of bars.

    Returns a report dict with classified gaps and a coverage metric. Weekend/holiday
    gaps are logged (INFO) but not counted as errors; only unexpected intra-week gaps
    count toward the missing-expected-bar ratio.
    """
    ordered = sorted(bars, key=lambda b: b["bar_time_utc"])
    gaps: List[dict] = []
    unexpected_missing = 0
    expected_total = max(len(ordered) - 1, 0)

    for prev, nxt in zip(ordered, ordered[1:]):
        pt: datetime = prev["bar_time_utc"]  # type: ignore[assignment]
        nt: datetime = nxt["bar_time_utc"]  # type: ignore[assignment]
        delta = nt - pt
        if delta <= interval * 1.5:
            continue
        missing = max(int(delta / interval) - 1, 0)
        if granularity in ("H1", "H4", "D1") and _is_weekend_gap(pt, nt):
            classification = "weekend"
        else:
            classification = "unexpected"
            unexpected_missing += missing
        gaps.append(
            {
                "after_bar_utc": pt.isoformat(),
                "before_bar_utc": nt.isoformat(),
                "gap_seconds": delta.total_seconds(),
                "missing_intervals": missing,
                "classification": classification,
            }
        )

    expected_denom = expected_total + unexpected_missing
    missing_ratio = (unexpected_missing / expected_denom) if expected_denom else 0.0
    return {
        "granularity": granularity,
        "bars_observed": len(ordered),
        "gaps": gaps,
        "weekend_gaps": sum(1 for g in gaps if g["classification"] == "weekend"),
        "unexpected_gaps": sum(1 for g in gaps if g["classification"] == "unexpected"),
        "unexpected_missing_bars": unexpected_missing,
        "missing_expected_bar_ratio": round(missing_ratio, 6),
    }
