import os
import numpy as np
import pytest
from src.gatekeeper.score import Scorer

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MODELS_DIR = os.path.join(REPO_ROOT, "models")


@pytest.fixture
def scorer():
    return Scorer(MODELS_DIR)


def get_valid_features(scorer):
    # Construct a valid feature dict based on pre.feature_names_in_
    features = {}
    if scorer.preprocessor:
        for f in scorer.preprocessor.feature_names_in_:
            if f in ["regime_causal", "entry_signal_type"]:
                features[f] = "Trending-Up" if f == "regime_causal" else "breakout"
            elif f == "strategy_id":
                features[f] = list(scorer.known_strategies)[0]
            else:
                features[f] = 0.5
    return features


def test_known_strategy_scores_normally(scorer):
    if not scorer.model:
        pytest.skip("No champion model found to test against")

    features = get_valid_features(scorer)
    res = scorer.score(features)
    assert res["status"] == "scored"
    assert isinstance(res["score"], float)


def test_unknown_strategy_refused(scorer):
    if not scorer.model:
        pytest.skip("No champion model found to test against")

    features = get_valid_features(scorer)
    features["strategy_id"] = "999999"  # unknown
    res = scorer.score(features)
    assert res["status"] == "refused"
    assert res["reason"] == "UNKNOWN_STRATEGY_ID"
    assert "score" not in res


def test_nan_feature_refused(scorer):
    if not scorer.model:
        pytest.skip("No champion model found to test against")

    features = get_valid_features(scorer)
    # Inject NaN in a numerical feature
    # Find a numerical feature
    num_feat = next(
        f
        for f in features
        if f not in ["regime_causal", "entry_signal_type", "strategy_id"]
    )
    features[num_feat] = np.nan

    res = scorer.score(features)
    assert res["status"] == "refused"
    assert "NAN_FEATURE" in res["reason"]
    assert "score" not in res


def test_missing_feature_refused(scorer):
    """An ABSENT feature is MISSING_FEATURE, not NAN_FEATURE.

    This asserted NAN_FEATURE while deleting the key outright, which is what let the two
    cases share a reason. The producer branches on the difference: absent means the
    gatekeeper had no input and the signal is emitted unscored; NaN means corrupt data
    and the signal is dropped. See test_score_refusal_reasons.py.
    """
    if not scorer.model:
        pytest.skip("No champion model found to test against")

    features = get_valid_features(scorer)
    num_feat = next(
        f
        for f in features
        if f not in ["regime_causal", "entry_signal_type", "strategy_id"]
    )
    del features[num_feat]

    res = scorer.score(features)
    assert res["status"] == "refused"
    assert res["reason"] == f"MISSING_FEATURE:{num_feat}"
    assert "score" not in res
