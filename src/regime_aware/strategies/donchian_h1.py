"""Regime-aware port of Trend_Donchian_H1."""

from __future__ import annotations
from typing import Dict, List
import pandas as pd
from src.layer0.data_access.indicators import adx, atr, donchian_channel
from src.layer0.strategies.strategieStaged.trend_donchian import TrendDonchian_H1_Only
from src.regime_aware.context import UNKNOWN
from src.regime_aware.contract import ParamBlock, RegimeParams, resolve_at

BASELINE = ParamBlock(
    enabled=True,
    channel_period=10,
    adx_period=14,
    adx_threshold=25.0,
    require_adx=True,
    stop_loss_atr=1.5,
    take_profit_atr=3.0,
)

# Reasoning:
# Ranging: Breakouts fail. Sit out.
# High-Vol: Trade, but widen stop to avoid noise.
# Trending: Trend is already established. Lower ADX threshold.
REGIME_AWARE = RegimeParams(
    {
        "Ranging": ParamBlock(**{**vars(BASELINE), "enabled": False}),
        "High-Vol": ParamBlock(**{**vars(BASELINE), "stop_loss_atr": 2.0}),
        "Trending-Up": ParamBlock(**{**vars(BASELINE), "adx_threshold": 20.0}),
        "Trending-Down": ParamBlock(**{**vars(BASELINE), "adx_threshold": 20.0}),
        UNKNOWN: ParamBlock(**{**vars(BASELINE), "enabled": False}),
    }
)

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
    if granularity == "H1":
        return base_period // 2
    if granularity == "D1":
        return base_period * 2
    return base_period

class RegimeAwareDonchianH1(TrendDonchian_H1_Only):
    def __init__(self, params: RegimeParams, name: str = "Trend_Donchian_H1_RA"):
        super().__init__()
        self.params = params
        self.config.name = name
        self._distinct_periods: List[int] = sorted(
            {b.channel_period for _, b in params.items()}
        )
        adx_periods = {b.adx_period for _, b in params.items()}
        if len(adx_periods) > 1:
            raise ValueError("per-regime adx_period not supported")
        self._adx_period = adx_periods.pop()

    def calculate_indicators(self, df: pd.DataFrame, asset: str, granularity: str) -> pd.DataFrame:
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

    def generate_signals(self, df: pd.DataFrame, asset: str, granularity: str) -> pd.Series:
        signals = pd.Series(0, index=df.index, dtype="int64")
        regimes = df["regime"]

        for regime, block in self.params.items():
            if not block.enabled:
                continue
            in_regime = regimes == regime
            if not in_regime.any():
                continue

            p = block.channel_period
            
            buy = df[f"DC_Breakout_Up_{p}"] & (~df[f"DC_Squeeze_{p}"]) & in_regime
            sell = df[f"DC_Breakout_Down_{p}"] & (~df[f"DC_Squeeze_{p}"]) & in_regime
            
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

    def calculate_stop_loss(self, df: pd.DataFrame, direction: int, entry_price: float, asset: str) -> float:
        block = resolve_at(self.params, df)
        atr_val = self._atr_at(df)
        distance = atr_val * block.stop_loss_atr
        return entry_price - distance if direction == 1 else entry_price + distance

    def calculate_take_profit(self, df: pd.DataFrame, direction: int, entry_price: float, asset: str) -> float:
        block = resolve_at(self.params, df)
        atr_val = self._atr_at(df)
        distance = atr_val * block.take_profit_atr
        return entry_price + distance if direction == 1 else entry_price - distance

    def _atr_at(self, df: pd.DataFrame) -> float:
        if "ATR" not in df.columns:
            return float(atr(df["High"], df["Low"], df["Close"], self._adx_period).iloc[-1])
        return float(df["ATR"].iloc[-1])

    def describe(self) -> Dict[str, dict]:
        return self.params.describe()

def build_baseline() -> RegimeAwareDonchianH1:
    return RegimeAwareDonchianH1(RegimeParams.uniform(BASELINE), name="Trend_Donchian_H1_blind")

def build_regime_aware() -> RegimeAwareDonchianH1:
    return RegimeAwareDonchianH1(REGIME_AWARE, name="Trend_Donchian_H1_RA")

def build_trend_aware() -> RegimeAwareDonchianH1:
    return RegimeAwareDonchianH1(TREND_AWARE, name="Trend_Donchian_H1_TA")
