"""FIX-S1-010 — guard tests for the proposed→champion promotion path.

The bug this closes: the orchestrator trained the gatekeeper in dry-run to obtain the
uplift that authorised a promote, then published only the regime/weights bundle, so the
live champion drifted arbitrarily far from the live strategy map (2026-07-05 model vs
2026-07-19 map). ``promote_proposed`` ships the audited artifact instead of retraining.
"""

from __future__ import annotations

import json
import os

import pytest

from src.gatekeeper.promote import (
    ProposedBundleInvalid,
    atomic_promote,
    bundle_paths,
    promote_proposed,
)


class _Estimator:
    """Minimal picklable stand-in — the promote path only round-trips the object."""

    def __init__(self, tag):
        self.tag = tag

    def __eq__(self, other):
        return isinstance(other, _Estimator) and other.tag == self.tag


def _write_proposed(models_dir, tag="v1"):
    atomic_promote(
        model=_Estimator(tag),
        # Mirrors the manifest train.py builds: it carries its own ``dry_run`` flag.
        manifest={
            "model_type": "xgboost",
            "created_at_utc": "2026-07-19T00:28:32Z",
            "dry_run": True,
        },
        models_dir=models_dir,
        preprocessor=_Estimator(f"pre-{tag}"),
        dry_run=True,
    )


def test_promote_proposed_ships_the_audited_artifact(tmp_path):
    """The champion must be byte-identical to the proposed model, not a retrain."""
    models = str(tmp_path)
    _write_proposed(models)
    src = bundle_paths(models, dry_run=True)
    proposed_sha = json.load(open(src["manifest_path"]))["sha256"]

    paths = promote_proposed(models)

    import joblib

    assert joblib.load(paths["model_path"]) == _Estimator("v1")
    manifest = json.load(open(paths["manifest_path"]))
    assert manifest["dry_run"] is False
    # Provenance: the champion records which dry-run bundle it came from.
    assert manifest["promoted_from"]["sha256"] == proposed_sha
    assert manifest["promoted_from"]["created_at_utc"] == "2026-07-19T00:28:32Z"


def test_promote_proposed_refuses_when_no_bundle(tmp_path):
    with pytest.raises(ProposedBundleInvalid, match="no proposed bundle"):
        promote_proposed(str(tmp_path))


def test_promote_proposed_refuses_tampered_bundle(tmp_path):
    """A proposed model altered after training must never become the champion."""
    models = str(tmp_path)
    _write_proposed(models)
    src = bundle_paths(models, dry_run=True)
    with open(src["model_path"], "ab") as fh:
        fh.write(b"tampered")

    with pytest.raises(ProposedBundleInvalid, match="checksum mismatch"):
        promote_proposed(models)

    # And the live champion namespace was never created.
    assert not os.path.exists(bundle_paths(models, dry_run=False)["model_path"])


def test_promote_proposed_does_not_disturb_proposed_namespace(tmp_path):
    models = str(tmp_path)
    _write_proposed(models)
    src = bundle_paths(models, dry_run=True)
    before = {k: os.path.getsize(p) for k, p in src.items()}

    promote_proposed(models)

    assert {k: os.path.getsize(p) for k, p in src.items()} == before
    assert json.load(open(src["manifest_path"]))["dry_run"] is True
