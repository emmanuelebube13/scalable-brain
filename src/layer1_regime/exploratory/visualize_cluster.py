import sys
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy import text
from dotenv import load_dotenv

# Ensure the repo root is importable so ``src.common`` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from src.common.db import get_engine  # noqa: E402

# --- Configuration ---
load_dotenv()


def visualize_regimes(asset_id, symbol):
    print(f"Fetching data for {symbol} visualization...")

    # Random sample of 10,000 rows so the graph isn't too cluttered to read.
    # (SQL Server NEWID() -> PostgreSQL random(); TOP N -> LIMIT N.)
    query = text("""
        SELECT atr_value AS "ATR_Value", adx_value AS "ADX_Value",
               regime_label AS "Regime_Label"
        FROM fact_market_regime
        WHERE asset_id = :asset_id AND atr_value > 0
        ORDER BY random()
        LIMIT 10000
        """)
    with get_engine().connect() as ec:
        df = pd.read_sql(query, ec, params={"asset_id": asset_id})

    if df.empty:
        print(f"No data found for {symbol}.")
        return

    print("Generating scatter plot...")

    # --- Build the Graph ---
    plt.figure(figsize=(12, 8))
    sns.set_theme(style="whitegrid")

    # Define distinct colors for our 4 business regimes
    custom_palette = {
        "Trending_HighVol": "#e74c3c",  # Red (Aggressive)
        "Trending_LowVol": "#2ecc71",  # Green (Steady)
        "Ranging_HighVol": "#9b59b6",  # Purple (Chaotic/Danger)
        "Ranging_LowVol": "#3498db",  # Blue (Quiet/Sideways)
    }

    sns.scatterplot(
        data=df,
        x="ADX_Value",
        y="ATR_Value",
        hue="Regime_Label",
        palette=custom_palette,
        alpha=0.6,
        s=30,
    )

    plt.title(
        f"K-Means Market Regimes: {symbol} (10k Hour Sample)",
        fontsize=16,
        fontweight="bold",
    )
    plt.xlabel("ADX (Trend Strength)", fontsize=12)
    plt.ylabel("ATR (Volatility / Price Movement)", fontsize=12)

    # Add business logic lines to show the Medians
    median_adx = df["ADX_Value"].median()
    median_atr = df["ATR_Value"].median()
    plt.axvline(
        median_adx, color="black", linestyle="--", alpha=0.5, label="ADX Median"
    )
    plt.axhline(
        median_atr, color="black", linestyle="--", alpha=0.5, label="ATR Median"
    )

    plt.legend(title="Market Weather State")
    plt.tight_layout()

    # Save the file
    save_path = f"regime_clusters_{symbol}.png"
    plt.savefig(save_path, dpi=300)
    print(f"✅ Visualization saved to: {save_path}")


if __name__ == "__main__":
    # Let's visualize the Euro to start
    visualize_regimes(1, "EUR_USD")
