import joblib
import pandas as pd
import numpy as np

model = joblib.load("models/champion_model.pkl")
pre = joblib.load("models/champion_preprocessor.pkl")

# We need to know what features the preprocessor expects.
# Let's inspect pre.feature_names_in_
print("Expected features:", pre.feature_names_in_)

for name, trans, cols in pre.transformers_:
    print(f"Transformer {name} applies to columns {cols}")

# Create a row with unknown strategy_id and NaN row
row = {feat: np.nan for feat in pre.feature_names_in_}
row["strategy_id"] = "999999"
row["regime_causal"] = "Trending-Up"
row["entry_signal_type"] = "breakout"

df = pd.DataFrame([row])

# Run it through preprocessor
X = pre.transform(df)

# Run it through model
prob = model.predict_proba(X)
print("Score for unknown strategy/NaN row:", prob[:, 1])
