# main_backtest.py
from data_loader import fetch_real_data
from strategy_engine import StrategyQualificationEngine
import pandas as pd

print("\n=== REAL STRATEGY QUALIFICATION ENGINE v2.0 ===\n")
data = fetch_real_data()
results = []

for symbol, df in data.items():
    if len(df) < 1000: continue
    print(f"Testing {symbol} ({len(df)} bars)...")
    engine = StrategyQualificationEngine(df, symbol)
    
    for strat in [
        "Trend_EMA_ADX_Long", "Trend_EMA_ADX_Short",
        "Range_Bollinger_Long", "Range_Bollinger_Short",
        "Trend_Donchian_Long", "Trend_Donchian_Short",
        "Range_Stochastic_Long", "Range_Stochastic_Short"
    ]:
        metrics = engine.evaluate(strat)
        results.append(metrics)
        pd.DataFrame({"Equity": metrics.get("Equity_Curve", [0])}).to_csv(f"equity_{symbol}_{strat}.csv", index=False)

# Leaderboard
print("\n" + "="*110)
print(f"{'STRATEGY':<18} {'SYMBOL':<8} {'TRADES':<6} {'WIN%':<6} {'EXPECT':<8} {'PF':<6} {'MAX DD':<7} {'STATUS'}")
print("="*110)
for r in results:
    print(f"{r['Strategy']:<18} {r['Symbol']:<8} {r['Trades']:<6} {r['Win_Rate']:<6} {r['Expectancy']:<8} {r['PF']:<6} {r['Max_DD']:<7} {r['Status']}")