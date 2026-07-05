"""
Layer 1: Market Regime Detection & Ingestion - Swing Trading
==========================================================

🚀 SWING TRADING SYSTEM | Market state classification for swing trade context

Production-grade pipeline for swing trading regime detection:
- Dynamic asset discovery from Dim_Asset (with Is_Active fallback)
- Fully granularity-aware (H1/H4 processed independently)
- Enhanced features + temporal context for swing trade decisions
- Quality-gated KMeans with deterministic label mapping
- Incremental mode (overlap buffer for warm-up) + optional full-rebuild
- Hardened temp-table + upsert (matches layer0 patterns)
- Full observability, idempotency, CLI controls, model versioning
- No hardcoded assets/symbols/granularities
"""

import os
import sys
import argparse
import logging
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
import pandas as pd
import numpy as np
import ta
import psycopg2
from psycopg2.extras import execute_values
from sqlalchemy import text
from dotenv import load_dotenv
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

# Ensure the repo root is importable so ``src.common`` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common.db import get_engine, get_psycopg2_connection  # noqa: E402

# ── Setup ─────────────────────────────────────────────────────────────────────
load_dotenv()


def clean_env_value(value: Optional[str]) -> Optional[str]:
    """Trim whitespace and optional surrounding quotes from env values."""
    if value is None:
        return None
    value = value.strip()
    if len(value) >= 2:
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
    return value.strip()


def load_repo_env_file() -> None:
    """Load key/value pairs from repo-root .env into process environment."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
    env_path = os.path.join(repo_root, ".env")

    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, raw_value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue

            cleaned_value = clean_env_value(raw_value)
            os.environ[key] = cleaned_value or ""


def read_env() -> dict[str, str]:
    """Read and validate required DB environment variables."""
    load_repo_env_file()

    required = ["DB_SERVER", "DB_USER", "DB_PASS", "DB_NAME"]
    env: dict[str, str] = {}
    missing = []

    for var in required:
        value = clean_env_value(os.getenv(var))
        if not value:
            missing.append(var)
        env[var] = value or ""

    env["DB_PORT"] = clean_env_value(os.getenv("DB_PORT")) or "5432"

    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    return env


def get_db_connection():
    """Create a PostgreSQL (psycopg2) connection via the canonical db module.

    The session timezone is forced to UTC so timestamps round-trip consistently
    between ``fact_market_prices`` and ``fact_market_regime_v2`` (both
    ``timestamptz``).
    """
    env = read_env()
    logger.info(
        "Connecting to PostgreSQL: %s:%s/%s",
        env["DB_SERVER"],
        env["DB_PORT"],
        env["DB_NAME"],
    )
    conn = get_psycopg2_connection()
    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'UTC'")
    conn.commit()
    return conn


def setup_logging():
    """Structured logging to console + rotating file (per-run)."""
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(
        log_dir, f"regime_ingest_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )

    logger = logging.getLogger("regime_v2")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    # Console
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File
    fh = logging.FileHandler(log_file)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger


logger = setup_logging()


# ── Dynamic Asset Discovery ───────────────────────────────────────────────────
def get_active_assets(conn, symbol_filter: Optional[str] = None):
    """Read active assets from Dim_Asset; fallback to all if Is_Active missing."""
    cursor = conn.cursor()

    # Check for is_active column
    cursor.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND lower(table_name) = 'dim_asset'
          AND column_name = 'is_active'
        """)
    has_active = cursor.fetchone() is not None

    query = 'SELECT asset_id AS "Asset_ID", symbol AS "Symbol" FROM dim_asset WHERE 1=1'
    params: dict = {}

    if has_active:
        query += " AND is_active = TRUE"

    if symbol_filter:
        query += " AND symbol = :symbol"
        params["symbol"] = symbol_filter

    query += " ORDER BY asset_id ASC"

    with get_engine().connect() as ec:
        df = pd.read_sql(text(query), ec, params=params or None)
    logger.info(f"Discovered {len(df)} asset(s) to process.")
    return df.to_dict("records")


# ── Table Management ──────────────────────────────────────────────────────────
def ensure_regime_table_v2(conn):
    """Create fact_market_regime_v2 (canonical schema) if it does not exist.

    On the live store the table already exists (this is a no-op there). The
    column-case contract keeps lowercase identifiers; mixed-case is unnecessary
    for this table.
    """
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fact_market_regime_v2 (
            "timestamp"            timestamptz   NOT NULL,
            asset_id               integer       NOT NULL,
            granularity            varchar(10)   NOT NULL,
            regime_label           varchar(50),
            atr_value              double precision,
            adx_value              double precision,
            session_volume_z       double precision,
            regime_model_version   varchar(30),
            cluster_centroids_json text,
            label_map_json         text,
            created_at             timestamptz   NOT NULL DEFAULT now(),
            updated_at             timestamptz   NOT NULL DEFAULT now(),
            PRIMARY KEY ("timestamp", asset_id, granularity)
        )
        """)
    conn.commit()
    logger.info("[DB] fact_market_regime_v2 table verified.")


def ensure_regime_lineage_schema(conn):
    """Add lineage columns to an existing regime table if needed (idempotent).

    Uses PostgreSQL ``ADD COLUMN IF NOT EXISTS`` — non-destructive and a no-op
    when the columns already exist.
    """
    cursor = conn.cursor()
    cursor.execute("""
        ALTER TABLE fact_market_regime_v2
            ADD COLUMN IF NOT EXISTS cluster_centroids_json text,
            ADD COLUMN IF NOT EXISTS label_map_json text
        """)
    conn.commit()


# ── Feature Engineering ───────────────────────────────────────────────────────
def calculate_features(df: pd.DataFrame, granularity: str):
    """Baseline + required temporal context features (granularity-aware windows)."""
    df = df.copy()

    if granularity == "H1":
        vol_window = 24
        context_window = 60
        momentum_window = 20
        bb_window = 20
        trend_window = 14
    else:
        vol_window = 6
        context_window = 15
        momentum_window = 5
        bb_window = 5
        trend_window = 4

    # Baseline
    df["ATR"] = ta.volatility.AverageTrueRange(
        high=df["High"], low=df["Low"], close=df["Close"], window=14
    ).average_true_range()

    df["ADX"] = ta.trend.ADXIndicator(
        high=df["High"], low=df["Low"], close=df["Close"], window=14
    ).adx()

    # Normalize ATR so the clustering is less biased by raw price scale.
    df["ATR_Pct"] = df["ATR"] / df["Close"].replace(0, np.nan)

    # Price-action structure features.
    price_range = (df["High"] - df["Low"]).replace(0, np.nan)
    body = (df["Close"] - df["Open"]).abs()
    df["Candle_Body"] = body / price_range
    df["Upper_Wick"] = (df["High"] - df[["Open", "Close"]].max(axis=1)) / price_range
    df["Lower_Wick"] = (df[["Open", "Close"]].min(axis=1) - df["Low"]) / price_range
    df["Close_Position"] = (df["Close"] - df["Low"]) / price_range

    # Return and trend structure.
    df["Log_Return"] = np.log(df["Close"] / df["Close"].shift(1))
    df["Return_Mean"] = (
        df["Log_Return"]
        .rolling(window=momentum_window, min_periods=momentum_window)
        .mean()
    )
    df["Return_Std"] = (
        df["Log_Return"]
        .rolling(window=momentum_window, min_periods=momentum_window)
        .std()
        .clip(lower=1e-8)
    )
    df["Trend_Ratio"] = df["Return_Mean"] / df["Return_Std"]
    df["Realized_Vol"] = (
        df["Log_Return"]
        .rolling(window=context_window, min_periods=context_window)
        .std()
        .clip(lower=1e-8)
    )
    df["Realized_Vol_Z"] = (
        df["Realized_Vol"]
        - df["Realized_Vol"].rolling(context_window, min_periods=context_window).mean()
    ) / df["Realized_Vol"].rolling(
        context_window, min_periods=context_window
    ).std().clip(
        lower=1e-8
    )

    # Session volume proxy (rolling z-score)
    df["Volume_Mean"] = (
        df["Volume"].rolling(window=vol_window, min_periods=vol_window).mean()
    )
    df["Volume_Std"] = (
        df["Volume"]
        .rolling(window=vol_window, min_periods=vol_window)
        .std()
        .clip(lower=1e-8)
    )
    df["Session_Volume_Z"] = (df["Volume"] - df["Volume_Mean"]) / df["Volume_Std"]

    # Temporal context
    df["ATR_Z"] = (
        df["ATR"] - df["ATR"].rolling(context_window, min_periods=context_window).mean()
    ) / df["ATR"].rolling(context_window, min_periods=context_window).std().clip(
        lower=1e-8
    )
    df["ADX_Delta"] = df["ADX"].diff().fillna(0)

    bb = ta.volatility.BollingerBands(close=df["Close"], window=bb_window, window_dev=2)
    df["BB_Width"] = (bb.bollinger_hband() - bb.bollinger_lband()) / df[
        "Close"
    ].replace(0, np.nan)
    df["BB_Width_Z"] = (
        df["BB_Width"]
        - df["BB_Width"].rolling(context_window, min_periods=context_window).mean()
    ) / df["BB_Width"].rolling(context_window, min_periods=context_window).std().clip(
        lower=1e-8
    )

    # Volatility persistence
    pers_window = trend_window
    df["Vol_Persistence"] = df["ATR"].rolling(
        pers_window, min_periods=pers_window
    ).mean() / df["ATR"].rolling(pers_window, min_periods=pers_window).std().clip(
        lower=1e-5
    )

    # Explicit warm-up cutoff to avoid unstable head-of-window values.
    warmup_cutoff = (
        max(14, vol_window, context_window, momentum_window, bb_window, pers_window) + 1
    )
    df = df.iloc[warmup_cutoff:].copy()

    # Safe warm-up drop
    before = len(df)
    df.dropna(
        subset=[
            "ATR",
            "ADX",
            "ATR_Pct",
            "Candle_Body",
            "Upper_Wick",
            "Lower_Wick",
            "Close_Position",
            "Log_Return",
            "Trend_Ratio",
            "Realized_Vol_Z",
            "Session_Volume_Z",
            "ATR_Z",
            "BB_Width_Z",
            "Vol_Persistence",
        ],
        inplace=True,
    )
    logger.debug(f"         Dropped {before - len(df)} warm-up rows for {granularity}.")

    return df


# ── Clustering & Labeling ─────────────────────────────────────────────────────
def cluster_and_label(
    df: pd.DataFrame,
    symbol: str,
    granularity: str,
    k: int = 4,
    silhouette_threshold: float = 0.25,
    force_write: bool = False,
):
    """KMeans (configurable k) with quality gate and deterministic label mapping."""
    if k < 2:
        logger.warning(
            f"         [{symbol} {granularity}] Invalid k={k}. Must be >= 2. Skipping."
        )
        return None, np.nan, None

    if len(df) < k:
        logger.warning(
            f"         [{symbol} {granularity}] Not enough rows for clustering "
            f"(rows={len(df)}, k={k}). Skipping."
        )
        return None, np.nan, None

    feature_cols = [
        "ATR_Pct",
        "ADX",
        "ADX_Delta",
        "Trend_Ratio",
        "Realized_Vol_Z",
        "Session_Volume_Z",
        "Candle_Body",
        "Close_Position",
        "BB_Width_Z",
    ]
    features = df[feature_cols].values

    try:
        scaler = StandardScaler()
        scaled = scaler.fit_transform(features)

        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        df = df.copy()
        df["Cluster"] = kmeans.fit_predict(scaled)

        unique_clusters = df["Cluster"].nunique()
        if unique_clusters < 2:
            logger.warning(
                f"         [{symbol} {granularity}] Cluster collapse ({unique_clusters} cluster). Skipping."
            )
            return None, np.nan, None

        # Quality metric
        sil = silhouette_score(scaled, df["Cluster"])
    except Exception as exc:
        logger.warning(
            f"         [{symbol} {granularity}] Clustering failed: {exc}. "
            "Skipping this slice."
        )
        return None, np.nan, None

    logger.info(f"         [{symbol} {granularity}] Silhouette Score: {sil:.4f}")

    if sil < silhouette_threshold and not force_write:
        logger.warning(
            f"         Quality gate FAILED (sil={sil:.3f} < {silhouette_threshold}). "
            f"Skipping write for {symbol} {granularity}."
        )
        return None, sil, None

    if sil < silhouette_threshold and force_write:
        logger.warning(
            f"         Quality gate FAILED (sil={sil:.3f} < {silhouette_threshold}), "
            f"but backfill mode is enabled so this slice will still be written."
        )

    # Deterministic business labels (based on normalized ATR/ADX centroids).
    centers = scaler.inverse_transform(kmeans.cluster_centers_)
    median_atr = np.median(centers[:, 0])
    median_adx = np.median(centers[:, 1])

    label_map = {}
    for i, (atr_c, adx_c) in enumerate(
        centers[:, :2]
    ):  # only first two dims for labels
        if adx_c >= median_adx and atr_c >= median_atr:
            label = "Trending_HighVol"
        elif adx_c >= median_adx:
            label = "Trending_LowVol"
        elif atr_c >= median_atr:
            label = "Ranging_HighVol"
        else:
            label = "Ranging_LowVol"
        label_map[i] = label

    df["Regime_Label"] = df["Cluster"].map(label_map)
    lineage = {
        "feature_columns": feature_cols,
        "cluster_centroids": centers.tolist(),
        "label_map": label_map,
    }
    return df, sil, lineage


# ── Hardened Batch Upsert (temp-table pattern) ───────────────────────────────
def upsert_regimes(
    conn,
    df: pd.DataFrame,
    asset_id: int,
    symbol: str,
    granularity: str,
    model_version: str,
    lineage: Optional[dict] = None,
    dry_run: bool = False,
):
    """Schema-aware ``INSERT ... ON CONFLICT`` upsert (PostgreSQL).

    Replaces the SQL Server temp-table + ``MERGE`` pattern. Only columns that
    actually exist on ``fact_market_regime_v2`` are written, so the writer is
    robust to schema drift (e.g. a live table that lacks the lineage/audit
    columns). The conflict target is the PK ``(timestamp, asset_id,
    granularity)`` — re-running is idempotent.
    """
    if df.empty or dry_run:
        return 0

    df_write = df.copy()
    df_write["Asset_ID"] = asset_id
    df_write["Granularity"] = granularity
    df_write["Regime_Model_Version"] = model_version
    df_write["Cluster_Centroids_JSON"] = (
        json.dumps(lineage.get("cluster_centroids"), sort_keys=True)
        if lineage
        else None
    )
    df_write["Label_Map_JSON"] = (
        json.dumps(lineage.get("label_map"), sort_keys=True) if lineage else None
    )
    df_write["Created_At"] = datetime.utcnow()
    df_write["Updated_At"] = datetime.utcnow()

    # Rename to match target schema
    df_write = df_write.rename(columns={"ATR": "ATR_Value", "ADX": "ADX_Value"})

    # Ordered map of DataFrame column -> PostgreSQL column.
    col_map = [
        ("Timestamp", "timestamp"),
        ("Asset_ID", "asset_id"),
        ("Granularity", "granularity"),
        ("Regime_Label", "regime_label"),
        ("ATR_Value", "atr_value"),
        ("ADX_Value", "adx_value"),
        ("Session_Volume_Z", "session_volume_z"),
        ("Regime_Model_Version", "regime_model_version"),
        ("Cluster_Centroids_JSON", "cluster_centroids_json"),
        ("Label_Map_JSON", "label_map_json"),
        ("Created_At", "created_at"),
        ("Updated_At", "updated_at"),
    ]

    cursor = conn.cursor()

    # Schema-aware: keep only columns that exist in the live table and that the
    # source DataFrame actually provides.
    cursor.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'fact_market_regime_v2'
        """)
    existing_cols = {r[0] for r in cursor.fetchall()}

    pk_cols = {"timestamp", "asset_id", "granularity"}
    active = [
        (df_col, pg_col)
        for df_col, pg_col in col_map
        if pg_col in existing_cols and df_col in df_write.columns
    ]
    df_cols = [df_col for df_col, _ in active]
    pg_cols = [pg_col for _, pg_col in active]

    # Quote identifiers; PK timestamp is a reserved word in PostgreSQL.
    quoted = ", ".join(f'"{c}"' for c in pg_cols)
    update_cols = [c for c in pg_cols if c not in pk_cols and c != "created_at"]
    set_clause = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in update_cols)

    upsert_sql = (
        f"INSERT INTO fact_market_regime_v2 ({quoted}) VALUES %s "
        f'ON CONFLICT ("timestamp", asset_id, granularity) '
        + (f"DO UPDATE SET {set_clause}" if set_clause else "DO NOTHING")
    )

    rows = [tuple(row) for row in df_write[df_cols].itertuples(index=False, name=None)]
    execute_values(cursor, upsert_sql, rows, page_size=1000)
    rows_affected = cursor.rowcount
    conn.commit()

    logger.info(f"  [{symbol}] Upserted {rows_affected:,} rows ({granularity}).")
    return rows_affected


# ── Per-Asset/Granularity Processing ──────────────────────────────────────────
def process_asset_granularity(
    conn,
    asset_id: int,
    symbol: str,
    granularity: str,
    full_rebuild: bool,
    model_version: str,
    min_rows: int,
    silhouette_threshold: float,
    k: int,
    dry_run: bool,
    force_write: bool,
):
    """Independent processing for one (Asset_ID, Granularity) slice."""
    start_time = datetime.now()
    logger.info(f"→ Processing {symbol} @ {granularity}")
    try:
        # Incremental start (with generous overlap buffer for indicators/rolling)
        start_ts = None
        if not full_rebuild:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT MAX("timestamp")
                FROM fact_market_regime_v2
                WHERE asset_id = %s AND granularity = %s
                """,
                (asset_id, granularity),
            )
            row = cursor.fetchone()
            if row and row[0]:
                max_ts = row[0]
                # Normalise timestamptz -> naive UTC for consistent arithmetic.
                if getattr(max_ts, "tzinfo", None) is not None:
                    max_ts = max_ts.astimezone(timezone.utc).replace(tzinfo=None)
                # Overlap buffer (covers ATR/ADX + rolling windows)
                buffer_hours = 200 if granularity == "H1" else 800
                start_ts = max_ts - pd.Timedelta(hours=buffer_hours)
                logger.info(
                    f"   Incremental mode – starting from {start_ts} (overlap buffer)"
                )

        # Fetch prices ("Open"/"Close" are genuinely mixed-case columns).
        query = """
            SELECT "timestamp" AS "Timestamp", "Open", high AS "High",
                   low AS "Low", "Close", volume AS "Volume"
            FROM fact_market_prices
            WHERE asset_id = :asset_id AND granularity = :granularity
        """
        params = {"asset_id": asset_id, "granularity": granularity}
        if start_ts is not None:
            query += ' AND "timestamp" >= :start_ts'
            params["start_ts"] = start_ts.strftime("%Y-%m-%d %H:%M:%S")
        query += ' ORDER BY "timestamp" ASC'

        with get_engine().connect() as ec:
            df_prices = pd.read_sql(
                text(query), ec, params=params, parse_dates=["Timestamp"]
            )
        # Normalise tz-aware timestamps to naive UTC (SQL Server contract).
        if not df_prices.empty:
            df_prices["Timestamp"] = pd.to_datetime(
                df_prices["Timestamp"], utc=True
            ).dt.tz_localize(None)
        logger.info(f"   Fetched {len(df_prices):,} price rows.")

        if len(df_prices) < min_rows:
            logger.warning(
                f"   Skipped – insufficient raw data ({len(df_prices)} < {min_rows})"
            )
            return

        # Features
        df_feat = calculate_features(df_prices, granularity)

        if len(df_feat) < min_rows:
            logger.warning(
                f"   Skipped after feature engineering – only {len(df_feat)} usable rows"
            )
            return

        # Cluster + label
        df_labeled, sil, lineage = cluster_and_label(
            df_feat,
            symbol,
            granularity,
            k=k,
            silhouette_threshold=silhouette_threshold,
            force_write=force_write,
        )
        if df_labeled is None:
            return

        # Incremental write filter (avoid rewriting history)
        if not full_rebuild and start_ts is not None:
            df_labeled = df_labeled[df_labeled["Timestamp"] >= start_ts]

        # Upsert
        rows_written = upsert_regimes(
            conn,
            df_labeled,
            asset_id,
            symbol,
            granularity,
            model_version,
            lineage=lineage,
            dry_run=dry_run,
        )

        duration = (datetime.now() - start_time).total_seconds()
        logger.info(
            f"   Completed {symbol} {granularity} in {duration:.1f}s | "
            f"sil={sil:.3f} | rows={rows_written}"
        )
    except Exception as exc:
        duration = (datetime.now() - start_time).total_seconds()
        logger.exception(
            f"   Failed {symbol} {granularity} after {duration:.1f}s: {exc}"
        )


# ── CLI Entry Point ───────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Layer 1 Regime Ingestion V2 (production)"
    )
    parser.add_argument(
        "--symbol", type=str, help="Single symbol filter (e.g. EUR_USD)"
    )
    parser.add_argument(
        "--granularity",
        type=str,
        choices=["H1", "H4"],
        help="Single granularity filter",
    )
    parser.add_argument(
        "--full-rebuild", action="store_true", help="Reprocess entire history"
    )
    parser.add_argument("--model-version", type=str, default=None)
    parser.add_argument("--min-rows", type=int, default=1000)
    parser.add_argument("--silhouette-threshold", type=float, default=0.25)
    parser.add_argument("--k", type=int, default=4, help="Number of regimes (KMeans)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Compute only, no DB write"
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Write regime rows even if silhouette is below the threshold (one-time backfill mode)",
    )
    args = parser.parse_args()

    if args.model_version is None:
        args.model_version = f"v2_{datetime.now().strftime('%Y%m%d')}"

    logger.info("=" * 80)
    logger.info("LAYER 1 REGIME INGESTION V2 START")
    logger.info(
        f"Mode: {'FULL REBUILD' if args.full_rebuild else 'INCREMENTAL'} | "
        f"Model: {args.model_version} | k={args.k}"
    )
    if args.backfill:
        logger.info(
            "Backfill mode enabled: low-silhouette slices will still be written."
        )
    logger.info("=" * 80)

    conn = get_db_connection()
    try:
        # Skip DDL in dry-run so the pass is strictly read-only.
        if not args.dry_run:
            ensure_regime_table_v2(conn)
            ensure_regime_lineage_schema(conn)

        assets = get_active_assets(conn, args.symbol)
        if not assets:
            logger.warning("No assets found for current filters; exiting cleanly.")
            return

        granularities = [args.granularity] if args.granularity else ["H1", "H4"]

        for asset in assets:
            asset_id = asset["Asset_ID"]
            symbol = asset["Symbol"]
            for gran in granularities:
                process_asset_granularity(
                    conn=conn,
                    asset_id=asset_id,
                    symbol=symbol,
                    granularity=gran,
                    full_rebuild=args.full_rebuild,
                    model_version=args.model_version,
                    min_rows=args.min_rows,
                    silhouette_threshold=args.silhouette_threshold,
                    k=args.k,
                    dry_run=args.dry_run,
                    force_write=args.backfill,
                )

        logger.info(
            "PIPELINE COMPLETE – All regimes ingested into Fact_Market_Regime_V2."
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
