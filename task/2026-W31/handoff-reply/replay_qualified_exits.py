"""Replay Computer 2's live trades under the QUALIFIED exit policy.

Live ran sl_atr_mult=1.0 / tp_atr_mult=3.0. Strategy 10 was qualified at
stop_loss_atr=1.5 / take_profit_atr=1.5 with max_bars_hold=15
(src/layer0/strategies/strategieStaged/range_stochastic.py:67-70).

Walk System 1's own H1 bars forward from each entry and see which barrier is struck
first. Conservative on intrabar ambiguity: if a bar's range spans both the stop and the
target, the STOP is assumed hit first.
"""
from __future__ import annotations

import json
import os

import pandas as pd
from sqlalchemy import text

from src.common.db import get_engine

HERE = os.path.dirname(os.path.abspath(__file__))
COMMS = "/home/emmanuel/Documents/Scalable_Brain/OtherSystems/comms"
SYMBOL_TO_ID = {"EUR_USD": 1, "GBP_USD": 2, "USD_JPY": 3, "AUD_USD": 4, "USD_CAD": 5}

SL_ATR, TP_ATR, MAX_BARS = 1.5, 1.5, 15

trades = json.load(open(os.path.join(COMMS, "s1-section9-trades.json")))
engine = get_engine()
out = []

with engine.connect() as conn:
    for i, t in enumerate(trades, 1):
        aid = SYMBOL_TO_ID[t["pair"]]
        entry_t = pd.to_datetime(t["entry_time"], utc=True)
        entry_p = float(t["entry_price"])
        atr = float(t["sig_atr"])
        short = t["direction"] == "short"
        sign = -1.0 if short else 1.0

        bars = pd.read_sql(
            text(
                'SELECT "timestamp", "Open", high, low, "Close" FROM fact_market_prices '
                "WHERE asset_id=:a AND granularity='H1' AND \"timestamp\" > :ts "
                'ORDER BY "timestamp" ASC LIMIT :lim'
            ),
            conn,
            params={"a": aid, "ts": entry_t.to_pydatetime(), "lim": MAX_BARS},
        )

        rec = {
            "n": i, "pair": t["pair"], "direction": t["direction"],
            "entry_time": t["entry_time"], "entry_price": entry_p, "atr": atr,
            "R_live_actual": round(float(t["R"]), 4),
            "live_exit": t["exit_reason"].split("[")[0],
        }
        if len(bars) < MAX_BARS:
            rec["status"] = f"insufficient_bars ({len(bars)}/{MAX_BARS}) — S1 data ends 2026-07-24"
            out.append(rec)
            continue

        sl = entry_p - sign * SL_ATR * atr
        tp = entry_p + sign * TP_ATR * atr
        result, bar_hit = None, None
        for k, b in bars.iterrows():
            hi, lo = float(b["high"]), float(b["low"])
            hit_sl = (hi >= sl) if short else (lo <= sl)
            hit_tp = (lo <= tp) if short else (hi >= tp)
            if hit_sl:           # conservative: stop wins an ambiguous bar
                result, bar_hit = ("stop", k + 1)
                break
            if hit_tp:
                result, bar_hit = ("target", k + 1)
                break
        if result is None:       # 15-bar time stop
            exit_p = float(bars.iloc[-1]["Close"])
            r = (exit_p - entry_p) * sign / (SL_ATR * atr)
            result, bar_hit = ("time_stop", MAX_BARS)
        else:
            exit_p = sl if result == "stop" else tp
            r = -1.0 if result == "stop" else 1.0

        rec.update({
            "status": "replayed", "qualified_sl": round(sl, 6),
            "qualified_tp": round(tp, 6), "exit_reason": result,
            "bars_held": int(bar_hit), "exit_price": round(exit_p, 6),
            "R_qualified": round(r, 4),
        })
        out.append(rec)

done = [r for r in out if r.get("status") == "replayed"]

print(f"{'#':>2} {'pair':<8} {'dir':<6} {'LIVE (1.0sl/3.0tp)':<26} {'QUALIFIED (1.5sl/1.5tp/15bar)':<34}")
print(f"{'':>2} {'':<8} {'':<6} {'exit':<14}{'R':>10}   {'exit':<12}{'bars':>5}{'R':>10}")
for r in out:
    if r.get("status") != "replayed":
        print(f"{r['n']:>2} {r['pair']:<8} {r['direction']:<6} {r['live_exit']:<14}"
              f"{r['R_live_actual']:>10.2f}   {r['status']}")
        continue
    print(f"{r['n']:>2} {r['pair']:<8} {r['direction']:<6} {r['live_exit']:<14}"
          f"{r['R_live_actual']:>10.2f}   {r['exit_reason']:<12}{r['bars_held']:>5}"
          f"{r['R_qualified']:>10.2f}")

if done:
    wins = sum(1 for r in done if r["R_qualified"] > 0)
    sr = sum(r["R_qualified"] for r in done)
    sl_ = sum(r["R_live_actual"] for r in done)
    print(f"\nreplayed {len(done)} of {len(out)} (S1 H1 data ends 2026-07-24 20:00)")
    print(f"  QUALIFIED policy : {wins}/{len(done)} wins ({wins/len(done):.1%}), "
          f"sum R {sr:+.2f}, mean R {sr/len(done):+.3f}")
    print(f"  LIVE policy      : {sum(1 for r in done if r['R_live_actual']>0)}/{len(done)} wins, "
          f"sum R {sl_:+.2f}, mean R {sl_/len(done):+.3f}")
    print("  (live R is in units of its own 1.0xATR stop; divide by 1.5 to compare "
          "like-for-like with a 1.5xATR-stop R)")
    print(f"  LIVE, restated in 1.5xATR-stop units: mean R {sl_/len(done)/1.5:+.3f}")

json.dump({
    "artifact": "system1-replay-of-live-trades-under-qualified-exits",
    "qualified_policy": {"stop_loss_atr": SL_ATR, "take_profit_atr": TP_ATR,
                         "max_bars_hold": MAX_BARS,
                         "source": "src/layer0/strategies/strategieStaged/range_stochastic.py:67-70"},
    "live_policy": {"sl_atr_mult": 1.0, "tp_atr_mult": 3.0},
    "intrabar_rule": "stop assumed hit first when a bar spans both barriers (conservative)",
    "trades": out,
}, open(os.path.join(HERE, "qualified-exit-replay.json"), "w"), indent=2)
print("\nwrote qualified-exit-replay.json")
