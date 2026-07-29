"""D6 — publish per-strategy risk statistics for System 3.

Writes a SELF-CONTAINED document (not a pointer) to a fixed key:

    risk/strategy_stats/latest.json

    {
      "produced_at": "<iso8601>",
      "checksum":    "<sha256 over the strategies map only>",
      "strategies": {"<id>": {"win_rate", "avg_win", "avg_loss", "expectancy"}}
    }

``checksum`` is ``sha256(json.dumps(strategies, sort_keys=True, separators=(",",":")))``
— over the ``strategies`` map ONLY, so it is invariant to how the enclosing document is
formatted. System 3 recomputes it from the parsed map and rejects on mismatch. This was
verified against the pre-existing hand-seeded object, whose checksum this recipe
reproduces exactly.

Publish ordering (the MODEL-007 contract, applied to a content document):

  1. compute the checksum + the artifact's SHA256 locally
  2. upload to an immutable versioned key ``risk/strategy_stats/<version>/strategy_stats.json``
  3. round-trip verify that uploaded object's SHA256 against the local value
  4. **only then** write the live ``latest.json``
  5. on ANY mismatch: delete the partial version, abort, and leave the previous
     ``latest.json`` byte-for-byte untouched

The upload-then-verify step cannot be performed against ``latest.json`` itself: writing
to the live key IS going live, so a post-hoc verification there would already have exposed
consumers to a corrupt document. Staging to a versioned key first is what makes
"abort and leave the previous latest.json untouched" achievable at all. The versioned
copies also give System 3 a rollback target.

UNITS — read before changing anything here
------------------------------------------
Values are **R-multiples** (profit/loss as a multiple of the amount risked), because
``fact_trade_outcomes.r_multiple`` is the only P/L representation System 1 stores; there
is no currency or pip column in the schema. ``avg_win`` is therefore ~1.0, not ~40.

The hand-seeded paper prior this replaced used a currency/pip scale
(``avg_win: 40.0, avg_loss: 30.0``). Anything downstream that multiplies these values by
a position size will behave ~40x differently against R-multiples. Converting R to
currency requires account equity and risk-per-trade, both of which are System 3's to own
(System 1 emits weights and R, never sizes) — so the conversion belongs there, not here.
``unit`` is stamped in the document so a consumer can assert on it rather than assume.

``avg_loss`` is a POSITIVE magnitude, matching the seed's convention and preserving the
identity ``expectancy == win_rate*avg_win - (1-win_rate)*avg_loss``.

Usage:
    python -m src.system1.analytics.publish_strategy_stats --dry-run   # print, no writes
    python -m src.system1.analytics.publish_strategy_stats             # publish
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
from sqlalchemy import text

from src.common.db import get_engine
from src.common.storage import build_storage

logger = logging.getLogger("system1.strategy_stats")

SCHEMA_VERSION = "1"
REMOTE_ROOT = "risk/strategy_stats"
POINTER_KEY = f"{REMOTE_ROOT}/latest.json"
ARTIFACT_NAME = "strategy_stats.json"
UNIT = "r_multiple"
# Gate metrics are OOS-only everywhere else in System 1 (Axiom 1: only out-of-sample
# survival is evidence). Risk parameters feeding System 3 are held to the same standard —
# in-sample stats would overstate the edge System 3 sizes against.
OOS_ONLY = True
MIN_TRADES = 1

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
STAGING_DIR = os.path.join(_REPO_ROOT, "results", "state", "strategy_stats_staging")


class StrategyStatsRefused(Exception):
    """Raised when the document cannot be produced or verified (never publishes)."""


def canonical_checksum(strategies: Dict[str, Dict[str, float]]) -> str:
    """``sha256`` over the strategies map in canonical JSON — the System 3 contract.

    Canonical form is ``sort_keys=True, separators=(",",":")``: no whitespace, stable key
    order. Computing it over the map ALONE (not the whole document) is what lets the
    enclosing file be pretty-printed, re-serialized, or gain metadata keys without
    invalidating the integrity check.
    """
    blob = json.dumps(strategies, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_trades(engine) -> pd.DataFrame:
    sql = "SELECT strategy_id, is_winner, r_multiple, is_oos FROM fact_trade_outcomes"
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    df["is_oos"] = df["is_oos"].fillna(False).astype(bool)
    return df


def compute_stats(trades: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Per-strategy {win_rate, avg_win, avg_loss, expectancy} in R-multiples.

    ``avg_win`` is the mean of positive R, ``avg_loss`` the mean ABSOLUTE value of
    negative R (positive magnitude). A strategy with no wins (or no losses) reports 0.0
    for that leg rather than NaN, so the document is always numerically valid JSON —
    NaN is not representable in JSON and would break System 3's parse.
    """
    out: Dict[str, Dict[str, float]] = {}
    for sid, g in trades.groupby("strategy_id"):
        r = g["r_multiple"].to_numpy(dtype="float64")
        r = r[np.isfinite(r)]
        if len(r) < MIN_TRADES:
            continue
        wins, losses = r[r > 0], r[r < 0]
        out[str(int(sid))] = {
            "win_rate": round(float(g["is_winner"].mean()), 6),
            "avg_win": round(float(wins.mean()) if len(wins) else 0.0, 6),
            "avg_loss": round(float(abs(losses.mean())) if len(losses) else 0.0, 6),
            "expectancy": round(float(r.mean()), 6),
        }
    return out


def build_document(strategies: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
    """Assemble the published document. ``checksum`` covers ``strategies`` only."""
    return {
        "schema_version": SCHEMA_VERSION,
        "produced_at": datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z"),
        "source": "system1-model-004-trade-outcomes",
        "unit": UNIT,
        "scope": "oos_only" if OOS_ONLY else "all_trades",
        "checksum": canonical_checksum(strategies),
        "strategies": strategies,
    }


def build(engine=None) -> Dict[str, Any]:
    """Compute the document from the database (no writes)."""
    engine = engine or get_engine()
    trades = _load_trades(engine)
    n_all = len(trades)
    if OOS_ONLY:
        trades = trades[trades["is_oos"]]
    if trades.empty:
        raise StrategyStatsRefused(
            "no trades available to compute strategy stats — refusing to publish an "
            "empty risk document"
        )
    strategies = compute_stats(trades)
    if not strategies:
        raise StrategyStatsRefused("no strategy met MIN_TRADES — refusing empty map")
    logger.info(
        "computed stats for %d strategies from %d/%d trades (%s)",
        len(strategies),
        len(trades),
        n_all,
        "OOS only" if OOS_ONLY else "all trades",
    )
    return build_document(strategies)


def publish(
    dry_run: bool = False, storage=None, staging_dir: str = STAGING_DIR
) -> Dict[str, Any]:
    """Publish the document under the verify-before-live contract (see module docstring)."""
    document = build()
    storage = storage or build_storage()

    os.makedirs(staging_dir, exist_ok=True)
    local_path = os.path.join(staging_dir, ARTIFACT_NAME)
    with open(local_path, "w", encoding="utf-8") as fh:
        json.dump(document, fh, indent=2, sort_keys=True)
    local_sha = _sha256_file(local_path)

    # Self-check: the checksum we are about to publish must validate the way System 3
    # will validate it. Catches any drift between build_document and the contract.
    if canonical_checksum(document["strategies"]) != document["checksum"]:
        raise StrategyStatsRefused("internal checksum self-check failed")

    if dry_run:
        logger.info("dry-run — nothing uploaded, live document untouched")
        return {**document, "published": False, "local_path": local_path}

    version = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    remote_prefix = f"{REMOTE_ROOT}/{version}"
    versioned_key = f"{remote_prefix}/{ARTIFACT_NAME}"

    # 2. upload to the immutable versioned key -> 3. round-trip verify BEFORE going live.
    try:
        storage.put_object(versioned_key, local_path, encrypt=True)
        remote_sha = storage.sha256(versioned_key)
        if remote_sha != local_sha:
            raise StrategyStatsRefused(
                f"round-trip checksum mismatch on {versioned_key}: "
                f"local={local_sha} remote={remote_sha}"
            )
    except Exception:
        storage.delete_prefix(remote_prefix)  # no half-uploaded version survives
        logger.error(
            "upload/verify failed — aborted; live %s left untouched", POINTER_KEY
        )
        raise

    # 4. only now make it live. The document is written whole; ``checksum`` covers the
    # strategies map, so re-serialization by the backend cannot invalidate it.
    storage.atomic_pointer_update(POINTER_KEY, document)

    # 5. confirm what a consumer will actually read back.
    verified = _verify_live(storage, document["checksum"])
    logger.info(
        "published %s (version %s, %d strategies, live checksum verified=%s)",
        POINTER_KEY,
        version,
        len(document["strategies"]),
        verified,
    )
    return {
        **document,
        "published": True,
        "version": version,
        "versioned_key": versioned_key,
        "live_verified": verified,
    }


def _verify_live(storage, expected_checksum: str) -> bool:
    """Re-read the live document and recompute its checksum the way System 3 does."""
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, ARTIFACT_NAME)
        storage.get_object(POINTER_KEY, p)
        with open(p, encoding="utf-8") as fh:
            live = json.load(fh)
    recomputed = canonical_checksum(live.get("strategies", {}))
    return bool(
        recomputed == expected_checksum and live.get("checksum") == expected_checksum
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="D6 — publish risk/strategy_stats")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and print the document without uploading or going live.",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_REPO_ROOT, ".env"))
    try:
        print(json.dumps(publish(dry_run=args.dry_run), indent=2))
    except StrategyStatsRefused as e:
        logger.error("STRATEGY STATS REFUSED: %s", e)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
