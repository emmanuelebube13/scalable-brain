import json
import pandas as pd
from src.registry import catalog
from src.layer0.strategies.v2_harness import build_frames

# Strategy 34: macd_divergence
record = catalog.by_id("34")
strategy = catalog.instantiate(record)

meta = strategy.metadata
inst = "EUR_USD"

frames = build_frames(
    inst,
    meta.primary_granularity,
    meta.context_granularities,
    lookback_years=3,
)

sliced_frames = {}
for g, df in frames.items():
    sliced_frames[g] = df.iloc[-300:].copy()

intents = strategy.generate_orders(sliced_frames)

while len(intents) == 0 and len(sliced_frames[meta.primary_granularity]) > 200:
    for g, df in sliced_frames.items():
        sliced_frames[g] = df.iloc[:-1]
    intents = strategy.generate_orders(sliced_frames)

if len(intents) == 0:
    print("Could not find a signal!")
else:
    intent = intents[-1]
    bar_ts = intent.decision_bar
    for g, df in sliced_frames.items():
        sliced_frames[g] = df.loc[:bar_ts]
    
    final_intents = strategy.generate_orders(sliced_frames)
    final_intent = final_intents[-1]
    
    out = {
        "strategy_id": "34",
        "instrument": inst,
        "primary_granularity": meta.primary_granularity,
        "inputs": {},
        "outputs": {
            "decision_bar": final_intent.decision_bar.isoformat(),
            "direction": str(final_intent.direction),
            "entry_kind": str(final_intent.entry),
            "entry_price": float(final_intent.entry_price) if final_intent.entry_price is not None else None,
            "stop_loss_price": float(final_intent.stop.price),
            "exits": [
                {
                    "label": ex.label,
                    "kind": str(ex.kind),
                    "price": float(ex.price) if ex.price is not None else None,
                    "fraction": float(ex.fraction)
                } for ex in final_intent.exits
            ]
        }
    }
    for g, df in sliced_frames.items():
        df_reset = df.reset_index()
        df_reset["timestamp"] = df_reset["timestamp"].dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        out["inputs"][g] = df_reset.to_dict(orient="records")
        
    with open("reference_vector.json", "w") as f:
        json.dump(out, f, indent=2)
    print("Success! Generated reference_vector.json with decision bar:", final_intent.decision_bar)

