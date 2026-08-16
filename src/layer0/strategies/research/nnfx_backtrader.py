import numpy as np
import pandas as pd
from typing import List, Mapping, Sequence

from ..contract_v2 import ExitLeg, OrderIntent, StopRule, StrategyMetadataV2, StrategyV2
from ...data_access.indicators import atr

def _calc_butterworth(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> tuple[np.ndarray, np.ndarray]:
    if period <= 0:
        period = 1
    a1 = np.exp(-np.pi / period)
    b1 = 2 * a1 * np.cos(np.radians(1.738 * 180 / period))
    c = a1**2
    c2 = b1 + c
    c3 = -(c + b1 * c)
    c4 = c**2
    c1 = (1 - b1 + c) * (1 - c) / 8
    
    p = (high + low) / 2
    butter = np.zeros_like(p)
    
    for t in range(len(p)):
        if t < 3:
            butter[t] = p[t]
        else:
            butter[t] = c1 * (p[t] + 3*p[t-1] + 3*p[t-2] + p[t-3]) + \
                        c2 * butter[t-1] + c3 * butter[t-2] + c4 * butter[t-3]
            
    base_up = np.zeros(len(p), dtype=bool)
    base_dn = np.zeros(len(p), dtype=bool)
    for t in range(1, len(p)):
        base_up[t] = (close[t] > butter[t]) and (close[t-1] <= butter[t-1])
        base_dn[t] = (close[t] < butter[t]) and (close[t-1] >= butter[t-1])
        
    return base_up, base_dn

def _ema(x: np.ndarray, period: int) -> np.ndarray:
    if period <= 0:
        period = 1
    alpha = 2 / (period + 1)
    res = np.zeros_like(x)
    if len(x) > 0:
        res[0] = x[0]
        for i in range(1, len(x)):
            res[i] = alpha * x[i] + (1 - alpha) * res[i-1]
    return res

def _calc_stc_c1(close: np.ndarray, fast: int, slow: int, cycle: int) -> np.ndarray:
    macd = _ema(close, fast) - _ema(close, slow)
    
    pf = np.zeros_like(close)
    stc = np.zeros_like(close)
    f1 = np.zeros_like(close)
    f2 = np.zeros_like(close)
    
    window = cycle - 1 if cycle > 1 else 1
    
    for t in range(len(close)):
        if t < window:
            v1 = np.min(macd[:t+1])
            v2 = np.max(macd[:t+1]) - v1
        else:
            v1 = np.min(macd[t-window:t+1])
            v2 = np.max(macd[t-window:t+1]) - v1
            
        if v2 > 0:
            f1[t] = 100 * (macd[t] - v1) / v2
        else:
            f1[t] = f1[t-1] if t > 0 else 0
            
        pf[t] = pf[t-1] + 0.5 * (f1[t] - (pf[t-1] if t > 0 else 0)) if t > 0 else f1[t]
        
    for t in range(len(close)):
        if t < window:
            v3 = np.min(pf[:t+1])
            v4 = np.max(pf[:t+1]) - v3
        else:
            v3 = np.min(pf[t-window:t+1])
            v4 = np.max(pf[t-window:t+1]) - v3
            
        if v4 > 0:
            f2[t] = 100 * (pf[t] - v3) / v4
        else:
            f2[t] = f2[t-1] if t > 0 else 0
            
        stc[t] = stc[t-1] + 0.5 * (f2[t] - (stc[t-1] if t > 0 else 0)) if t > 0 else f2[t]
        
    c1_state = np.zeros(len(close), dtype=int)
    for t in range(1, len(close)):
        if stc[t-1] <= 25 and stc[t] > 25:
            c1_state[t] = 1
        elif stc[t-1] >= 75 and stc[t] < 75:
            c1_state[t] = -1
        else:
            c1_state[t] = c1_state[t-1]
            
    return c1_state

def _calc_itrend_c2(close: np.ndarray, period: int) -> np.ndarray:
    if period <= 0:
        period = 1
    a = 2.0 / (1 + period)
    itrend = np.zeros_like(close)
    trigger = np.zeros_like(close)
    c2_state = np.zeros(len(close), dtype=int)
    
    for t in range(len(close)):
        if t < period:
            if t < 2:
                itrend[t] = close[t]
            else:
                itrend[t] = (close[t] + 2*close[t-1] + close[t-2]) / 4
        else:
            itrend[t] = (a - (a/2)**2)*close[t] + (a**2/2)*close[t-1] - (a - 3*a**2/4)*close[t-2] \
                        + 2*(1-a)*itrend[t-1] - (1-a)**2 * itrend[t-2]
            
        if t >= 2:
            trigger[t] = 2*itrend[t] - itrend[t-2]
            
        if trigger[t] > itrend[t]:
            c2_state[t] = 1
        elif trigger[t] < itrend[t]:
            c2_state[t] = -1
        else:
            c2_state[t] = 0
            
    return c2_state

def _calc_damiani(high: pd.Series, low: pd.Series, close: pd.Series, atr_fast: int, atr_slow: int, std_fast: int, std_slow: int) -> np.ndarray:
    if atr_fast <= 0: atr_fast = 1
    if atr_slow <= 0: atr_slow = 1
    if std_fast <= 0: std_fast = 1
    if std_slow <= 0: std_slow = 1
    
    aF = atr(high, low, close, atr_fast).to_numpy()
    aS = atr(high, low, close, atr_slow).to_numpy()
    
    sF = close.rolling(std_fast, min_periods=std_fast).std(ddof=0).to_numpy()
    sS = close.rolling(std_slow, min_periods=std_slow).std(ddof=0).to_numpy()
    
    c_arr = close.to_numpy()
    v = np.zeros_like(c_arr)
    vol_f = np.zeros(len(c_arr), dtype=int)
    dv_t = np.zeros_like(c_arr)
    
    max_lookback = max(atr_slow, std_slow)
    
    for t in range(len(c_arr)):
        if t < max_lookback - 1 or np.isnan(aS[t]) or np.isnan(sS[t]) or aS[t] == 0 or sS[t] == 0:
            v[t] = 0.005
            vol_f[t] = 0
        else:
            v[t] = aF[t]/aS[t] + 0.5 * (v[t-1] - (v[t-3] if t >= 3 else 0))
            dv_t[t] = 1.4 - sF[t]/sS[t]
            if v[t] > dv_t[t]:
                vol_f[t] = 1
            else:
                vol_f[t] = 0
                
    return vol_f


class NnfxBacktrader(StrategyV2):
    BUTTER_PERIOD = 40
    STC_FAST = 20
    STC_SLOW = 50
    STC_CYCLE = 10
    ITREND_PERIOD = 30
    DAMIANI_ATR_FAST = 13
    DAMIANI_ATR_SLOW = 40
    DAMIANI_STD_FAST = 20
    DAMIANI_STD_SLOW = 100
    ATR_PERIOD = 14

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="nnfx_backtrader",
            name="NNFX Backtrader",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "Daily-trend persistence in FX is exploitable when several independent "
                "trend/volatility measurements agree: a smoothed-price baseline cross "
                "(Butterworth low-pass filter) fires the trigger, two mathematically "
                "unrelated confirmation oscillators (Schaff Trend Cycle and iTrend) "
                "veto whipsaws, and a volatility-regime meter (Damiani) blocks entries "
                "in flat markets."
            ),
            granularities=["D1"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="D1",
            context_granularities=(),
            simulate_on="H1",
            source_row=42,
            source_url="https://github.com/ddm-j/NNFX-Backtrader",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["atr"]

    @property
    def warmup_bars(self) -> int:
        return 150

    def generate_orders(self, frames: Mapping[str, pd.DataFrame]) -> Sequence[OrderIntent]:
        d1 = frames["D1"]
        high = d1["High"]
        low = d1["Low"]
        close = d1["Close"]
        
        h_arr = high.to_numpy(dtype=float)
        l_arr = low.to_numpy(dtype=float)
        c_arr = close.to_numpy(dtype=float)
        
        base_up, base_dn = _calc_butterworth(h_arr, l_arr, c_arr, self.BUTTER_PERIOD)
        c1_state = _calc_stc_c1(c_arr, self.STC_FAST, self.STC_SLOW, self.STC_CYCLE)
        c2_state = _calc_itrend_c2(c_arr, self.ITREND_PERIOD)
        vol_f = _calc_damiani(
            high, low, close, 
            self.DAMIANI_ATR_FAST, self.DAMIANI_ATR_SLOW, 
            self.DAMIANI_STD_FAST, self.DAMIANI_STD_SLOW
        )
        atr14 = atr(high, low, close, self.ATR_PERIOD).to_numpy(dtype=float)
        
        orders: List[OrderIntent] = []
        for t in range(self.warmup_bars, len(d1)):
            if vol_f[t] != 1:
                continue
                
            is_long = base_up[t] and (c1_state[t] == 1) and (c2_state[t] == 1)
            is_short = base_dn[t] and (c1_state[t] == -1) and (c2_state[t] == -1)
            
            if is_long:
                anchor = float(c_arr[t])
                stop_val = anchor - 1.5 * float(atr14[t])
                tp_val = anchor + 3.0 * float(atr14[t])
                
                orders.append(
                    OrderIntent(
                        decision_bar=d1.index[t],
                        direction=1,
                        entry="market",
                        entry_price=None,
                        stop=StopRule(
                            price=stop_val,
                            move_to_breakeven_on=None,
                            breakeven_offset_pips=0.0
                        ),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="take_profit",
                                price=tp_val,
                                label="TP1"
                            )
                        ],
                        size_fraction=1.0,
                        tag="nnfx_long"
                    )
                )
            elif is_short:
                anchor = float(c_arr[t])
                stop_val = anchor + 1.5 * float(atr14[t])
                tp_val = anchor - 3.0 * float(atr14[t])
                
                orders.append(
                    OrderIntent(
                        decision_bar=d1.index[t],
                        direction=-1,
                        entry="market",
                        entry_price=None,
                        stop=StopRule(
                            price=stop_val,
                            move_to_breakeven_on=None,
                            breakeven_offset_pips=0.0
                        ),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="take_profit",
                                price=tp_val,
                                label="TP1"
                            )
                        ],
                        size_fraction=1.0,
                        tag="nnfx_short"
                    )
                )
                
        return orders
