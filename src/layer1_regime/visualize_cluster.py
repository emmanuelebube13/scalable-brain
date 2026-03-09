import os
import pyodbc
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
CONN_STR = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={os.getenv('DB_SERVER', 'localhost')};DATABASE=ForexBrainDB;UID={os.getenv('DB_USER', 'sa')};PWD={os.getenv('DB_PASS')}"

def visualize_regimes(asset_id, symbol):
    print(f"Fetching data for {symbol} visualization...")
    
    conn = pyodbc.connect(CONN_STR)
    # We pull a random sample of 10,000 rows so the graph isn't too cluttered to read
    query = f"""
        SELECT TOP 10000 ATR_Value, ADX_Value, Regime_Label 
        FROM Fact_Market_Regime 
        WHERE Asset_ID = {asset_id} AND ATR_Value > 0
        ORDER BY NEWID() 
    """
    
    import warnings
    warnings.filterwarnings('ignore', category=UserWarning) # Hide pandas SQL warning
    df = pd.read_sql(query, conn)
    conn.close()

    if df.empty:
        print(f"No data found for {symbol}.")
        return

    print("Generating scatter plot...")
    
    # --- Build the Graph ---
    plt.figure(figsize=(12, 8))
    sns.set_theme(style="whitegrid")
    
    # Define distinct colors for our 4 business regimes
    custom_palette = {
        'Trending_HighVol': '#e74c3c', # Red (Aggressive)
        'Trending_LowVol': '#2ecc71',  # Green (Steady)
        'Ranging_HighVol': '#9b59b6',  # Purple (Chaotic/Danger)
        'Ranging_LowVol': '#3498db'    # Blue (Quiet/Sideways)
    }

    sns.scatterplot(
        data=df, 
        x='ADX_Value', 
        y='ATR_Value', 
        hue='Regime_Label', 
        palette=custom_palette,
        alpha=0.6,
        s=30
    )

    plt.title(f'K-Means Market Regimes: {symbol} (10k Hour Sample)', fontsize=16, fontweight='bold')
    plt.xlabel('ADX (Trend Strength)', fontsize=12)
    plt.ylabel('ATR (Volatility / Price Movement)', fontsize=12)
    
    # Add business logic lines to show the Medians
    median_adx = df['ADX_Value'].median()
    median_atr = df['ATR_Value'].median()
    plt.axvline(median_adx, color='black', linestyle='--', alpha=0.5, label='ADX Median')
    plt.axhline(median_atr, color='black', linestyle='--', alpha=0.5, label='ATR Median')
    
    plt.legend(title='Market Weather State')
    plt.tight_layout()
    
    # Save the file
    save_path = f"regime_clusters_{symbol}.png"
    plt.savefig(save_path, dpi=300)
    print(f"✅ Visualization saved to: {save_path}")

if __name__ == "__main__":
    # Let's visualize the Euro to start
    visualize_regimes(5, "EUR_USD")