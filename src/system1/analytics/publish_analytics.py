"""S1-EXPORT-002 — build + publish the strategy analytics bundle to object storage.

Read-only w.r.t. training and promotion: consumes the live regime→strategy map, the
vetting report, dim tables and OOS trade outcomes; never touches champion files
(FIX-S1-009 — the orchestrator remains the only champion writer).

Publish contract (same as publish_gatekeeper, minus the incumbent gate — analytics has
no "beats incumbent" notion, freshest data wins):
  1. build strategy_catalog.json / trade_returns.json / frequency_stats.json +
     manifest.json (name, bytes, sha256) in a local staging dir
  2. upload to the immutable versioned prefix system1/analytics/<version>/
  3. SHA256 round-trip verify every object BEFORE advancing the pointer
     (mismatch -> delete the partial version, abort, pointer NOT flipped)
  4. archive the superseded pointer to system1/analytics/previous.json
  5. atomic_pointer_update("system1/analytics/latest.json", ...) LAST

Usage:
    python -m src.system1.analytics.publish_analytics            # build + publish
    python -m src.system1.analytics.publish_analytics --dry-run  # build + print manifest only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

from dotenv import load_dotenv

from src.common.db import get_engine
from src.common.storage import build_storage
from src.system1.analytics import catalog as CAT
from src.system1.analytics import extract as EX
from src.system1.analytics import frequency as FREQ
from src.system1.analytics import returns as RET
from src.system1.attribution.attribute import _folds_by_granularity

logger = logging.getLogger("system1.publish_analytics")

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
STAGING_DIR = os.path.join(_REPO_ROOT, "results", "state", "analytics_staging")
REMOTE_ROOT = "system1/analytics"
POINTER_KEY = f"{REMOTE_ROOT}/latest.json"
PREVIOUS_KEY = f"{REMOTE_ROOT}/previous.json"
BUNDLE_FILES = ("strategy_catalog.json", "trade_returns.json", "frequency_stats.json")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, default=str)


def build_bundle(staging_dir: str = STAGING_DIR) -> Dict[str, Any]:
    """Build the three analytics files + manifest into ``staging_dir`` (pure read)."""
    generated_at = datetime.now(timezone.utc).isoformat()
    engine = get_engine()

    tagged = EX.load_tagged_trades(engine)
    folds_by_gran = _folds_by_granularity(tagged)
    asset_symbols = EX.load_asset_symbols(engine)
    strategy_dim = EX.load_strategy_dim(engine)
    occupancy = EX.load_regime_occupancy(engine)
    regime_map = EX.load_regime_strategy_map()
    vetting_report = EX.load_vetting_report(regime_map.get("qualification_run_id", ""))
    approval_rate = EX.load_gatekeeper_approval_rate()

    cells = RET.qualified_cells(regime_map)
    granularities_by_sid = {
        int(sid): sorted(g["granularity"].unique())
        for sid, g in tagged.groupby("strategy_id")
    }

    payloads = {
        "strategy_catalog.json": CAT.build_catalog(
            strategy_dim, regime_map, vetting_report, granularities_by_sid, generated_at
        ),
        "trade_returns.json": RET.build_trade_returns(
            tagged, cells, asset_symbols, folds_by_gran
        ),
        "frequency_stats.json": FREQ.build_frequency_stats(
            tagged, cells, asset_symbols, occupancy, approval_rate
        ),
    }

    os.makedirs(staging_dir, exist_ok=True)
    manifest_files = []
    for name in BUNDLE_FILES:
        path = os.path.join(staging_dir, name)
        _write_json(path, payloads[name])
        manifest_files.append(
            {"name": name, "bytes": os.path.getsize(path), "sha256": _sha256(path)}
        )
    manifest = {
        "schema_version": "1",
        "generated_at_utc": generated_at,
        "qualification_run_id": regime_map.get("qualification_run_id"),
        "files": manifest_files,
    }
    _write_json(os.path.join(staging_dir, "manifest.json"), manifest)
    logger.info(
        "Bundle staged in %s: %s",
        staging_dir,
        {f["name"]: f["bytes"] for f in manifest_files},
    )
    return manifest


def publish(staging_dir: str = STAGING_DIR, storage=None) -> Dict[str, Any]:
    """Upload the staged bundle: verify SHA256 round-trip, then flip the pointer LAST."""
    manifest_path = os.path.join(staging_dir, "manifest.json")
    local = {name: os.path.join(staging_dir, name) for name in BUNDLE_FILES}
    local["manifest.json"] = manifest_path
    missing = [p for p in local.values() if not os.path.exists(p)]
    if missing:
        raise SystemExit(f"missing staged file(s): {missing} — run build_bundle first")

    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)

    storage = storage or build_storage()
    version = (
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
        + "-"
        + _sha256(manifest_path)[:8]
    )
    remote_prefix = f"{REMOTE_ROOT}/{version}"
    local_sha = {name: _sha256(p) for name, p in local.items()}
    logger.info("publishing analytics bundle -> %s", remote_prefix)
    try:
        for name, p in local.items():
            storage.put_object(f"{remote_prefix}/{name}", p, encrypt=True)
        for name in local:
            if storage.sha256(f"{remote_prefix}/{name}") != local_sha[name]:
                raise RuntimeError(f"round-trip checksum mismatch: {name}")
    except Exception:
        storage.delete_prefix(remote_prefix)  # never leave a half-uploaded version
        raise

    if storage.exists(POINTER_KEY):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            prev_path = os.path.join(td, "latest.json")
            storage.get_object(POINTER_KEY, prev_path)
            with open(prev_path, encoding="utf-8") as fh:
                storage.atomic_pointer_update(PREVIOUS_KEY, json.load(fh))

    pointer = {
        "artifact": "system1-analytics",
        # Same consumer rule as the model set (S2-REPLY-2026-08-15 §4.1): anything other
        # than "published" is a REJECT downstream. Stated explicitly so the two artefacts
        # obey one rule rather than two.
        "status": "published",
        "version": version,
        "path": f"{remote_prefix}/",
        "manifest_sha256": local_sha["manifest.json"],
        "qualification_run_id": manifest.get("qualification_run_id"),
        "generated_at_utc": manifest.get("generated_at_utc"),
        "published_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    storage.atomic_pointer_update(POINTER_KEY, pointer)
    logger.info("analytics pointer flipped -> %s", version)
    return pointer


def run(dry_run: bool = False) -> Dict[str, Any]:
    manifest = build_bundle()
    if dry_run:
        print(json.dumps(manifest, indent=2))
        return manifest
    pointer = publish()
    print(json.dumps(pointer, indent=2))
    return pointer


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish the S1 strategy analytics bundle"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Build + stage locally; do not upload."
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    load_dotenv(os.path.join(_REPO_ROOT, ".env"))
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
