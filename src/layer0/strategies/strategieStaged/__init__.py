"""
Strategy Implementations
========================

This module contains all trading strategy implementations for Layer 0.

Trend Strategies:
- Trend_EMA_ADX: EMA crossover with ADX filter
- Trend_Donchian: Donchian channel breakout

Mean Reversion Strategies:
- Range_Bollinger: Bollinger Band mean reversion
- Range_Stochastic: Stochastic oscillator signals

Support/Resistance Strategies:
- Support_Resistance: Price action around key levels

Breakout Strategies:
- VCP_Breakout: Volatility Contraction Pattern breakout
"""

from .trend_ema_adx import (
    TrendEMAADXStrategy,
    TrendEMAADX_H1_Only,
    TrendEMAADX_H4_Only,
    TrendEMAADX_MultiTF,
)
from .trend_donchian import (
    TrendDonchianStrategy,
    TrendDonchian_H1_Only,
    TrendDonchian_H4_Only,
    TrendDonchian_VCP,
)
from .range_bollinger import (
    RangeBollingerStrategy,
    RangeBollinger_H1_Only,
    RangeBollinger_H4_Only,
    RangeBollinger_Aggressive,
)
from .range_stochastic import (
    RangeStochasticStrategy,
    RangeStochastic_H1_Only,
    RangeStochastic_H4_Only,
    RangeStochastic_Divergence,
)
from .support_resistance import (
    SupportResistanceStrategy,
    SupportResistance_H1_Only,
    SupportResistance_H4_Only,
    SupportResistance_Breakout,
)
from .vcp_breakout import (
    VCPBreakoutStrategy,
    VCPBreakout_H1_Only,
    VCPBreakout_H4_Only,
    VCPBreakout_Aggressive,
)

__all__ = [
    'TrendEMAADXStrategy',
    'TrendEMAADX_H1_Only',
    'TrendEMAADX_H4_Only',
    'TrendEMAADX_MultiTF',
    'TrendDonchianStrategy',
    'TrendDonchian_H1_Only',
    'TrendDonchian_H4_Only',
    'TrendDonchian_VCP',
    'RangeBollingerStrategy',
    'RangeBollinger_H1_Only',
    'RangeBollinger_H4_Only',
    'RangeBollinger_Aggressive',
    'RangeStochasticStrategy',
    'RangeStochastic_H1_Only',
    'RangeStochastic_H4_Only',
    'RangeStochastic_Divergence',
    'SupportResistanceStrategy',
    'SupportResistance_H1_Only',
    'SupportResistance_H4_Only',
    'SupportResistance_Breakout',
    'VCPBreakoutStrategy',
    'VCPBreakout_H1_Only',
    'VCPBreakout_H4_Only',
    'VCPBreakout_Aggressive',
]
