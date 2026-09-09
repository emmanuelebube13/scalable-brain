"""Q4.2 / Q4.3 for the v2 engine, using the engine's OWN resolved exit levels.

Supersedes the v2 rows of q4_ambiguity_count.csv / q4_counterfactual_R.csv, which
reconstructed the take-profit level from a winner-conditional R:R proxy. That proxy
is wrong here: `exit_price` is the fraction-weighted average across all exit fills,
so on a multi-leg trade it sits far closer to entry than any declared target — and
at D1 the median v2 trade declares NO take-profit leg at all (measured:
v2_declared_levels.parquet, n_tp_legs median 0 at D1), so there is no second level
for the exit bar to be ambiguous about.

Levels here come from `_InstrumentedEngine`, which records what
`position_engine._open_position` actually resolved.
"""

from __future__ import annotations

import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from src.common.db import get_engine  # noqa: E402
from src.validation import walk_forward as WF  # noqa: E402

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("ev2.q4v2")
OUT = _REPO / "audit" / "reports" / "engine_validation_2"
_BAR = {"H1": pd.Timedelta("1h"), "H4": pd.Timedelta("4h"), "D1": pd.Timedelta("1D")}


def main() -> None:
    d = pd.read_parquet(OUT / "v2_declared_levels.parquet")
    d["reason"] = d["exit_reason"].str.lower()
    d["is_stop"] = d.reason == "stop"
    d["is_tp"] = d.reason == "take_profit"

    # same walk-forward labelling as persist_all, per granularity
    keep = []
    for gran, sub in d.groupby("granularity"):
        smin, smax = WF.series_bounds(sub["entry_time"])
        is_oos, _ = WF.assign_oos(sub["entry_time"], WF.default_folds(smin, smax))
        s = sub.copy()
        s["is_oos"] = np.asarray(is_oos)
        keep.append(s)
    d = pd.concat(keep, ignore_index=True)
    d = d[d.is_oos].copy()

    e = get_engine()
    with e.connect() as c:
        px = pd.read_sql(
            text("""SELECT da.symbol, p.granularity, p.timestamp AS exit_time,
                           p.high, p.low FROM fact_market_prices p
                    JOIN dim_asset da ON da.asset_id = p.asset_id
                    WHERE p.granularity IN ('H1','H4','D1')"""), c)
    px["exit_time"] = pd.to_datetime(px["exit_time"], utc=True)
    d = d.merge(px, on=["symbol", "granularity", "exit_time"], how="left")

    d["risk"] = (d.entry_price - d.initial_stop_price).abs()
    d["has_tp"] = d.tp1_level.notna()
    d["stop_level"] = d.final_stop_price
    d["stop_in_bar"] = (d.stop_level >= d.low) & (d.stop_level <= d.high)
    d["tp_in_bar"] = d.has_tp & (d.tp1_level >= d.low) & (d.tp1_level <= d.high)
    # An exit is ambiguous only if BOTH levels sat inside the SAME exit bar and that
    # exit actually resolved at one of them.
    d["ambiguous"] = d.stop_in_bar & d.tp_in_bar & (d.is_stop | d.is_tp) & d.high.notna()
    # what the flipped resolution would have paid, in the trade's own R units
    d["r_if_tp"] = d.tp1_fraction.fillna(1.0) * (d.tp1_level - d.entry_price) * d.direction / d.risk
    d["r_if_stop"] = (d.stop_level - d.entry_price) * d.direction / d.risk

    d = _resolve_with_m15(d, e)

    cnt = (d.groupby("granularity")
           .agg(n_oos_trades=("trade_id", "size"),
                n_bar_matched=("high", "count"),
                frac_declaring_a_tp=("has_tp", "mean"),
                n_stop_or_tp_exits=("is_stop", lambda s: int((s | d.loc[s.index, "is_tp"]).sum())),
                n_ambiguous=("ambiguous", "sum")).reset_index())
    cnt["engine"] = "position_engine_v2"
    cnt["pct_ambiguous_of_oos_trades"] = 100 * cnt.n_ambiguous / cnt.n_oos_trades
    cnt.to_csv(OUT / "q4_ambiguity_count_v2_measured.csv", index=False)

    rows = []
    for gran, sub in d.groupby("granularity"):
        a = sub[sub.ambiguous]
        n = len(sub)
        base = sub.r_multiple.mean()
        d_tp = (a.loc[a.is_stop, "r_if_tp"] - a.loc[a.is_stop, "r_multiple"]).sum()
        d_sl = (a.loc[a.is_tp, "r_if_stop"] - a.loc[a.is_tp, "r_multiple"]).sum()
        # M15 truth: flip only the exits the finer bars say were resolved the wrong way
        wrong_stop = a[(a.is_stop) & (a.m15_first_touch == "tp_first")]
        wrong_tp = a[(a.is_tp) & (a.m15_first_touch == "stop_first")]
        d_m15 = ((wrong_stop.r_if_tp - wrong_stop.r_multiple).sum()
                 + (wrong_tp.r_if_stop - wrong_tp.r_multiple).sum())
        rows.append({
            "engine": "position_engine_v2", "granularity": gran, "n_trades": n,
            "n_ambiguous": len(a),
            "mean_R_stop_first_as_is": base,
            "mean_R_tp_first": base + d_tp / n,
            "mean_R_coin_flip": base + 0.5 * (d_tp + d_sl) / n,
            "mean_R_m15_resolved": base + d_m15 / n,
            "bias_vs_coin_flip_R": 0.5 * (d_tp + d_sl) / n,
            "bias_vs_m15_truth_R": d_m15 / n,
            "n_m15_says_wrong": len(wrong_stop) + len(wrong_tp),
        })
    cf = pd.DataFrame(rows)
    cf.to_csv(OUT / "q4_counterfactual_R_v2_measured.csv", index=False)

    res = (d[d.ambiguous].groupby("granularity")["m15_first_touch"]
           .value_counts().unstack(fill_value=0).reset_index())
    res.to_csv(OUT / "q4_m15_resolution_v2_measured.csv", index=False)

    log.info("\n=== v2 ambiguity, measured levels ===\n%s", cnt.round(4).to_string(index=False))
    log.info("\n=== v2 counterfactual ===\n%s", cf.round(5).to_string(index=False))
    log.info("\n=== M15 first touch on ambiguous exits ===\n%s", res.to_string(index=False))


def _resolve_with_m15(d: pd.DataFrame, e) -> pd.DataFrame:
    d = d.copy()
    d["m15_first_touch"] = "not_ambiguous"
    amb = d[d.ambiguous]
    log.info("resolving %d ambiguous exits against M15 bars", len(amb))
    for sym, sub in amb.groupby("symbol"):
        with e.connect() as c:
            m = pd.read_sql(
                text("""SELECT p.timestamp, p.high, p.low FROM fact_market_prices p
                        JOIN dim_asset da ON da.asset_id = p.asset_id
                        WHERE da.symbol = :s AND p.granularity = 'M15'
                          AND p.timestamp >= :lo AND p.timestamp <= :hi
                        ORDER BY p.timestamp"""),
                c, params={"s": sym, "lo": sub.exit_time.min(),
                           "hi": sub.exit_time.max() + pd.Timedelta("2D")})
        if not len(m):
            continue
        ts = pd.to_datetime(m["timestamp"], utc=True).values
        mh, ml = m["high"].values, m["low"].values
        for idx, t in sub.iterrows():
            span = _BAR.get(t.granularity)
            a = np.searchsorted(ts, np.datetime64(t.exit_time))
            b = np.searchsorted(ts, np.datetime64(t.exit_time + span))
            if b <= a:
                continue
            sl = (ml[a:b] <= t.stop_level) & (mh[a:b] >= t.stop_level)
            tp = (ml[a:b] <= t.tp1_level) & (mh[a:b] >= t.tp1_level)
            i_sl = int(np.argmax(sl)) if sl.any() else 10**9
            i_tp = int(np.argmax(tp)) if tp.any() else 10**9
            if i_sl == i_tp == 10**9:
                d.at[idx, "m15_first_touch"] = "neither_in_m15"
            elif i_sl < i_tp:
                d.at[idx, "m15_first_touch"] = "stop_first"
            elif i_tp < i_sl:
                d.at[idx, "m15_first_touch"] = "tp_first"
            else:
                d.at[idx, "m15_first_touch"] = "same_m15_bar"
    return d


if __name__ == "__main__":
    main()
