"""The load-bearing test: uniform blocks must reproduce production trade-for-trade.

If a regime-aware strategy with the SAME parameters in every regime does not emit exactly what
production ``Trend_Donchian_VCP`` emits, then the regime plumbing is changing outcomes by itself
— and every A/B number produced by this package would be measuring the port, not the regime.

The synthetic frame is deterministic (seeded) and shaped to produce squeezes and breakouts, so
the comparison exercises real signal paths rather than an all-zero series.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.layer0.backtest_engine import BacktestConfig, BacktestEngine
from src.layer0.strategies.strategieStaged.trend_donchian import TrendDonchian_VCP
from src.regime_aware.context import ALL_REGIMES, UNKNOWN
from src.regime_aware.contract import ParamBlock, RegimeParams
from src.regime_aware.strategies.donchian_vcp import (
    BASELINE,
    RegimeAwareDonchianVCP,
    build_baseline,
)


def _synthetic_frame(n: int = 1500, seed: int = 7) -> pd.DataFrame:
    """Prices with alternating quiet and volatile stretches, so squeezes and breakouts occur."""
    rng = np.random.default_rng(seed)
    vol = np.where((np.arange(n) // 150) % 2 == 0, 0.0004, 0.0025)
    steps = rng.normal(0, 1, n) * vol
    close = 1.10 * np.exp(np.cumsum(steps))
    spread = np.abs(rng.normal(0, 1, n)) * vol * close
    idx = pd.date_range("2018-01-01", periods=n, freq="4h", tz="UTC")
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + spread,
            "Low": close - spread,
            "Close": close,
            "Volume": rng.integers(100, 1000, n).astype(float),
        },
        index=idx,
    )


def _trade_tuples(trades):
    return [
        (
            t.entry_time,
            t.direction,
            round(float(t.entry_price), 10),
            round(float(t.stop_loss), 10),
            round(float(t.take_profit), 10),
            t.exit_reason,
            round(float(t.r_multiple), 10) if t.r_multiple is not None else None,
        )
        for t in trades
    ]


@pytest.fixture(scope="module")
def frame():
    return _synthetic_frame()


def _run(strategy, df):
    engine = BacktestEngine(BacktestConfig())
    return engine.run_backtest(
        strategy,
        df,
        "EUR_USD",
        "H4",
        warmup_bars=strategy.get_required_warmup_bars(),
    )


def test_uniform_blocks_reproduce_production_exactly(frame):
    """Uniform BASELINE == production Trend_Donchian_VCP, trade for trade."""
    production = _run(TrendDonchian_VCP(), frame.copy())
    ported = _run(build_baseline(), frame.copy())

    assert len(production.trades) > 0, "fixture produced no trades — test proves nothing"
    assert _trade_tuples(ported.trades) == _trade_tuples(production.trades)


def test_regime_column_is_irrelevant_when_blocks_are_uniform(frame):
    """With uniform blocks, changing the regime labels must change nothing.

    This separates "the regime matters" from "adding a column perturbed something".
    """
    rng = np.random.default_rng(3)
    labelled = frame.copy()
    labelled["regime"] = rng.choice(list(ALL_REGIMES), size=len(frame))

    all_unknown = frame.copy()
    all_unknown["regime"] = UNKNOWN

    a = _run(build_baseline(), labelled)
    b = _run(build_baseline(), all_unknown)
    assert _trade_tuples(a.trades) == _trade_tuples(b.trades)


def test_disabled_regime_emits_no_entries_in_that_regime(frame):
    """enabled=False must suppress entries on exactly the bars carrying that label."""
    labelled = frame.copy()
    half = len(frame) // 2
    labelled["regime"] = ["Ranging"] * half + ["High-Vol"] * (len(frame) - half)

    params = RegimeParams(
        {r: BASELINE for r in ALL_REGIMES}
    ).with_override("Ranging", enabled=False)
    strategy = RegimeAwareDonchianVCP(params, name="vcp_ranging_off")

    prepared = strategy.calculate_indicators(labelled.copy(), "EUR_USD", "H4")
    signals = strategy.generate_signals(prepared, "EUR_USD", "H4")

    ranging_bars = prepared["regime"] == "Ranging"
    assert (signals[ranging_bars] == 0).all()
    assert (signals[~ranging_bars] != 0).any(), "control half produced no signals"


def test_allowed_directions_restricts_signal_side(frame):
    """A long-only regime must emit no shorts on its bars, and vice versa."""
    labelled = frame.copy()
    half = len(frame) // 2
    labelled["regime"] = ["Trending-Up"] * half + ["Trending-Down"] * (len(frame) - half)

    params = (
        RegimeParams({r: BASELINE for r in ALL_REGIMES})
        .with_override("Trending-Up", allowed_directions=(1,))
        .with_override("Trending-Down", allowed_directions=(-1,))
    )
    strategy = RegimeAwareDonchianVCP(params, name="vcp_directional")
    prepared = strategy.calculate_indicators(labelled.copy(), "EUR_USD", "H4")
    signals = strategy.generate_signals(prepared, "EUR_USD", "H4")

    up_bars = prepared["regime"] == "Trending-Up"
    assert (signals[up_bars] >= 0).all(), "short emitted in a long-only regime"
    assert (signals[~up_bars] <= 0).all(), "long emitted in a short-only regime"
    assert (signals != 0).any(), "no signals at all — the test proves nothing"


def test_default_allowed_directions_are_unrestricted():
    """The default must be both sides, or adding the field would silently change the baseline."""
    assert set(BASELINE.allowed_directions) == {1, -1}


def test_missing_regime_block_is_rejected():
    """A parameter set with a gap must fail loudly, not fall through to a default."""
    with pytest.raises(ValueError, match="missing a block"):
        RegimeParams({"Ranging": BASELINE})


def test_per_regime_stop_multiple_is_applied(frame):
    """The ATR stop multiple must come from the block of the regime at the ENTRY bar."""
    labelled = frame.copy()
    labelled["regime"] = "High-Vol"

    wide = RegimeParams({r: BASELINE for r in ALL_REGIMES}).with_override(
        "High-Vol", stop_loss_atr=3.0
    )
    narrow_run = _run(build_baseline(), labelled.copy())
    wide_run = _run(RegimeAwareDonchianVCP(wide, name="vcp_wide"), labelled.copy())

    assert narrow_run.trades and wide_run.trades
    narrow_risk = abs(
        narrow_run.trades[0].entry_price - narrow_run.trades[0].stop_loss
    )
    wide_risk = abs(wide_run.trades[0].entry_price - wide_run.trades[0].stop_loss)
    assert wide_risk == pytest.approx(narrow_risk * 3.0, rel=1e-6)


def test_param_block_is_immutable():
    """Blocks are frozen so a strategy cannot mutate the set it was handed mid-backtest."""
    with pytest.raises(Exception):
        BASELINE.stop_loss_atr = 99.0  # type: ignore[misc]


def test_baseline_matches_production_config():
    """BASELINE must track the production strategy's settings, or the control arm is a fiction."""
    prod = TrendDonchian_VCP()
    assert BASELINE.channel_period == prod.channel_period
    assert BASELINE.adx_period == prod.adx_period
    assert BASELINE.adx_threshold == prod.adx_threshold
    assert BASELINE.require_adx == prod.require_adx
    assert BASELINE.stop_loss_atr == prod.config.stop_loss_atr
    assert BASELINE.take_profit_atr == prod.config.take_profit_atr
