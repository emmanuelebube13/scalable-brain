from __future__ import annotations
import pandas as pd
import numpy as np
from src.layer0.strategies.research.precision_swing import PrecisionSwing

CLOSES = []
# generate 80 bars of a noisy sine wave with an upward drift
for i in range(80):
    val = 10.0 + i * 0.05 + 2.0 * np.sin(i / 5.0)
    CLOSES.append(round(val, 2))

# generate 80 bars of a noisy sine wave with a downward drift
for i in range(80, 160):
    val = 15.0 - (i - 80) * 0.05 + 2.0 * np.sin(i / 5.0)
    CLOSES.append(round(val, 2))

HIGHS = [round(c + 0.50, 2) for c in CLOSES]
LOWS = [round(c - 0.50, 2) for c in CLOSES]

idx = pd.date_range("2020-01-01", periods=len(CLOSES), freq="4h", tz="UTC")
h4 = pd.DataFrame(
    {
        "Open": CLOSES,
        "High": HIGHS,
        "Low": LOWS,
        "Close": CLOSES,
        "Volume": 1.0,
    },
    index=idx,
)

orders = list(PrecisionSwing().generate_orders({"H4": h4}))
print(f"Found {len(orders)} orders")
for o in orders:
    print(o.decision_bar, o.direction, "stop:", o.stop.price, "tp:", o.exits[0].price)

print("CLOSES array:")
print("[" + ", ".join([f"{c:.2f}" for c in CLOSES]) + "]")
