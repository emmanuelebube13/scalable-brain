"""Guards on the gatekeeper's feature basis (FEATURE_SET_VERSION 2.0.0).

Two of these protect things that would fail silently and expensively:

* ``_derive_features`` must keep producing ``trending_strength`` while any live bundle was
  fit on it. It is no longer trained on, so nothing else would notice its removal — the
  symptom would be every live signal going out unscored with
  ``MISSING_FEATURE:trending_strength``, which reads as a gatekeeper outage rather than as
  a training-side cleanup.
* ``atr_tp_multiplier`` must stay OUT of the required columns. Putting it back would drop
  every trade that declares no take-profit — ~12% of the table, and not a random 12%.
"""

import numpy as np
import pandas as pd
import pytest

from src.gatekeeper import train as T


def _row(**over):
    base = {
        "atr_value": 0.0012,
        "adx_value": 24.0,
        "regime_structural": "Trending-Up",
        "entry_signal_type": "long",
        "atr_sl_multiplier": 1.5,
        "atr_tp_multiplier": 3.0,
        "strategy_id": "58",
    }
    base.update(over)
    return pd.DataFrame([base])


# --- what the model learns from --------------------------------------------------


def test_strategy_id_is_not_a_trained_feature():
    """FIX-S1-012 and the WO-04B verdict. It carried 96.78% of gain importance and
    generalised to nothing; the degeneracy guard exists because of it."""
    assert "strategy_id" not in T.CATEGORICAL
    assert "strategy_id" not in T.NUMERIC_DERIVED


def test_strategy_id_is_still_available_for_the_degeneracy_check():
    """`per_cell_approval` groups by it, so it must stay in the frame — just not be
    something the model can learn from."""
    import inspect

    src = inspect.getsource(T.build_frame)
    assert "strategy_id" in src


def test_the_trended_strength_duplicate_is_not_trained_on():
    assert "trending_strength" not in T.NUMERIC_DERIVED


def test_trade_geometry_is_in_the_trained_basis():
    for col in ("atr_sl_multiplier", "atr_tp_multiplier", "risk_reward_ratio"):
        assert col in T.NUMERIC_DERIVED, col


# --- serve-side back-compat ------------------------------------------------------


def test_derive_features_still_produces_the_duplicate_for_live_bundles():
    """The live champion's preprocessor asks for it by name. Deleting the line is a live
    regression; excluding it from NUMERIC_DERIVED is the cleanup."""
    out = T._derive_features(_row())
    assert "trending_strength" in out.columns
    assert out["trending_strength"].iloc[0] == pytest.approx(24.0)


def test_derive_features_covers_every_feature_the_live_champion_asks_for():
    """Reads the SHIPPED artifact, not a list in this file — the list is what drifts."""
    import os

    from src.gatekeeper.score import Scorer

    models_dir = T.MODELS_DIR
    if not os.path.exists(os.path.join(models_dir, "champion_preprocessor.pkl")):
        pytest.skip("no live champion bundle on this machine")
    scorer = Scorer(models_dir)
    expected = getattr(scorer.preprocessor, "feature_names_in_", None)
    if expected is None:
        pytest.skip("shipped preprocessor records no feature names")

    produced = set(T._derive_features(_row()).columns)
    missing = [f for f in expected if f not in produced]
    assert not missing, (
        f"the live champion asks for {missing}, which _derive_features no longer "
        "produces — every live signal would refuse MISSING_FEATURE"
    )


# --- the payoff feature ----------------------------------------------------------


def test_risk_reward_ratio_is_reward_over_risk():
    out = T._derive_features(_row(atr_sl_multiplier=1.5, atr_tp_multiplier=3.0))
    assert out["risk_reward_ratio"].iloc[0] == pytest.approx(2.0)


def test_risk_reward_is_nan_when_no_target_was_declared():
    """NaN, not 0.0. A zero ratio says "target at the entry price", which is a real and
    very different statement from "no target"."""
    out = T._derive_features(_row(atr_tp_multiplier=np.nan))
    assert np.isnan(out["risk_reward_ratio"].iloc[0])


def test_risk_reward_is_nan_rather_than_infinite_on_a_zero_stop():
    out = T._derive_features(_row(atr_sl_multiplier=0.0))
    assert np.isnan(out["risk_reward_ratio"].iloc[0])


# --- missingness is a feature, not a hole ----------------------------------------


def test_the_preprocessor_accepts_a_missing_take_profit():
    """StandardScaler cannot take NaN, so without the imputer this raises — which is
    what would happen to ~12% of the training frame."""
    frame = pd.concat(
        [
            T._derive_features(_row()),
            T._derive_features(_row(atr_tp_multiplier=np.nan)),
        ],
        ignore_index=True,
    )
    cols = T.NUMERIC_DERIVED + T.CATEGORICAL
    pre = T._make_preprocessor().fit(frame[cols])
    out = pre.transform(frame[cols])
    assert np.isfinite(out).all()


def test_the_preprocessor_flags_the_missing_take_profit_rather_than_hiding_it():
    """`add_indicator=True`: the model must be able to tell a filled value from a real
    one, or it learns that every trade had a median-sized target."""
    frame = pd.concat(
        [
            T._derive_features(_row()),
            T._derive_features(_row(atr_tp_multiplier=np.nan)),
        ],
        ignore_index=True,
    )
    cols = T.NUMERIC_DERIVED + T.CATEGORICAL
    pre = T._make_preprocessor().fit(frame[cols])
    names = list(pre.get_feature_names_out())
    assert any(
        "missingindicator" in n and "atr_tp_multiplier" in n for n in names
    ), names


def test_atr_tp_multiplier_is_not_required_but_atr_sl_multiplier_is():
    """A trade always has a stop; a declared target is optional. Requiring both would
    silently remove trailing-stop, time-exit and opposite-signal strategies wholesale.
    """
    assert "atr_sl_multiplier" in T.NUMERIC_REQUIRED
    assert "atr_tp_multiplier" not in T.NUMERIC_REQUIRED


def test_the_feature_set_version_was_bumped_for_an_incompatible_basis():
    """A 1.0.0 model cannot be scored on this basis. Consumers compare this string."""
    assert T.FEATURE_SET_VERSION.startswith("2.")
