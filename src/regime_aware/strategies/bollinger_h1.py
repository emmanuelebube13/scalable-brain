"""Regime-aware port of Range_Bollinger_H1."""

from __future__ import annotations
from typing import Dict, List
import pandas as pd
from src.layer0.data_access.indicators import bollinger_bands, rsi, atr
from src.layer0.strategies.strategieStaged.range_bollinger import RangeBollinger_H1_Only
from src.regime_aware.context import UNKNOWN
from src.regime_aware.contract import ParamBlock, RegimeParams, resolve_at

BASELINE = ParamBlock(
    enabled=True,
    bb_period=20,
    bb_std=2.0,
    rsi_period=14,
    rsi_oversold=30.0,
    rsi_overbought=70.0,
    require_rsi=True,
    stop_loss_atr=1.5,
    take_profit_atr=1.5,
)

# Reasoning:
# Trending: Mean reversion gets run over by trends. Sit out.
# High-Vol: Trade, but increase stop.
# Ranging: The intended regime. Trade with standard parameters.
REGIME_AWARE = RegimeParams(
    {
        "Ranging": ParamBlock(**{**vars(BASELINE)}),
        "High-Vol": ParamBlock(**{**vars(BASELINE), "stop_loss_atr": 2.0}),
        "Trending-Up": ParamBlock(**{**vars(BASELINE), "enabled": False}),
        "Trending-Down": ParamBlock(**{**vars(BASELINE), "enabled": False}),
        UNKNOWN: ParamBlock(**{**vars(BASELINE), "enabled": False}),
    }
)

TREND_AWARE = RegimeParams(
    {
        "Trending-Up": ParamBlock(**{**vars(BASELINE), "enabled": False}),
        "Trending-Down": ParamBlock(**{**vars(BASELINE), "enabled": False}),
        "Ranging": ParamBlock(**{**vars(BASELINE), "enabled": False}),
        "High-Vol": ParamBlock(**{**vars(BASELINE), "enabled": False}),
        UNKNOWN: ParamBlock(**{**vars(BASELINE), "enabled": False}),
    }
)

class RegimeAwareBollingerH1(RangeBollinger_H1_Only):
    def __init__(self, params: RegimeParams, name: str = "Range_Bollinger_H1_RA"):
        super().__init__()
        self.params = params
        self.config.name = name
        self._distinct_periods = sorted({b.bb_period for _, b in params.items()})
        self._distinct_stds = sorted({b.bb_std for _, b in params.items()})
        self._distinct_rsi = sorted({b.rsi_period for _, b in params.items()})

    def calculate_indicators(self, df: pd.DataFrame, asset: str, granularity: str) -> pd.DataFrame:
        df = df.copy()
        
        for p in self._distinct_periods:
            for std in self._distinct_stds:
                bb_scaled = max(10, p // 2) if granularity == "H1" else p
                upper, middle, lower = bollinger_bands(df['Close'], bb_scaled, std)
                df[f'BB_Upper_{p}_{std}'] = upper
                df[f'BB_Lower_{p}_{std}'] = lower
                width = (upper - lower) / middle
                df[f'BB_Squeeze_{p}_{std}'] = width < width.rolling(window=50).quantile(0.2)
                
        for r_p in self._distinct_rsi:
            rsi_scaled = max(7, r_p // 2) if granularity == "H1" else r_p
            df[f'RSI_{r_p}'] = rsi(df['Close'], rsi_scaled)
            
        df['ATR'] = atr(df['High'], df['Low'], df['Close'], 14)
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
            
            p, std, r_p = block.bb_period, block.bb_std, block.rsi_period
            
            lower = df[f'BB_Lower_{p}_{std}']
            upper = df[f'BB_Upper_{p}_{std}']
            squeeze = df[f'BB_Squeeze_{p}_{std}']
            rsi_val = df[f'RSI_{r_p}']
            
            buy = (df['Close'] <= lower) & (~squeeze) & in_regime
            sell = (df['Close'] >= upper) & (~squeeze) & in_regime
            
            if block.require_rsi:
                buy = buy & (rsi_val < block.rsi_oversold)
                sell = sell & (rsi_val > block.rsi_overbought)
                
            buy = buy & (df['Close'].shift(1) > lower.shift(1))
            sell = sell & (df['Close'].shift(1) < upper.shift(1))
            
            if 1 not in block.allowed_directions: buy = buy & False
            if -1 not in block.allowed_directions: sell = sell & False

            signals[buy.fillna(False)] = 1
            signals[sell.fillna(False)] = -1
            
        return signals

    def calculate_stop_loss(self, df: pd.DataFrame, direction: int, entry_price: float, asset: str) -> float:
        block = resolve_at(self.params, df)
        atr_val = df["ATR"].iloc[-1] if "ATR" in df.columns else atr(df["High"], df["Low"], df["Close"], 14).iloc[-1]
        return entry_price - atr_val * block.stop_loss_atr if direction == 1 else entry_price + atr_val * block.stop_loss_atr

    def calculate_take_profit(self, df: pd.DataFrame, direction: int, entry_price: float, asset: str) -> float:
        block = resolve_at(self.params, df)
        atr_val = df["ATR"].iloc[-1] if "ATR" in df.columns else atr(df["High"], df["Low"], df["Close"], 14).iloc[-1]
        return entry_price + atr_val * block.take_profit_atr if direction == 1 else entry_price - atr_val * block.take_profit_atr

    def describe(self) -> Dict[str, dict]: return self.params.describe()

def build_baseline() -> RegimeAwareBollingerH1: return RegimeAwareBollingerH1(RegimeParams.uniform(BASELINE), "Range_Bollinger_H1_blind")
def build_regime_aware() -> RegimeAwareBollingerH1: return RegimeAwareBollingerH1(REGIME_AWARE, "Range_Bollinger_H1_RA")
def build_trend_aware() -> RegimeAwareBollingerH1: return RegimeAwareBollingerH1(TREND_AWARE, "Range_Bollinger_H1_TA")
