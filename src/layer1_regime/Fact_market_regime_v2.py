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
import argparse
import logging
import json
from datetime import datetime
from typing import Optional
import pandas as pd
import numpy as np
import ta
import psycopg2
from dotenv import load_dotenv
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

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
    env["DB_DRIVER"] = clean_env_value(os.getenv("DB_DRIVER")) or "PostgreSQL"

    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    return env


def get_db_connection():
    """Create psycopg2 connection for PostgreSQL."""
    env = read_env()
    
    host = env["DB_SERVER"]
    user = env["DB_USER"]
    password = env["DB_PASS"]
    database = env["DB_NAME"]
    port = int(env["DB_PORT"])
    
    logger.info(f"Connecting to PostgreSQL via psycopg2: {host}:{port}/{database}")
    
    conn = psycopg2.connect(
        host=host,
        dbname=database,
        user=user,
        password=password,
        port=port
    )
    
    return conn


def setup_logging():
    """Structured logging to console + rotating file (per-run)."""
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"regime_ingest_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

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

    # Check for Is_Active column
    col_check = """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'dim_asset' AND column_name = 'is_active'
    """
    cursor.execute(col_check)
    has_active = cursor.fetchone() is not None

    query = "SELECT Asset_ID, Symbol FROM Dim_Asset WHERE 1=1"

    if has_active:
        query += " AND Is_Active = 1"

    if symbol_filter:
        # Escape single quotes in symbol_filter for SQL injection safety
        safe_symbol = symbol_filter.replace("'", "''")
        query += f" AND Symbol = '{safe_symbol}'"

    query += " ORDER BY Asset_ID ASC"

    df = pd.read_sql(query, conn)
    logger.info(f"Discovered {len(df)} asset(s) to process.")
    return df.to_dict("records")


# ── Table Management ──────────────────────────────────────────────────────────
def ensure_regime_table_v2(conn):
    """Create Fact_Market_Regime_V2 (exact schema per spec) if it does not exist."""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Fact_Market_Regime_V2 (
            Timestamp            TIMESTAMPTZ  NOT NULL,
            Asset_ID             INT          NOT NULL,
            Granularity          VARCHAR(10)  NOT NULL,
            Regime_Label         VARCHAR(50)  NOT NULL,
            ATR_Value            FLOAT        NOT NULL,
            ADX_Value            FLOAT        NOT NULL,
            Session_Volume_Z     FLOAT        NULL,
            Regime_Model_Version VARCHAR(30)  NOT NULL,
            Cluster_Centroids_JSON TEXT       NULL,
            Label_Map_JSON       TEXT         NULL,
            Created_At           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            Updated_At           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            PRIMARY KEY (Timestamp, Asset_ID, Granularity),
            FOREIGN KEY (Asset_ID) REFERENCES Dim_Asset(Asset_ID)
        );
    """)
    conn.commit()
    logger.info("[DB] Fact_Market_Regime_V2 table verified.")


def ensure_regime_lineage_schema(conn):
    """Add lineage columns to an existing regime table if needed."""
    cursor = conn.cursor()
    for column_name, alter_sql in [
        ("Cluster_Centroids_JSON", "ALTER TABLE Fact_Market_Regime_V2 ADD COLUMN IF NOT EXISTS Cluster_Centroids_JSON TEXT NULL;"),
        ("Label_Map_JSON", "ALTER TABLE Fact_Market_Regime_V2 ADD COLUMN IF NOT EXISTS Label_Map_JSON TEXT NULL;"),
    ]:
        cursor.execute(
            f"""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'fact_market_regime_v2' AND column_name = '{column_name.lower()}'
            """
        )
        if cursor.fetchone() is None:
            cursor.execute(alter_sql)
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
    df["Return_Mean"] = df["Log_Return"].rolling(window=momentum_window, min_periods=momentum_window).mean()
    df["Return_Std"] = df["Log_Return"].rolling(window=momentum_window, min_periods=momentum_window).std().clip(lower=1e-8)
    df["Trend_Ratio"] = df["Return_Mean"] / df["Return_Std"]
    df["Realized_Vol"] = df["Log_Return"].rolling(window=context_window, min_periods=context_window).std().clip(lower=1e-8)
    df["Realized_Vol_Z"] = (
        (df["Realized_Vol"] - df["Realized_Vol"].rolling(context_window, min_periods=context_window).mean())
        / df["Realized_Vol"].rolling(context_window, min_periods=context_window).std().clip(lower=1e-8)
    )

    # Session volume proxy (rolling z-score)
    df["Volume_Mean"] = df["Volume"].rolling(window=vol_window, min_periods=vol_window).mean()
    df["Volume_Std"] = df["Volume"].rolling(window=vol_window, min_periods=vol_window).std().clip(lower=1e-8)
    df["Session_Volume_Z"] = (df["Volume"] - df["Volume_Mean"]) / df["Volume_Std"]

    # Temporal context
    df["ATR_Z"] = (
        (df["ATR"] - df["ATR"].rolling(context_window, min_periods=context_window).mean())
        / df["ATR"].rolling(context_window, min_periods=context_window).std().clip(lower=1e-8)
    )
    df["ADX_Delta"] = df["ADX"].diff().fillna(0)

    bb = ta.volatility.BollingerBands(close=df["Close"], window=bb_window, window_dev=2)
    df["BB_Width"] = (bb.bollinger_hband() - bb.bollinger_lband()) / df["Close"].replace(0, np.nan)
    df["BB_Width_Z"] = (
        (df["BB_Width"] - df["BB_Width"].rolling(context_window, min_periods=context_window).mean())
        / df["BB_Width"].rolling(context_window, min_periods=context_window).std().clip(lower=1e-8)
    )

    # Volatility persistence
    pers_window = trend_window
    df["Vol_Persistence"] = (
        df["ATR"].rolling(pers_window, min_periods=pers_window).mean()
        / df["ATR"].rolling(pers_window, min_periods=pers_window).std().clip(lower=1e-5)
    )

    # Explicit warm-up cutoff to avoid unstable head-of-window values.
    warmup_cutoff = max(14, vol_window, context_window, momentum_window, bb_window, pers_window) + 1
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
        logger.warning(f"         [{symbol} {granularity}] Invalid k={k}. Must be >= 2. Skipping.")
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
    for i, (atr_c, adx_c) in enumerate(centers[:, :2]):  # only first two dims for labels
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
    """Temp-table + upsert – production pattern matching layer0."""
    if df.empty or dry_run:
        return 0

    df_write = df.copy()
    df_write["Asset_ID"] = asset_id
    df_write["Granularity"] = granularity
    df_write["Regime_Model_Version"] = model_version
    df_write["Cluster_Centroids_JSON"] = json.dumps(lineage.get("cluster_centroids"), sort_keys=True) if lineage else None
    df_write["Label_Map_JSON"] = json.dumps(lineage.get("label_map"), sort_keys=True) if lineage else None
    df_write["Created_At"] = datetime.now()
    df_write["Updated_At"] = datetime.now()

    # Rename to match target schema
    df_write = df_write.rename(
        columns={
            "ATR": "ATR_Value",
            "ADX": "ADX_Value",
        }
    )

    cursor = conn.cursor()
    temp_name = "TempRegimeV2"

    # Create temp table
    cursor.execute(f"""
        DROP TABLE IF EXISTS {temp_name};
        CREATE TEMP TABLE {temp_name} (
            Timestamp TIMESTAMPTZ,
            Asset_ID INT,
            Granularity VARCHAR(10),
            Regime_Label VARCHAR(50),
            ATR_Value FLOAT,
            ADX_Value FLOAT,
            Session_Volume_Z FLOAT,
            Regime_Model_Version VARCHAR(30),
            Cluster_Centroids_JSON TEXT,
            Label_Map_JSON TEXT,
            Created_At TIMESTAMPTZ,
            Updated_At TIMESTAMPTZ
        )
    """)

    # Bulk insert to temp
    cols = [
        "Timestamp", "Asset_ID", "Granularity", "Regime_Label",
        "ATR_Value", "ADX_Value", "Session_Volume_Z",
        "Regime_Model_Version", "Cluster_Centroids_JSON", "Label_Map_JSON", "Created_At", "Updated_At"
    ]
    placeholders = ",".join(["%s"] * len(cols))
    insert_sql = f"INSERT INTO {temp_name} ({','.join(cols)}) VALUES ({placeholders})"
    rows = [tuple(row) for row in df_write[cols].itertuples(index=False, name=None)]
    cursor.executemany(insert_sql, rows)

    # Atomic upsert
    upsert_sql = f"""
        INSERT INTO Fact_Market_Regime_V2 ({','.join(cols)})
        SELECT {','.join(cols)} FROM {temp_name}
        ON CONFLICT (Timestamp, Asset_ID, Granularity)
        DO UPDATE SET
            Regime_Label = EXCLUDED.Regime_Label,
            ATR_Value = EXCLUDED.ATR_Value,
            ADX_Value = EXCLUDED.ADX_Value,
            Session_Volume_Z = EXCLUDED.Session_Volume_Z,
            Regime_Model_Version = EXCLUDED.Regime_Model_Version,
            Cluster_Centroids_JSON = EXCLUDED.Cluster_Centroids_JSON,
            Label_Map_JSON = EXCLUDED.Label_Map_JSON,
            Updated_At = EXCLUDED.Updated_At;
    """
    cursor.execute(upsert_sql)
    rows_affected = cursor.rowcount
    conn.commit()

    # Cleanup
    cursor.execute(f"DROP TABLE {temp_name}")
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
                f"""
                SELECT MAX(Timestamp)
                FROM Fact_Market_Regime_V2
                WHERE Asset_ID = {asset_id} AND Granularity = '{granularity}'
                """
            )
            row = cursor.fetchone()
            if row and row[0]:
                max_ts = row[0]
                # Overlap buffer (covers ATR/ADX + rolling windows)
                buffer_hours = 200 if granularity == "H1" else 800
                start_ts = max_ts - pd.Timedelta(hours=buffer_hours)
                logger.info(f"   Incremental mode – starting from {start_ts} (overlap buffer)")

        # Fetch prices
        query = f"""
            SELECT Timestamp, "Open", High, Low, "Close", Volume
            FROM Fact_Market_Prices
            WHERE Asset_ID = {asset_id} AND Granularity = '{granularity}'
        """
        if start_ts is not None:
            ts_str = start_ts.strftime("%Y-%m-%d %H:%M:%S")
            query += f" AND Timestamp >= '{ts_str}'"
        query += " ORDER BY Timestamp ASC"

        df_prices = pd.read_sql(query, conn, parse_dates=["Timestamp"])
        logger.info(f"   Fetched {len(df_prices):,} price rows.")

        if len(df_prices) < min_rows:
            logger.warning(f"   Skipped – insufficient raw data ({len(df_prices)} < {min_rows})")
            return

        # Features
        df_feat = calculate_features(df_prices, granularity)

        if len(df_feat) < min_rows:
            logger.warning(f"   Skipped after feature engineering – only {len(df_feat)} usable rows")
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
    parser = argparse.ArgumentParser(description="Layer 1 Regime Ingestion V2 (production)")
    parser.add_argument("--symbol", type=str, help="Single symbol filter (e.g. EUR_USD)")
    parser.add_argument("--granularity", type=str, choices=["H1", "H4"], help="Single granularity filter")
    parser.add_argument("--full-rebuild", action="store_true", help="Reprocess entire history")
    parser.add_argument("--model-version", type=str, default=None)
    parser.add_argument("--min-rows", type=int, default=1000)
    parser.add_argument("--silhouette-threshold", type=float, default=0.25)
    parser.add_argument("--k", type=int, default=4, help="Number of regimes (KMeans)")
    parser.add_argument("--dry-run", action="store_true", help="Compute only, no DB write")
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
    logger.info(f"Mode: {'FULL REBUILD' if args.full_rebuild else 'INCREMENTAL'} | "
                f"Model: {args.model_version} | k={args.k}")
    if args.backfill:
        logger.info("Backfill mode enabled: low-silhouette slices will still be written.")
    logger.info("=" * 80)

    conn = get_db_connection()
    try:
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

        logger.info("PIPELINE COMPLETE – All regimes ingested into Fact_Market_Regime_V2.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
