"""Import-integrity guards for the Layer 0 strategy package.

These tests exist because of a silent, month-long production failure: the
``layer0.strategies`` package lost its ``__init__.py`` during the subpackage
reorg, which broke ``layer0/persist_trade_outcomes.py`` — the only writer of
``fact_trade_outcomes``. Nothing failed loudly, so every System-1 retrain from
June to late July 2026 re-derived its verdicts from stale trade outcomes.

The point of this module is that the *next* packaging break fails in pytest
instead of quietly freezing the feedback loop. See
``task/2026-July-week4/T1-reconnect-feedback-loop.md``.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import pytest

LAYER0 = Path(__file__).resolve().parent.parent

# The full public surface qualify_strategies imports. If any of these stops
# being importable, the qualification pipeline and the outcomes writer are dead.
STRATEGY_EXPORTS = [
    "TrendEMAADXStrategy",
    "TrendEMAADX_H1_Only",
    "TrendEMAADX_H4_Only",
    "TrendEMAADX_MultiTF",
    "TrendDonchianStrategy",
    "TrendDonchian_H1_Only",
    "TrendDonchian_H4_Only",
    "TrendDonchian_VCP",
    "RangeBollingerStrategy",
    "RangeBollinger_H1_Only",
    "RangeBollinger_H4_Only",
    "RangeBollinger_Aggressive",
    "RangeStochasticStrategy",
    "RangeStochastic_H1_Only",
    "RangeStochastic_H4_Only",
    "RangeStochastic_Divergence",
    "SupportResistanceStrategy",
    "SupportResistance_H1_Only",
    "SupportResistance_H4_Only",
    "SupportResistance_Breakout",
    "VCPBreakoutStrategy",
    "VCPBreakout_H1_Only",
    "VCPBreakout_H4_Only",
    "VCPBreakout_Aggressive",
]


def test_outcomes_writer_imports():
    """The only writer of fact_trade_outcomes must be importable.

    This is the single most important assertion in the file: when it failed,
    the feedback loop was severed and no alarm went off anywhere.
    """
    importlib.import_module("src.layer0.persist_trade_outcomes")


def test_strategies_is_a_real_package_not_a_namespace_package():
    """`strategies/` must keep its __init__.py.

    Without it Python silently creates an implicit namespace package that has
    no attributes, and every `from layer0.strategies import X` fails with the
    obscure "unknown location" error.
    """
    assert (LAYER0 / "strategies" / "__init__.py").is_file(), (
        "src/layer0/strategies/__init__.py is missing — layer0.strategies has "
        "degraded to an implicit namespace package and the outcomes writer "
        "cannot import. This is the exact June 2026 breakage."
    )


@pytest.mark.parametrize("name", STRATEGY_EXPORTS)
def test_every_strategy_class_is_importable(name):
    mod = importlib.import_module("src.layer0.strategies")
    assert hasattr(mod, name), f"layer0.strategies no longer exports {name}"


def test_get_all_strategies_returns_the_full_roster():
    from src.layer0.qualify_strategies import get_all_strategies

    strategies = get_all_strategies()
    assert len(strategies) == 10, (
        f"expected the 10 qualified strategies, got {len(strategies)}: "
        f"{[s.config.name for s in strategies]}"
    )


def test_no_package_directory_names_contain_spaces():
    """Directory names with spaces can never be imported as Python packages."""
    offenders = [
        str(p.relative_to(LAYER0))
        for p in (LAYER0 / "strategies").rglob("*")
        if p.is_dir() and p.name != p.name.strip() or (p.is_dir() and " " in p.name)
    ]
    assert not offenders, f"un-importable directory names: {offenders}"


@pytest.mark.parametrize(
    "shim",
    [
        "backtest_engine",
        "indicators",
        "multi_timeframe",
        "strategy_analyzer",
        "utils",
        "layer2_config_adapter",
        "demo",
        "seed_dim_asset_test",
        "qualify_strategies",
    ],
)
def test_backward_compatible_shims_import(shim):
    """Every top-level layer0 wrapper must resolve to its grouped module.

    These shims swallow ImportError to support two import styles. Each one is
    therefore a place a real breakage can hide, so each is imported here.
    """
    importlib.import_module(f"src.layer0.{shim}")


def test_shims_do_not_swallow_the_real_import_error():
    """A failing shim must re-raise the ORIGINAL error, not the fallback's.

    The June breakage surfaced as `No module named 'qualification'` — the
    fallback's error — which pointed investigators at the wrong thing entirely.
    The real cause (`cannot import name 'TrendEMAADXStrategy'`) was discarded.
    """
    shim_dir = LAYER0
    for name in ("qualify_strategies", "demo", "seed_dim_asset_test"):
        source = (shim_dir / f"{name}.py").read_text()
        assert "raise _relative_import_error" in source, (
            f"{name}.py swallows the relative-import failure instead of "
            "re-raising it; a real breakage inside the package would be "
            "reported as a misleading 'No module named ...' error"
        )


def test_all_layer0_submodules_are_importable():
    """Sweep every module under layer0 so a new packaging break can't hide."""
    import src.layer0 as layer0

    failures = []
    for info in pkgutil.walk_packages(layer0.__path__, prefix="src.layer0."):
        if ".tests" in info.name or "__pycache__" in info.name:
            continue
        try:
            importlib.import_module(info.name)
        except Exception as exc:  # noqa: BLE001 - reporting, not handling
            failures.append(f"{info.name}: {type(exc).__name__}: {exc}")
    assert not failures, "un-importable layer0 modules:\n" + "\n".join(failures)
