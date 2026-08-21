"""
Layer 0 Strategy Package
========================

Public import surface for the Layer 0 strategy implementations.

The concrete implementations live in the ``strategieStaged`` subpackage. This
module re-exports them so that ``from layer0.strategies import
TrendEMAADXStrategy`` keeps working — that is the form used by
``layer0/qualification/qualify_strategies.py``, which is the import chain
``layer0/persist_trade_outcomes.py`` (the only writer of ``fact_trade_outcomes``)
depends on.

History: this file was lost when the implementations were moved down into
``strategieStaged/``, which turned ``layer0.strategies`` into an implicit
namespace package with no attributes. Every import of a strategy class then
failed with "cannot import name ... (unknown location)", the outcomes writer
died on import, and ``fact_trade_outcomes`` stopped being written in June 2026.
See ``task/2026-July-week4/T1-reconnect-feedback-loop.md``.

Do not delete this file. ``tests/test_strategies_package.py`` guards it.
"""

from .strategieStaged import (
    TrendEMAADXStrategy,
    TrendEMAADX_H1_Only,
    TrendEMAADX_H4_Only,
    TrendEMAADX_MultiTF,
    TrendDonchianStrategy,
    TrendDonchian_H1_Only,
    TrendDonchian_H4_Only,
    TrendDonchian_VCP,
    RangeStochasticStrategy,
    RangeStochastic_H1_Only,
    RangeStochastic_H4_Only,
    RangeStochastic_Divergence,
    SupportResistanceStrategy,
    SupportResistance_H1_Only,
    SupportResistance_H4_Only,
    SupportResistance_Breakout,
    VCPBreakoutStrategy,
    VCPBreakout_H1_Only,
    VCPBreakout_H4_Only,
    VCPBreakout_Aggressive,
)

__all__ = [
    "TrendEMAADXStrategy",
    "TrendEMAADX_H1_Only",
    "TrendEMAADX_H4_Only",
    "TrendEMAADX_MultiTF",
    "TrendDonchianStrategy",
    "TrendDonchian_H1_Only",
    "TrendDonchian_H4_Only",
    "TrendDonchian_VCP",
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
