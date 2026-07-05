"""MODEL-002 — build the versioned Parquet feature store.

Reads prices per granularity from ``fact_market_prices``, computes trailing-only
features (see ``definitions.py``), and writes:

  feature-store/{feature_set_version}/
    schema.json
    lineage.json
    granularity={D1|H4|W1}/year=YYYY/part-0000.parquet   (Snappy)

Determinism: rows are sorted by (asset_id, bar_time_utc), the Arrow schema is explicit
and pandas index/metadata is stripped, so identical inputs → byte-identical partitions
(build wall-clock lives only in lineage.json). Registers the build in MLflow.

Usage:
    python -m src.system1.features.feature_pipeline --version 1.0.0
    python -m src.system1.features.feature_pipeline --version 1.0.0 --out-root /tmp/fs  # for determinism check
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import text

from src.common.db import get_engine
from src.system1.features import definitions as D

logger = logging.getLogger("system1.features.pipeline")

GRANULARITIES = ["D1", "H4", "W1"]
DEFAULT_VERSION = "1.0.0"

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DEFAULT_OUT_ROOT = os.path.join(_REPO_ROOT, "feature-store")

# Explicit Arrow schema (fixed column order = deterministic bytes).
# NOTE: `granularity` and `year` are PARTITION KEYS encoded in the directory path
# (Hive-style), NOT stored in the file — storing them in-file too collides with
# pyarrow's path-inferred partition columns on read.
ARROW_SCHEMA = pa.schema(
    [
        ("asset_id", pa.int32()),
        ("bar_time_utc", pa.timestamp("us", tz="UTC")),
        ("returns_1", pa.float64()),
        ("atr_14", pa.float64()),
        ("adx_14", pa.float64()),
        ("price_position_20", pa.float64()),
        ("volatility_20", pa.float64()),
    ]
)
OUTPUT_COLUMNS = [f.name for f in ARROW_SCHEMA]


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=_REPO_ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _read_prices(granularity: str) -> pd.DataFrame:
    """Read one granularity's prices, ordered for deterministic feature computation."""
    sql = text(
        'SELECT asset_id, "timestamp" AS bar_time_utc, "Open" AS open, high, low, '
        '"Close" AS close, volume, ingest_run_id '
        "FROM fact_market_prices WHERE granularity = :g "
        'ORDER BY asset_id, "timestamp"'
    )
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"g": granularity})
    df["bar_time_utc"] = pd.to_datetime(df["bar_time_utc"], utc=True)
    return df


def _compute_all(df: pd.DataFrame, granularity: str) -> pd.DataFrame:
    """Compute features per instrument (so windows never cross instrument boundaries)."""
    frames: List[pd.DataFrame] = []
    for asset_id, grp in df.groupby("asset_id", sort=True):
        grp = grp.sort_values("bar_time_utc").reset_index(drop=True)
        feats = D.compute_features(grp)
        feats["granularity"] = granularity
        frames.append(feats)
    out = pd.concat(frames, ignore_index=True)
    return out.sort_values(["asset_id", "bar_time_utc"]).reset_index(drop=True)


def _write_partition(part_df: pd.DataFrame, path_dir: str) -> str:
    """Write one (granularity, year) partition deterministically; return sha256."""
    os.makedirs(path_dir, exist_ok=True)
    table = pa.Table.from_pandas(
        part_df[OUTPUT_COLUMNS], schema=ARROW_SCHEMA, preserve_index=False
    )
    # Strip pandas metadata (carries non-essential, version-tagged info) for stable bytes.
    table = table.replace_schema_metadata(None)
    out_path = os.path.join(path_dir, "part-0000.parquet")
    pq.write_table(
        table, out_path, compression="snappy", version="2.6", write_statistics=True
    )
    with open(out_path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def build(
    version: str = DEFAULT_VERSION,
    out_root: str = DEFAULT_OUT_ROOT,
    register_mlflow: bool = True,
) -> Dict[str, Any]:
    """Build the feature store for ``version`` under ``out_root``. Returns a summary."""
    build_started = datetime.now(timezone.utc)
    version_dir = os.path.join(out_root, version)
    os.makedirs(version_dir, exist_ok=True)

    partition_hashes: Dict[str, str] = {}
    row_counts: Dict[str, int] = {}
    warmup_nulls: Dict[str, Dict[str, int]] = {}
    source_run_ids: set = set()
    price_ranges: Dict[str, Dict[str, str]] = {}

    for g in GRANULARITIES:
        prices = _read_prices(g)
        if prices.empty:
            logger.warning("No prices for granularity %s — skipping", g)
            continue
        source_run_ids.update(
            str(r) for r in prices["ingest_run_id"].dropna().unique().tolist()
        )
        price_ranges[g] = {
            "first_bar_utc": prices["bar_time_utc"].min().isoformat(),
            "last_bar_utc": prices["bar_time_utc"].max().isoformat(),
        }
        feats = _compute_all(prices, g)
        row_counts[g] = int(len(feats))
        warmup_nulls[g] = {c: int(feats[c].isna().sum()) for c in D.FEATURE_COLUMNS}

        feats["year"] = feats["bar_time_utc"].dt.year
        for year, part in feats.groupby("year", sort=True):
            path_dir = os.path.join(version_dir, f"granularity={g}", f"year={year}")
            sha = _write_partition(part, path_dir)
            partition_hashes[f"granularity={g}/year={year}"] = sha

    # schema.json — column/dtype/window/formulae contract.
    schema_doc = {
        "feature_set_version": version,
        "columns": {
            "asset_id": "int32",
            "bar_time_utc": "timestamp[us, tz=UTC]",
            "returns_1": "float64",
            "atr_14": "float64",
            "adx_14": "float64",
            "price_position_20": "float64",
            "volatility_20": "float64",
        },
        "partition_columns": {"granularity": "string", "year": "int32"},
        "feature_columns": D.FEATURE_COLUMNS,
        "regime_feature_columns": D.REGIME_FEATURE_COLUMNS,
        "window_params": {
            "ATR_PERIOD": D.ATR_PERIOD,
            "ADX_PERIOD": D.ADX_PERIOD,
            "PRICE_POSITION_WINDOW": D.PRICE_POSITION_WINDOW,
            "VOLATILITY_WINDOW": D.VOLATILITY_WINDOW,
        },
        "warmup_by_feature": D.WARMUP_BY_FEATURE,
        "formulae": D.FEATURE_FORMULAE,
        "partition_keys": ["granularity", "year"],
        "compression": "snappy",
    }
    _write_json(os.path.join(version_dir, "schema.json"), schema_doc)

    build_ended = datetime.now(timezone.utc)
    lineage_doc = {
        "feature_set_version": version,
        "build_started_utc": build_started.isoformat(),
        "build_ended_utc": build_ended.isoformat(),
        "git_sha": _git_sha(),
        "source_table": "fact_market_prices",
        "source_ingest_run_ids": sorted(source_run_ids),
        "price_date_ranges": price_ranges,
        "row_counts": row_counts,
        "warmup_null_counts": warmup_nulls,
        "partition_sha256": partition_hashes,
    }
    _write_json(os.path.join(version_dir, "lineage.json"), lineage_doc)

    mlflow_run_id: Optional[str] = None
    if register_mlflow:
        mlflow_run_id = _register_mlflow(version, schema_doc, lineage_doc, version_dir)

    summary = {
        "feature_set_version": version,
        "version_dir": version_dir,
        "row_counts": row_counts,
        "partitions": len(partition_hashes),
        "source_ingest_run_ids": len(source_run_ids),
        "mlflow_run_id": mlflow_run_id,
    }
    logger.info("Feature store build complete: %s", summary)
    return summary


def _write_json(path: str, payload: Any) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, default=str)
    os.replace(tmp, path)


def _resolve_mlflow_uri() -> str:
    """Resolve a usable MLflow tracking URI (absolute sqlite; file-store is rejected)."""
    uri = os.environ.get("MLFLOW_TRACKING_URI", "")
    default_db = os.path.join(_REPO_ROOT, "results", "state", "mlflow.db")
    if not uri or uri.startswith("file:"):
        os.makedirs(os.path.dirname(default_db), exist_ok=True)
        return f"sqlite:///{default_db}"
    if uri.startswith("sqlite:///") and not uri.startswith("sqlite:////"):
        rel = uri[len("sqlite:///"):]
        db_path = rel if os.path.isabs(rel) else os.path.join(_REPO_ROOT, rel)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        return f"sqlite:///{db_path}"
    return uri


def _register_mlflow(version, schema_doc, lineage_doc, version_dir) -> Optional[str]:
    try:
        import mlflow

        mlflow.set_tracking_uri(_resolve_mlflow_uri())
        mlflow.set_experiment("system1-feature-store")
        with mlflow.start_run(run_name=f"feature-store-{version}") as run:
            mlflow.log_param("feature_set_version", version)
            mlflow.log_params(schema_doc["window_params"])
            for g, n in lineage_doc["row_counts"].items():
                mlflow.log_metric(f"rows_{g}", n)
            mlflow.log_metric("source_ingest_run_ids", len(lineage_doc["source_ingest_run_ids"]))
            mlflow.log_artifact(os.path.join(version_dir, "schema.json"))
            mlflow.log_artifact(os.path.join(version_dir, "lineage.json"))
            return run.info.run_id
    except Exception as e:  # noqa: BLE001
        logger.error("MLflow registration failed: %s", e)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="MODEL-002 feature store builder")
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument("--out-root", default=DEFAULT_OUT_ROOT)
    parser.add_argument("--no-mlflow", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    summary = build(args.version, args.out_root, register_mlflow=not args.no_mlflow)
    print(summary)


if __name__ == "__main__":
    main()
