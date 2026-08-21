"""Pure freshness logic — no DB, no network, no clock reads.

Kept separate from ``heartbeat.py`` so every threshold decision is testable by
passing timestamps in. Repo convention: pure math separated from I/O.

The FX-market awareness here is the part that matters. Naive "data must be < N
hours old" thresholds false-alarm every weekend, and a check that cries wolf
every Monday is a check that gets ignored — which is how the last two outages
stayed invisible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import IntEnum


class Status(IntEnum):
    """Ordered so ``max()`` over statuses yields the overall severity."""

    OK = 0
    WARN = 1
    CRITICAL = 2
    BLOCKED = 3  # cannot be evaluated — visible degradation, never silent


# Exit codes: 0 all fresh, 1 warnings, 2 critical/blocked.
EXIT_FOR_STATUS = {
    Status.OK: 0,
    Status.WARN: 1,
    Status.CRITICAL: 2,
    Status.BLOCKED: 2,
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    detail: str
    age_hours: float | None = None
    threshold_hours: float | None = None
    budget_used: float | None = None
    """Fraction of this check's own tolerance consumed (1.0 = at the limit).

    Checks measure incomparable things — wall-clock age for the cron log,
    shortfall against the last market close for price data, pass/fail for the
    bundle checksum. ``age_hours / threshold_hours`` is meaningless across that
    mix, so each check reports its own normalised headroom and dashboards use
    this instead. ``None`` means the check has no continuous tolerance.
    """
    held_reason: str | None = None
    underlying_status: "Status | None" = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.name,
            "detail": self.detail,
            "age_hours": (
                round(self.age_hours, 2) if self.age_hours is not None else None
            ),
            "threshold_hours": self.threshold_hours,
            "budget_used": (
                round(self.budget_used, 3) if self.budget_used is not None else None
            ),
            "held": self.held_reason is not None,
            "held_reason": self.held_reason,
            # `is not None`, not truthiness: Status.OK is IntEnum 0, so a held
            # check whose underlying measurement is healthy would serialise as
            # null — the one held state that would silently lose its provenance.
            "underlying_status": (
                self.underlying_status.name
                if self.underlying_status is not None
                else None
            ),
        }


# --- FX market calendar -------------------------------------------------------
# The market closes Friday ~21:00 UTC and reopens Sunday ~21:00 UTC. Price data
# therefore *cannot* be fresher than the last close, no matter how healthy the
# ingest is.

FRIDAY = 4
SATURDAY = 5

# Bars are timestamped at their open. The last H1 bar before a 21:00 Friday
# close is stamped 20:00, so "fully covered" means reaching close - 1h.
FINAL_BAR_OFFSET = timedelta(hours=1)


def last_market_close(now: datetime) -> datetime:
    """The most recent Friday 21:00 UTC at or before ``now``."""
    now = now.astimezone(timezone.utc)
    days_since_friday = (now.weekday() - FRIDAY) % 7
    candidate = (now - timedelta(days=days_since_friday)).replace(
        hour=21, minute=0, second=0, microsecond=0
    )
    if candidate > now:
        candidate -= timedelta(days=7)
    return candidate


def last_scheduled_ingest(now: datetime) -> datetime:
    """The most recent Saturday 00:00 UTC at or before ``now``.

    This is the weekly `cron_oanda_ingest_saturday.sh` slot. It is the *only*
    thing that advances price data, so it — not wall-clock hours — defines what
    "fresh" can possibly mean.
    """
    now = now.astimezone(timezone.utc)
    days_since_saturday = (now.weekday() - SATURDAY) % 7
    candidate = (now - timedelta(days=days_since_saturday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    if candidate > now:
        candidate -= timedelta(days=7)
    return candidate


def expected_price_coverage(now: datetime) -> datetime:
    """How far price data should reach, given the weekly ingest cadence.

    The last Saturday ingest should have pulled everything up to the Friday
    close immediately preceding it. Bars are stamped at their **open**, so the
    final H1 bar of the week is stamped 20:00, not the 21:00 close — expecting
    a row *at* the close would flag healthy data as one hour short.
    """
    return last_market_close(last_scheduled_ingest(now)) - FINAL_BAR_OFFSET


def check_market_data_freshness(
    name: str,
    latest: datetime | None,
    now: datetime,
    *,
    grace_hours: float = 26.0,
) -> CheckResult:
    """Market-calendar-aware freshness for price/regime-style tables.

    ``grace_hours`` covers the ingest run itself plus the last partial bar; it
    is not a tolerance for a dead pipeline.
    """
    if latest is None:
        return CheckResult(name, Status.CRITICAL, "no rows at all")

    expected = expected_price_coverage(now)
    age = (now - latest).total_seconds() / 3600.0
    shortfall = (expected - latest).total_seconds() / 3600.0

    if shortfall <= 0:
        return CheckResult(
            name,
            Status.OK,
            f"covers through {latest:%Y-%m-%d %H:%MZ} "
            f"(last market close {expected:%Y-%m-%d %H:%MZ})",
            age,
            grace_hours,
            0.0,
        )
    if shortfall <= grace_hours:
        # Inside the grace band is normal, not noteworthy. Reporting it as WARN
        # would put the heartbeat in a permanent non-green state, and a monitor
        # that is always yellow is a monitor nobody reads.
        return CheckResult(
            name,
            Status.OK,
            f"covers through {latest:%Y-%m-%d %H:%MZ}, {shortfall:.1f}h inside the "
            f"{grace_hours:.0f}h grace on the last close ({expected:%Y-%m-%d %H:%MZ})",
            age,
            grace_hours,
            shortfall / grace_hours,
        )
    if shortfall <= 2 * grace_hours:
        return CheckResult(
            name,
            Status.WARN,
            f"{shortfall:.1f}h short of the last market close "
            f"({expected:%Y-%m-%d %H:%MZ}) — past the {grace_hours:.0f}h grace",
            age,
            grace_hours,
            shortfall / grace_hours,
        )
    return CheckResult(
        name,
        Status.CRITICAL,
        f"{shortfall/24:.1f} days behind the last market close "
        f"({expected:%Y-%m-%d %H:%MZ}); latest row {latest:%Y-%m-%d %H:%MZ}",
        age,
        grace_hours,
        shortfall / grace_hours,
    )


def check_age(
    name: str,
    latest: datetime | None,
    now: datetime,
    *,
    warn_hours: float,
    critical_hours: float,
    what: str = "last update",
) -> CheckResult:
    """Plain wall-clock age check, for things that do not follow the FX calendar."""
    if latest is None:
        return CheckResult(name, Status.CRITICAL, f"{what}: never")
    # Clamp at zero: a remote object written moments ago can carry a timestamp
    # marginally ahead of our clock, and "-0.0h ago" reads like a bug.
    age = max(0.0, (now - latest).total_seconds() / 3600.0)
    if age >= critical_hours:
        status = Status.CRITICAL
    elif age >= warn_hours:
        status = Status.WARN
    else:
        status = Status.OK
    return CheckResult(
        name,
        status,
        f"{what} {latest:%Y-%m-%d %H:%MZ} ({age:.1f}h ago, "
        f"warn ≥{warn_hours:g}h / critical ≥{critical_hours:g}h)",
        age,
        critical_hours,
        age / critical_hours if critical_hours else None,
    )


def overall_status(results: list[CheckResult]) -> Status:
    return max((r.status for r in results), default=Status.OK)


def exit_code(results: list[CheckResult]) -> int:
    return EXIT_FOR_STATUS[overall_status(results)]
