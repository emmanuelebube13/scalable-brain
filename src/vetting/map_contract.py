"""The regime map's provenance contract, freeze switch, and routing admissibility check.

Why this module exists
----------------------
``regime_strategy_map.json`` is the artifact that decides which strategy may fire in which
regime. Until now it recorded **when** it was built and **which attribution run** it came
from, and nothing else. In particular it did not record *which regime label it was selected
under* — and on 2026-08-24 a map selected on the HMM's ``regime_causal`` was published and
executed against the **structural** label, whose agreement with it is 19-36% (kappa ~0).

Every cell in that map was a statement about conditions that never fired it. Nothing in the
system could detect this, because nothing in the artifact stated the assumption that was
being violated. The header block below exists so that assumption is written down, and
:func:`routing_refusals` exists so it is *checked* rather than trusted.

The three rules this module enforces
------------------------------------
1. **A map states the label it was selected under.** ``source_label``. A map whose
   ``source_label`` differs from the label the live path routes on is inadmissible.
2. **A map expires.** ``expires_at_utc`` / ``MAP_MAX_AGE_DAYS``. A map that outlives its
   evidence must stop trading, not keep trading.
3. **Failure is closed.** Every defect here means *no signals*, loudly, with a distinct
   outcome. It never means "fall back to something permissive".

That third rule is the whole point. Before this, a stale map kept trading — the system
failed **open**, which is strictly worse than the FIX-S1-016 silent stall it replaced: that
at least failed closed by emitting nothing.
"""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("system1.vetting.map_contract")

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

#: How old a map may be before it stops being tradable, in days. Config, not a literal,
#: because the right value is an operational judgement and it appears in refusal messages.
#: Read from the environment so it can be tightened without a deploy.
MAP_MAX_AGE_DAYS = float(os.environ.get("MAP_MAX_AGE_DAYS", "7"))

#: The label the LIVE path actually routes on today. ``src/signals/run.py`` resolves the
#: regime via ``src.regime.structural.build_structural_labels``, so this is structural, and
#: it is asserted against every map's ``source_label`` before that map may route anything.
#:
#: If the live routing label ever changes, change it HERE and the mismatch check follows
#: automatically. Do not let this drift from what ``run.py`` does — a wrong value here would
#: re-authorise exactly the defect the module was written to stop.
ROUTING_SOURCE_LABEL = "regime_structural"

#: Recognised regime-label sources. A map naming anything else is inadmissible rather than
#: assumed-compatible: an unrecognised label is an unknown assumption, not a benign one.
KNOWN_SOURCE_LABELS = ("regime_structural", "regime_causal")

#: Header fields a map must carry to be admissible for routing. Absence of any one of them
#: is a refusal, not a default — a defaulted provenance field is a fabricated one.
REQUIRED_PROVENANCE_FIELDS = (
    "built_at_utc",
    "built_from_run_id",
    "source_label",
    "labeller_version",
    "code_git_sha",
    "expires_at_utc",
)

#: Environment switch for R1.1. **Default is FROZEN.**
#:
#: Fail-closed applies to writes as well as reads. The map is expected to be EMPTY at the
#: end of Remediation Pass 2 (§7), so a writer that refuses by default is aligned with the
#: intended end state, not an obstacle to it. Un-freezing is a deliberate operator action:
#:
#:     REGIME_MAP_WRITES_FROZEN=false python -m src.vetting.vet --live
#:
#: Note that ``vet`` WITHOUT ``--live`` writes only ``results/reports/proposed_*`` and is
#: unaffected — you can always measure without being able to publish.
_FREEZE_ENV = "REGIME_MAP_WRITES_FROZEN"


class MapWritesFrozen(RuntimeError):
    """Raised when something tries to write the live regime map while writes are frozen."""


def map_writes_frozen() -> bool:
    """True when live regime-map writes are blocked. Defaults to True (frozen)."""
    return os.environ.get(_FREEZE_ENV, "true").strip().lower() not in (
        "false",
        "0",
        "no",
    )


def assert_map_writes_allowed(what: str) -> None:
    """Refuse a live map write while the freeze is on.

    ``what`` names the caller (e.g. ``"vet --live"``) so the refusal says which path was
    blocked rather than merely that something was.
    """
    if map_writes_frozen():
        raise MapWritesFrozen(
            f"{what} refused: live regime-map writes are FROZEN "
            f"({_FREEZE_ENV} is not 'false').\n"
            "The map is frozen for Remediation Pass 2: selection ran on HMM labels while "
            "routing ran on structural ones, so the current map's cells do not correspond "
            "to the conditions that fire them. Rebuilding it before the selection path is "
            "fixed would just produce a differently-wrong map.\n"
            f"To override deliberately: {_FREEZE_ENV}=false <command>"
        )


def git_sha() -> Optional[str]:
    """Current repo HEAD, or None. None is honest; a placeholder string is not."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=_REPO_ROOT, stderr=subprocess.DEVNULL
        )
        return out.decode().strip()
    except Exception:  # noqa: BLE001 - provenance must never break a pipeline
        return None


def provenance_header(
    *,
    run_id: Optional[str],
    source_label: str,
    labeller_version: str,
    built_at: Optional[datetime] = None,
    max_age_days: Optional[float] = None,
) -> Dict[str, Any]:
    """The R1.2 provenance block, to be merged into a map's header.

    ``expires_at_utc`` is stamped by the producer rather than computed by each consumer, so
    every consumer agrees on when the map dies without having to agree on a policy constant.
    """
    built = built_at or datetime.now(timezone.utc)
    age = MAP_MAX_AGE_DAYS if max_age_days is None else max_age_days
    return {
        "built_at_utc": built.isoformat(),
        "built_from_run_id": run_id,
        "source_label": source_label,
        "labeller_version": labeller_version,
        "code_git_sha": git_sha(),
        "expires_at_utc": (built + timedelta(days=age)).isoformat(),
        "max_age_days": age,
    }


def _parse_ts(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp to an aware UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # A naive timestamp is NOT assumed to be UTC. Assuming would silently shift the
    # expiry by the local offset, which on this host would make a dead map look alive.
    return dt if dt.tzinfo is not None else None


def routing_refusals(
    map_obj: Optional[Dict[str, Any]],
    *,
    routing_label: str = ROUTING_SOURCE_LABEL,
    now: Optional[datetime] = None,
) -> List[str]:
    """Reasons this map may NOT be used to route signals. Empty list == admissible.

    Returns *all* reasons rather than the first, so one run's log says everything that is
    wrong with the artifact instead of revealing the defects one deploy at a time.

    Deliberately a pure function of the map object and the clock: it does no I/O, so it is
    fully testable and cannot itself fail open on a network error.
    """
    now = now or datetime.now(timezone.utc)
    reasons: List[str] = []

    if not map_obj:
        return ["map is missing or unparseable"]

    if not map_obj.get("regimes"):
        reasons.append("map carries no 'regimes' block")

    # --- provenance completeness -------------------------------------------------
    missing = [f for f in REQUIRED_PROVENANCE_FIELDS if map_obj.get(f) in (None, "")]
    if missing:
        reasons.append(
            "map is missing required provenance field(s): " + ", ".join(missing)
        )

    # --- label agreement ---------------------------------------------------------
    # The defect this whole module exists for. A map selected under one label and routed
    # under another is not "approximately right"; its cells describe different conditions.
    source_label = map_obj.get("source_label")
    if source_label is None:
        # Already reported as missing above; do not double-report as a mismatch.
        pass
    elif source_label not in KNOWN_SOURCE_LABELS:
        reasons.append(
            f"map source_label {source_label!r} is not a recognised label "
            f"(known: {', '.join(KNOWN_SOURCE_LABELS)})"
        )
    elif source_label != routing_label:
        reasons.append(
            f"map was SELECTED under {source_label!r} but signals are ROUTED under "
            f"{routing_label!r} — the map's cells do not describe the conditions that "
            "would fire them"
        )

    # --- age / expiry ------------------------------------------------------------
    built = _parse_ts(map_obj.get("built_at_utc"))
    if map_obj.get("built_at_utc") and built is None:
        reasons.append(
            f"map built_at_utc {map_obj.get('built_at_utc')!r} is unparseable or "
            "timezone-naive"
        )
    elif built is not None:
        age_days = (now - built).total_seconds() / 86400.0
        if age_days > MAP_MAX_AGE_DAYS:
            reasons.append(
                f"map is {age_days:.1f} days old, over the {MAP_MAX_AGE_DAYS} day limit "
                f"(built {built.isoformat()})"
            )

    expires = _parse_ts(map_obj.get("expires_at_utc"))
    if map_obj.get("expires_at_utc") and expires is None:
        reasons.append(
            f"map expires_at_utc {map_obj.get('expires_at_utc')!r} is unparseable or "
            "timezone-naive"
        )
    elif expires is not None and now >= expires:
        reasons.append(f"map expired at {expires.isoformat()}")

    return reasons
