"""Reconcile the emitter's cumulative counters against the signal ledger.

``results/state/signal_emitter_state.json`` holds System 1's lifetime counters —
``signals_published_total`` above all, the number quoted to Systems 2 and 3 and printed
in every status document. They are maintained **incrementally**: each run reads the
previous file and adds this run's delta. That design has one failure mode and it is not
theoretical.

**What happened on 2026-09-11.** Between 05:15:57Z and 14:07:04Z every cumulative total
in the file went to zero — ``signals_published_total`` 63 -> 0, ``signals_scored_total``
21 -> 0, ``shadow_would_refuse_total`` 20 -> 0, ``dlq_count_total`` 0 -> null — while
``last_signal_emitted_at`` stayed at ``2026-09-04T21:15:44Z``. That combination is
**not reachable from ``record_emitter_state``**: every total is written as
``prev.get(key, 0) + delta``, the dlq totals have an explicit ``setdefault`` carry-forward,
and the one path that discards ``prev`` (the unreadable-file self-heal) also blanks
``last_signal_emitted_at`` and logs an ERROR — no such line exists in any log. Verified by
replaying the pre-reset file through ``record_emitter_state("risk_off")``: all five fields
survive unchanged. The tests are isolated (``test_run_once_never_writes_the_live_emitter_state``
exists precisely for this) and no shell script touches the file. So the totals were
overwritten out of band — a hand edit of a machine-written artifact — and **nothing
noticed**, because an incrementally-maintained integer has no other copy to disagree with.

This module gives it one. The ledger under ``results/signals/`` is one durable NDJSON row
per candidate at every gatekeeper exit, so the counters become **derivable** rather than
only accumulated: a lost total is repaired by running something, not by typing a number
back in — which is the same class of edit that caused the loss.

**The ledger has an epoch, and pretending otherwise would silently shrink the count.** It
began on 2026-08-30 (commit ``51ec34a``); ``signals_published_total`` stood at 49 then, and
those 49 emissions have no rows. A pure ledger rebuild would produce 14, not 63, and would
look authoritative. ``LEDGER_EPOCH_BASELINE`` below carries the pre-ledger counts
explicitly so the arithmetic is visible: 49 + 14 = 63, which is exactly the value that was
destroyed.

**Counter and ledger are related, not identical, and the difference is real.** A ledger row
is written *before* the publish call, from the intent to publish; the counter is advanced
*after* it, from ``producer.publish_signals()``'s reported ``published_count``. They
diverge in both directions for different reasons (O-21): a mid-run crash between the
ledger append and ``record_emitter_state`` leaves rows no counter ever saw, and a failed
ledger append still increments the tally, because emission is never blocked on the audit
trail. So this module **reports** the gap and treats the ledger as a floor; it does not
assert equality. Today the two agree exactly.

Pruning is the other reason the ledger is a floor and not a truth:
``publish_ledger --prune`` deletes local rows past 90 days (O-19), after which
``baseline + ledger`` under-counts by however much was pruned. ``repair`` therefore only
ever raises a counter, never lowers one.

Usage::

    python -m src.signals.reconcile            # report only (default)
    python -m src.signals.reconcile --repair   # rewrite the cumulative totals
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

from src.signals.ledger import LEDGER_DIR

logger = logging.getLogger("system1.signals.reconcile")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EMITTER_STATE = os.path.join(REPO_ROOT, "results", "state", "signal_emitter_state.json")

# The ledger's first day. Rows before this do not exist, so the counters cannot be
# reconstructed from the ledger alone below this date.
LEDGER_EPOCH = "2026-08-30"

# Counter values as they stood immediately before the ledger's first row, so
# `baseline + ledger` reproduces the lifetime figure instead of the post-epoch one.
#
# Provenance: `results/state/signal_emitter_state.json` at commit `51ec34a` (2026-08-30,
# "Gate-1 signal ledger"), which is the commit that created the ledger. Corroborated at
# the far end for the emissions it covers — Cloud Monitoring
# `pubsub.googleapis.com/topic/send_message_operation_count` on `scored_signal_queue`
# (see docs/critical/REPO_STATE.md). The scored/unscored/dropped and shadow_* counters
# were introduced by that same commit, so their pre-ledger baseline is genuinely 0 rather
# than unknown.
LEDGER_EPOCH_BASELINE: Dict[str, int] = {
    "signals_published_total": 49,
    "signals_scored_total": 0,
    "signals_unscored_total": 0,
    "signals_dropped_total": 0,
    "shadow_would_pass_total": 0,
    "shadow_would_refuse_total": 0,
}

# counter name -> (ledger field, accepted values). One row contributes to a counter when
# its field holds one of the listed values.
_LEDGER_RULES = {
    "signals_published_total": ("wire_action", {"published"}),
    "signals_scored_total": ("gate1_outcome", {"scored"}),
    "signals_unscored_total": ("gate1_outcome", {"unscored", "unknown_status"}),
    "signals_dropped_total": ("gate1_outcome", {"dropped_corrupt_feature"}),
    "shadow_would_pass_total": ("shadow_verdict", {"would_pass"}),
    "shadow_would_refuse_total": ("shadow_verdict", {"would_refuse"}),
}


def tally_ledger(ledger_dir: str = LEDGER_DIR) -> Dict[str, Any]:
    """Count ledger rows into the emitter-state counter vocabulary.

    Unparseable lines are counted, never skipped silently: a truncated NDJSON tail is
    exactly the situation where an under-count would be mistaken for a lost counter.
    """
    counts = {name: 0 for name in _LEDGER_RULES}
    rows = 0
    bad_lines = 0
    days: List[str] = []
    for path in sorted(glob.glob(os.path.join(ledger_dir, "*.ndjson"))):
        days.append(os.path.basename(path)[: -len(".ndjson")])
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    bad_lines += 1
                    continue
                rows += 1
                for name, (field, accepted) in _LEDGER_RULES.items():
                    if row.get(field) in accepted:
                        counts[name] += 1
    return {
        "counts": counts,
        "rows": rows,
        "bad_lines": bad_lines,
        "days": days,
        "first_day": days[0] if days else None,
        "last_day": days[-1] if days else None,
    }


def _floors(ledger_counts: Dict[str, int]) -> Dict[str, int]:
    """``LEDGER_EPOCH_BASELINE + ledger`` — the floor each counter must not sit below.

    The single definition of the floor. ``reconcile`` and ``expected_totals`` both go
    through it rather than each doing the arithmetic, so the two can never disagree about
    what "expected" means.
    """
    return {
        name: LEDGER_EPOCH_BASELINE.get(name, 0) + ledger_counts.get(name, 0)
        for name in _LEDGER_RULES
    }


def expected_totals(ledger_dir: str = LEDGER_DIR) -> Dict[str, int]:
    """The floors, read straight from the ledger on disk."""
    return _floors(tally_ledger(ledger_dir)["counts"])


def _read_state(state_path: str) -> Dict[str, Any]:
    if not os.path.exists(state_path):
        return {}
    try:
        with open(state_path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Emitter state at %s is unreadable: %s", state_path, exc)
        return {}


def reconcile(
    state_path: str = EMITTER_STATE, ledger_dir: str = LEDGER_DIR
) -> Dict[str, Any]:
    """Compare the persisted counters against ``baseline + ledger``.

    Two kinds of finding, kept apart because they mean different things:

    ``shortfalls``
        A counter sitting BELOW the floor. The ledger is evidence those emissions
        happened, so the counter has lost history. This is the 2026-09-11 shape.

    ``surpluses``
        A counter ABOVE the floor. Expected and usually benign — pruned ledger days
        (O-19) and publishes whose ledger append failed (O-21) both land here. Reported
        so a large or sudden one is visible, never treated as an error.

    ``inconsistencies`` carries the cross-field invariant that needs no ledger at all:
    a non-null ``last_signal_emitted_at`` asserts a signal was published, so a zero
    ``signals_published_total`` beside it contradicts the file's own record.
    """
    state = _read_state(state_path)
    led = tally_ledger(ledger_dir)
    expected = _floors(led["counts"])

    shortfalls: List[Dict[str, Any]] = []
    surpluses: List[Dict[str, Any]] = []
    for name, floor in expected.items():
        actual = state.get(name)
        actual = 0 if actual is None else int(actual)
        if actual < floor:
            shortfalls.append(
                {
                    "counter": name,
                    "actual": actual,
                    "expected_floor": floor,
                    "baseline": LEDGER_EPOCH_BASELINE.get(name, 0),
                    "ledger": led["counts"].get(name, 0),
                    "lost": floor - actual,
                }
            )
        elif actual > floor:
            surpluses.append(
                {
                    "counter": name,
                    "actual": actual,
                    "expected_floor": floor,
                    "excess": actual - floor,
                }
            )

    inconsistencies: List[str] = []
    emitted_at = state.get("last_signal_emitted_at")
    published_total = state.get("signals_published_total")
    if emitted_at and not published_total:
        inconsistencies.append(
            f"last_signal_emitted_at is {emitted_at} but signals_published_total is "
            f"{published_total!r} — the file contradicts itself: a signal cannot have "
            "been emitted by a producer that has published nothing"
        )
    if led["bad_lines"]:
        inconsistencies.append(
            f"{led['bad_lines']} unparseable ledger line(s) — the ledger tally is a "
            "lower bound on its own terms"
        )

    return {
        "state_path": state_path,
        "ledger_dir": ledger_dir,
        "ledger": led,
        "expected": expected,
        "actual": {
            name: (0 if state.get(name) is None else int(state[name]))
            for name in _LEDGER_RULES
        },
        "shortfalls": shortfalls,
        "surpluses": surpluses,
        "inconsistencies": inconsistencies,
        "ok": not shortfalls and not inconsistencies,
    }


def repair(
    state_path: str = EMITTER_STATE, ledger_dir: str = LEDGER_DIR
) -> Dict[str, Any]:
    """Raise every short counter to ``baseline + ledger``. Never lowers one.

    Monotonic on purpose. A counter above the floor may be correct history the ledger
    cannot see — pruned days, or a publish whose ledger append failed — and lowering it
    to match would destroy exactly the kind of record this module exists to protect.

    Only the cumulative totals are touched. ``last_run_*``, ``last_signal_emitted_at``,
    ``consecutive_faults`` and the rest describe a specific run and are none of this
    module's business; they are written back byte-identical.
    """
    report = reconcile(state_path, ledger_dir)
    if not report["shortfalls"]:
        logger.info("Nothing to repair — no counter sits below its floor.")
        return {"repaired": [], "report": report}

    state = _read_state(state_path)
    if not state:
        raise RuntimeError(
            f"refusing to repair {state_path}: it is missing or unreadable, so the "
            "run-level fields cannot be preserved"
        )

    repaired = []
    for item in report["shortfalls"]:
        name = item["counter"]
        state[name] = item["expected_floor"]
        repaired.append(item)
        logger.warning(
            "Repaired %s: %d -> %d (%d baseline + %d ledger)",
            name,
            item["actual"],
            item["expected_floor"],
            item["baseline"],
            item["ledger"],
        )

    # Same atomic write as record_emitter_state, and for the same reason: a crash
    # mid-write leaves a truncated file, and the next run's `prev.get(key, 0)` reads that
    # as zero. Repairing the counters non-atomically would be able to cause the defect it
    # is repairing.
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(state_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    try:
        os.replace(tmp, state_path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise

    return {"repaired": repaired, "report": report}


def render(report: Dict[str, Any]) -> str:
    led = report["ledger"]
    lines = [
        "Emitter counter reconciliation",
        f"  ledger   : {led['rows']} rows over {len(led['days'])} day(s) "
        f"({led['first_day']} .. {led['last_day']})",
        f"  epoch    : {LEDGER_EPOCH} — rows before this do not exist",
        "",
        f"  {'counter':<28} {'actual':>8} {'floor':>8} {'baseline':>9} {'ledger':>8}",
    ]
    for name in _LEDGER_RULES:
        lines.append(
            f"  {name:<28} {report['actual'][name]:>8} {report['expected'][name]:>8} "
            f"{LEDGER_EPOCH_BASELINE.get(name, 0):>9} {led['counts'][name]:>8}"
        )
    lines.append("")
    for item in report["shortfalls"]:
        lines.append(
            f"  SHORTFALL  {item['counter']}: {item['actual']} < {item['expected_floor']} "
            f"({item['lost']} lost)"
        )
    for item in report["surpluses"]:
        lines.append(
            f"  surplus    {item['counter']}: {item['actual']} > "
            f"{item['expected_floor']} (+{item['excess']}; pruned ledger days or a "
            "failed ledger append both land here)"
        )
    for msg in report["inconsistencies"]:
        lines.append(f"  INCONSISTENT  {msg}")
    if report["ok"]:
        lines.append("  OK — no counter sits below its floor.")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile emitter counters against the signal ledger"
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="raise short counters to baseline + ledger (never lowers one). "
        "Report-only without this flag.",
    )
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    if args.repair:
        result = repair()
        report = reconcile()
    else:
        result = None
        report = reconcile()

    if args.json:
        print(
            json.dumps(
                {"report": report, "repaired": (result or {}).get("repaired")},
                indent=2,
                default=str,
            )
        )
    else:
        print(render(report))
        if result and result["repaired"]:
            print(f"\nRepaired {len(result['repaired'])} counter(s).")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
