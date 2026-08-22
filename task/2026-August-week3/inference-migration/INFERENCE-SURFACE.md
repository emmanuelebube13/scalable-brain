# System 1 Inference Surface

To reproduce a signal, System 2 needs a specific subset of System 1's modules. This document outlines those files, their purpose, third-party dependencies, and blockers related to database or network access.

## Files required for inference

1. **`src/signals/build.py`**
   - **Purpose:** Core entrypoint `build_signals()` that loads the strategy modules, passes them the closed bars, and generates signal dictionaries (intents).
   - **Blockers:** 
     - **Database Access:** It imports `src.registry.catalog` which queries `dim_strategy` in the PostgreSQL database (`src/common/db.py`) to discover strategy metadata. This will fail on System 2 which has no DB access.

2. **`src/registry/catalog.py`**
   - **Purpose:** Looks up strategy records and instantiates the strategy classes.
   - **Blockers:** 
     - **Database Access:** Functions `by_id()` and `by_key()` use `src.common.db` to query the database.

3. **`src/layer0/strategies/v2_harness.py`**
   - **Purpose:** Defines `discover()` which scans the local directory structure to find contract-v2 strategy classes.

4. **`src/layer0/strategies/contract_v2.py`**
   - **Purpose:** Defines the `StrategyV2` base class, `TradeIntent`, and order types that the strategies return.

5. **`src/layer0/strategies/causal_structure.py`**
   - **Purpose:** Provides base math and classes for some strategies (e.g., `liquidity_grab_fade.py`).

6. **`src/layer0/data_access/indicators.py`**
   - **Purpose:** Vectorized technical indicators (like `ema`, `atr`, `macd`) used by the strategies.

7. **`src/regime/structural.py`**
   - **Purpose:** Contains the causal structural regime labels (CSRM) logic that currently routes live signals (imported by `src/signals/run.py` to tag regimes).
   - **Blockers:** None inherently, but note it pulls in `ta` which is slated for removal.

8. **Strategy Implementations (from the live map):**
   - **`src/layer0/strategies/research/macd_divergence.py`**
   - **`src/layer0/strategies/research/liquidity_grab_fade.py`**
   - **`src/layer0/strategies/research/weekly_day_reversal_ea.py`**
   - **Purpose:** The actual trading algorithms defining `generate_orders()`.

## Third-Party Dependencies (Pinned)

To run the above surface, System 2 requires the following exact versions of third-party libraries (as seen in System 1's `.venv`):

- **`numpy==2.4.4`**
- **`pandas==2.3.3`**
- **`scikit-learn==1.8.0`**
- **`joblib==1.5.3`**
- **`hmmlearn==0.3.3`**
- **`ta`** (currently used by `src/regime/structural.py` but flagged for removal in Step S3b)
