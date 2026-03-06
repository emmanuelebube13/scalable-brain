"""
Layer 1: Market Regime Detection & Ingestion
=============================================
Fetches historical OHLCV data per asset, clusters market states via K-Means,
dynamically maps clusters to business regime labels, and writes the labeled
data into Fact_Market_Regime.
"""

import os
import pyodbc
import pandas as pd
import numpy as np
import ta
from dotenv import load_dotenv
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

# ── Configuration ────────────────────────────────────────────────────────────
load_dotenv()
CONN_STR = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={os.getenv('DB_SERVER', 'localhost')};"
    f"DATABASE=ForexBrainDB;"
    f"UID={os.getenv('DB_USER', 'sa')};"
    f"PWD={os.getenv('DB_PASS')}"
)

ASSETS = {5: "EUR_USD", 6: "GBP_USD", 7: "USD_JPY"}


# ── Step 1: Fetch OHLCV Data ────────────────────────────────────────────────
def fetch_ohlcv(conn, asset_id, symbol):
    """Fetch ALL historical OHLCV rows for a single asset."""
    query = """
        SELECT Timestamp, [Open], High, Low, [Close], Volume
        FROM Fact_Market_Prices
        WHERE Asset_ID = ?
        ORDER BY Timestamp ASC
    """
    df = pd.read_sql(query, conn, params=[asset_id], parse_dates=["Timestamp"])
    print(f"  [{symbol}] Fetched {len(df):,} rows from Fact_Market_Prices.")
    return df


# ── Step 2: Calculate Technical Features ─────────────────────────────────────
def calculate_features(df):
    """ATR-14 (volatility) and ADX-14 (trend strength)."""
    df = df.copy()
    df["ATR"] = ta.volatility.AverageTrueRange(
        df["High"], df["Low"], df["Close"], window=14
    ).average_true_range()

    df["ADX"] = ta.trend.ADXIndicator(
        df["High"], df["Low"], df["Close"], window=14
    ).adx()

    before = len(df)
    df.dropna(subset=["ATR", "ADX"], inplace=True)
    print(f"         Indicators calculated. {before - len(df)} warm-up rows dropped, {len(df):,} rows remaining.")
    return df


# ── Step 3: Cluster & Label ──────────────────────────────────────────────────
def cluster_and_label(df, symbol):
    """
    Scale ATR+ADX, run K-Means(4), then dynamically assign business labels
    by comparing each centroid to the median ATR / median ADX across centroids.
    """
    features = df[["ATR", "ADX"]].values

    # Scale
    scaler = StandardScaler()
    scaled = scaler.fit_transform(features)

    # Cluster
    kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
    df = df.copy()
    df["Cluster"] = kmeans.fit_predict(scaled)

    # Quality metric
    sil = silhouette_score(scaled, df["Cluster"])
    quality = "Excellent" if sil > 0.5 else "Acceptable" if sil > 0.3 else "Poor"
    print(f"         Silhouette Score: {sil:.4f} ({quality})")

    # Inverse-transform centroids back to original ATR / ADX scale
    centers = scaler.inverse_transform(kmeans.cluster_centers_)  # shape (4, 2)
    median_atr = np.median(centers[:, 0])
    median_adx = np.median(centers[:, 1])

    print(f"         Centroid medians  ->  ATR: {median_atr:.5f}  |  ADX: {median_adx:.2f}")

    # Dynamic label map: cluster_id -> business string
    label_map = {}
    for i, (atr_c, adx_c) in enumerate(centers):
        if adx_c >= median_adx and atr_c >= median_atr:
            label = "Trending_HighVol"
        elif adx_c >= median_adx and atr_c < median_atr:
            label = "Trending_LowVol"
        elif adx_c < median_adx and atr_c >= median_atr:
            label = "Ranging_HighVol"
        else:
            label = "Ranging_LowVol"
        label_map[i] = label
        print(f"         Cluster {i}  ATR={atr_c:.5f}  ADX={adx_c:.2f}  ->  {label}")

    df["Regime_Label"] = df["Cluster"].map(label_map)
    return df


# ── Step 4: Ensure Target Table Exists ───────────────────────────────────────
def ensure_table(conn):
    """Create Fact_Market_Regime if it doesn't already exist."""
    cursor = conn.cursor()
    cursor.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME = 'Fact_Market_Regime'
        )
        BEGIN
            CREATE TABLE Fact_Market_Regime (
                Timestamp   DATETIME     NOT NULL,
                Asset_ID    INT          NOT NULL,
                Regime_Label VARCHAR(50) NOT NULL,
                ATR_Value   FLOAT        NOT NULL,
                ADX_Value   FLOAT        NOT NULL,
                PRIMARY KEY (Timestamp, Asset_ID)
            );
            PRINT 'Created Fact_Market_Regime table.';
        END
    """)
    conn.commit()
    print("[DB] Fact_Market_Regime table verified.")


# ── Step 5: Batch Insert ─────────────────────────────────────────────────────
def ingest_regimes(conn, df, asset_id, symbol):
    """
    MERGE-based upsert: insert new rows, update existing ones.
    Uses fast_executemany for bulk throughput.
    """
    cursor = conn.cursor()
    cursor.fast_executemany = True

    rows = list(
        df[["Timestamp", "Regime_Label", "ATR", "ADX"]].itertuples(index=False, name=None)
    )

    # MERGE handles insert-or-update in a single atomic statement
    merge_sql = """
        MERGE Fact_Market_Regime AS target
        USING (SELECT ? AS Timestamp, ? AS Asset_ID, ? AS Regime_Label, ? AS ATR_Value, ? AS ADX_Value) AS source
        ON target.Timestamp = source.Timestamp AND target.Asset_ID = source.Asset_ID
        WHEN MATCHED THEN
            UPDATE SET Regime_Label = source.Regime_Label,
                       ATR_Value   = source.ATR_Value,
                       ADX_Value   = source.ADX_Value
        WHEN NOT MATCHED THEN
            INSERT (Timestamp, Asset_ID, Regime_Label, ATR_Value, ADX_Value)
            VALUES (source.Timestamp, source.Asset_ID, source.Regime_Label, source.ATR_Value, source.ADX_Value);
    """

    # Build parameter tuples: (Timestamp, Asset_ID, Regime_Label, ATR, ADX)
    params = [(ts, asset_id, label, atr, adx) for ts, label, atr, adx in rows]

    batch_size = 5000
    total = len(params)
    for i in range(0, total, batch_size):
        batch = params[i : i + batch_size]
        cursor.executemany(merge_sql, batch)
        conn.commit()
        print(f"  [{symbol}] Inserted batch {i // batch_size + 1}  ({min(i + batch_size, total):,}/{total:,} rows)")

    print(f"  [{symbol}] Ingestion complete. {total:,} rows written to Fact_Market_Regime.\n")


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print(" LAYER 1: Market Regime Detection & Ingestion Pipeline")
    print("=" * 70)

    conn = pyodbc.connect(CONN_STR)
    ensure_table(conn)

    for asset_id, symbol in ASSETS.items():
        print(f"\n{'─' * 50}")
        print(f"  Processing Asset {asset_id}: {symbol}")
        print(f"{'─' * 50}")

        df = fetch_ohlcv(conn, asset_id, symbol)
        if df.empty:
            print(f"  [{symbol}] No data found. Skipping.")
            continue

        df = calculate_features(df)
        df = cluster_and_label(df, symbol)
        ingest_regimes(conn, df, asset_id, symbol)

    conn.close()
    print("=" * 70)
    print(" Pipeline complete. All regimes ingested into Fact_Market_Regime.")
    print("=" * 70)


if __name__ == "__main__":
    main()
