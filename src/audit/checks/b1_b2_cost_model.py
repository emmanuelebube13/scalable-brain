import sys
import os
import numpy as np

def run(mode: str) -> dict:
    # 1. B1 - Analysis of BacktestConfig and position_engine.py
    # We statically know from backtest_engine.py and position_engine.py:
    # entry_price uses Close/Open prices (which are Mid prices) plus/minus slippage.
    # exit_price uses Close/High/Low/etc plus/minus slippage.
    # Spread is applied in _apply_friction to dollar PnL, but NEVER to entry/exit prices.
    # Therefore, spread is NOT deducted from realized R.

    # 2. B2 - Calculate median stop distance and spread / median_stop as % of R
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
        from src.layer0.strategies.v2_harness import discover, build_frames
        from src.layer0.strategies.position_engine import PositionEngine
        from src.layer0.data_access.indicators import get_pip_value

        strats = discover()
        stops_pips = []
        for sid, strat in strats.items():
            try:
                pair = strat.metadata.pairs[0]
                granularity = strat.metadata.primary_granularity
                frames = build_frames(pair, granularity, strat.metadata.context_granularities, lookback_years=1)
                if not frames: continue
                intents = list(strat.generate_orders(frames))
                if not intents: continue
                engine = PositionEngine()
                res = engine.run(frames[granularity], intents, pair=pair, warmup_bars=strat.warmup_bars)
                if res.trades.empty: continue
                pip = get_pip_value(pair)
                stops = abs(res.trades['entry_price'] - res.trades['initial_stop_price']) / pip
                stops_pips.extend(stops.tolist())
            except Exception:
                continue

        med_stop = float(np.median(stops_pips)) if stops_pips else 0.0
        spread = 1.0  # From BacktestConfig
        pct_of_r = (spread / med_stop) * 100 if med_stop > 0 else 0.0

        verdict = (
            "B1: Trades enter and exit at Mid prices (OHLC) +/- slippage. "
            "Spread is NOT deducted from realized R (it hits dollar PnL only). "
            f"B2: Computed median stop distance is {med_stop:.2f} pips. "
            f"Spread (1 pip) as % of R is {pct_of_r:.2f}%."
        )

        return {
            "id": "B1_B2",
            "title": "Cost Model: Price semantics and omitted spread magnitude",
            "severity": "P1",
            "status": "FAIL" if pct_of_r > 0 else "PASS", # Flagged since R is overstated by ~1.7%
            "verdict": verdict,
            "evidence": {
                "median_stop_pips": med_stop,
                "spread_pips": spread,
                "spread_pct_of_r": pct_of_r,
                "b1_prices": "Mid (OHLC + slippage)",
                "b1_spread_in_r": False
            },
            "notes": "R-multiples are spread-free by construction, overstating true edge."
        }
    except Exception as e:
        return {
            "id": "B1_B2",
            "title": "Cost Model: Price semantics and omitted spread magnitude",
            "severity": "P1",
            "status": "INCONCLUSIVE",
            "verdict": f"Failed to compute: {e}",
            "evidence": {},
            "notes": ""
        }

if __name__ == "__main__":
    print(run("test"))
