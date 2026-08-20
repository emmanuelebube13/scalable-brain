"""MODEL-009 — pure trigger + cooldown logic (no DB/network/clock side effects)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

SHARPE_14D_FLOOR = 0.3
REGIME_ACCURACY_FLOOR = 0.70
DEFAULT_COOLDOWN_SECONDS = 6 * 3600  # 6h debounce between retrains


def is_scheduled_window(now: datetime) -> bool:
    """True at the Sunday 00:00 UTC weekly slot (weekday 6, hour 0)."""
    now = now.astimezone(timezone.utc)
    return now.weekday() == 6 and now.hour == 0


def evaluate_performance_triggers(metrics: Dict[str, Optional[float]]) -> List[str]:
    """Return the list of fired performance-trigger reasons.

    Fail-safe: a missing/None metric does NOT fire (no false trigger on absent telemetry).
    """
    fired: List[str] = []
    sharpe = metrics.get("sharpe_14d")
    if sharpe is not None and sharpe < SHARPE_14D_FLOOR:
        fired.append(f"sharpe_14d={sharpe:.3f}<{SHARPE_14D_FLOOR}")
    acc = metrics.get("regime_accuracy")
    if acc is not None and acc < REGIME_ACCURACY_FLOOR:
        fired.append(f"regime_accuracy={acc:.3f}<{REGIME_ACCURACY_FLOOR}")
    if metrics.get("circuit_breaker"):
        fired.append("circuit_breaker")
    return fired


def within_cooldown(last_run_utc: Optional[str], now: datetime, cooldown_seconds: int) -> bool:
    if not last_run_utc:
        return False
    last = datetime.fromisoformat(last_run_utc)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (now.astimezone(timezone.utc) - last).total_seconds() < cooldown_seconds


def decide(now: datetime, metrics: Dict, state: Dict, cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS):
    """Return (should_run: bool, reasons: list[str]). Honors cooldown debounce."""
    reasons: List[str] = []
    if is_scheduled_window(now):
        reasons.append("scheduled:sunday-00utc")
    reasons.extend(evaluate_performance_triggers(metrics))
    if not reasons:
        return False, []
    if within_cooldown(state.get("last_run_utc"), now, cooldown_seconds):
        return False, [f"suppressed-by-cooldown ({reasons})"]
    return True, reasons
