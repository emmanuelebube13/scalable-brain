"""Regime-aware port of ``Trend_Donchian_VCP``.

Subclasses the production strategy so the control arm is not a re-implementation: config,
warm-up, exit handling and the engine's cost model are inherited unchanged. Only three hooks are
overridden — ``calculate_indicators``, ``generate_signals``, and the two per-entry risk hooks —
and each consults the regime in force at the bar it is deciding on.

Baseline parity
---------------
``BASELINE`` reproduces production ``Trend_Donchian_VCP`` exactly: channel_period 20 (halved on
H1 by the inherited granularity scaling), ADX 14 / threshold 25 required, squeeze lookback 5,
stop 1.0×ATR, target 4.0×ATR. Instantiated with ``RegimeParams.uniform(BASELINE)`` this class
must emit trade-for-trade identical output to the production strategy — see
``tests/test_equivalence.py``.

Where REGIME_AWARE came from — read this before trusting any result
-------------------------------------------------------------------
The per-regime blocks below were chosen **a priori, from the strategy's economics, before any
regime-aware backtest was run**. They are not fitted, not tuned, and were not adjusted after
seeing output. The reasoning, stated in advance so it can be judged independently of the result:

* **Ranging** — a breakout system's classic failure mode is the false break in a range. Production
  data agrees: VCP's worst cell is Ranging (PF 0.77–0.78). Sit it out entirely.
* **High-Vol** — VCP's best cell (PF 1.31 blind, 1.96 under the D1 macro filter). Volatility is
  what a volatility-contraction breakout is built for. Trade it, but widen the stop to 1.5×ATR:
  a 1.0×ATR stop in a high-volatility regime is stopped out by noise before the move develops.
* **Trending-Up / Trending-Down** — a breakout in the direction of an established trend is the
  textbook case. Trade both with the baseline stop, but drop the ADX requirement to 20: ADX is a
  trend-strength filter, and requiring strong trend confirmation *inside* an already-classified
  trending regime is redundant gating that only costs entries.
* **UNKNOWN** — the HMM has not produced a causal label yet (warm-up). No opinion, no trade.

If the result is good, the honesty of this list is what makes it believable. Do not edit these
values in response to output; add a new named variant instead.
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from src.layer0.data_access.indicators import adx, atr, donchian_channel
from src.layer0.strategies.strategieStaged.trend_donchian import TrendDonchian_VCP
from src.regime_aware.context import UNKNOWN
from src.regime_aware.contract import ParamBlock, RegimeParams, resolve_at

#: Production ``Trend_Donchian_VCP`` settings, exactly.
BASELINE = ParamBlock(
    enabled=True,
    channel_period=20,
    adx_period=14,
    adx_threshold=25.0,
    require_adx=True,
    stop_loss_atr=1.0,
    take_profit_atr=4.0,
    squeeze_lookback=5,
)

#: The a-priori regime-aware set. See the module docstring for the reasoning behind each block.
REGIME_AWARE = RegimeParams(
    {
        "Ranging": ParamBlock(**{**vars(BASELINE), "enabled": False}),
        "High-Vol": ParamBlock(**{**vars(BASELINE), "stop_loss_atr": 1.5}),
        "Trending-Up": ParamBlock(**{**vars(BASELINE), "adx_threshold": 20.0}),
        "Trending-Down": ParamBlock(**{**vars(BASELINE), "adx_threshold": 20.0}),
        UNKNOWN: ParamBlock(**{**vars(BASELINE), "enabled": False}),
    }
)


#: Parameter set for the **D1-trend context** (``build_trend_labels``), whose vocabulary is only
#: Trending-Up / Trending-Down / UNKNOWN. Also chosen a priori: trade breakouts only in the
#: direction of the established daily trend — the rule the MTF experiment tested externally,
#: here expressed inside the regime contract. Ranging/High-Vol blocks are declared because the
#: contract demands completeness; under this context they never occur.
TREND_AWARE = RegimeParams(
    {
        "Trending-Up": ParamBlock(**{**vars(BASELINE), "allowed_directions": (1,)}),
        "Trending-Down": ParamBlock(**{**vars(BASELINE), "allowed_directions": (-1,)}),
        "Ranging": ParamBlock(**{**vars(BASELINE), "enabled": False}),
        "High-Vol": ParamBlock(**{**vars(BASELINE), "enabled": False}),
        UNKNOWN: ParamBlock(**{**vars(BASELINE), "enabled": False}),
    }
)


def _scaled_period(base_period: int, granularity: str) -> int:
    """The inherited granularity scaling from ``TrendDonchianStrategy.calculate_indicators``.

    Reproduced rather than imported because the production method bakes it into a larger body.
    Any drift here breaks the equivalence test, which is exactly the alarm we want.
    """
    if granularity == "H1":
        return base_period // 2
    if granularity == "D1":
        return base_period * 2
    return base_period


class RegimeAwareDonchianVCP(TrendDonchian_VCP):
    """``Trend_Donchian_VCP`` with the regime label as a first-class input."""

    def __init__(self, params: RegimeParams, name: str = "Trend_Donchian_VCP_RA"):
        super().__init__()
        self.params = params
        self.config.name = name
        # Risk multiples now vary per regime; the config values are the UNKNOWN-block fallback
        # for any caller that reads them without a frame (nothing in this path does).
        self._distinct_periods: List[int] = sorted(
            {b.channel_period for _, b in params.items()}
        )
        adx_periods = {b.adx_period for _, b in params.items()}
        if len(adx_periods) > 1:
            raise ValueError(
                f"per-regime adx_period is not supported ({adx_periods}); ADX and ATR are shared "
                "across blocks so that the ATR used for risk is identical between arms"
            )
        self._adx_period = adx_periods.pop()

    # ---------------------------------------------------------------- indicators

    def calculate_indicators(
        self, df: pd.DataFrame, asset: str, granularity: str
    ) -> pd.DataFrame:
        """Donchian columns for EVERY distinct channel_period, computed over the full series.

        Computing per parameter value over the continuous frame (rather than within regime
        segments) is what keeps the channel honest across regime boundaries — see the contract
        module docstring.
        """
        df = df.copy()
        df["ADX"] = adx(df["High"], df["Low"], df["Close"], self._adx_period)
        df["ATR"] = atr(df["High"], df["Low"], df["Close"], self._adx_period)

        for base in self._distinct_periods:
            p = _scaled_period(base, granularity)
            upper, middle, lower = donchian_channel(df["High"], df["Low"], p)
            width = upper - lower
            df[f"DC_Upper_{base}"] = upper
            df[f"DC_Lower_{base}"] = lower
            df[f"DC_Width_{base}"] = width
            df[f"DC_Squeeze_{base}"] = width < width.rolling(window=50).quantile(0.2)
            df[f"DC_Breakout_Up_{base}"] = df["Close"] > upper.shift(1)
            df[f"DC_Breakout_Down_{base}"] = df["Close"] < lower.shift(1)

        if "regime" not in df.columns:
            df["regime"] = UNKNOWN
        return df

    # ---------------------------------------------------------------- signals

    def generate_signals(
        self, df: pd.DataFrame, asset: str, granularity: str
    ) -> pd.Series:
        """VCP entries, with each bar judged under its own regime's parameter block.

        One vectorised pass per regime, masked to the bars carrying that label. A bar whose block
        is ``enabled=False`` can never produce an entry, which is how "sit this regime out" is
        expressed.
        """
        signals = pd.Series(0, index=df.index, dtype="int64")
        regimes = df["regime"]

        for regime, block in self.params.items():
            if not block.enabled:
                continue
            in_regime = regimes == regime
            if not in_regime.any():
                continue

            p = block.channel_period
            squeeze_recent = (
                df[f"DC_Squeeze_{p}"]
                .rolling(window=block.squeeze_lookback)
                .max()
                .fillna(0)
                .astype(bool)
                .shift(1, fill_value=False)
            )
            buy = df[f"DC_Breakout_Up_{p}"] & squeeze_recent & in_regime
            sell = df[f"DC_Breakout_Down_{p}"] & squeeze_recent & in_regime
            if block.require_adx:
                strong = df["ADX"] > block.adx_threshold
                buy = buy & strong
                sell = sell & strong
            if 1 not in block.allowed_directions:
                buy = buy & False
            if -1 not in block.allowed_directions:
                sell = sell & False

            signals[buy.fillna(False)] = 1
            signals[sell.fillna(False)] = -1

        return signals

    # ---------------------------------------------------------------- per-entry risk

    def calculate_stop_loss(
        self, df: pd.DataFrame, direction: int, entry_price: float, asset: str
    ) -> float:
        """ATR stop using the multiple belonging to the regime at the ENTRY bar.

        The engine passes a window ending at the entry bar, so reading its last row is causal.
        """
        block = resolve_at(self.params, df)
        atr_val = self._atr_at(df)
        distance = atr_val * block.stop_loss_atr
        return entry_price - distance if direction == 1 else entry_price + distance

    def calculate_take_profit(
        self, df: pd.DataFrame, direction: int, entry_price: float, asset: str
    ) -> float:
        block = resolve_at(self.params, df)
        atr_val = self._atr_at(df)
        distance = atr_val * block.take_profit_atr
        return entry_price + distance if direction == 1 else entry_price - distance

    def _atr_at(self, df: pd.DataFrame) -> float:
        if "ATR" not in df.columns:
            return float(
                atr(df["High"], df["Low"], df["Close"], self._adx_period).iloc[-1]
            )
        return float(df["ATR"].iloc[-1])

    # ---------------------------------------------------------------- reporting

    def describe(self) -> Dict[str, dict]:
        return self.params.describe()


def build_baseline() -> RegimeAwareDonchianVCP:
    """Control arm: one uniform block, i.e. production behaviour expressed in this contract."""
    return RegimeAwareDonchianVCP(
        RegimeParams.uniform(BASELINE), name="Trend_Donchian_VCP_blind"
    )


def build_regime_aware() -> RegimeAwareDonchianVCP:
    """Treatment arm A: a-priori blocks over the HMM regime labels."""
    return RegimeAwareDonchianVCP(REGIME_AWARE, name="Trend_Donchian_VCP_RA")


def build_trend_aware() -> RegimeAwareDonchianVCP:
    """Treatment arm B: a-priori blocks over the D1-trend context."""
    return RegimeAwareDonchianVCP(TREND_AWARE, name="Trend_Donchian_VCP_TA")
