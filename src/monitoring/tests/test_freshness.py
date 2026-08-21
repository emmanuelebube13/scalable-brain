"""Threshold and market-calendar tests for the T4 heartbeat.

All timestamps are injected — nothing here touches the database, the clock, or
the network. The weekend-awareness cases are the ones that matter: a heartbeat
that warns every Monday gets muted, and a muted heartbeat is why the last two
outages ran for weeks.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.monitoring.freshness import (
    Status,
    check_age,
    check_market_data_freshness,
    exit_code,
    expected_price_coverage,
    last_market_close,
    last_scheduled_ingest,
    overall_status,
)


def utc(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


# --- market calendar ----------------------------------------------------------


@pytest.mark.parametrize(
    "now,expected",
    [
        # Wednesday → the previous Friday's close.
        (utc(2026, 7, 29, 10), utc(2026, 7, 24, 21)),
        # Saturday morning, after the ingest cron → still Friday's close.
        (utc(2026, 7, 25, 3), utc(2026, 7, 24, 21)),
        # Friday 20:00, before that day's close → the PREVIOUS week's close.
        (utc(2026, 7, 24, 20), utc(2026, 7, 17, 21)),
        # Friday 22:00, just after the close → that day's close.
        (utc(2026, 7, 24, 22), utc(2026, 7, 24, 21)),
        # Sunday, market reopened but no new close yet.
        (utc(2026, 7, 26, 23), utc(2026, 7, 24, 21)),
    ],
)
def test_last_market_close(now, expected):
    assert last_market_close(now) == expected


@pytest.mark.parametrize(
    "now,expected",
    [
        (utc(2026, 7, 29, 10), utc(2026, 7, 25)),  # Wed → last Saturday
        (utc(2026, 7, 25, 0, 30), utc(2026, 7, 25)),  # Sat just after the cron
        (utc(2026, 7, 24, 23), utc(2026, 7, 18)),  # Fri → the prior Saturday
    ],
)
def test_last_scheduled_ingest(now, expected):
    assert last_scheduled_ingest(now) == expected


def test_expected_coverage_accounts_for_bar_open_stamping():
    """Bars are stamped at open, so full coverage is close - 1h, not the close."""
    assert expected_price_coverage(utc(2026, 7, 29, 10)) == utc(2026, 7, 24, 20)


# --- market-data freshness ----------------------------------------------------


def test_fresh_prices_midweek_do_not_warn():
    """The real 2026-07-29 case: 110h old by wall clock, but perfectly fresh.

    The ingest is weekly and the market is shut — a naive 26h age threshold
    would fire six days out of seven.
    """
    r = check_market_data_freshness(
        "prices", utc(2026, 7, 24, 20), utc(2026, 7, 29, 10)
    )
    assert r.status is Status.OK
    assert r.age_hours > 100  # genuinely old by wall clock...
    # ...and still correct, because nothing newer can exist.


def test_monday_morning_does_not_false_alarm():
    r = check_market_data_freshness("prices", utc(2026, 7, 24, 20), utc(2026, 7, 27, 8))
    assert r.status is Status.OK


def test_one_missed_weekly_ingest_is_critical():
    """The 16-day ingest outage: data stops advancing while the cron 'succeeds'."""
    r = check_market_data_freshness(
        "prices", utc(2026, 7, 17, 20), utc(2026, 7, 29, 10)
    )
    assert r.status is Status.CRITICAL
    assert "behind the last market close" in r.detail


def test_shortfall_just_past_grace_warns_before_it_crits():
    r = check_market_data_freshness(
        "prices", utc(2026, 7, 24, 20) - timedelta(hours=30), utc(2026, 7, 29, 10)
    )
    assert r.status is Status.WARN


def test_empty_table_is_critical():
    r = check_market_data_freshness("prices", None, utc(2026, 7, 29, 10))
    assert r.status is Status.CRITICAL
    assert "no rows" in r.detail


def test_long_dead_ingest_is_critical_not_merely_warn():
    """Two months of silence must never degrade to a warning."""
    r = check_market_data_freshness("outcomes", utc(2026, 5, 20), utc(2026, 7, 29, 10))
    assert r.status is Status.CRITICAL


# --- plain age checks ---------------------------------------------------------


def test_age_check_bands():
    now = utc(2026, 7, 29, 12)
    fresh = check_age(
        "cron", now - timedelta(minutes=30), now, warn_hours=2, critical_hours=6
    )
    warn = check_age(
        "cron", now - timedelta(hours=3), now, warn_hours=2, critical_hours=6
    )
    crit = check_age(
        "cron", now - timedelta(hours=9), now, warn_hours=2, critical_hours=6
    )
    assert (fresh.status, warn.status, crit.status) == (
        Status.OK,
        Status.WARN,
        Status.CRITICAL,
    )


def test_age_check_never_reports_negative_age():
    """A remote object written a moment ago can be marginally ahead of our clock."""
    now = utc(2026, 7, 29, 12)
    r = check_age(
        "telemetry", now + timedelta(seconds=90), now, warn_hours=24, critical_hours=72
    )
    assert r.age_hours == 0.0
    assert r.status is Status.OK


def test_never_updated_is_critical():
    r = check_age("telemetry", None, utc(2026, 7, 29), warn_hours=24, critical_hours=72)
    assert r.status is Status.CRITICAL


# --- aggregation --------------------------------------------------------------


def test_overall_status_and_exit_codes():
    from src.monitoring.freshness import CheckResult

    ok = CheckResult("a", Status.OK, "")
    warn = CheckResult("b", Status.WARN, "")
    crit = CheckResult("c", Status.CRITICAL, "")
    blocked = CheckResult("d", Status.BLOCKED, "")

    assert exit_code([ok, ok]) == 0
    assert exit_code([ok, warn]) == 1
    assert exit_code([ok, warn, crit]) == 2
    assert overall_status([ok, blocked]) is Status.BLOCKED
    # A check that cannot be evaluated must fail the run, never pass quietly.
    assert exit_code([ok, blocked]) == 2
