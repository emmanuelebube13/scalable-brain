"""MODEL-003 — Regime engine HMM upgrade.

4-state Gaussian HMM (Trending-Up / Trending-Down / Ranging / High-Vol) with full
probability vectors and 3-bar persistence smoothing, writing additive probabilistic
columns to ``fact_market_regime_v2``. K-Means is retained as a first-class fallback.
Reuses MODEL-002's feature definitions (``src/system1/features/definitions.py``) so the
regime feature contract is identical to the feature store.
"""
