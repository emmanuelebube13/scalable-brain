import logging
import pandas as pd
from datetime import datetime, timezone
import pytest
from src.signals.build import build_signals
from src.layer0.strategies.contract_v2 import OrderIntent, StopRule, ExitLeg


class FakeStrategy:
    class Meta:
        strategy_id = "41"
        pairs = ["EUR_USD"]
        primary_granularity = "H1"
        context_granularities = ()

    @property
    def metadata(self):
        return self.Meta()

    def generate_orders(self, frames, pair):
        return [
            OrderIntent(
                decision_bar=datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
                direction=1,
                entry="market",
                entry_price=None,
                stop=StopRule(price=1.0),
                exits=[
                    ExitLeg(fraction=1.0, kind="take_profit", price=2.0, label="TP1")
                ],
                expires_after_bars=None,
                tag="test",
            ),
            OrderIntent(
                decision_bar=datetime(2026, 1, 1, 11, tzinfo=timezone.utc),
                direction=-1,
                entry="market",
                entry_price=None,
                stop=StopRule(price=1.0),
                exits=[
                    ExitLeg(fraction=1.0, kind="take_profit", price=0.5, label="TP1")
                ],
                expires_after_bars=None,
                tag="test",
            ),
        ]


def test_d6_guard_aggregates_warnings(monkeypatch, caplog):
    import src.signals.build as b

    monkeypatch.setattr(b.catalog, "by_id", lambda x: {})
    monkeypatch.setattr(b.catalog, "instantiate", lambda x: FakeStrategy())
    monkeypatch.setattr(
        b, "build_frames", lambda *args, **kwargs: {"H1": pd.DataFrame()}
    )
    monkeypatch.setattr(b, "_atr_at", lambda *args, **kwargs: 0.001)

    model_set = {
        "model_set_id": "test_model_set",
        "generated_at_utc": "2026-01-01T00:00:00Z",
        "regimes": {
            "Trending": [{"strategy_id": "41", "selection_basis": "qualified"}]
        },
    }
    bars_df = pd.DataFrame(
        [
            {
                "instrument": "EUR_USD",
                "timestamp": "2026-01-01T12:00:00Z",
                "granularity": "H1",
                "Close": 1.5,
            }
        ]
    )

    with caplog.at_level(logging.DEBUG):
        signals = build_signals(bars_df, model_set, {"EUR_USD": "Trending"})

    assert len(signals) == 0

    warnings = [
        r.message
        for r in caplog.records
        if r.levelname == "WARNING" and "D6 stale-bar guard: discarded" in r.message
    ]
    debugs = [
        r.message
        for r in caplog.records
        if r.levelname == "DEBUG" and "D6 stale-bar guard: strategy" in r.message
    ]

    assert len(warnings) == 1
    assert "discarded 2 stale intents for strategy 41 EUR_USD H1" in warnings[0]
    assert "oldest 2026-01-01T10:00:00+00:00" in warnings[0]
    assert "newest 2026-01-01T11:00:00+00:00" in warnings[0]
    assert len(debugs) == 2
