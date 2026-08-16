"""T4 — daily freshness heartbeat (I/O layer).

Run:  python -m src.system1.monitoring.heartbeat [--check NAME] [--json]

Exit codes: 0 = all fresh · 1 = warnings · 2 = critical or blocked.

On a non-zero result this writes a dated entry to ``logs/heartbeat_alerts.log``
and a flag file at ``results/state/HEARTBEAT_ALERT``. That flag file is the
contract — its presence means something is stale and nobody has looked yet.
The machine-readable snapshot always lands at
``results/state/heartbeat_latest.json``.

A check that cannot be evaluated reports BLOCKED with the reason. It is never
skipped: an unevaluated check that looks like a pass is precisely the failure
mode this task exists to eliminate.

Holds (declared pauses for known issues) are read from ``results/state/cron_holds.json``.
A held check retains its underlying measurement but suppresses its failure status.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .freshness import (
    CheckResult,
    Status,
    check_age,
    check_market_data_freshness,
    exit_code,
    overall_status,
)
from .holds import apply_hold, parse_holds, summarise

REPO = Path(__file__).resolve().parents[3]
STATE_DIR = REPO / "results" / "state"
LOG_DIR = REPO / "logs"
SNAPSHOT = STATE_DIR / "heartbeat_latest.json"
ALERT_FLAG = STATE_DIR / "HEARTBEAT_ALERT"
ALERT_LOG = LOG_DIR / "heartbeat_alerts.log"
HOLDS_FILE = STATE_DIR / "cron_holds.json"

# The hourly cron writes here; used as the liveness probe for cron itself.
CRON_LOG = LOG_DIR / "cron_system1_retrain.log"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_env() -> None:
    """Load .env explicitly.

    Without this, ``build_storage()`` falls back to STORAGE_PROVIDER=local and
    silently validates the stale local pointer instead of the live GCS one —
    a wrong-but-plausible pass. Found while building this check.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO / ".env")
    except Exception:  # noqa: BLE001 - absence of dotenv must not kill the run
        pass


# --- individual checks --------------------------------------------------------


def check_prices(now: datetime) -> CheckResult:
    from sqlalchemy import text

    from src.common.db import get_engine

    try:
        with get_engine().connect() as c:
            latest = c.execute(
                text('SELECT max("timestamp") FROM fact_market_prices '
                     "WHERE granularity IN ('H1','H4','D1')")
            ).scalar()
    except Exception as exc:  # noqa: BLE001
        return CheckResult("prices", Status.BLOCKED, f"DB unreachable: {exc}")
    return check_market_data_freshness("prices", latest, now)


def check_outcomes(now: datetime) -> CheckResult:
    from sqlalchemy import text

    from src.common.db import get_engine

    try:
        with get_engine().connect() as c:
            latest = c.execute(
                text('SELECT max("timestamp") FROM fact_trade_outcomes')
            ).scalar()
            written = c.execute(
                text("SELECT max(created_at) FROM fact_trade_outcomes")
            ).scalar()
    except Exception as exc:  # noqa: BLE001
        return CheckResult("outcomes", Status.BLOCKED, f"DB unreachable: {exc}")

    # Outcomes are sparse *events*, not bars: there is no guarantee a trade
    # opens in the final bar of the week, so bar-tight coverage would warn on
    # perfectly healthy data. A week of slack, with `created_at` below carrying
    # the real liveness signal.
    coverage = check_market_data_freshness(
        "outcomes", latest, now, grace_hours=7 * 24
    )
    if coverage.status is not Status.OK:
        return coverage
    # Coverage can look fine while the writer is dead, because the backtest
    # replays history. The write recency is the real liveness signal — that is
    # exactly what went unnoticed for five weeks.
    freshness = check_age(
        "outcomes", written, now,
        warn_hours=8 * 24, critical_hours=14 * 24, what="last written",
    )
    if freshness.status is not Status.OK:
        return CheckResult(
            "outcomes", freshness.status,
            f"data covers through {latest:%Y-%m-%d} but {freshness.detail}",
            freshness.age_hours, freshness.threshold_hours, freshness.budget_used,
        )
    return CheckResult(
        "outcomes", Status.OK,
        f"{coverage.detail}; written {written:%Y-%m-%d %H:%MZ}",
        freshness.age_hours, freshness.threshold_hours, freshness.budget_used,
    )


def check_regimes(now: datetime) -> CheckResult:
    from sqlalchemy import text

    from src.common.db import get_engine

    try:
        with get_engine().connect() as c:
            latest = c.execute(
                text('SELECT max("timestamp") FROM fact_market_regime_v2')
            ).scalar()
    except Exception as exc:  # noqa: BLE001
        return CheckResult("regimes", Status.BLOCKED, f"DB unreachable: {exc}")
    return check_market_data_freshness("regimes", latest, now)


def check_champion_bundle(now: datetime) -> CheckResult:
    """The live pointer must be readable and every artifact must match its SHA256."""
    _load_env()
    provider = os.environ.get("STORAGE_PROVIDER", "local")
    try:
        from src.common.storage import build_storage

        backend = build_storage()
        with tempfile.NamedTemporaryFile(suffix=".json") as tmp:
            backend.get_object("latest.json", tmp.name)
            pointer = json.load(open(tmp.name))
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            "champion_bundle", Status.CRITICAL,
            f"latest.json unreadable via {provider}: {exc}",
        )

    status = pointer.get("status")
    if status == "withdrawn":
        return CheckResult(
            "champion_bundle", Status.OK, "bundle withdrawn (no active model set)"
        )
        
    artifacts = pointer.get("artifacts", [])
    if not artifacts:
        return CheckResult(
            "champion_bundle", Status.CRITICAL, "latest.json lists no artifacts"
        )

    mismatched = []
    for art in artifacts:
        try:
            actual = backend.sha256(art["path"])
        except Exception as exc:  # noqa: BLE001
            mismatched.append(f"{art['name']}: unreadable ({exc})")
            continue
        if actual != art["sha256"]:
            mismatched.append(f"{art['name']}: sha256 mismatch")

    version = pointer.get("version") or artifacts[0]["path"].split("/")[1]
    if mismatched:
        return CheckResult(
            "champion_bundle", Status.CRITICAL,
            f"bundle {version} FAILED integrity: " + "; ".join(mismatched),
        )
    return CheckResult(
        "champion_bundle", Status.OK,
        f"bundle {version} on {provider}: {len(artifacts)} artifacts, all SHA256 verified",
    )


def check_telemetry(now: datetime) -> CheckResult:
    """Read ``telemetry/latest-vm.json`` — NOT ``latest.json``, which is dead."""
    _load_env()
    try:
        from src.common.storage import build_storage

        backend = build_storage()
        if not backend.exists("telemetry/latest-vm.json"):
            return CheckResult(
                "telemetry", Status.CRITICAL,
                "telemetry/latest-vm.json missing — the VM publisher is not writing",
            )
        meta = backend.head("telemetry/latest-vm.json")
    except Exception as exc:  # noqa: BLE001
        return CheckResult("telemetry", Status.BLOCKED, f"storage unreachable: {exc}")

    updated = meta.get("updated") or meta.get("last_modified")
    if isinstance(updated, str):
        updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))
    if updated is None:
        return CheckResult(
            "telemetry", Status.BLOCKED,
            "object exists but the backend exposed no modification time",
        )
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return check_age(
        "telemetry", updated, now,
        warn_hours=24, critical_hours=72, what="latest-vm.json written",
    )


def check_retrain_state(now: datetime) -> CheckResult:
    logs = sorted(STATE_DIR.glob("retrain_log_*.json"))
    if not logs:
        return CheckResult("retrain_state", Status.CRITICAL, "no retrain_log_*.json at all")
    newest = logs[-1]
    mtime = datetime.fromtimestamp(newest.stat().st_mtime, timezone.utc)
    try:
        payload = json.loads(newest.read_text())
    except Exception as exc:  # noqa: BLE001
        return CheckResult("retrain_state", Status.CRITICAL, f"{newest.name} unparseable: {exc}")

    outcome = payload.get("outcome", "unknown")
    result = check_age(
        "retrain_state", mtime, now,
        warn_hours=8 * 24, critical_hours=14 * 24, what=f"{newest.name} written",
    )
    if "fail" in str(outcome).lower() or "error" in str(outcome).lower():
        return CheckResult(
            "retrain_state", Status.CRITICAL,
            f"last evaluation outcome={outcome!r} ({newest.name})",
            result.age_hours, result.threshold_hours, result.budget_used,
        )
    return CheckResult(
        "retrain_state", result.status,
        f"outcome={outcome!r}; {result.detail}",
        result.age_hours, result.threshold_hours, result.budget_used,
    )


def check_cron_liveness(now: datetime) -> CheckResult:
    """The retrain cron runs hourly; its log should never be more than ~2h stale."""
    if not CRON_LOG.exists():
        return CheckResult(
            "cron_liveness", Status.CRITICAL, f"{CRON_LOG.name} does not exist — cron never ran"
        )
    mtime = datetime.fromtimestamp(CRON_LOG.stat().st_mtime, timezone.utc)
    return check_age(
        "cron_liveness", mtime, now,
        warn_hours=2, critical_hours=6, what=f"{CRON_LOG.name} touched",
    )


def check_imports(now: datetime) -> CheckResult:
    """Import canary — the exact failure that froze the feedback loop for 5 weeks.

    Runs in a subprocess so a broken import cannot take the heartbeat down with
    it (a monitor that dies with the thing it monitors reports nothing).
    """
    modules = [
        "src.layer0.persist_trade_outcomes",
        "src.system1.scheduler.orchestrator",
        "src.system1.attribution.attribute",
        "src.system1.vetting.vet",
    ]
    code = "import importlib,sys\n" + "".join(
        f"importlib.import_module({m!r})\n" for m in modules
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, timeout=180
    )
    if proc.returncode == 0:
        return CheckResult(
            "imports", Status.OK, f"all {len(modules)} critical modules import"
        )
    last = (proc.stderr.strip().splitlines() or ["<no output>"])[-1]
    return CheckResult("imports", Status.CRITICAL, f"import canary FAILED: {last}")


CHECKS = {
    "prices": check_prices,
    "outcomes": check_outcomes,
    "regimes": check_regimes,
    "champion_bundle": check_champion_bundle,
    "telemetry": check_telemetry,
    "retrain_state": check_retrain_state,
    "cron_liveness": check_cron_liveness,
    "imports": check_imports,
}


# --- runner -------------------------------------------------------------------

_GLYPH = {
    Status.OK: "PASS",
    Status.WARN: "WARN",
    Status.CRITICAL: "CRIT",
    Status.BLOCKED: "BLKD",
}


def _load_holds(now: datetime) -> tuple[dict, list[str]]:
    if not HOLDS_FILE.exists():
        return {}, []
    try:
        payload = json.loads(HOLDS_FILE.read_text())
    except Exception as exc:
        return {}, [f"cron_holds.json unparseable: {exc}"]
    return parse_holds(payload, now)


def run_checks(only: str | None = None, now: datetime | None = None) -> list[CheckResult]:
    now = now or _utcnow()
    names = [only] if only else list(CHECKS)
    results = []
    
    holds_by_check, holds_problems = _load_holds(now)
    active_holds = {} if holds_problems else holds_by_check
    
    for name in names:
        try:
            res = CHECKS[name](now)
            if name in active_holds:
                res = apply_hold(res, active_holds[name], now)
            results.append(res)
        except Exception as exc:  # noqa: BLE001 - a crashing check must still report
            results.append(
                CheckResult(name, Status.BLOCKED, f"check raised {type(exc).__name__}: {exc}")
            )
            
    results.append(summarise(holds_by_check, holds_problems, now))
    return results


def render(results: list[CheckResult], now: datetime) -> str:
    width = max(len(r.name) for r in results)
    lines = [f"System-1 freshness heartbeat — {now:%Y-%m-%d %H:%M:%SZ}", ""]
    for r in results:
        lines.append(f"  [{_GLYPH[r.status]}] {r.name:<{width}}  {r.detail}")
    status = overall_status(results)
    counts = {g: sum(1 for r in results if r.status is s) for s, g in _GLYPH.items()}
    lines += [
        "",
        "  " + " · ".join(f"{g}={n}" for g, n in counts.items() if n),
        f"  overall: {status.name} (exit {exit_code(results)})",
    ]
    return "\n".join(lines)


def persist(results: list[CheckResult], now: datetime) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    status = overall_status(results)
    SNAPSHOT.write_text(json.dumps({
        "evaluated_at_utc": now.isoformat(),
        "overall_status": status.name,
        "exit_code": exit_code(results),
        "checks": [r.to_dict() for r in results],
    }, indent=2) + "\n")

    failing = [r for r in results if r.status is not Status.OK]
    if not failing:
        # Clear a stale flag once everything is healthy again.
        ALERT_FLAG.unlink(missing_ok=True)
        return

    summary = "; ".join(f"{r.name}={r.status.name}: {r.detail}" for r in failing)
    ALERT_FLAG.write_text(
        f"{now:%Y-%m-%d %H:%M:%SZ} overall={status.name}\n"
        + "\n".join(f"{r.status.name} {r.name}: {r.detail}" for r in failing)
        + "\n"
    )
    with ALERT_LOG.open("a") as fh:
        fh.write(f"{now:%Y-%m-%dT%H:%M:%SZ} {status.name} {summary}\n")


def main() -> None:
    p = argparse.ArgumentParser(description="T4 System-1 freshness heartbeat")
    p.add_argument("--check", choices=sorted(CHECKS), help="run a single check")
    p.add_argument("--json", action="store_true", help="print the JSON snapshot instead of a table")
    p.add_argument("--holds", action="store_true", help="print declared holds and exit")
    args = p.parse_args()

    now = _utcnow()
    
    if args.holds:
        holds_by_check, problems = _load_holds(now)
        unique_holds = []
        for h in holds_by_check.values():
            if h not in unique_holds:
                unique_holds.append(h)
        for h in unique_holds:
            days_left = (h.expires_utc.date() - now.date()).days
            print(f"Checks: {', '.join(h.checks)}")
            print(f"Reason: {h.reason}")
            print(f"By: {h.declared_by} on {h.declared_at_utc:%Y-%m-%d}")
            print(f"Expires: {h.expires_utc:%Y-%m-%d} ({days_left}d left)")
            print(f"Evidence: {h.evidence}")
            print()
        if problems:
            print("Problems:")
            for prob in problems:
                print(f"  - {prob}")
        if not unique_holds and not problems:
            print("no holds declared")
        sys.exit(0)

    results = run_checks(args.check, now)
    persist(results, now)
    if args.json:
        print(SNAPSHOT.read_text().rstrip())
    else:
        print(render(results, now))
    sys.exit(exit_code(results))


if __name__ == "__main__":
    main()
