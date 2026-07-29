"""FIX-S1-008 Fix 1 — target-leakage guard tests for the Layer 3 gatekeeper.

Two independent leakage sources are covered:

  Source A: post-trade outcome columns (R_Multiple, Exit_Reason, ...) becoming
            model features. Guarded by :func:`test_outcome_columns_excluded`.

  Source B: rolling strategy-performance windows that include the current row's
            own realized label (no ``.shift(1)``). Guarded by
            :func:`test_own_label_does_not_leak_into_own_features`.

The Source-B test is the strict, correct formulation of "features are label
independent": perturbing row *i*'s own ``Is_Winner`` / ``R_Multiple`` must not
change row *i*'s feature vector. It deliberately does NOT assert that *future*
rows are unchanged — using a *past* trade's outcome is legitimate signal, only
using the current row's own outcome is leakage.

These tests use an in-memory synthetic fixture; they do not touch the database
(``fact_signals`` / ``fact_trade_outcomes`` are empty in this environment).
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

# Make ``src`` importable when pytest is run from the repo root.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.layer3_ml.training.train_ml_gatekeeper import (  # noqa: E402
    POST_TRADE_OUTCOME_COLS,
    TARGET_COL,
    comprehensive_feature_engineering,
    select_feature_columns,
)


def _make_fixture(n_per_strategy: int = 30, seed: int = 7) -> pd.DataFrame:
    """Deterministic raw-signal frame with two strategies and known outcomes.

    Includes every post-trade outcome column (to prove they are excluded) plus a
    couple of legitimate non-leaky feature inputs. Rows are pre-sorted by unique
    Timestamp so the engineered frame keeps a stable 0..n-1 index (the pipeline
    sorts by Timestamp and resets the index).
    """
    rng = np.random.default_rng(seed)
    strategies = ["A", "B"]
    rows = []
    ts = pd.Timestamp("2026-01-01 00:00:00")
    for k in range(n_per_strategy):
        for strat in strategies:
            is_winner = int(rng.integers(0, 2))
            rows.append(
                {
                    "Timestamp": ts,
                    "Granularity_Key": "H1",
                    "Strategy_ID": strat,
                    "Is_Winner": is_winner,
                    # Post-trade outcome columns (realized after close -> leakage):
                    "R_Multiple": float(rng.normal(0.2 if is_winner else -0.8, 0.5)),
                    "Holding_Bars": int(rng.integers(1, 40)),
                    "Exit_Reason": "TP" if is_winner else "SL",
                    "Entry_Signal_Type": "breakout",
                    "ATR_SL_Multiplier": 1.0,
                    "ATR_TP_Multiplier": 3.0,
                    # Legitimate, pre-decision feature inputs:
                    "ADX_Value": float(rng.uniform(10, 45)),
                    "Signal_Confidence": float(rng.uniform(0.3, 0.9)),
                    "Signal_Value": float(rng.choice([-1.0, 1.0])),
                }
            )
            ts += pd.Timedelta(hours=1)
    return pd.DataFrame(rows).sort_values("Timestamp").reset_index(drop=True)


def _cells_equal(a, b) -> bool:
    """Scalar equality treating NaN == NaN as equal."""
    a_na = pd.isna(a)
    b_na = pd.isna(b)
    if a_na or b_na:
        return bool(a_na and b_na)
    return bool(a == b)


def test_outcome_columns_excluded():
    """Source A: no post-trade outcome column (nor the target) is a feature."""
    df = comprehensive_feature_engineering(_make_fixture())
    feature_cols = set(select_feature_columns(df.columns))

    leaked = feature_cols & set(POST_TRADE_OUTCOME_COLS)
    assert (
        not leaked
    ), f"post-trade outcome columns leaked into features: {sorted(leaked)}"
    assert TARGET_COL not in feature_cols, "target column present in features"


def test_own_label_does_not_leak_into_own_features():
    """Source B: perturbing row i's own label must not change row i's features.

    Before Fix 1.2 (no ``.shift(1)``) the rolling Strat_WinRate_* / Strat_Expectancy_*
    for row i include row i's own Is_Winner / R_Multiple, so this assertion fails.
    """
    df = _make_fixture()
    target = 45  # deep enough that the rolling window is fully populated

    base = comprehensive_feature_engineering(df.copy())

    perturbed_raw = df.copy()
    perturbed_raw.loc[target, "Is_Winner"] = 1 - int(
        perturbed_raw.loc[target, "Is_Winner"]
    )
    perturbed_raw.loc[target, "R_Multiple"] = (
        float(perturbed_raw.loc[target, "R_Multiple"]) + 5.0
    )
    perturbed = comprehensive_feature_engineering(perturbed_raw)

    feature_cols = select_feature_columns(base.columns)
    assert feature_cols, "no feature columns were produced by the fixture"

    changed = [
        col
        for col in feature_cols
        if not _cells_equal(base.iloc[target][col], perturbed.iloc[target][col])
    ]
    assert not changed, (
        "row's own realized label leaked into its own features "
        f"(these feature columns changed when only row {target}'s label was flipped): {changed}"
    )


def test_perturbing_label_still_affects_a_future_row():
    """Sanity: the fixture is sensitive enough to detect a real change.

    Flipping row i's label SHOULD move a later row's rolling stats (legitimate use
    of a past outcome). This guards against a vacuous green in the test above (e.g.
    if strategy-perf features silently stopped being produced).
    """
    df = _make_fixture()
    target = 45

    base = comprehensive_feature_engineering(df.copy())
    perturbed_raw = df.copy()
    perturbed_raw.loc[target, "Is_Winner"] = 1 - int(
        perturbed_raw.loc[target, "Is_Winner"]
    )
    perturbed = comprehensive_feature_engineering(perturbed_raw)

    winrate_cols = [c for c in base.columns if c.startswith("Strat_WinRate_")]
    assert winrate_cols, "strategy win-rate features were not produced"

    # Some row strictly after `target` in the same strategy must differ.
    diffs = (base[winrate_cols] != perturbed[winrate_cols]) & ~(
        base[winrate_cols].isna() & perturbed[winrate_cols].isna()
    )
    future_changed = diffs.iloc[target + 1 :].to_numpy().any()
    assert future_changed, "flipping a past label had no effect on any future feature"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
