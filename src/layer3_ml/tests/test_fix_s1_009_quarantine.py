"""FIX-S1-009 — legacy-trainer quarantine and RandomForest factory regression.

Three contracts are asserted, all hermetic (no DB access, no real training):

  1. The legacy trainer's artifact constants are repointed to the quarantined
     ``models/legacy_gatekeeper_*`` namespace and can no longer name any
     governed ``champion_*`` artifact as a write target.

  2. Invoking the legacy trainer's ``main`` with ``--promote-as-champion``
     refuses immediately — before any DB access, training, or file write — and
     leaves the live champion bundle (``models/champion_manifest.json`` et al.)
     byte-for-byte untouched.

  3. ``tree_model_factory`` constructs a RandomForestClassifier when the params
     dict already carries the Optuna-tuned ``min_samples_leaf`` (the previous
     hardcoded duplicate raised ``TypeError: multiple values for keyword
     argument`` and silently dropped RandomForest from every tournament).
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

# Make ``src`` importable when pytest is run from the repo root.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.layer3_ml.training import train_ml_gatekeeper as tmg  # noqa: E402

_MODELS_DIR = Path(_REPO_ROOT) / "models"
_GOVERNED_CHAMPION_FILES = (
    "champion_model.pkl",
    "champion_preprocessor.pkl",
    "champion_manifest.json",
)


def _snapshot(path: Path) -> tuple[bool, float | None, str | None]:
    """(exists, mtime, sha256) fingerprint of a governed artifact."""
    if not path.exists():
        return (False, None, None)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return (True, path.stat().st_mtime, digest)


# =============================================================================
# 1. Quarantined artifact namespace
# =============================================================================


def test_constants_no_longer_point_at_champion_namespace() -> None:
    """All legacy output constants must live in the legacy_* namespace."""
    for const in (
        tmg.CHAMPION_MODEL_PATH,
        tmg.CHAMPION_PREPROCESSOR_PATH,
        tmg.CHAMPION_MANIFEST_PATH,
    ):
        assert not const.name.startswith(
            "champion"
        ), f"{const} still targets the governed champion namespace"
        assert const.name.startswith(
            "legacy_gatekeeper"
        ), f"{const} is not in the quarantined legacy_gatekeeper_* namespace"


def test_manifest_artifact_paths_are_legacy() -> None:
    """The manifest the legacy trainer emits must reference legacy paths only."""
    manifest = tmg.create_champion_manifest(
        model_type="xgboost",
        threshold=0.5,
        feature_columns=["ADX_Value"],
        run_id="test",
        training_timestamp="2026-07-04T00:00:00+00:00",
        metrics={},
        artifact_hashes={},
    )
    for key in ("artifact_path", "preprocessor_path"):
        assert "legacy_gatekeeper" in manifest[key]
        assert "champion_" not in Path(manifest[key]).name


# =============================================================================
# 2. --promote-as-champion hard refusal (before any work)
# =============================================================================


def test_promote_as_champion_refuses_before_any_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal must fire before DB/query/training and not touch champion_*."""
    before = {name: _snapshot(_MODELS_DIR / name) for name in _GOVERNED_CHAMPION_FILES}

    def _must_not_be_reached(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "refusal did not fire first: main() reached the data-load path"
        )

    # If main() gets past the refusal, these tripwires fail the test before any
    # DB access or file write can happen.
    monkeypatch.setattr(tmg, "build_query_with_contract", _must_not_be_reached)
    monkeypatch.setattr(tmg, "promote_to_champion", _must_not_be_reached)
    monkeypatch.setattr(
        sys, "argv", ["train_ml_gatekeeper.py", "--promote-as-champion"]
    )

    with pytest.raises(SystemExit, match="FIX-S1-009"):
        tmg.main()

    after = {name: _snapshot(_MODELS_DIR / name) for name in _GOVERNED_CHAMPION_FILES}
    assert after == before, "governed champion bundle changed during a refused promote"


def test_promote_refusal_message_names_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The error must route operators to the governed promote path."""
    monkeypatch.setattr(
        sys, "argv", ["train_ml_gatekeeper.py", "--promote-as-champion"]
    )
    with pytest.raises(SystemExit, match=r"src\.system1\.scheduler\.orchestrator"):
        tmg.main()


# =============================================================================
# 3. RandomForest duplicate-kwarg regression (FIX-S1-009 Fix 3)
# =============================================================================


def test_tree_model_factory_randomforest_accepts_optuna_params() -> None:
    """Optuna-style params (incl. min_samples_leaf) must construct without TypeError."""
    params = {"n_estimators": 10, "max_depth": 4, "min_samples_leaf": 3}
    model = tmg.tree_model_factory("randomforest", params, class_ratio=1.0)

    assert isinstance(model, RandomForestClassifier)
    assert model.get_params()["min_samples_leaf"] == 3  # Optuna value wins
    assert model.get_params()["min_samples_split"] == 5  # kept: not Optuna-tuned

    # Prove it is actually trainable (the old bug surfaced at construction, but
    # a cheap fit guards against any residual kwarg conflict).
    rng = np.random.default_rng(0)
    X = rng.normal(size=(30, 3))
    y = np.array([0, 1] * 15)
    model.fit(X, y)
    assert model.predict_proba(X).shape == (30, 2)
