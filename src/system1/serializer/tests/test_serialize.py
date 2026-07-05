"""MODEL-007 serializer guard + secret-scan tests (no network; uses LocalFSBackend)."""

from __future__ import annotations

import json
import os

import pytest

from src.system1.serializer import serialize as S


def test_secret_scan_detects_and_clean(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"api_key": "AKIA0123456789ABCDEF"}')
    assert S._scan_secrets(str(bad))
    good = tmp_path / "good.json"
    good.write_text('{"weights": {"1": 0.5, "2": 0.5}}')
    assert S._scan_secrets(str(good)) == []


def test_guard_missing_artifact(tmp_path, monkeypatch):
    monkeypatch.setitem(S.SOURCES, "hmm_model.joblib", str(tmp_path / "nope.joblib"))
    with pytest.raises(S.PromotionRefused):
        S._guard_inputs()


def test_guard_empty_map(tmp_path, monkeypatch):
    # all sources exist but the map has zero qualifying strategies
    for name in S.SOURCES:
        p = tmp_path / name
        p.write_text("{}")
        monkeypatch.setitem(S.SOURCES, name, str(p))
    empty_map = tmp_path / "regime_strategy_map.json"
    empty_map.write_text(json.dumps({"regimes": {}, "empty_regimes": ["Ranging"]}))
    monkeypatch.setitem(S.SOURCES, "regime_strategy_map.json", str(empty_map))
    with pytest.raises(S.PromotionRefused):
        S._guard_inputs()


def test_bundle_version_format():
    import re

    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z$", S._bundle_version())


def _stage_valid_sources(tmp_path, monkeypatch):
    """Stage minimal valid source artifacts (a non-empty regime map) for publish()."""
    for name in S.SOURCES:
        p = tmp_path / name
        p.write_text("{}")
        monkeypatch.setitem(S.SOURCES, name, str(p))
    regime_map = tmp_path / "regime_strategy_map.json"
    regime_map.write_text(json.dumps({"regimes": {"Ranging": [{"strategy_id": 1}]}}))
    monkeypatch.setitem(S.SOURCES, "regime_strategy_map.json", str(regime_map))
    root = tmp_path / "model-artifacts"
    monkeypatch.setenv("STORAGE_PROVIDER", "local")
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(root))
    return root


def test_publish_persists_regime_accuracy(tmp_path, monkeypatch):
    """FIX-S1-006: gate-relevant metrics (regime_accuracy) are written to model_metadata.json so
    the orchestrator's beats_incumbent comparison is no longer vacuous. Pre-fix the only persisted
    metric was n_qualified_strategies, so this assertion would fail (KeyError)."""
    root = _stage_valid_sources(tmp_path, monkeypatch)
    result = S.publish(
        register_mlflow=False,
        metrics={
            "regime_accuracy": 0.85,
            "oos_uplift": 0.05,
            "oos_uplift_significant": True,
        },
    )
    meta_path = root / result["bundle_version"] / "model_metadata.json"
    metrics = json.loads(meta_path.read_text())["metrics"]
    assert metrics["regime_accuracy"] == 0.85
    assert metrics["oos_uplift"] == 0.05
    assert metrics["n_qualified_strategies"] == 1  # always-present metric still written


def test_publish_drops_none_metrics(tmp_path, monkeypatch):
    """None-valued candidate metrics are not persisted (producer never writes a null metric)."""
    root = _stage_valid_sources(tmp_path, monkeypatch)
    result = S.publish(register_mlflow=False, metrics={"regime_accuracy": None})
    meta_path = root / result["bundle_version"] / "model_metadata.json"
    metrics = json.loads(meta_path.read_text())["metrics"]
    assert "regime_accuracy" not in metrics
    assert metrics["n_qualified_strategies"] == 1
