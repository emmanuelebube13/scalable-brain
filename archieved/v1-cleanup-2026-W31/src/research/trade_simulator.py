# trade_simulator.py
import numpy as np
import pandas as pd
from config import SPREAD_ATR, SLIPPAGE_ATR, COMMISSION_PER_TRADE_ATR

class RealTradeSimulator:
    def __init__(self, df: pd.DataFrame, symbol: str, strategy_name: str):
        self.df = df.copy()
        self.symbol = symbol
        self.strategy_name = strategy_name
        self.spread_atr = SPREAD_ATR.get(symbol, 0.15)
        # Fallback for new _Long/_Short names
        clean_name = strategy_name.replace("_Long", "").replace("_Short", "")
        self.slippage_atr = SLIPPAGE_ATR.get(clean_name, 0.10)
        self.direction = "long" if "Long" in strategy_name else "short"   # <<< AUTO-DETECT

    def simulate_trade(self, entry_idx: int, sl_mult: float = 1.0, tp_mult: float = 3.0):
        """Bar-by-bar realistic simulation — NOW FULLY SUPPORTS LONG + SHORT with 1:3 R:R."""
        if entry_idx + 2 >= len(self.df):
            return 0.0, 0

        atr = self.df['ATR'].iloc[entry_idx]
        spread = self.spread_atr * atr
        slippage = self.slippage_atr * atr
        commission = COMMISSION_PER_TRADE_ATR * atr

        entry_price = self.df['Open'].iloc[entry_idx + 1]

        if self.direction == "long":
            entry_price += (spread + slippage) / 2
            sl_price = entry_price - sl_mult * atr
            tp_price = entry_price + tp_mult * atr

            for j in range(entry_idx + 2, len(self.df)):
                high = self.df['High'].iloc[j]
                low = self.df['Low'].iloc[j]

                if high >= tp_price:  # TP hit
                    exit_price = tp_price - (spread + slippage) / 2
                    r = (exit_price - entry_price) / atr - commission / atr
                    return round(r, 4), j - entry_idx

                if low <= sl_price:   # SL hit
                    exit_price = sl_price + (spread + slippage) / 2
                    r = (exit_price - entry_price) / atr - commission / atr
                    return round(r, 4), j - entry_idx

                if j - entry_idx > 120:
                    break

            # Never hit → force close
            exit_price = self.df['Close'].iloc[-1]
            r = (exit_price - entry_price) / atr - commission / atr
            return round(r, 4), len(self.df) - entry_idx - 1

        else:  # SHORT
            entry_price -= (spread + slippage) / 2
            sl_price = entry_price + sl_mult * atr
            tp_price = entry_price - tp_mult * atr

            for j in range(entry_idx + 2, len(self.df)):
                high = self.df['High'].iloc[j]
                low = self.df['Low'].iloc[j]

                if low <= tp_price:   # TP hit (price falls)
                    exit_price = tp_price + (spread + slippage) / 2
                    r = (entry_price - exit_price) / atr - commission / atr
                    return round(r, 4), j - entry_idx

                if high >= sl_price:  # SL hit (price rises)
                    exit_price = sl_price - (spread + slippage) / 2
                    r = (entry_price - exit_price) / atr - commission / atr
                    return round(r, 4), j - entry_idx

                if j - entry_idx > 120:
                    break

            # Never hit → force close
            exit_price = self.df['Close'].iloc[-1]
            r = (entry_price - exit_price) / atr - commission / atr
            return round(r, 4), len(self.df) - entry_idx - 1

    def run_backtest(self, entry_indices: list) -> dict:
        if len(entry_indices) < 30:
            return {"Status": "REJECTED ❌ (Too few trades)", "Trades": len(entry_indices)}

        results = []
        equity = [0.0]
        for idx in entry_indices:
            r, bars = self.simulate_trade(idx)
            if bars == 0: continue
            results.append({"R": r, "Bars": bars})
            equity.append(equity[-1] + r)

        eq = np.array(equity[1:])
        wins = sum(1 for r in results if r["R"] > 0)
        total_profit = sum(r["R"] for r in results if r["R"] > 0)
        total_loss = abs(sum(r["R"] for r in results if r["R"] < 0)) or 0.0001

        metrics = {
            "Strategy": self.strategy_name,
            "Symbol": self.symbol,
            "Trades": len(results),
            "Win_Rate": f"{(wins / len(results) * 100):.1f}%" if results else "0%",
            "Expectancy": round(np.mean([r["R"] for r in results]), 4) if results else 0,
            "PF": round(total_profit / total_loss, 2),
            "Max_DD": round((eq - np.maximum.accumulate(eq)).min(), 2) if len(eq) > 1 else 0,
            "Sharpe": round(np.mean([r["R"] for r in results]) / (np.std([r["R"] for r in results]) + 1e-8) * np.sqrt(252/24), 2),
            "Avg_Hold_Bars": round(np.mean([r["Bars"] for r in results]), 1) if results else 0,
            "Status": "PROMOTED ✅" if (results and np.mean([r["R"] for r in results]) > 0.20 and (eq - np.maximum.accumulate(eq)).min() > -6.0) else "REJECTED ❌",
            "Equity_Curve": eq.tolist()
        }
        return metrics