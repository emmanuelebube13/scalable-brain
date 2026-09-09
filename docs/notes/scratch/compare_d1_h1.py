import pandas as pd
import numpy as np
import sys
sys.path.append("/home/emmanuel/Documents/Scalable_Brain/scalable-brain")

from src.regime.structural import build_structural_labels

# Generate a multi-year random walk
days = 1500
np.random.seed(42)
returns = np.random.normal(0, 0.005, size=days * 24)

# Create H1 dataframe
idx_h1 = pd.date_range("2018-01-01", periods=days*24, freq="h", tz="UTC")
price_h1 = 100 * np.exp(np.cumsum(returns))
df_h1 = pd.DataFrame({
    "Open": price_h1,
    "High": price_h1 * 1.001,
    "Low": price_h1 * 0.999,
    "Close": price_h1
}, index=idx_h1)

# Create D1 dataframe by resampling
df_d1 = df_h1.resample("D").agg({
    "Open": "first",
    "High": "max",
    "Low": "min",
    "Close": "last"
}).dropna()

# Label D1
d1_labels = build_structural_labels(df_d1, return_indicators=True, granularity="D1")

# Label H1 with default (unscaled) settings
h1_labels = build_structural_labels(df_h1, return_indicators=True, granularity="H1")

# Map D1 labels to H1 by ffill
d1_aligned = d1_labels.set_index("bar_time")["regime"].reindex(h1_labels["bar_time"].dt.floor("D")).values
h1_labels["d1_regime_borrowed"] = d1_aligned

mask = (h1_labels["regime"] != "UNKNOWN") & (h1_labels["d1_regime_borrowed"] != "UNKNOWN")
valid_h1 = h1_labels[mask]

match_pct = (valid_h1["regime"] == valid_h1["d1_regime_borrowed"]).mean() * 100

print(f"Agreement between H1 unscaled 'regimes' and D1 regimes: {match_pct:.2f}%")

# Now what if we scaled the H1 parameters to calendar equivalent?
# ADX period = 14 * 24 = 336
# EMA fast = 50 * 24 = 1200
# EMA slow = 200 * 24 = 4800
# Vol window = 252 * 24 = 6048 (already scaled)
