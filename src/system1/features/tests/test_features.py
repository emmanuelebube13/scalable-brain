"""Unit / leakage / bounds tests for MODEL-002 features (no DB / no network)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from src.system1.features import definitions as D


def _series(n=80, seed=0):
    rng = np.random.default_rng(seed)
    base = 1.10 + np.cumsum(rng.normal(0, 0.001, n))
    t0 = datetime(2020, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(n):
        c = float(base[i])
        o = c - rng.normal(0, 0.0005)
        hi = max(o, c) + abs(rng.normal(0, 0.0005))
        lo = min(o, c) - abs(rng.normal(0, 0.0005))
        rows.append(
            {
                "asset_id": 1,
                "bar_time_utc": t0 + timedelta(days=i),
                "open": o,
                "high": hi,
                "low": lo,
                "close": c,
                "volume": 100,
            }
        )
    return pd.DataFrame(rows)


def test_returns_1_matches_hand_computation():
    df = _series()
    out = D.compute_features(df)
    expected = np.log(df["close"].iloc[5] / df["close"].iloc[4])
    assert np.isclose(out["returns_1"].iloc[5], expected)
    # first bar is warm-up null
    assert pd.isna(out["returns_1"].iloc[0])


def test_price_position_in_bounds():
    out = D.compute_features(_series())
    pp = out["price_position_20"].dropna()
    assert ((pp >= 0.0) & (pp <= 1.0)).all()


def test_warmup_nulls_present():
    out = D.compute_features(_series())
    # First N-1 rows null for each rolling feature.
    assert pd.isna(out["atr_14"].iloc[: D.ATR_PERIOD - 1]).all()
    assert pd.isna(out["price_position_20"].iloc[: D.PRICE_POSITION_WINDOW - 1]).all()
    assert pd.isna(out["adx_14"].iloc[: 2 * D.ADX_PERIOD - 1]).all()


def test_no_nan_in_nonwarmup_returns():
    out = D.compute_features(_series())
    # After the 1-bar warm-up, returns_1 must be fully defined (no NaN) for positive prices.
    assert not out["returns_1"].iloc[1:].isna().any()


def test_constant_price_window_no_divzero():
    # Constant prices -> price_position_20 null (not inf/NaN-from-div), no exception.
    n = 40
    t0 = datetime(2020, 1, 1, tzinfo=timezone.utc)
    df = pd.DataFrame(
        [
            {
                "asset_id": 1,
                "bar_time_utc": t0 + timedelta(days=i),
                "open": 1.10,
                "high": 1.10,
                "low": 1.10,
                "close": 1.10,
                "volume": 100,
            }
            for i in range(n)
        ]
    )
    out = D.compute_features(df)
    assert out["price_position_20"].isna().all()
    assert not np.isinf(out["price_position_20"].to_numpy(dtype="float64", na_value=0.0)).any()


def test_no_lookahead_leakage():
    """Inject a future shock — only rows at/after the shock may change."""
    df = _series()
    out0 = D.compute_features(df)
    idx = 50
    shocked = df.copy()
    shocked.loc[idx, "close"] *= 10.0
    shocked.loc[idx, "high"] *= 10.0
    out1 = D.compute_features(shocked)
    for col in D.FEATURE_COLUMNS:
        a = out0[col].iloc[:idx].to_numpy()
        b = out1[col].iloc[:idx].to_numpy()
        assert np.array_equal(a, b, equal_nan=True), f"leakage: {col} changed before shock"
