"""Trade geometry — the payoff shape a trade was entered with, in ATR units.

``fact_trade_outcomes.atr_sl_multiplier`` and ``atr_tp_multiplier`` were declared when the
table was created and have been **100% NULL for every one of its 93,738 rows**. Both
writers pass a literal ``None`` with the comment "strategy SL not ATR-multiple here" — true,
the strategies set absolute prices, but the ATR multiple is derivable from those prices and
nothing ever derived it. The columns were a place to put the number, not a source of it.

**Why this matters beyond tidiness.** The gatekeeper's whole feature basis was
``atr_value``, ``adx_value``, ``regime_structural`` and ``strategy_id``, and ``strategy_id``
carried 96.78% of its gain importance — the "regime-aware gatekeeper" had learned strategy
identity and essentially nothing else (FIX-S1-012). Removing ``strategy_id`` left a model
with no significant uplift at H4 (p=0.44) or D1 (p=1.00) (WO-04B). That is the expected
result: market state alone does not say much about whether a trade wins, but **how far the
stop is and how far the target is** say a great deal, and they say it in terms that transfer
between strategies. A 1.5×ATR stop against a 3×ATR target is the same bet whichever
strategy places it, which is exactly what ``strategy_id`` is not.

Three properties this module is built around:

**Known at entry.** Every input is the geometry the trade was *entered with* — the fill
price, the initial stop, the declared target. Nothing here reads an exit, a realised fill,
or ``holding_bars``. Those describe the outcome and would make a feature a function of the
label it is meant to predict.

**One rule for the ATR reference, two correct resolutions.** The rule is *the most recent
ATR available at entry under that engine's fill model*, and the two engines genuinely
differ:

``backtest_engine_v1`` (``reference="entry_bar"``)
    Enters at ``df["Close"].iloc[i]`` — the close of bar ``i``, by which time bar ``i`` is
    complete. ``ATR(i)`` is therefore known at entry, and it is what the v1 strategies
    declare against.

``position_engine_v2`` (``reference="prior_bar"``)
    May fill *intrabar* on bar ``i``, so ``ATR(i)`` is not knowable at the fill. The engine
    itself resolves ATR-multiple legs against ``atr_values[fill_bar - 1]``, and this module
    matches it.

Using one reference for both was tried first and rejected on measurement, not taste. On
``Trend_EMA_ADX_H4`` / EUR_USD, 201 trades:

===========================  ======  ======  ==============================
reference                      mean      sd  reads as
===========================  ======  ======  ==============================
``ATR(i)``   entry bar        1.5000  0.0000  the declared 1.5x, exactly
``ATR(i-1)`` prior bar        1.4968  0.1079  1.5x plus 7% of noise
===========================  ======  ======  ==============================

That dispersion is entirely ``ATR(i-1)/ATR(i)`` — a volatility-acceleration signal folded
into what is supposed to be a geometry feature. Two quantities in one column is the
conflation this repo keeps paying for; a tree model splitting on "stop wider than 2xATR"
wants the clean number.

``ATR_PERIOD`` is 14 in all four places that compute one — here,
``ContractStrategyAdapter``, ``PositionEngine``, and ``build_inference_features``.
Agreement is asserted by test rather than assumed; see
``test_geometry.py::test_the_reference_matches_the_position_engines_own_atr``.

**Null, never a placeholder.** A trade with no declared take-profit (trailing stop, time
exit, opposite-signal close) gets ``None``, not a filled-in number. A placeholder would be
indistinguishable from a real target of that size, and would teach the model that every
trade has one.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pandas as pd

from src.layer0.data_access.indicators import atr

# Matches ContractStrategyAdapter.ATR_PERIOD and build_inference_features. Imported
# rather than redeclared would be better still, but engine_adapter pulls in the whole
# strategy stack; the equality is pinned by test instead.
ATR_PERIOD = 14

# Below this the ATR is effectively zero (a dead or synthetic series) and the ratio would
# explode. Same order as the guard in the gatekeeper's `adx_over_atr`.
_MIN_ATR = 1e-8


# Which ATR bar each engine's fill model makes available at entry. Keyed by the
# `engine` column of `dim_strategy`, so a new engine has to declare its answer rather
# than inherit someone else's by accident.
REFERENCE_BY_ENGINE = {
    "backtest_engine_v1": "entry_bar",
    "position_engine_v2": "prior_bar",
}
_VALID_REFERENCES = ("entry_bar", "prior_bar")


def atr_reference(
    frame: pd.DataFrame, reference: str = "prior_bar", period: int = ATR_PERIOD
) -> pd.Series:
    """ATR available at entry for each bar, indexed like ``frame``.

    ``reference="entry_bar"`` is ``ATR(i)``: valid only where entry is at the bar's close,
    so the bar is complete. ``reference="prior_bar"`` is ``ATR(i-1)``: required wherever a
    fill can land inside bar ``i``, which is ``PositionEngine``'s case.

    Neither is a default worth guessing at, but ``prior_bar`` is the conservative one — it
    is never less causal than the truth — so it is what an unspecified caller gets.
    """
    if reference not in _VALID_REFERENCES:
        raise ValueError(
            f"reference must be one of {_VALID_REFERENCES}, got {reference!r}"
        )
    values = atr(frame["High"], frame["Low"], frame["Close"], period=period)
    return values if reference == "entry_bar" else values.shift(1)


def multiples(
    entry_price: Optional[float],
    stop_price: Optional[float],
    take_profit_price: Optional[float],
    atr_ref: Optional[float],
) -> Tuple[Optional[float], Optional[float]]:
    """``(atr_sl_multiplier, atr_tp_multiplier)`` for one trade.

    Both are unsigned distances in ATR units — direction lives in ``entry_signal_type``
    and duplicating it here would just give the model two copies of the same column, which
    is the ``trending_strength``/``adx_value`` mistake.

    Returns ``(None, None)`` when the ATR reference is missing or degenerate: during the
    warmup window ``atr_reference`` is NaN by construction, and a trade there has no
    meaningful scale to be expressed in.
    """
    if atr_ref is None or not np.isfinite(atr_ref) or atr_ref < _MIN_ATR:
        return None, None
    if entry_price is None or not np.isfinite(entry_price):
        return None, None

    sl_mult: Optional[float] = None
    if stop_price is not None and np.isfinite(stop_price):
        sl_mult = abs(float(entry_price) - float(stop_price)) / float(atr_ref)

    tp_mult: Optional[float] = None
    if take_profit_price is not None and np.isfinite(take_profit_price):
        tp_mult = abs(float(take_profit_price) - float(entry_price)) / float(atr_ref)

    return sl_mult, tp_mult


class GeometryLookup:
    """ATR reference for one (symbol × granularity) price frame, keyed by entry time.

    Built once per series rather than per trade: the ATR is an EWM recursion over the
    whole frame, and recomputing it inside a per-trade loop is both slow and — because
    ``ewm(adjust=False)`` seeds from the first row it is given — a way to get three
    different answers for the same bar. That is precisely the defect R2 was opened to fix
    in the structural labeller; the same trap is here.
    """

    def __init__(
        self,
        frame: pd.DataFrame,
        reference: str = "prior_bar",
        period: int = ATR_PERIOD,
    ) -> None:
        self.reference = reference
        self._atr = atr_reference(frame, reference=reference, period=period)

    def at(self, when) -> Optional[float]:
        """ATR reference for the bar at ``when``, or ``None`` if there is no such bar.

        An exact index lookup, not ``asof``. ``when`` is an entry time taken straight from
        the engine's own bar index, so it either matches a bar or something upstream is
        wrong — and silently sliding to the nearest earlier bar would hide that.
        """
        key = pd.Timestamp(when)
        if key.tzinfo is not None:
            key = key.tz_convert("UTC").tz_localize(None)
        try:
            value = self._atr.get(key)
        except (KeyError, TypeError):
            return None
        if value is None:
            return None
        value = float(value)
        return None if not np.isfinite(value) else value

    def for_trade(
        self,
        when,
        entry_price: Optional[float],
        stop_price: Optional[float],
        take_profit_price: Optional[float],
    ) -> Tuple[Optional[float], Optional[float]]:
        """``multiples()`` with the ATR reference resolved from ``when``."""
        return multiples(entry_price, stop_price, take_profit_price, self.at(when))
