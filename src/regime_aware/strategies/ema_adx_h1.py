"""Regime-aware port of Trend_EMA_ADX_H1."""

from __future__ import annotations
from typing import Dict, List
import pandas as pd
import numpy as np
from src.layer0.data_access.indicators import ema, adx, atr
from src.layer0.strategies.strategieStaged.trend_ema_adx import TrendEMAADX_H1_Only
from src.regime_aware.context import UNKNOWN
from src.regime_aware.contract import ParamBlock, RegimeParams, resolve_at

BASELINE = ParamBlock(
    enabled=True,
    fast_ema=10,
    slow_ema=20,
    adx_period=14,
    adx_threshold=25.0,
    stop_loss_atr=1.5,
    take_profit_atr=2.5,
)

# Reasoning:
# Ranging: Moving averages whip-saw. Sit out.
# High-Vol: EMAs lag, wide stops hit. Sit out.
# Trending: Relax ADX, the trend is known.
REGIME_AWARE = RegimeParams(
    {
        "Ranging": ParamBlock(**{**vars(BASELINE), "enabled": False}),
        "High-Vol": ParamBlock(**{**vars(BASELINE), "enabled": False}),
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

class RegimeAwareEMAADXH1(TrendEMAADX_H1_Only):
    def __init__(self, params: RegimeParams, name: str = "Trend_EMA_ADX_H1_RA"):
        super().__init__()
        self.params = params
        self.config.name = name
        self._distinct_fast = sorted({b.fast_ema for _, b in params.items()})
        self._distinct_slow = sorted({b.slow_ema for _, b in params.items()})
        
        adx_periods = {b.adx_period for _, b in params.items()}
        if len(adx_periods) > 1: raise ValueError()
        self._adx_period = adx_periods.pop()

    def calculate_indicators(self, df: pd.DataFrame, asset: str, granularity: str) -> pd.DataFrame:
        df = df.copy()
        
        for fast in self._distinct_fast:
            f_scaled = fast // 2 if granularity == "H1" else (fast * 2 if granularity == "D1" else fast)
            df[f'EMA_{fast}'] = ema(df['Close'], f_scaled)
            
        for slow in self._distinct_slow:
            s_scaled = slow // 2 if granularity == "H1" else (slow * 2 if granularity == "D1" else slow)
            df[f'EMA_{slow}'] = ema(df['Close'], s_scaled)
            
        df['ADX'] = adx(df['High'], df['Low'], df['Close'], self._adx_period)
        df['ATR'] = atr(df['High'], df['Low'], df['Close'], self._adx_period)
        
        if "regime" not in df.columns:
            df["regime"] = UNKNOWN
        return df

    def generate_signals(self, df: pd.DataFrame, asset: str, granularity: str) -> pd.Series:
        signals = pd.Series(0, index=df.index, dtype="int64")
        regimes = df["regime"]

        for regime, block in self.params.items():
            if not block.enabled: continue
            in_regime = regimes == regime
            if not in_regime.any(): continue
            
            fast, slow = block.fast_ema, block.slow_ema
            align = np.where(df[f'EMA_{fast}'] > df[f'EMA_{slow}'], 1,
                             np.where(df[f'EMA_{fast}'] < df[f'EMA_{slow}'], -1, 0))
            align_series = pd.Series(align, index=df.index)
            
            buy = (align_series == 1) & (align_series.shift(1) <= 0) & (df['ADX'] > block.adx_threshold) & in_regime
            sell = (align_series == -1) & (align_series.shift(1) >= 0) & (df['ADX'] > block.adx_threshold) & in_regime
            
            if 1 not in block.allowed_directions: buy = buy & False
            if -1 not in block.allowed_directions: sell = sell & False

            signals[buy.fillna(False)] = 1
            signals[sell.fillna(False)] = -1
            
        return signals

    def calculate_stop_loss(self, df: pd.DataFrame, direction: int, entry_price: float, asset: str) -> float:
        block = resolve_at(self.params, df)
        atr_val = df["ATR"].iloc[-1] if "ATR" in df.columns else atr(df["High"], df["Low"], df["Close"], self._adx_period).iloc[-1]
        return entry_price - atr_val * block.stop_loss_atr if direction == 1 else entry_price + atr_val * block.stop_loss_atr

    def calculate_take_profit(self, df: pd.DataFrame, direction: int, entry_price: float, asset: str) -> float:
        block = resolve_at(self.params, df)
        atr_val = df["ATR"].iloc[-1] if "ATR" in df.columns else atr(df["High"], df["Low"], df["Close"], self._adx_period).iloc[-1]
        return entry_price + atr_val * block.take_profit_atr if direction == 1 else entry_price - atr_val * block.take_profit_atr

    def describe(self) -> Dict[str, dict]: return self.params.describe()

def build_baseline() -> RegimeAwareEMAADXH1: return RegimeAwareEMAADXH1(RegimeParams.uniform(BASELINE), "Trend_EMA_ADX_H1_blind")
def build_regime_aware() -> RegimeAwareEMAADXH1: return RegimeAwareEMAADXH1(REGIME_AWARE, "Trend_EMA_ADX_H1_RA")
def build_trend_aware() -> RegimeAwareEMAADXH1: return RegimeAwareEMAADXH1(TREND_AWARE, "Trend_EMA_ADX_H1_TA")
