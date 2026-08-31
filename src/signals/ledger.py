"""Gate-1 signal ledger — one durable row per candidate at every GATEKEEPER exit.

**Scope, stated precisely, because the obvious reading is wrong.** This records what the
gatekeeper did to a fully-formed signal. It does NOT record what System 1 decided not to
build. ``build_signals`` discards candidates at roughly a dozen points before this module
ever sees them — no structural regime, unknown ``selection_basis``, an
``INTEGRITY_DISQUALIFIED`` strategy, no stop declared, no take-profit declared, **no ATR
available**, an undecodable direction, and a bare ``except`` around each (bar × strategy)
unit. Several of those are genuine decisions not to emit a would-be trade, and they leave
no row here, because ``signal_id`` is only minted at the end of that function — after
every one of those discards. The no-ATR path in particular is recorded in ``build.py`` as
having once dropped 100% of signals silently, and it is still unledgered.

Closing that gap means minting the id earlier, which is a change to ``build_signals`` and
its own piece of work. Until then: **absence of a row is not evidence a candidate never
existed.**


System 1 kept no per-signal record. The only durable trace of an emission was two
integers in ``results/state/signal_emitter_state.json`` plus the Pub/Sub message itself,
and a signal the gatekeeper dropped left a single ``logger.warning`` with no
``signal_id`` — unrecoverable the moment the log rotated. That made two questions
unanswerable: *what did System 1 decide, and on what basis?* and *what is the denominator
of the approval rate?*

This module answers the first. It does NOT answer the second, and the distinction
matters enough to state here rather than in a doc nobody opens:

**There is no approval decision to record yet.** ``Scorer.score()`` returns
``{status, score}`` and never compares that score to a threshold; ``run.py`` stamps a
hardcoded ``threshold_applied = 0.5`` while the champion's calibrated per-regime
thresholds (0.60-0.80) sit unread in ``models/champion_manifest.json``. Every scored
signal is published regardless of score, and the only true drop is ``NAN_FEATURE``.
Separately, ``MISSING_FEATURE`` applies to every live signal because the champion trains
on ``fact_market_regime_v2`` columns written retrospectively, which a live bar has no row
in. So the honest outcome vocabulary here is ``scored`` / ``unscored`` /
``dropped_corrupt_feature`` — NOT ``approved`` / ``refused``. Writing the latter would
claim a decision the system does not make, which is the FIX-S1-016 status-conflation
defect rebuilt one layer up. ``threshold_calibrated`` is recorded alongside the
hardcoded ``threshold_applied`` precisely so the gap is measurable from the data rather
than argued from code; that gap is FIX-S1-018.

Format is NDJSON, one file per UTC day under ``results/signals/``. Append-only, so the
``os.replace`` staging used elsewhere in this repo is the wrong tool — the durability
primitive is ``flush()`` + ``fsync()``, copied from
``src/common/queue/local_durable.py``, which has held the queue log since FND-002.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import sys
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("system1.signals.ledger")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LEDGER_DIR = os.path.join(REPO_ROOT, "results", "signals")

SCHEMA_VERSION = "1"

# Retention is stated in results/README.md and enforced by prune_local(). Anything written
# on a cadence needs a stated retention (GOVERNANCE.md 1.4); the ~600-file
# results/state/retrain_log_*.json pile is what happens without one.
RETENTION_DAYS = 90

# The full outcome vocabulary. Deliberately does not contain "approved"/"refused" — see
# the module docstring.
GATE1_OUTCOMES = ("scored", "unscored", "dropped_corrupt_feature", "unknown_status")

# What System 1 DID with the candidate. Note the limit of the claim: `published` means
# "handed to the producer", not "accepted by the broker". The producer dead-letters
# individual messages after this row is written — BUILD_ERROR, SCHEMA_INVALID, QUEUE_FULL,
# PUBLISH_NACK — and counts idempotent replays as deduped, none of which reach the wire.
# So a `published` row with no matching ams_decision_log entry means EITHER a lost message
# OR a DLQ, and the two are separated by the run's dlq_count, not by this field.
# `suppressed` exists because DISABLE_LEGACY_SIGNALS=true would otherwise make every row
# in the run claim `published` when nothing was sent at all.
WIRE_ACTIONS = ("published", "dropped", "suppressed")

_write_lock = threading.Lock()


def ledger_path(when: Optional[datetime] = None, ledger_dir: str = LEDGER_DIR) -> str:
    """Path to the ledger for ``when``'s UTC day.

    One file per day rather than per run: the hourly cadence would otherwise produce
    ~8,760 files a year in one directory, which is the state results/state/ is already in
    and the reason nobody notices a new file appearing there.
    """
    day = (when or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    return os.path.join(ledger_dir, f"{day}.ndjson")


@functools.lru_cache(maxsize=4)
def champion_model_sha256(models_dir: str) -> Optional[str]:
    """SHA256 of the model file the Scorer actually loaded.

    NOT the ``bundle_id`` the wire carries. Those are two different claims and they are
    currently disagreeing: the live scorer loads ``models/champion_model.pkl`` from the
    working directory, while ``build_message`` stamps ``bundle_id`` from the *backend*
    pointer. A non-dry-run local train silently becomes the live scoring model without
    ever being published, and nothing downstream can tell. Recording both is what makes
    that visible.

    Cached because it is a per-run constant and hashing a 235 KB pickle per signal is
    waste.
    """
    path = os.path.join(models_dir, "champion_model.pkl")
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError as e:
        logger.warning("Could not hash champion model at %s: %s", path, e)
        return None


@functools.lru_cache(maxsize=4)
def _dynamic_thresholds(models_dir: str) -> Dict[str, float]:
    """The champion's calibrated per-regime thresholds, read for the record only.

    This module reads them; the live path still does not apply them. Recording the value
    that *should* have been applied next to the one that was is the evidence for
    FIX-S1-018 — it turns "the gate is inert" from a code reading into a measurement.
    """
    path = os.path.join(models_dir, "champion_manifest.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return dict(json.load(fh).get("dynamic_thresholds") or {})
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Could not read dynamic_thresholds from %s: %s", path, e)
        return {}


def calibrated_threshold(models_dir: str, regime: Optional[str]) -> Optional[float]:
    """The threshold this regime *would* use, mirroring train.py's fallback rule."""
    thresholds = _dynamic_thresholds(models_dir)
    if not thresholds:
        return None
    value = thresholds.get(str(regime), thresholds.get("fallback"))
    return float(value) if value is not None else None


def build_record(
    signal: Dict[str, Any],
    *,
    gate1_outcome: str,
    wire_action: str,
    score_run_id: str,
    models_dir: str,
    refusal_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble one ledger row from a signal dict at its decision point.

    Pure: no I/O beyond the two cached model-artifact reads, so it is directly testable.
    """
    if gate1_outcome not in GATE1_OUTCOMES:
        raise ValueError(f"unknown gate1_outcome: {gate1_outcome!r}")
    if wire_action not in WIRE_ACTIONS:
        raise ValueError(f"unknown wire_action: {wire_action!r}")

    score = signal.get("model_score")
    regime = signal.get("regime")

    # SHADOW MODE (owner decision 2026-08-30): the calibrated threshold is recorded but
    # NOT applied — live routing stays permissive. These three fields are what makes the
    # shadow rejection rate computable, so the pairing has to be exactly right.
    #
    # The threshold must be keyed on the SAME label the model consumed. train.py maps
    # `regime_structural` to the threshold, and `regime_structural` is what the scorer was
    # fed. `signal["regime"]` is a different field: the routing label, computed from the
    # newest D1 close at the start of the run, whereas `regime_structural` is computed as
    # of this signal's bar. With the market shut they are identical for every instrument
    # (measured 2026-08-30: 15/15 agree), which is precisely why keying on the wrong one
    # would not show up until live traffic — and by then a week of shadow data would be
    # quietly mispaired. Key on what the model saw; fall back only if it is absent.
    regime_structural = signal.get("regime_structural")
    threshold_key = regime_structural if regime_structural is not None else regime
    threshold_calibrated = calibrated_threshold(models_dir, threshold_key)

    # Evaluated at write time, against the threshold in force at this moment. Recomputing
    # it later from the row would silently use whatever manifest is current then — wrong if
    # a champion is promoted mid-window, which is exactly what a 7-day study invites.
    # This is an OBSERVATION, never an action: `wire_action` above is what actually
    # happened, and it is unaffected by this field.
    if score is None or threshold_calibrated is None:
        shadow_verdict = None
    else:
        shadow_verdict = (
            "would_pass" if float(score) >= threshold_calibrated else "would_refuse"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        # uuid5 over (strategy_id, instrument, granularity, bar_ts) — minted in
        # build_signals() BEFORE the scorer runs, which is what lets a dropped candidate
        # be recorded at all. Note it does NOT include model_set_id, so a re-run against a
        # different model set on the same bar reuses the id; score_run_id below is what
        # separates those two rows.
        "signal_id": str(signal["signal_id"]),
        "score_run_id": score_run_id,
        "logged_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "signal_time_utc": signal.get("signal_time_utc"),
        # `pair` on the wire, `instrument` internally. Use the wire name so the ledger
        # joins to ams_decision_log without a translation step.
        "pair": signal.get("pair", signal.get("instrument")),
        # long/short, per contracts/signal-message-contract.json (additionalProperties is
        # false, so BUY/SELL would dead-letter the message it describes).
        "direction": signal.get("direction"),
        "strategy_id": signal.get("strategy_id"),
        "strategy_key": signal.get("strategy_key"),
        "regime": regime,
        "granularity": signal.get("granularity"),
        "selection_basis": signal.get("selection_basis"),
        "gate1_outcome": gate1_outcome,
        "wire_action": wire_action,
        "scoring_status": "scored" if score is not None else "unscored",
        # The full reason string, e.g. "NAN_FEATURE:atr_value" or
        # "MISSING_FEATURE:regime_causal". The prefix is the category; the suffix names
        # the field, and that suffix is the whole diagnostic value.
        "refusal_reason": refusal_reason,
        # NULL means unscored, never "scored zero" (ScoredSignal v1). Never coerce.
        "model_score": float(score) if score is not None else None,
        "threshold_applied": (
            float(signal["threshold_applied"])
            if signal.get("threshold_applied") is not None
            else None
        ),
        # What the manifest says SHOULD apply. Recorded, not enforced — see shadow mode
        # above. `threshold_regime_key` names the label it was looked up by, so the
        # pairing is auditable from the row alone rather than assumed.
        "threshold_calibrated": threshold_calibrated,
        "threshold_regime_key": threshold_key,
        "regime_structural": regime_structural,
        "shadow_verdict": shadow_verdict,
        "gatekeeper_model_sha256": champion_model_sha256(models_dir),
        "bundle_id": signal.get("model_set_id"),
        "proposed_entry": signal.get("entry"),
        "proposed_sl": signal.get("stop"),
        "proposed_tp": signal.get("target"),
        "atr": signal.get("atr"),
    }


def append(record: Dict[str, Any], ledger_dir: str = LEDGER_DIR) -> str:
    """Append one row, durably. Returns the file written.

    Guarded against pytest writing the production ledger, the same way
    LocalDurableBackend guards the production queue path — a test suite that stamps rows
    into the live audit trail corrupts the very record this exists to be.
    """
    if "pytest" in sys.modules and os.path.abspath(ledger_dir) == os.path.abspath(
        LEDGER_DIR
    ):
        raise RuntimeError(
            "Tests cannot write to the production ledger path — pass a tmp_path ledger_dir"
        )

    path = ledger_path(ledger_dir=ledger_dir)
    line = json.dumps(record, sort_keys=True, default=str)
    with _write_lock:
        os.makedirs(ledger_dir, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())  # durable before the message goes anywhere
    return path


def record(
    signal: Dict[str, Any],
    *,
    gate1_outcome: str,
    wire_action: str,
    score_run_id: str,
    models_dir: str,
    refusal_reason: Optional[str] = None,
    ledger_dir: str = LEDGER_DIR,
) -> Optional[Dict[str, Any]]:
    """Build and append one row, never raising. Returns the row, or None if it failed.

    The return value is what lets the caller tally `shadow_verdict` without rebuilding the
    record or re-reading the manifest. Returning None on failure is deliberate: a row that
    was not written must not be counted, or the shadow rate would include rows that are
    not in the ledger backing it.

    Owner decision: a ledger failure must not block emission. The cost is stated rather
    than hidden — a signal that reaches the wire but not the ledger is NOT detectable
    from the counters, so the denominator can silently under-count. Logged at ERROR with
    the signal_id so the row is at least reconstructable from the log.
    """
    try:
        row = build_record(
            signal,
            gate1_outcome=gate1_outcome,
            wire_action=wire_action,
            score_run_id=score_run_id,
            models_dir=models_dir,
            refusal_reason=refusal_reason,
        )
        append(row, ledger_dir=ledger_dir)
        return row
    except Exception as e:  # noqa: BLE001 - emission must survive a ledger fault
        logger.error(
            "LEDGER WRITE FAILED for signal_id=%s (%s/%s): %s — signal not recorded",
            signal.get("signal_id"),
            gate1_outcome,
            wire_action,
            e,
        )
        return None


def read_day(day: str, ledger_dir: str = LEDGER_DIR) -> list:
    """Read one day's rows. Used by publish_ledger and by tests."""
    path = os.path.join(ledger_dir, f"{day}.ndjson")
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                # A torn final line is possible if the process died mid-write. Skip it
                # loudly rather than failing the whole read — the other rows are intact,
                # which is the point of an append-only format.
                logger.warning("Skipping malformed ledger line %s:%d", path, n)
    return rows


def prune_local(
    retention_days: int = RETENTION_DAYS,
    ledger_dir: str = LEDGER_DIR,
    uploaded_offsets: Optional[Dict[str, int]] = None,
) -> int:
    """Delete local ledger files past retention that are FULLY uploaded. Returns count.

    ``uploaded_offsets`` is the publisher's per-day byte cursor. A day is only deletable
    once its cursor has reached the file size — otherwise pruning would destroy the last
    copy of rows that never shipped. Without that check a day whose upload failed for 90
    days is silently deleted with nothing remote to show for it, which is the opposite of
    what an audit trail is for. Pass ``{}`` to prune nothing.
    """
    if not os.path.isdir(ledger_dir):
        return 0
    offsets = uploaded_offsets if uploaded_offsets is not None else {}
    cutoff = datetime.now(timezone.utc).timestamp() - retention_days * 86400
    removed = 0
    for name in sorted(os.listdir(ledger_dir)):
        if not name.endswith(".ndjson"):
            continue
        path = os.path.join(ledger_dir, name)
        day = name[: -len(".ndjson")]
        try:
            if os.path.getmtime(path) >= cutoff:
                continue
            size = os.path.getsize(path)
            if int(offsets.get(day, 0)) < size:
                logger.warning(
                    "Not pruning %s: only %d of %d bytes are uploaded. The local copy is "
                    "the only one that has these rows.",
                    path,
                    int(offsets.get(day, 0)),
                    size,
                )
                continue
            os.unlink(path)
            removed += 1
        except OSError as e:
            logger.warning("Could not prune %s: %s", path, e)
    return removed
