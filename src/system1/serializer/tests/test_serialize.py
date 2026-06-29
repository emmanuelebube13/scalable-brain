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
