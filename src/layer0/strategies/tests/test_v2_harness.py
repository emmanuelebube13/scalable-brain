"""Wave 1, agent E — harness tests (spec §8: per-cell, pooled, dispersion).

Runs against a synthetic in-memory loader, so the suite stays independent of
``ForexBrainDB``. What is asserted here is the *reporting contract*: that a
verdict exists per (pair × granularity), that the pooled verdict is computed
from raw trades rather than an average of fold averages, that dispersion
surfaces concentration, and that both bar resolutions are reported with their
delta.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd
import pytest

from src.layer0.strategies import v2_harness as H
from src.layer0.strategies.contract_v2 import (
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)

PAIRS = ["EUR_USD", "GBP_USD"]


# ---------------------------------------------------------------------------
# Synthetic data
# ---------------------------------------------------------------------------


def _series(
    pair: str, granularity: str, lookback_years: int = 10
) -> Optional[pd.DataFrame]:
    """Deterministic ~12 years of bars, enough for the 36mo+6mo fold design."""
    freq = {"H1": "1h", "H4": "4h", "D1": "1D", "W1": "7D"}[granularity]
    idx = pd.date_range("2014-01-01", "2026-01-01", freq=freq, tz="UTC")
    seed = abs(hash((pair, granularity))) % (2**32)
    rng = np.random.default_rng(seed)
    step = rng.normal(0.0, 8e-4, len(idx))
    px = 1.20 + np.cumsum(step)
    span = np.abs(rng.normal(0.0, 6e-4, len(idx))) + 2e-4
    return pd.DataFrame(
        {
            "Open": px,
            "High": px + span,
            "Low": px - span,
            "Close": px + rng.normal(0.0, 1e-4, len(idx)),
            "Volume": 1000.0,
        },
        index=idx,
    )


def _loader(pair: str, granularity: str, lookback_years: int = 10):
    if pair not in PAIRS:
        return None
    return _series(pair, granularity, lookback_years)


# ---------------------------------------------------------------------------
# A minimal, honest v2 strategy
# ---------------------------------------------------------------------------


class _SmaCrossV2(StrategyV2):
    """Trailing-only SMA cross with a fixed 1:2 bracket. No look-ahead."""

    FAST, SLOW = 10, 40

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="harness_sma_cross",
            name="Harness SMA Cross",
            version="0.1.0",
            author="wave1-review",
            hypothesis=(
                "trend persistence after a fast/slow moving average cross is enough "
                "to cover costs on major pairs"
            ),
            granularities=["D1"],
            pairs=list(PAIRS),
            primary_granularity="D1",
            context_granularities=(),
            simulate_on="H1",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["sma"]

    @property
    def warmup_bars(self) -> int:
        return 60

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        df = frames["D1"]
        close = df["Close"]
        fast = close.rolling(self.FAST).mean()
        slow = close.rolling(self.SLOW).mean()
        up = (fast > slow) & (fast.shift(1) <= slow.shift(1))
        dn = (fast < slow) & (fast.shift(1) >= slow.shift(1))

        out: List[OrderIntent] = []
        for i in range(self.warmup_bars, len(df)):
            long_, short_ = bool(up.iloc[i]), bool(dn.iloc[i])
            if not (long_ or short_):
                continue
            direction = 1 if long_ else -1
            entry = float(close.iloc[i])
            risk = 0.0050
            stop = entry - direction * risk
            out.append(
                OrderIntent(
                    decision_bar=df.index[i],
                    direction=direction,
                    entry="market",
                    entry_price=None,
                    stop=StopRule(price=stop),
                    exits=[
                        ExitLeg(
                            fraction=1.0,
                            kind="take_profit",
                            price=entry + direction * 2 * risk,
                            label="TP1",
                        )
                    ],
                )
            )
        return out


@pytest.fixture(scope="module")
def report() -> Dict[str, Any]:
    return H.evaluate_strategy(_SmaCrossV2(), loader=_loader, resolve_on_h1=True)


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------


def test_produces_one_cell_per_declared_pair(report: Dict[str, Any]) -> None:
    assert [c["pair"] for c in report["cells"]] == PAIRS
    for cell in report["cells"]:
        assert cell["granularity"] == "D1"


def test_every_cell_carries_its_own_verdict(report: Dict[str, Any]) -> None:
    """Spec §8: a strategy strong on one cell and worthless on another must not
    be reducible to a single blended number."""
    for cell in report["cells"]:
        for label, res in cell["resolutions"].items():
            assert isinstance(res["passed"], bool)
            assert set(res["cell"]) >= {
                "profit_factor",
                "sharpe",
                "max_drawdown",
                "win_rate",
                "recovery_factor",
                "oos_months",
                "trade_count",
            }
            if not res["passed"]:
                assert res["failures"], f"{label} failed with no stated reason"


def test_both_resolutions_reported_with_delta(report: Dict[str, Any]) -> None:
    """Spec §5: the D1-vs-H1 delta is the measurement of the bar-path assumption."""
    assert report["resolution"]["resolved_on_h1"] is True
    for cell in report["cells"]:
        assert set(cell["resolutions"]) == {"native", "h1"}
        assert cell["resolution_delta"] is not None
        assert "sharpe" in cell["resolution_delta"]


def test_h1_resolution_changes_the_outcome(report: Dict[str, Any]) -> None:
    """If native and H1 resolution agreed exactly, the H1 pass would be doing
    nothing and the extra ~24x compute would be waste. It should not agree."""
    deltas = [
        abs(c["resolution_delta"]["n_trades"])
        + abs(float(c["resolution_delta"]["sharpe"]))
        for c in report["cells"]
    ]
    assert any(d > 0 for d in deltas), (
        "native and H1 resolution produced identical results on every cell — "
        "the eligibility hook is probably not being applied"
    )


def test_pooled_is_computed_from_trades_not_fold_means(report: Dict[str, Any]) -> None:
    """A pooled trade count must equal the sum of its cells' trade counts."""
    pooled_n = report["pooled"]["n_oos_trades"]
    per_cell = sum(
        (c["resolutions"].get("h1") or c["resolutions"]["native"])["n_oos_trades"]
        for c in report["cells"]
    )
    assert pooled_n == per_cell
    assert report["pooled"]["cell"]["trade_count"] == pooled_n


def test_dispersion_reports_best_worst_and_pass_count(report: Dict[str, Any]) -> None:
    d = report["dispersion"]
    assert d["n_cells"] == len(report["cells"])
    assert 0 <= d["n_passed"] <= d["n_cells"]
    assert d["best"] is not None and d["worst"] is not None
    assert float(d["best"]["sharpe"]) >= float(d["worst"]["sharpe"])


def test_unknown_pairs_are_skipped_not_fatal() -> None:
    """A declared pair whose backfill has not finished must not sink the run."""

    class _WithMissingPair(_SmaCrossV2):
        @property
        def metadata(self) -> StrategyMetadataV2:
            base = super().metadata
            return StrategyMetadataV2(
                strategy_id="harness_missing_pair",
                name=base.name,
                version=base.version,
                author=base.author,
                hypothesis=base.hypothesis,
                granularities=list(base.granularities),
                pairs=["EUR_USD", "GBP_JPY"],  # GBP_JPY not yet backfilled
                primary_granularity=base.primary_granularity,
                context_granularities=base.context_granularities,
                simulate_on=base.simulate_on,
            )

    rep = H.evaluate_strategy(_WithMissingPair(), loader=_loader, resolve_on_h1=False)
    assert [c["pair"] for c in rep["cells"]] == ["EUR_USD"]
    assert any(s["pair"] == "GBP_JPY" for s in rep["skipped"])


def test_report_is_json_serialisable(report: Dict[str, Any], tmp_path) -> None:
    path = H.write_report(report, root=tmp_path)
    assert path.is_file() and path.stat().st_size > 0
