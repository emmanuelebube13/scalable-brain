"""Push new Gate-1 ledger rows to the telemetry bucket.

Runs as a separate process after ``src.signals.run``, deliberately. The ledger append in
the emission path is local + fsync only, so a GCS outage cannot touch emission *by
construction* rather than by exception handling — which is a stronger guarantee than the
try/except in ``ledger.record`` and the reason the upload does not live in ``run.py``.

**Why ``telemetry/`` and not ``system1/``.** The RFC asked for
``system1/signals/`` with a 90-day deletion policy. Three reasons that prefix is wrong:

1. ``serialize._list_versions`` calls ``storage.list("system1")`` on *every* publish, so a
   growing ledger there adds paginated list cost to the publish path.
2. ``GCSBackend.delete_prefix`` is a raw string-prefix match with no delimiter. A
   lifecycle rule or sweep written against ``system1/`` rather than ``system1/signals/``
   deletes model bundles. Putting a deletion policy inside that namespace invites it.
3. Two frozen, already-sent messages assert to Systems 2/3 that System 1's retention is
   "hard-scoped to the ``system1/`` prefix". ``docs/comms/`` is append-only; a correction
   is a new message, not a quiet contradiction on the bucket.

``telemetry/`` is already the mutable observability namespace (``s1_health.json``,
``s1_model.json``) and carries no retention promise.

**Why one object per upload.** ``put_object`` uploads a whole local file with
``if_generation_match=0`` and raises ``FileExistsError`` if the key exists. There is no
append, no streaming and no compose, and ``atomic_pointer_update`` can only write a single
pretty-printed JSON object — it cannot emit NDJSON. So the ledger cannot be one growing
remote object. Each run uploads only the rows appended since the last successful upload,
under a fresh immutable key, and records its byte offset locally.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.common.storage import build_storage
from src.signals import ledger

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("system1.signals.publish_ledger")

REMOTE_ROOT = "telemetry/signals"

# STATED RETENTION for the remote copy — required by GOVERNANCE.md §1.4, because this is
# written on an hourly cadence. It is stated here and NOT YET ENFORCED: no GCS lifecycle
# rule exists anywhere in this repo, and the machine's `system1-rw` identity is
# storage-scoped, so it may not hold the bucket-admin right needed to set one. Tracked as
# an open item rather than left implicit.
#
# This matters more than it looks: `prune_local()` deletes the local file at 90 days, so
# from day 91 the remote copy is the sole archive of record. An unbounded sole archive is
# not a retention policy, it is the absence of one.
REMOTE_RETENTION_DAYS = 365
REMOTE_RETENTION_ENFORCED = False
STATE_PATH = os.path.join(
    ledger.REPO_ROOT, "results", "state", "ledger_publish_state.json"
)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_PATH):
        return {"offsets": {}}
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            state = json.load(fh)
            state.setdefault("offsets", {})
            return state
    except (OSError, json.JSONDecodeError):
        # A corrupt state file must not silently re-upload the whole history under new
        # keys. Start clean but say so — the operator can decide.
        logger.warning("Unreadable %s — restarting offsets from zero", STATE_PATH)
        return {"offsets": {}}


def _save_state(state: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STATE_PATH), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, STATE_PATH)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _pending(ledger_dir: str, offsets: Dict[str, int]) -> List[Dict[str, Any]]:
    """Per-day byte ranges not yet uploaded. Safe because the ledger is append-only."""
    if not os.path.isdir(ledger_dir):
        return []
    out = []
    for name in sorted(os.listdir(ledger_dir)):
        if not name.endswith(".ndjson"):
            continue
        day = name[: -len(".ndjson")]
        path = os.path.join(ledger_dir, name)
        size = os.path.getsize(path)
        start = int(offsets.get(day, 0))
        if start > size:
            # The file shrank, which append-only forbids — it was truncated or replaced.
            # Re-upload the whole day rather than silently skipping rows.
            logger.warning(
                "%s shrank (offset %d > size %d) — re-uploading the full day",
                path,
                start,
                size,
            )
            start = 0
        if start < size:
            out.append({"day": day, "path": path, "start": start, "end": size})
    return out


def publish(
    ledger_dir: str = ledger.LEDGER_DIR, storage=None, dry_run: bool = False
) -> Dict[str, Any]:
    """Upload every pending byte range. Returns a summary."""
    state = _load_state()
    offsets: Dict[str, int] = state["offsets"]
    pending = _pending(ledger_dir, offsets)
    if not pending:
        logger.info("No new ledger rows to publish.")
        return {"uploaded": [], "rows": 0, "dry_run": dry_run}

    storage = storage or build_storage()
    now = datetime.now(timezone.utc)
    uploaded, total_rows = [], 0

    for item in pending:
        with open(item["path"], "rb") as fh:
            fh.seek(item["start"])
            chunk = fh.read(item["end"] - item["start"])
        rows = chunk.count(b"\n")
        if not rows:
            # A partial final line with no newline: leave the offset where it is and take
            # the row on the next run, once it is complete.
            continue

        # Only whole lines. Anything after the last newline is a row still being written.
        chunk = chunk[: chunk.rfind(b"\n") + 1]
        digest = hashlib.sha256(chunk).hexdigest()
        version = now.strftime("%Y-%m-%dT%H-%M-%SZ") + "-" + digest[:8]
        key = f"{REMOTE_ROOT}/{item['day']}/{version}.ndjson"

        if dry_run:
            logger.info("DRY RUN: would upload %d rows -> %s", rows, key)
            uploaded.append({"key": key, "rows": rows, "day": item["day"]})
            total_rows += rows
            continue

        with tempfile.TemporaryDirectory() as td:
            staged = os.path.join(td, "chunk.ndjson")
            with open(staged, "wb") as fh:
                fh.write(chunk)
            local_sha = _sha256(staged)
            try:
                storage.put_object(key, staged, encrypt=True)
            except FileExistsError:
                # The key is already there. That is NOT a half-upload, and deleting it
                # would destroy a verified object: `put_object` refuses to overwrite, and
                # the version string is second-resolution, so a retry inside the same UTC
                # second regenerates the identical key. The old code called
                # delete_prefix(key) here and removed the very rows it had already
                # round-trip verified.
                #
                # Same content under the same key is a completed upload — verify and
                # advance. Different content is a genuine collision, and the safe move is
                # to abort with the remote object untouched.
                if storage.sha256(key) == local_sha:
                    logger.info("Already uploaded, treating as complete: %s", key)
                else:
                    raise RuntimeError(
                        f"key collision with different content, refusing to overwrite: {key}"
                    )
            except Exception:
                # A genuine mid-upload failure. This key was created by THIS call, so
                # clearing it cannot destroy anyone else's object.
                storage.delete_prefix(key)
                raise
            else:
                # Round-trip verify, same as every other publish path here. A ledger that
                # silently truncated in transit is worse than no ledger: it reads as a
                # complete record of fewer signals.
                if storage.sha256(key) != local_sha:
                    storage.delete_prefix(key)
                    raise RuntimeError(f"round-trip checksum mismatch: {key}")

        # Advance only after a verified upload, so a failure re-sends the same range.
        offsets[item["day"]] = item["start"] + len(chunk)
        uploaded.append(
            {"key": key, "rows": rows, "day": item["day"], "sha256": local_sha}
        )
        total_rows += rows
        logger.info("Published %d ledger rows -> %s", rows, key)

        # Persist after EVERY verified day, not once at the end. `offsets` is a live
        # reference into `state`, and the raise above propagates straight out of this
        # function — so a failure on day 2 used to discard day 1's verified advance, and
        # the next run re-sent day 1 under a new key. That silently duplicated rows in the
        # archive whose row count is meant to answer "what did System 1 decide".
        state["offsets"] = offsets
        state["last_publish_at"] = now.isoformat().replace("+00:00", "Z")
        _save_state(state)

    return {"uploaded": uploaded, "rows": total_rows, "dry_run": dry_run}


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish the Gate-1 signal ledger")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be uploaded; touch neither the bucket nor the offsets.",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help=f"Also delete local ledger files older than {ledger.RETENTION_DAYS} days.",
    )
    args = parser.parse_args()

    result = publish(dry_run=args.dry_run)
    if args.prune and not args.dry_run:
        # Re-read the state AFTER publishing so the cursors include this run's uploads.
        # prune_local refuses to delete a day whose rows have not all shipped.
        result["pruned_local"] = ledger.prune_local(
            uploaded_offsets=_load_state()["offsets"]
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
