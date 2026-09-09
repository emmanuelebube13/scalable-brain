import pandas as pd
import numpy as np
import sys
sys.path.append("/home/emmanuel/Documents/Scalable_Brain/scalable-brain")

from src.regime.structural import build_structural_labels

hours = 8000
idx = pd.date_range("2020-01-01", periods=hours, freq="h", tz="UTC")
high_vol_hours = np.isin(idx.hour, np.arange(8, 17))
returns = np.random.normal(0, 0.001, size=hours)
returns[high_vol_hours] *= 3

price = 100 * np.exp(np.cumsum(returns))
high = price * (1 + 0.0005)
high[high_vol_hours] = price[high_vol_hours] * (1 + 0.0015)
low = price * (1 - 0.0005)
low[high_vol_hours] = price[high_vol_hours] * (1 - 0.0015)

df = pd.DataFrame({
    "Open": price,
    "High": high,
    "Low": low,
    "Close": price
}, index=idx)

out = build_structural_labels(df, return_indicators=True, granularity="H1")

# Let's see if High-Vol vs Ranging correlates heavily with time of day
# Filter to non-UNKNOWN, non-trending (ADX <= 25)
filtered = out[(out["regime"] != "UNKNOWN") & (out["adx"] <= 25)].copy()
filtered["hour"] = filtered["bar_time"].dt.hour

high_vol = filtered[filtered["regime"] == "High-Vol"]
ranging = filtered[filtered["regime"] == "Ranging"]

print(f"Total non-trending hours tested: {len(filtered)}")
print(f"High-Vol hours between 8-16 UTC: {len(high_vol[high_vol['hour'].isin(np.arange(8, 17))])} / {len(high_vol)}")
print(f"Ranging hours between 8-16 UTC: {len(ranging[ranging['hour'].isin(np.arange(8, 17))])} / {len(ranging)}")
print("Mean z-score by hour of day:")
print(filtered.groupby("hour")["vol_zscore"].mean())
