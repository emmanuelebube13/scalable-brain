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
            if f == "regime_structural":
                features[f] = "Trending-Up"
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
    num_feat = next(
        f for f in features if f not in ["regime_structural", "strategy_id"]
    )
    features[num_feat] = np.nan

    res = scorer.score(features)
    assert res["status"] == "refused"
    assert "NAN_FEATURE" in res["reason"]
    assert "score" not in res


def test_missing_feature_refused(scorer):
    """An ABSENT feature is MISSING_FEATURE, not NAN_FEATURE."""
    if not scorer.model:
        pytest.skip("No champion model found to test against")

    features = get_valid_features(scorer)
    num_feat = next(
        f for f in features if f not in ["regime_structural", "strategy_id"]
    )
    del features[num_feat]

    res = scorer.score(features)
    assert res["status"] == "refused"
    assert res["reason"] == f"MISSING_FEATURE:{num_feat}"
    assert "score" not in res


def test_real_live_signal_is_scored(scorer):
    if not scorer.model:
        pytest.skip("No champion model found to test against")

    signal = {
        "signal_id": "c138b329-8f0a-42c2-9019-74a00cb0cc17",
        "strategy_id": list(scorer.known_strategies)[0],
        "strategy_key": "some_strategy_key",
        "instrument": "GBP_USD",
        "granularity": "H1",
        "signal_time_utc": "2026-08-19T11:00:00Z",
        "direction": "short",
        "entry": 1.2500,
        "stop": 1.2550,
        "target": 1.2400,
        "atr": 0.001047,
        "atr_value": 0.001047,
        "adx_value": 35.5,
        "regime_structural": "Trending-Down",
        "model_set_id": "2026-08-23T18-12-43Z-1a029257_gk-d614163c",
        "regime": "Trending-Down",
    }

    res = scorer.score(signal)
    assert res["status"] == "scored", f"Expected 'scored', got: {res}"
