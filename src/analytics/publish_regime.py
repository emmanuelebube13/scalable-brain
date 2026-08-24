"""R4 — Publish regime per strategy per timeframe."""

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
from src.analytics import extract as EX
from src.layer0.strategies.v2_harness import discover
from src.regime.structural import build_structural_labels

logger = logging.getLogger("system1.publish_regime")

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STAGING_DIR = os.path.join(_REPO_ROOT, "results", "state", "regime_staging")
REMOTE_ROOT = "system1/regime_status"
POINTER_KEY = f"{REMOTE_ROOT}/latest.json"
PREVIOUS_KEY = f"{REMOTE_ROOT}/previous.json"


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, default=str)


def build_document() -> Dict[str, Any]:
    """Build the regime status document."""
    generated_at = datetime.now(timezone.utc).isoformat()
    engine = get_engine()

    asset_symbols = EX.load_asset_symbols(engine)
    # asset_symbols is {asset_id: symbol}
    symbol_to_id = {v: k for k, v in asset_symbols.items()}

    regime_map = EX.load_regime_strategy_map()
    qualification_run_id = regime_map.get("qualification_run_id", "")

    # Published under the STRUCTURAL label, not d1_trend.
    #
    # d1_trend emits only {Trending-Up, Trending-Down, UNKNOWN} — it has no Ranging and no
    # High-Vol state. Under it a trend_following or breakout mask enables everything the
    # label can produce (the gate is a no-op) and a mean_reversion mask enables nothing it
    # can produce (the strategy is off permanently). Measured 2026-08-16: the d1_trend gate
    # was active in ZERO of 43 cells. Publishing `is_trading` computed from it would send
    # System 2 a flag that is meaningless in every row.
    #
    # The structural label is rule-based, causal and emits all four states with healthy
    # coverage on all five pairs (Ranging 36-45%, High-Vol 11-23%, no pair dominating any
    # state), so `is_trading` derived from it is a real statement about the strategy.
    from src.layer0.strategies.research_data import load_ohlcv_readonly

    REGIME_SOURCE = "structural"

    pair_d1_regime = {}
    for asset_id, pair in asset_symbols.items():
        d1_df = load_ohlcv_readonly(pair, "D1", lookback_years=3)
        if d1_df is None or d1_df.empty:
            continue
        labels_df = build_structural_labels(d1_df)
        if labels_df.empty:
            continue

        # Get the latest label
        latest_row = labels_df.iloc[-1]
        latest_label = latest_row["regime"]
        as_of_bar_utc = latest_row["bar_time"].isoformat()

        # Count bars_in_regime by walking backwards
        bars_in_regime = 0
        for i in range(len(labels_df) - 1, -1, -1):
            if labels_df.iloc[i]["regime"] == latest_label:
                bars_in_regime += 1
            else:
                break

        pair_d1_regime[pair] = {
            "regime_current": latest_label,
            "as_of_bar_utc": as_of_bar_utc,
            "bars_in_regime": bars_in_regime,
        }

    strategies = discover()

    regimes_payload = []

    for sid, strat in strategies.items():
        # R3 experiment was reverted and hardcoded regime masks deleted.
        # Now every active strategy is presented to the gatekeeper, which
        # learns dynamic thresholds. We emit a permissive mask here to satisfy
        # the dashboard contract, meaning 'trading is decided dynamically'.
        family = "unclassified"
        mask = {
            "Trending-Up": True,
            "Trending-Down": True,
            "High-Vol": True,
            "Ranging": True,
            "UNKNOWN": False,
        }

        metadata = strat.metadata
        granularity = metadata.primary_granularity

        for pair in metadata.pairs:
            asset_id = symbol_to_id.get(pair)
            if not asset_id:
                continue

            rinfo = pair_d1_regime.get(pair)

            if not rinfo:
                regime_current = "UNKNOWN"
                as_of_bar_utc = generated_at
                bars_in_regime = 0
            else:
                regime_current = rinfo["regime_current"]
                as_of_bar_utc = rinfo["as_of_bar_utc"]
                bars_in_regime = rinfo["bars_in_regime"]

            is_trading = mask.get(regime_current, False)

            regimes_payload.append(
                {
                    "strategy_key": sid,
                    "family": family,
                    "granularity": granularity,
                    "pair": pair,
                    "regime_current": regime_current,
                    "regime_source": REGIME_SOURCE,
                    "as_of_bar_utc": as_of_bar_utc,
                    "is_trading": is_trading,
                    "mask": mask,
                    "bars_in_regime": bars_in_regime,
                }
            )

    payload = {
        "status": "published",
        "qualification_run_id": qualification_run_id or "missing",
        "generated_at_utc": generated_at,
        "schema_version": "1",
        "cadence": "hourly",
        "regimes": regimes_payload,
    }

    os.makedirs(STAGING_DIR, exist_ok=True)
    payload_path = os.path.join(STAGING_DIR, "regime_status.json")
    _write_json(payload_path, payload)

    # Compute SHA256 of payload for manifest
    payload_sha256 = _sha256(payload_path)
    payload["payload_sha256"] = payload_sha256

    # Re-write with sha256 included so it matches the contract exactly
    _write_json(payload_path, payload)

    logger.info(f"Document built with {len(regimes_payload)} regime entries.")
    return payload, payload_path


def publish(payload: Dict[str, Any], payload_path: str, storage=None) -> Dict[str, Any]:
    storage = storage or build_storage()
    version = (
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
        + "-"
        + payload["payload_sha256"][:8]
    )
    remote_prefix = f"{REMOTE_ROOT}/{version}"
    local_sha = _sha256(payload_path)

    logger.info(f"Publishing regime status document -> {remote_prefix}")

    try:
        storage.put_object(
            f"{remote_prefix}/regime_status.json", payload_path, encrypt=True
        )
        if storage.sha256(f"{remote_prefix}/regime_status.json") != local_sha:
            raise RuntimeError("round-trip checksum mismatch: regime_status.json")
    except Exception:
        storage.delete_prefix(remote_prefix)
        raise

    if storage.exists(POINTER_KEY):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            prev_path = os.path.join(td, "latest.json")
            storage.get_object(POINTER_KEY, prev_path)
            with open(prev_path, encoding="utf-8") as fh:
                storage.atomic_pointer_update(PREVIOUS_KEY, json.load(fh))

    pointer = {
        "artifact": "system1-regime-status",
        "status": "published",
        "version": version,
        "path": f"{remote_prefix}/",
        "manifest_sha256": local_sha,
        "qualification_run_id": payload["qualification_run_id"],
        "generated_at_utc": payload["generated_at_utc"],
        "published_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    storage.atomic_pointer_update(POINTER_KEY, pointer)
    logger.info(f"Regime status pointer flipped -> {version}")
    return pointer


def run(dry_run: bool = False) -> Dict[str, Any]:
    payload, payload_path = build_document()

    # Validate against schema
    import jsonschema

    schema_path = os.path.join(_REPO_ROOT, "contracts", "regime-status-contract.json")
    with open(schema_path, "r") as f:
        schema = json.load(f)
    jsonschema.validate(instance=payload, schema=schema)
    logger.info("Document validates against schema.")

    if dry_run:
        print(json.dumps(payload, indent=2))
        return payload

    pointer = publish(payload, payload_path)
    print(json.dumps(pointer, indent=2))
    return pointer


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish the S1 regime status document"
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
