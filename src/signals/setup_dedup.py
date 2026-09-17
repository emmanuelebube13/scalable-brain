"""D9 — cross-run suppression of re-armed setups.

Owner decision 2026-09-16 (the standing Q1): **re-affirmation is never wanted.** A pending
setup that a strategy re-arms on every bar is one trade idea, and it must reach the wire
once.

Why this module exists: between 2026-09-14T09:00Z and 2026-09-16T17:00Z strategy 43
(``reference_pullback_continuation``) published the same EUR_USD H4 buy-stop **15 times**
— ``proposed_entry`` byte-identical on every row, a fresh ``signal_id`` each bar (the
uuid5 key includes ``bar_ts``), so nothing upstream or downstream could see them as one.
System 3's re-fire guard uses a 90-minute window; H4 re-arms arrive 4 hours apart, so
every copy cleared it. O-26 shows the identical shape realised as double exposure and
real losses on 2026-09-01.

The key is the signal's ECONOMIC content — ``strategy_id | instrument | granularity |
direction | entry price`` — deliberately excluding ``bar_ts`` (what defeats ``signal_id``
dedup) and excluding stop/target: a revised stop on the same pending level is still the
same trade idea, and publishing the revision is what sizes it twice. System 1 does not
manage positions; it must not narrate them either.

Window semantics: a key is suppressed while the setup keeps being re-emitted, measured in
**market-open hours** (``freshness.open_hours_between`` — a weekend cannot expire a
setup, FIX-S1-019's arithmetic). Every suppressed re-emission refreshes ``last_seen_at``,
so a continuously re-armed level stays suppressed for its whole life. Once the strategy
stops emitting it for longer than the window (level invalidated or filled), the key goes
cold and the same price re-appearing later is a NEW setup, published normally.

Fail-safe direction: an unreadable state file degrades to "publish" (at worst one
duplicate per setup, visible in the ledger), never to "suppress everything" — losing real
signals to a corrupt bookkeeping file would be the FIX-S1-016 shape rebuilt here. State
is committed only after a successful publish, so a failed publish cannot poison the next
attempt.

Suppressed candidates are still scored and still get a ledger row
(``wire_action="suppressed_duplicate"``) — absence of a wire message must never mean
absence of a record (O-20).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.monitoring.freshness import open_hours_between

logger = logging.getLogger("system1.signals.setup_dedup")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STATE_PATH = os.path.join(REPO_ROOT, "results", "state", "published_setups.json")

# Suppression window per granularity, in MARKET-OPEN hours: three bars of silence before
# a re-appearing key counts as a new setup. Wide enough that an hourly cadence cannot
# expire a live re-armed level between runs, narrow enough that a genuinely new signal at
# an old price is not swallowed for days.
SUPPRESS_WINDOW_OPEN_HOURS: Dict[str, float] = {
    "H1": 3.0,
    "H4": 12.0,
    "D1": 72.0,
    "W1": 504.0,
}
DEFAULT_WINDOW_OPEN_HOURS = 12.0

# Keys not seen for this long (wall-clock) are pruned so the file stays bounded.
PRUNE_AFTER_DAYS = 30


def setup_key(sig: Dict[str, Any]) -> str:
    """The economic identity of a signal. Excludes bar_ts, stop and target on purpose."""
    return "|".join(
        [
            str(sig.get("strategy_id")),
            str(sig.get("instrument")),
            str(sig.get("granularity")),
            str(sig.get("direction")),
            f"{float(sig['entry']):.6f}",
        ]
    )


def load_state(path: Optional[str] = None) -> Dict[str, Any]:
    """Read the setup state. Unreadable or absent degrades to empty — see module docstring.

    ``path`` resolves to ``STATE_PATH`` at call time (not def time) so tests can
    monkeypatch the module attribute and run_once cannot touch the real file.
    """
    path = path or STATE_PATH
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
        if not isinstance(state, dict):
            raise ValueError(f"expected object, got {type(state).__name__}")
        return state
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError, ValueError) as e:
        logger.error(
            "Setup-dedup state at %s is unreadable (%s) — treating as empty. At worst "
            "one duplicate per live setup publishes once more; the ledger records it.",
            path,
            e,
        )
        return {}


def save_state(state: Dict[str, Any], path: Optional[str] = None) -> None:
    """Atomic write (tmp + rename). Never raises — bookkeeping must not kill emission."""
    path = path or STATE_PATH
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=os.path.dirname(path), prefix=".published_setups.", suffix=".tmp"
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except OSError as e:
        logger.error("Could not persist setup-dedup state to %s: %s", path, e)


def _parse_ts(value: Any) -> Optional[datetime]:
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is None:
        return None  # refuse tz-naive rather than assume — same rule as map_contract
    return ts


def duplicate_of(
    state: Dict[str, Any], sig: Dict[str, Any], now: datetime
) -> Optional[Dict[str, Any]]:
    """The prior record if ``sig`` is a live re-arm of an already-published setup, else None.

    A malformed prior record (bad timestamp) counts as NOT a duplicate — fail toward
    publishing, per the module docstring.
    """
    prior = state.get(setup_key(sig))
    if not isinstance(prior, dict):
        return None
    last_seen = _parse_ts(prior.get("last_seen_at"))
    if last_seen is None:
        return None
    window = SUPPRESS_WINDOW_OPEN_HOURS.get(
        str(sig.get("granularity")), DEFAULT_WINDOW_OPEN_HOURS
    )
    if open_hours_between(last_seen, now) <= window:
        return prior
    return None


def note_suppressed(state: Dict[str, Any], sig: Dict[str, Any], now: datetime) -> None:
    """Refresh a suppressed key so a continuously re-armed setup never expires mid-life."""
    prior = state.get(setup_key(sig))
    if isinstance(prior, dict):
        prior["last_seen_at"] = now.isoformat().replace("+00:00", "Z")
        prior["suppressed_count"] = int(prior.get("suppressed_count", 0)) + 1


def note_published(state: Dict[str, Any], sig: Dict[str, Any], now: datetime) -> None:
    """Record a setup the producer actually published. Call ONLY after publish succeeded."""
    ts = now.isoformat().replace("+00:00", "Z")
    state[setup_key(sig)] = {
        "signal_id": sig.get("signal_id"),
        "first_published_at": ts,
        "last_seen_at": ts,
        "suppressed_count": 0,
    }


def prune(state: Dict[str, Any], now: datetime) -> None:
    """Drop keys cold for more than PRUNE_AFTER_DAYS (wall-clock) to bound the file."""
    cutoff_seconds = PRUNE_AFTER_DAYS * 24 * 3600
    stale = []
    for key, rec in state.items():
        last_seen = (
            _parse_ts(rec.get("last_seen_at")) if isinstance(rec, dict) else None
        )
        if last_seen is None or (now - last_seen).total_seconds() > cutoff_seconds:
            stale.append(key)
    for key in stale:
        del state[key]
