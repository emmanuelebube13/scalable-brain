"""Unit tests for MODEL-001 data-quality checks and gap detection (no DB / no network)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.system1.ingestion import dq


def _bar(t, o, h, l, c, asset_id=1, granularity="D1", volume=100):
    return {
        "asset_id": asset_id,
        "granularity": granularity,
        "bar_time_utc": t,
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": volume,
        "complete": True,
    }


def _dt(y, m, d, hh=22):
    return datetime(y, m, d, hh, tzinfo=timezone.utc)


def test_clean_page_passes():
    bars = [
        _bar(_dt(2020, 1, 1), 1.10, 1.12, 1.09, 1.11),
        _bar(_dt(2020, 1, 2), 1.11, 1.13, 1.10, 1.12),
    ]
    ok, q = dq.run_dq_checks(bars)
    assert len(ok) == 2 and q == []


def test_ohlc_sanity_quarantined():
    # high < close violates sanity
    bars = [_bar(_dt(2020, 1, 1), 1.10, 1.105, 1.09, 1.20)]
    ok, q = dq.run_dq_checks(bars)
    assert ok == [] and q[0][1] == dq.OHLC_SANITY


def test_non_positive_price_quarantined():
    bars = [_bar(_dt(2020, 1, 1), 0.0, 1.1, 0.0, 1.0)]
    ok, q = dq.run_dq_checks(bars)
    assert ok == [] and q[0][1] == dq.NON_POSITIVE_PRICE


def test_non_monotonic_quarantined():
    bars = [
        _bar(_dt(2020, 1, 2), 1.11, 1.13, 1.10, 1.12),
        _bar(_dt(2020, 1, 1), 1.10, 1.12, 1.09, 1.11),  # goes backwards
    ]
    ok, q = dq.run_dq_checks(bars)
    reasons = {r for (_, r, _) in q}
    assert dq.NON_MONOTONIC in reasons


def test_duplicate_quarantined():
    t = _dt(2020, 1, 1)
    bars = [_bar(t, 1.10, 1.12, 1.09, 1.11), _bar(t, 1.10, 1.12, 1.09, 1.11)]
    ok, q = dq.run_dq_checks(bars)
    reasons = {r for (_, r, _) in q}
    assert dq.DUPLICATE in reasons and len(ok) == 1  # first kept, dup quarantined


def test_weekend_gap_not_counted_as_error():
    # Friday -> Monday daily gap (weekend) should classify as weekend, ratio stays 0.
    fri = datetime(2020, 1, 3, 22, tzinfo=timezone.utc)  # Friday
    mon = datetime(2020, 1, 6, 22, tzinfo=timezone.utc)  # Monday
    bars = [_bar(fri, 1.1, 1.2, 1.0, 1.15), _bar(mon, 1.15, 1.25, 1.1, 1.2)]
    rep = dq.detect_gaps(bars, "D1", timedelta(days=1))
    assert rep["weekend_gaps"] == 1
    assert rep["unexpected_gaps"] == 0
    assert rep["missing_expected_bar_ratio"] == 0.0


def test_unexpected_midweek_gap_counted():
    # Tuesday -> Friday daily gap (Wed/Thu missing) is unexpected.
    tue = datetime(2020, 1, 7, 22, tzinfo=timezone.utc)
    fri = datetime(2020, 1, 10, 22, tzinfo=timezone.utc)
    bars = [_bar(tue, 1.1, 1.2, 1.0, 1.15), _bar(fri, 1.15, 1.25, 1.1, 1.2)]
    rep = dq.detect_gaps(bars, "D1", timedelta(days=1))
    assert rep["unexpected_gaps"] == 1
    assert rep["unexpected_missing_bars"] == 2
    assert rep["missing_expected_bar_ratio"] > 0
