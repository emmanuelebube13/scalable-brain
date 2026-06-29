"""MODEL-002 — point-in-time (trailing-only) feature definitions.

Every feature at bar ``t`` depends only on bars ``<= t`` (no look-ahead). Rolling
features are null for their warm-up window (first ``N-1`` bars) so downstream training
can exclude them. Reuses the causal ATR/ADX implementations in
``src/layer0/indicators.py`` (both are trailing EWM/rolling — no leakage).
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from src.layer0.indicators import adx as _adx
from src.layer0.indicators import atr as _atr

# Window parameters (also written to schema.json).
RETURNS_WARMUP = 1
ATR_PERIOD = 14
ADX_PERIOD = 14
PRICE_POSITION_WINDOW = 20
VOLATILITY_WINDOW = 20

# Emitted feature columns (fixed order = determinism).
FEATURE_COLUMNS: List[str] = [
    "returns_1",
    "atr_14",
    "adx_14",
    "price_position_20",
    "volatility_20",
]

# The ordered vector MODEL-003 (HMM / K-Means) consumes. Documented in schema.json so
# the regime engine binds to a stable contract.
REGIME_FEATURE_COLUMNS: List[str] = ["atr_14", "adx_14", "volatility_20", "returns_1"]

# Per-feature warm-up (number of leading null rows expected per instrument).
WARMUP_BY_FEATURE: Dict[str, int] = {
    "returns_1": RETURNS_WARMUP,
    "atr_14": ATR_PERIOD - 1,
    "adx_14": 2 * ADX_PERIOD - 1,
    "price_position_20": PRICE_POSITION_WINDOW - 1,
    "volatility_20": VOLATILITY_WINDOW,  # rolling std of returns_1 (itself 1-bar warmed)
}

FEATURE_FORMULAE: Dict[str, str] = {
    "returns_1": "log(Close_t / Close_{t-1})  (trailing 1 bar; first bar = null)",
    "atr_14": "ATR(14) via causal EWM of true range (src.layer0.indicators.atr); first 13 bars null",
    "adx_14": "ADX(14) (src.layer0.indicators.adx); first 27 bars null",
    "price_position_20": "(Close - min(Low,20)) / (max(High,20) - min(Low,20)) in [0,1]; constant-price window -> null",
    "volatility_20": "rolling std of returns_1 over trailing 20 bars; first 20 bars null",
}


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute trailing-only features for one (instrument, granularity) series.

    ``df`` must be sorted ascending by ``bar_time_utc`` and contain columns
    ``open, high, low, close, volume``. Returns ``df`` plus the FEATURE_COLUMNS.
    """
    out = df.copy()
    close = out["close"].astype("float64")
    high = out["high"].astype("float64")
    low = out["low"].astype("float64")

    # returns_1 — log return; prices are strictly positive (FX) so this is NaN-safe
    # except the unavoidable first-bar warm-up.
    out["returns_1"] = np.log(close / close.shift(1))

    # atr_14 — reuse causal EWM ATR, then null the warm-up region.
    atr = _atr(high, low, close, ATR_PERIOD).astype("float64")
    atr.iloc[: ATR_PERIOD - 1] = np.nan
    out["atr_14"] = atr.to_numpy()

    # adx_14 — reuse ADX, null warm-up (ADX needs ~2*period to stabilise).
    adx = _adx(high, low, close, ADX_PERIOD).astype("float64")
    adx.iloc[: 2 * ADX_PERIOD - 1] = np.nan
    out["adx_14"] = adx.to_numpy()

    # price_position_20 — trailing channel position, divide-by-zero (constant price) -> null.
    roll_low = low.rolling(PRICE_POSITION_WINDOW, min_periods=PRICE_POSITION_WINDOW).min()
    roll_high = high.rolling(PRICE_POSITION_WINDOW, min_periods=PRICE_POSITION_WINDOW).max()
    rng = (roll_high - roll_low).replace(0.0, np.nan)
    out["price_position_20"] = ((close - roll_low) / rng).clip(0.0, 1.0)

    # volatility_20 — trailing std of returns.
    out["volatility_20"] = out["returns_1"].rolling(
        VOLATILITY_WINDOW, min_periods=VOLATILITY_WINDOW
    ).std()

    return out
