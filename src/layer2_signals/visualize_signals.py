import os
import pyodbc
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from dotenv import load_dotenv
import warnings

warnings.filterwarnings('ignore', category=UserWarning)

# Configuration
load_dotenv()
DB_SERVER = os.getenv('DB_SERVER')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')
DB_NAME = 'ForexBrainDB'

# Ensure the exact target directory exists
output_dir = "/home/eem/Documents/trading_system/doc/ml"
os.makedirs(output_dir, exist_ok=True)

def visualize_signal_distribution():
    print("Fetching signal distribution from Fact_Signals...")
    conn = pyodbc.connect(f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={DB_SERVER};DATABASE={DB_NAME};UID={DB_USER};PWD={DB_PASS}')
    
    # Query to count Buys (1) and Sells (-1), ignoring Holds (0) for the chart
    query = """
    SELECT 
        s.Strategy_Name, 
        f.Signal_Value, 
        COUNT(*) as Signal_Count
    FROM Fact_Signals f
    JOIN Dim_Strategy_Registry s ON f.Strategy_ID = s.Strategy_ID
    WHERE f.Signal_Value IN (1, -1)
    GROUP BY s.Strategy_Name, f.Signal_Value
    ORDER BY s.Strategy_Name, f.Signal_Value DESC
    """
    
    df = pd.read_sql(query, conn)
    conn.close()

    if df.empty:
        print("No active Buy/Sell signals found. Something went wrong.")
        return

    # Map signal values to readable labels
    df['Signal_Type'] = df['Signal_Value'].map({1: 'Buy (1)', -1: 'Sell (-1)'})

    # Build the Chart
    print("Generating distribution chart...")
    plt.figure(figsize=(14, 8))
    sns.set_theme(style="whitegrid")
    
    # Grouped Bar Chart
    ax = sns.barplot(
        data=df, 
        x='Strategy_Name', 
        y='Signal_Count', 
        hue='Signal_Type',
        palette={'Buy (1)': '#2ecc71', 'Sell (-1)': '#e74c3c'}
    )

    plt.title('Layer 2: Signal Distribution by Strategy (Buy vs. Sell)', fontsize=16, fontweight='bold')
    plt.xlabel('Strategy Name', fontsize=12)
    plt.ylabel('Total Number of Signals Generated', fontsize=12)
    plt.xticks(rotation=45, ha='right')
    
    # Add exact numbers on top of the bars
    for i in ax.containers:
        ax.bar_label(i, padding=3)

    plt.tight_layout()
    
    # Save to the specific user-defined path
    save_path = os.path.join(output_dir, "layer2_signal_distribution.png")
    plt.savefig(save_path, dpi=300)
    print(f"✅ Visualization saved successfully to: {save_path}")

if __name__ == "__main__":
    visualize_signal_distribution()