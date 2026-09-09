import pandas as pd
df = pd.read_parquet('results/state/strategy_regime_attribution.parquet')
print("Columns:", df.columns)
print("Label source (from metadata if any)?")
if 'regime' in df.columns:
    print(df['regime'].value_counts())
