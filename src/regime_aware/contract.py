"""The regime-aware contract: a parameter block per regime, resolved per bar.

This is where model 1 actually lives. A regime-blind strategy has one set of parameters. A
regime-aware strategy has one set **per regime**, and the label in force at each bar selects
which set applies. That lets a strategy do all three of the things model 1 promises:

* **suppress entries**   — ``enabled=False`` for a regime it should sit out
* **change parameters**  — a different breakout period or ADX threshold per regime
* **change risk**        — a different ATR stop/target multiple per regime

How resolution avoids breaking indicators
-----------------------------------------
The obvious implementation — slice the frame into regime segments and compute indicators within
each — is wrong. A Donchian channel computed inside a segment restarts at every regime boundary,
inventing breakouts that the continuous series never produced. Instead, indicators are computed
**once over the full continuous frame for each distinct parameter value** any block asks for, and
each bar then selects the column belonging to its own regime's block. Continuous indicators,
per-regime decisions, and still fully vectorised — no Python loop over 28,000 bars.

The equivalence property
------------------------
If every block is identical, a regime-aware strategy must produce **exactly** the trades of its
regime-blind twin. That is the load-bearing test of this whole experiment
(``tests/test_equivalence.py``): if it fails, the plumbing is changing outcomes on its own and
no comparison built on it means anything.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Mapping, Tuple

import pandas as pd

from src.regime_aware.context import ALL_REGIMES, UNKNOWN


@dataclass(frozen=True)
class ParamBlock:
    """One regime's worth of behaviour for a Donchian-family breakout strategy.

    Frozen so a block cannot be mutated mid-backtest by a strategy that received it — the same
    reasoning behind the "strategies must not mutate their frames" rule in ``contract_v2``.

    ``enabled=False`` means "emit no entries in this regime". It does not close open positions;
    exits are always allowed to run, because abandoning a live position because the regime
    changed is a different intervention and would confound the comparison.
    """

    enabled: bool = True
    channel_period: int = 20
    adx_period: int = 14
    adx_threshold: float = 25.0
    require_adx: bool = True
    stop_loss_atr: float = 1.0
    take_profit_atr: float = 4.0
    squeeze_lookback: int = 5
    fast_ema: int = 20
    slow_ema: int = 50
    bb_period: int = 20
    bb_std: float = 2.0
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    require_rsi: bool = True
    #: Signal directions this regime permits (1 = long, -1 = short). The default allows both,
    #: which is regime-blind behaviour. Restricting it expresses "in an uptrend, only take
    #: longs" — the trade-with-the-trend rule, stated as a property of the regime rather than
    #: bolted on as an external filter.
    allowed_directions: Tuple[int, ...] = (1, -1)


class RegimeParams:
    """A complete parameter set: one :class:`ParamBlock` per regime, no gaps permitted.

    Requiring every label — including ``UNKNOWN`` — is deliberate. A missing key would otherwise
    fall through to whatever default the strategy happened to carry, which is how a strategy ends
    up quietly trading a regime nobody decided it should trade.
    """

    def __init__(self, blocks: Mapping[str, ParamBlock]):
        missing = [r for r in ALL_REGIMES if r not in blocks]
        if missing:
            raise ValueError(
                f"RegimeParams is missing a block for {missing}. Every regime in "
                f"{list(ALL_REGIMES)} must be declared explicitly, including {UNKNOWN!r}."
            )
        unknown_keys = [k for k in blocks if k not in ALL_REGIMES]
        if unknown_keys:
            raise ValueError(f"unrecognised regime keys: {unknown_keys}")
        self._blocks: Dict[str, ParamBlock] = dict(blocks)

    def __getitem__(self, regime: str) -> ParamBlock:
        return self._blocks[regime]

    def items(self):
        return self._blocks.items()

    @classmethod
    def uniform(cls, block: ParamBlock) -> "RegimeParams":
        """The same block for every regime — i.e. regime-blind behaviour, expressed in this
        contract. This is the control arm, and the subject of the equivalence test."""
        return cls({r: block for r in ALL_REGIMES})

    def with_override(self, regime: str, **kwargs) -> "RegimeParams":
        """A copy with one regime's block adjusted. Used to build variants without mutation."""
        blocks = dict(self._blocks)
        blocks[regime] = replace(blocks[regime], **kwargs)
        return RegimeParams(blocks)

    def is_uniform(self) -> bool:
        blocks = list(self._blocks.values())
        return all(b == blocks[0] for b in blocks)

    def describe(self) -> Dict[str, dict]:
        return {r: vars(b).copy() for r, b in self._blocks.items()}


def resolve_at(params: RegimeParams, frame: pd.DataFrame) -> ParamBlock:
    """The block in force at the LAST bar of ``frame``.

    Used by the per-entry hooks (``calculate_stop_loss`` / ``calculate_take_profit``), which the
    engine calls with a window ending at the entry bar — so reading the final row is causal by
    construction. A frame with no ``regime`` column resolves to ``UNKNOWN`` rather than guessing.
    """
    if "regime" not in frame.columns or frame.empty:
        return params[UNKNOWN]
    return params[str(frame["regime"].iloc[-1])]
