# Determinism and Reproducibility

System 2 MUST prove they compute identical signals to System 1 locally before trading.

## Contract
1. **Tolerances**:
   - `1e-9` (relative) for feature values (e.g. indicators like MACD, ATR) and state probabilities.
   - **Exact equality** on every discrete output: regime label, direction, instrument, granularity, bar timestamp. No tolerance for flipped labels.
2. **Reference Vector**:
   - We have supplied `reference_vector.json` which contains a frozen set of H4 bars for `EUR_USD` leading up to `2026-08-10T09:00:00Z`.
   - The boundary-adjacent bar is included to ensure boundary failure modes are caught.
   - Run the same `generate_orders(frames)` method with these exact bars as input. You must reproduce the exact `outputs` as specified in `reference_vector.json`.
3. **Sequence length**:
   - The sequence length of the bars passed to the strategy matters (especially for indicators with warm-ups like `macd` and `atr`). The vector includes the exact sequence of 210 bars required.

## Testing Instructions
Load `reference_vector.json`, construct a Pandas DataFrame for the `H4` key in `inputs`, cast `timestamp` back to `datetime64[ns, UTC]`, and set it as the index. Pass this mapping to `Strategy34.generate_orders(frames)`. Assert the resulting `intent` matches the `outputs` key.
