"""ABSENT and NaN features are different refusals, and the difference is load-bearing.

A feature the caller never supplied means the gatekeeper has no input, so it has no
opinion — unscorable, and the producer emits with `model_score: null` for System 3 to
decide. A feature that is present but NaN means corrupt data — untradeable, and the
producer drops it.

Both used to return `NAN_FEATURE`, so the producer could not tell them apart. Since the
live path supplies none of the champion's 12 training features (they are read from
`fact_market_regime_v2`, which is written retrospectively), every live signal refused
with `NAN_FEATURE:atr_value` and was silently discarded.
"""

import numpy as np
import pytest

from src.gatekeeper.score import Scorer


class _FakePreprocessor:
    feature_names_in_ = np.array(["atr_value", "adx_value"])
    transformers_ = ()


@pytest.fixture
def scorer():
    s = Scorer.__new__(Scorer)  # bypass __init__: no champion files needed
    s.model = object()
    s.preprocessor = _FakePreprocessor()
    s.known_strategies = {"58"}
    return s


def test_absent_feature_is_missing_not_nan(scorer):
    res = scorer.score({"strategy_id": "58"})
    assert res["status"] == "refused"
    assert res["reason"] == "MISSING_FEATURE:atr_value"


def test_present_but_nan_feature_stays_nan(scorer):
    res = scorer.score(
        {"strategy_id": "58", "atr_value": float("nan"), "adx_value": 25.0}
    )
    assert res["reason"] == "NAN_FEATURE:atr_value"


def test_present_but_none_feature_stays_nan(scorer):
    """Explicit None is a supplied-and-empty value, not an absent key."""
    res = scorer.score({"strategy_id": "58", "atr_value": None, "adx_value": 25.0})
    assert res["reason"] == "NAN_FEATURE:atr_value"


def test_unknown_strategy_still_refused_before_features_are_examined(scorer):
    res = scorer.score({"strategy_id": "9999"})
    assert res["reason"] == "UNKNOWN_STRATEGY_ID"


def test_no_champion_refuses_before_anything_else():
    s = Scorer.__new__(Scorer)
    s.model = None
    s.preprocessor = None
    s.known_strategies = set()
    assert s.score({})["reason"] == "NO_CHAMPION_MODEL"


def test_the_live_signal_shape_is_unscorable_not_corrupt(scorer):
    """The exact dict `build_signals` produces must read as unscorable.

    If this ever returns NAN_FEATURE, the producer goes back to silently dropping every
    live signal — the failure this distinction exists to prevent.
    """
    live_signal = {
        "signal_id": "x",
        "strategy_id": "58",
        "instrument": "GBP_USD",
        "granularity": "H1",
        "direction": "long",
        "entry": 1.3553,
        "stop": 1.3530,
        "target": 1.3600,
        "atr": 0.001047,
        "regime": "Trending-Up",
        "selection_basis": "designated",
    }
    res = scorer.score(live_signal)
    assert res["reason"].startswith("MISSING_FEATURE:")
