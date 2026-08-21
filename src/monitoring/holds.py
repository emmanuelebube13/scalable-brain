"""Holds for freshness monitoring."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .freshness import CheckResult, Status

HOLDABLE = {
    "prices",
    "outcomes",
    "regimes",
    "telemetry",
    "retrain_state",
    "cron_liveness",
}
# champion_bundle and imports are not holdable, and a hold naming either is a
# configuration error. Those two do not measure staleness — they measure whether the artifact you
# would ship is intact and whether the code still imports. Nobody ever *intends* a SHA256 mismatch
# or a broken import chain, so there is no honest declaration to make about them.

MAX_HOLD_DAYS = 90


@dataclass
class Hold:
    checks: list[str]
    reason: str
    declared_by: str
    declared_at_utc: datetime
    expires_utc: datetime
    evidence: str


def parse_holds(
    payload: dict[str, Any], now: datetime
) -> tuple[dict[str, Hold], list[str]]:
    problems = []
    holds_by_check = {}

    if "schema_version" not in payload or payload["schema_version"] != 1:
        problems.append("missing or unsupported schema_version")
        return {}, problems

    if "holds" not in payload or not isinstance(payload["holds"], list):
        problems.append("missing or invalid 'holds' list")
        return {}, problems

    for i, h in enumerate(payload["holds"]):
        if not isinstance(h, dict):
            problems.append(f"hold[{i}]: not an object")
            continue

        expected_keys = {
            "checks",
            "reason",
            "declared_by",
            "declared_at_utc",
            "expires_utc",
            "evidence",
        }
        missing = expected_keys - h.keys()
        extra = h.keys() - expected_keys

        if missing:
            problems.append(f"hold[{i}]: missing keys {', '.join(sorted(missing))}")
            continue
        if extra:
            problems.append(f"hold[{i}]: unknown keys {', '.join(sorted(extra))}")
            continue

        checks = h["checks"]
        if not isinstance(checks, list) or len(checks) == 0:
            problems.append(f"hold[{i}]: 'checks' must be a non-empty list")
            continue

        invalid = [c for c in checks if c not in HOLDABLE]
        if invalid:
            problems.append(f"hold[{i}]: {invalid[0]!r} is not holdable")
            continue

        try:
            declared_at = datetime.fromisoformat(
                h["declared_at_utc"].replace("Z", "+00:00")
            )
            expires = datetime.fromisoformat(h["expires_utc"].replace("Z", "+00:00"))
        except Exception:
            problems.append(f"hold[{i}]: invalid timestamp format")
            continue

        if declared_at.tzinfo is None:
            problems.append(f"hold[{i}]: declared_at_utc is naive")
            continue
        if expires.tzinfo is None:
            problems.append(f"hold[{i}]: expires_utc is naive")
            continue

        if expires > declared_at + timedelta(days=MAX_HOLD_DAYS):
            problems.append(f"hold[{i}]: duration exceeds {MAX_HOLD_DAYS} days")
            continue

        hold_obj = Hold(
            checks=checks,
            reason=h["reason"],
            declared_by=h["declared_by"],
            declared_at_utc=declared_at,
            expires_utc=expires,
            evidence=h["evidence"],
        )
        for c in checks:
            holds_by_check[c] = hold_obj

    return holds_by_check, problems


def apply_hold(result: CheckResult, hold: Hold, now: datetime) -> CheckResult:
    if now >= hold.expires_utc:
        return result

    days_left = (hold.expires_utc.date() - now.date()).days

    return CheckResult(
        name=result.name,
        status=Status.OK,
        detail=f"HELD until {hold.expires_utc:%Y-%m-%d} ({days_left}d left); underlying: {result.detail}",
        age_hours=result.age_hours,
        threshold_hours=result.threshold_hours,
        budget_used=result.budget_used,
        held_reason=hold.reason,
        underlying_status=result.status,
    )


def summarise(
    holds_by_check: dict[str, Hold], problems: list[str], now: datetime
) -> CheckResult:
    if problems:
        return CheckResult("holds", Status.BLOCKED, problems[0])

    if not holds_by_check:
        return CheckResult("holds", Status.OK, "no holds declared")

    unique_holds = []
    for h in holds_by_check.values():
        if h not in unique_holds:
            unique_holds.append(h)

    # Find worst status
    worst_status = Status.OK
    worst_detail = ""

    # We should evaluate expired first, then warning
    for h in unique_holds:
        if now >= h.expires_utc:
            days_ago = (now.date() - h.expires_utc.date()).days
            return CheckResult(
                "holds",
                Status.CRITICAL,
                f"hold on {'/'.join(h.checks)} expired {days_ago}d ago and nobody renewed it",
            )

    for h in unique_holds:
        days_left = (h.expires_utc.date() - now.date()).days
        if days_left <= 7:
            return CheckResult(
                "holds",
                Status.WARN,
                f"hold on {'/'.join(h.checks)} expires in {days_left}d — renew it or lift it",
            )

    # All holds are active and > 7 days left
    soonest = min((h.expires_utc.date() - now.date()).days for h in unique_holds)
    count = len(unique_holds)
    plural = "holds" if count > 1 else "hold"
    return CheckResult(
        "holds", Status.OK, f"{count} {plural} active, soonest expires in {soonest}d"
    )
