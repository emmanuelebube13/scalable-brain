"""Tests for the rehearsal emitter — cell selection and, above all, the refusal."""

from __future__ import annotations

import pytest

from src.queue_producer import emit_drill as D

MODEL_SET = {
    "model_set_id": "2026-08-24T10-08-20Z-cb697b59_gk-d614163c",
    "regimes": {
        "Trending-Up": [
            {"strategy_id": 58, "strategy_key": "xard_ma_cross_daily_open"},
            {"strategy_id": 36, "strategy_key": "nnfx_backtrader"},
        ],
        "Ranging": [{"strategy_id": 43, "strategy_key": "reference_pullback"}],
    },
}


def _signal(**over):
    sig = {
        "signal_id": "drill-1",
        "drill": True,
        "strategy_id": 58,
        "instrument": "EUR_USD",
        "granularity": "H1",
        "direction": "long",
        "entry": 1.1582,
        "stop": 1.1563,
        "target": 1.1620,
        "atr": 0.00125,
        "model_set_id": MODEL_SET["model_set_id"],
        "regime": "Trending-Up",
        "selection_basis": "designated",
        "model_score": None,
        "threshold_applied": None,
    }
    sig.update(over)
    return sig


def test_picks_first_cell_by_default():
    reg, cell = D._pick_cell(MODEL_SET, None, None)
    assert reg == "Trending-Up" and cell["strategy_id"] == 58


def test_selects_by_key_or_id():
    assert D._pick_cell(MODEL_SET, None, "nnfx_backtrader")[1]["strategy_id"] == 36
    assert D._pick_cell(MODEL_SET, None, "36")[1]["strategy_key"] == "nnfx_backtrader"


def test_regime_scopes_the_choice():
    reg, cell = D._pick_cell(MODEL_SET, "Ranging", None)
    assert reg == "Ranging" and cell["strategy_id"] == 43


def test_unknown_regime_or_strategy_raises():
    with pytest.raises(RuntimeError, match="High-Vol"):
        D._pick_cell(MODEL_SET, "High-Vol", None)
    with pytest.raises(RuntimeError, match="not in the live map"):
        D._pick_cell(MODEL_SET, None, "nope")


def test_refuses_to_publish_when_stamping_is_off(monkeypatch, caplog):
    """The one that matters.

    With ``EMIT_PROVENANCE_FIELDS=false`` the ``drill`` flag is stripped from the built
    message, so what arrives is indistinguishable from a real order. The tool must refuse
    — and must refuse in dry run too, so the dry run rehearses the publish decision
    rather than only showing the payload.
    """
    monkeypatch.setenv("EMIT_PROVENANCE_FIELDS", "false")
    monkeypatch.setattr(D, "build_drill_signal", lambda **kw: _signal())

    published = []
    monkeypatch.setattr(
        D, "ScoredSignalProducer", lambda *a, **k: published.append(1) or object()
    )

    assert D.main([]) == 2
    assert D.main(["--publish"]) == 2
    assert not published
    assert "REAL order" in caplog.text


def test_dry_run_does_not_publish(monkeypatch, capsys):
    monkeypatch.delenv("EMIT_PROVENANCE_FIELDS", raising=False)
    monkeypatch.setattr(D, "build_drill_signal", lambda **kw: _signal())

    def _boom(*a, **k):  # pragma: no cover - fails the test if reached
        raise AssertionError("dry run must not construct a producer")

    monkeypatch.setattr(D, "ScoredSignalProducer", _boom)

    assert D.main([]) == 0
    out = capsys.readouterr().out
    assert '"drill": true' in out
    assert MODEL_SET["model_set_id"] in out  # the real bundle_id is carried


def test_a_refusal_to_build_is_not_a_silent_success(monkeypatch):
    def _raise(**kw):
        raise RuntimeError("no published model set")

    monkeypatch.setattr(D, "build_drill_signal", _raise)
    assert D.main([]) == 1
