# walk_forward_analysis.py
import pandas as pd
import numpy as np
import glob

print("\n=== WALK-FORWARD ANALYSIS FIREWALL (Time Robustness) ===")
print("4 rolling windows | 75% IS → 25% OOS | No parameter optimization\n")

files = glob.glob("equity_*.csv")
if not files:
    print("❌ Run main_backtest.py first to generate equity_*.csv files!")
    exit()

for file in sorted(files):
    name = file.replace("equity_", "").replace(".csv", "")
    eq = pd.read_csv(file)['Equity'].values
    n = len(eq)
    window_size = n // 4
    
    print(f"→ {name} ({n} trades)")
    passed = 0
    for i in range(3):  # 3 out-of-sample tests
        oos_start = (i + 1) * window_size
        oos_end = min((i + 2) * window_size, n)
        oos_r = np.diff(eq[oos_start:oos_end])
        if len(oos_r) < 10:
            continue
        exp_oos = np.mean(oos_r)
        pf_oos = (np.sum(oos_r[oos_r > 0]) / abs(np.sum(oos_r[oos_r < 0]))) if any(oos_r < 0) else float('inf')
        status = "PASSED ✅" if exp_oos > 0.15 else "FAILED ❌"
        print(f"   Window {i+1} OOS → Expectancy {exp_oos:.4f} | PF {pf_oos:.2f} | {status}")
        if status == "PASSED ✅":
            passed += 1
    final = "STRATEGY SURVIVES WALK-FORWARD ✅" if passed >= 2 else "STRATEGY FAILS WALK-FORWARD ❌"
    print(f"   → {final}\n")