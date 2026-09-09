import pandas as pd
import numpy as np

idx = pd.date_range("2026-09-01", periods=10, freq="h")
# Let's do 3 days, 4 hours each to see groupings
idx = pd.date_range("2026-09-01", periods=12, freq="6h")
s = pd.Series(range(12), index=idx)
grouped = s.groupby(s.index.time)

res = grouped.transform(lambda g: g.shift(1).rolling(window=2, min_periods=1).mean())

df = pd.DataFrame({"s": s, "res": res, "time": s.index.time})
print(df)
