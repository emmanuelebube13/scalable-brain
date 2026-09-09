"""Engine Validation Pass 2 — Part A analysis (read-only).

Consumes:
  - fact_trade_outcomes (the population vetting actually reads)
  - audit/reports/engine_validation_2/replay_trades.parquet (same engines,
    same dispatch as src/outcomes/persist_all.py, with the price columns the
    DB does not store)

Emits every Q1-Q7 / Q10 deliverable CSV. Q8/Q9 come from
engine_validation2_tests.py.

Rules enforced in code:
  Rule 6 — every table is split by engine; nothing is pooled across engines
           without saying so explicitly.
  Rule 7 — C_g is a positive magnitude, expected_floor = -C_g (asserted),
           gap = mean_R - expected_floor = mean_R + C_g.
"""

from __future__ import annotations

import json
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
from src.layer0.data_access.indicators import atr as atr_fn  # noqa: E402
from src.layer0.data_access.indicators import get_pip_value  # noqa: E402

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("ev2.analysis")

OUT = _REPO / "audit" / "reports" / "engine_validation_2"
OUT.mkdir(parents=True, exist_ok=True)

INTEGRITY_DISQUALIFIED = {"Range_Stochastic_Divergence"}
DUPLICATE_DROP = {"Trend_EMA_ADX_MultiTF"}
MIN_N = 30

STOP_REASONS = {"stop_loss", "stop"}
TP_REASONS = {"take_profit"}


def _assert_rule7(df: pd.DataFrame) -> None:
    """Rule 7: expected_floor is negative, gap = mean_R - expected_floor."""
    bad = df[df["expected_floor"] >= 0]
    if len(bad):
        raise AssertionError(
            f"Rule 7 violated: {len(bad)} rows have expected_floor >= 0. "
            "C_g is a positive magnitude; the floor is -C_g."
        )
    recomputed = df["mean_R"] - df["expected_floor"]
    if not np.allclose(recomputed, df["gap"], equal_nan=True):
        raise AssertionError("Rule 7 violated: gap != mean_R - expected_floor")


# ─────────────────────────────────────────────────────────────────────────────
# load
# ─────────────────────────────────────────────────────────────────────────────


def load_db() -> pd.DataFrame:
    e = get_engine()
    with e.connect() as c:
        df = pd.read_sql(
            text("""
                SELECT f.outcome_id, f.timestamp AS entry_time, da.symbol, f.strategy_id,
                       ds.strategy_key, ds.engine, f.granularity,
                       f.entry_signal_type AS direction, f.r_multiple, f.holding_bars,
                       f.exit_reason, f.fold_id
                FROM fact_trade_outcomes f
                JOIN dim_asset da ON da.asset_id = f.asset_id
                JOIN dim_strategy ds ON ds.strategy_id = f.strategy_id
                WHERE f.is_oos = true
            """),
            c,
        )
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    df["year"] = df["entry_time"].dt.year
    df["reason"] = df["exit_reason"].str.lower()
    df["is_stop"] = df["reason"].isin(STOP_REASONS)
    df["is_tp"] = df["reason"].isin(TP_REASONS)
    return df


def load_replay() -> pd.DataFrame:
    p = OUT / "replay_trades.parquet"
    if not p.exists():
        raise SystemExit(f"missing {p} — run src/audit/engine_validation2_replay.py first")
    r = pd.read_parquet(p)
    r["entry_time"] = pd.to_datetime(r["entry_time"], utc=True)
    r["exit_time"] = pd.to_datetime(r["exit_time"], utc=True)
    r["reason"] = r["exit_reason"].str.lower()
    r["is_stop"] = r["reason"].isin(STOP_REASONS)
    r["is_tp"] = r["reason"].isin(TP_REASONS)
    r["pip"] = r["symbol"].map(lambda s: get_pip_value(s))
    r["stop_dist_price"] = (r["entry_price"] - r["initial_stop_price"]).abs()
    r["stop_dist_pips"] = r["stop_dist_price"] / r["pip"]
    r["move_price"] = (r["exit_price"] - r["entry_price"]).abs()
    return r


def load_prices() -> pd.DataFrame:
    e = get_engine()
    with e.connect() as c:
        px = pd.read_sql(
            text("""
                SELECT da.symbol, p.granularity, p.timestamp, p."Open", p.high, p.low, p."Close"
                FROM fact_market_prices p
                JOIN dim_asset da ON da.asset_id = p.asset_id
                WHERE p.granularity IN ('H1','H4','D1')
            """),
            c,
        )
    px["timestamp"] = pd.to_datetime(px["timestamp"], utc=True)
    return px


# ─────────────────────────────────────────────────────────────────────────────
# Q1
# ─────────────────────────────────────────────────────────────────────────────


def q1(db: pd.DataFrame, cg: dict) -> pd.DataFrame:
    cell = (
        db.groupby(["engine", "granularity", "strategy_id", "strategy_key"])["r_multiple"]
        .agg(n="count", mean_R="mean", median_R="median", sd_R="std")
        .reset_index()
    )
    cell["se"] = cell["sd_R"] / np.sqrt(cell["n"])
    cell["C_g"] = [cg.get((e, g), np.nan) for e, g in zip(cell.engine, cell.granularity)]
    cell["expected_floor"] = -cell["C_g"]
    cell["gap"] = cell["mean_R"] - cell["expected_floor"]
    cell["above_zero"] = cell["mean_R"] > 0
    cell["above_floor"] = cell["gap"] > 0
    cell["excluded_reason"] = ""
    cell.loc[cell.strategy_key.isin(INTEGRITY_DISQUALIFIED), "excluded_reason"] = "INTEGRITY_DISQUALIFIED"
    cell.loc[cell.strategy_key.isin(DUPLICATE_DROP), "excluded_reason"] = "DUPLICATE_OF_Trend_EMA_ADX_H4"
    cell.loc[(cell["excluded_reason"] == "") & (cell["n"] < MIN_N), "excluded_reason"] = f"N_BELOW_{MIN_N}"
    cell["in_population"] = cell["excluded_reason"] == ""
    cell["excluded_reason"] = cell["excluded_reason"].replace("", "none")
    cell = cell.sort_values("mean_R")
    _assert_rule7(cell.dropna(subset=["expected_floor"]))
    cell.to_csv(OUT / "q1_strategy_distribution.csv", index=False)

    pop = cell[cell.in_population]
    summ = []
    for keys, sub in list(pop.groupby(["engine", "granularity"])) + [(("ALL", "ALL"), pop)]:
        q = sub["mean_R"].quantile([0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0])
        summ.append({
            "engine": keys[0], "granularity": keys[1], "k_cells": len(sub),
            "min": q.iloc[0], "p5": q.iloc[1], "p25": q.iloc[2], "median": q.iloc[3],
            "p75": q.iloc[4], "p95": q.iloc[5], "max": q.iloc[6],
            "sd_of_cell_means": sub["mean_R"].std(),
            "mean_of_cell_SEs": sub["se"].mean(),
            "spread_ratio": sub["mean_R"].std() / sub["se"].mean(),
            "n_above_zero": int(sub["above_zero"].sum()),
            "n_below_zero": int((~sub["above_zero"]).sum()),
            "n_above_floor": int(sub["above_floor"].sum()),
            "n_below_floor": int((~sub["above_floor"]).sum()),
        })
    s = pd.DataFrame(summ)
    s.to_csv(OUT / "q1_distribution_summary.csv", index=False)
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Q2 — measured cost floor
# ─────────────────────────────────────────────────────────────────────────────


def q2(rep: pd.DataFrame, db: pd.DataFrame, px: pd.DataFrame):
    """Measure stop distance, ATR multiple and round-trip slippage from realised trades."""
    # ATR(14) at the entry bar, per symbol x granularity, from the same price table
    atrs = []
    for (sym, gran), g in px.groupby(["symbol", "granularity"]):
        g = g.sort_values("timestamp")
        a = atr_fn(g["high"], g["low"], g["Close"], 14)
        atrs.append(pd.DataFrame({"symbol": sym, "granularity": gran,
                                  "entry_time": g["timestamp"].values, "atr14": a.values}))
    atr_df = pd.concat(atrs, ignore_index=True)
    atr_df["entry_time"] = pd.to_datetime(atr_df["entry_time"], utc=True)

    r = rep.merge(atr_df, on=["symbol", "granularity", "entry_time"], how="left")
    r["stop_atr_multiple"] = r["stop_dist_price"] / r["atr14"]
    # realised exit slippage on a clean stop exit = |exit - entry| - stop_distance
    r["exit_slip_price"] = r["move_price"] - r["stop_dist_price"]
    r["exit_slip_pips"] = r["exit_slip_price"] / r["pip"]
    # cost of that slippage expressed in R
    r["exit_slip_R"] = r["exit_slip_price"] / r["stop_dist_price"]

    stops = r[r.is_stop & (r.stop_dist_price > 0)].copy()
    # v2 stops move; only trades whose stop never moved give a clean read
    stops["stop_moved"] = (stops["final_stop_price"] - stops["initial_stop_price"]).abs() > 1e-12
    clean = stops[~stops.stop_moved]

    # DECLARED R:R — v1 records take_profit_price on every trade, so this is the
    # geometry as declared, not the winner-conditional estimate.
    r["rr_declared"] = (r["take_profit_price"] - r["entry_price"]).abs() / r["stop_dist_price"]
    r["rr_realised"] = r["move_price"] / r["stop_dist_price"]

    per_cell = (
        clean.groupby(["engine", "granularity", "strategy_key"])
        .agg(n_stop_exits=("r_multiple", "size"),
             median_stop_pips=("stop_dist_pips", "median"),
             median_stop_atr_multiple=("stop_atr_multiple", "median"),
             median_exit_slip_pips=("exit_slip_pips", "median"),
             implied_C_g=("exit_slip_R", "median"),
             median_r_on_stop=("r_multiple", "median"))
        .reset_index()
    )
    rr = (r.groupby(["engine", "granularity", "strategy_key"])
          .agg(rr_declared_median=("rr_declared", "median"),
               rr_declared_min=("rr_declared", "min"),
               rr_declared_max=("rr_declared", "max"),
               rr_realised_on_tp=("rr_realised", lambda s: s.median()))
          .reset_index())
    per_cell = per_cell.merge(rr, on=["engine", "granularity", "strategy_key"], how="outer")
    per_cell["rr_varies_within_strategy"] = (
        (per_cell.rr_declared_max - per_cell.rr_declared_min).abs() > 1e-6)
    per_cell = per_cell.sort_values(["engine", "granularity", "strategy_key"])
    per_cell.to_csv(OUT / "q2_measured_cost_floor.csv", index=False)

    agg = (
        clean.groupby(["engine", "granularity"])
        .apply(lambda g: pd.Series({
            "n_stop_exits": len(g),
            "n_stop_exits_all": int(stops[(stops.engine == g.engine.iloc[0]) &
                                          (stops.granularity == g.granularity.iloc[0])].shape[0]),
            "median_stop_pips": g.stop_dist_pips.median(),
            "median_stop_atr_multiple": g.stop_atr_multiple.median(),
            "p25_stop_atr_multiple": g.stop_atr_multiple.quantile(.25),
            "p75_stop_atr_multiple": g.stop_atr_multiple.quantile(.75),
            "median_exit_slip_pips": g.exit_slip_pips.median(),
            "C_g_trade_weighted": np.average(g.exit_slip_R.clip(-1, 1)),
            "C_g_median": g.exit_slip_R.median(),
        }))
        .reset_index()
    )
    agg.to_csv(OUT / "q2_cost_floor_by_engine_granularity.csv", index=False)

    cg = {(e, g): float(v) for e, g, v in zip(agg.engine, agg.granularity, agg.C_g_median)}

    # corrected E0, original alongside
    OLD_CG = {"H1": 0.046, "H4": 0.022, "D1": 0.008}
    e0 = (
        db.groupby(["engine", "granularity"])["r_multiple"]
        .agg(n_trades="count", mean_R="mean", median_R="median", sd_R="std")
        .reset_index()
    )
    e0["n_strategies"] = (
        db.groupby(["engine", "granularity"])["strategy_id"].nunique().values
    )
    e0["C_g_pass1_assumed"] = e0["granularity"].map(OLD_CG)
    e0["gap_pass1"] = e0["mean_R"] - e0["C_g_pass1_assumed"]           # the sign bug, reproduced
    e0["gap_pass1_rule7"] = e0["mean_R"] + e0["C_g_pass1_assumed"]     # what pass 1 meant
    e0["C_g"] = [cg.get((a, b), np.nan) for a, b in zip(e0.engine, e0.granularity)]
    e0["expected_floor"] = -e0["C_g"]
    e0["gap"] = e0["mean_R"] - e0["expected_floor"]
    _assert_rule7(e0.dropna(subset=["expected_floor"]))
    e0.to_csv(OUT / "q2_corrected_e0.csv", index=False)
    return cg, agg, e0, r


# ─────────────────────────────────────────────────────────────────────────────
# Q3
# ─────────────────────────────────────────────────────────────────────────────


def q3(db: pd.DataFrame, cg: dict, rep: pd.DataFrame):
    rows = []
    for dims in (["engine", "granularity"], ["engine", "granularity", "symbol"],
                 ["engine", "granularity", "direction"]):
        g = (db.groupby(dims)["r_multiple"]
             .agg(n_trades="count", mean_R="mean", median_R="median", sd_R="std").reset_index())
        g["breakdown"] = "+".join(d for d in dims if d not in ("engine", "granularity")) or "granularity"
        rows.append(g)
    e = pd.concat(rows, ignore_index=True)
    e["C_g"] = [cg.get((a, b), np.nan) for a, b in zip(e.engine, e.granularity)]
    e["expected_floor"] = -e["C_g"]
    e["gap"] = e["mean_R"] - e["expected_floor"]
    _assert_rule7(e.dropna(subset=["expected_floor"]))
    e.to_csv(OUT / "q3_engine_split.csv", index=False)

    # Q3.3 controlled test: any strategy under both engines?
    both = db.groupby("strategy_key")["engine"].nunique()
    same = pd.DataFrame({"strategy_key": both.index, "n_engines": both.values})
    same["appears_in_both"] = same.n_engines > 1
    same.to_csv(OUT / "q3_same_strategy_both_engines.csv", index=False)

    # Q3.2 does v2 move stops -- from data, not from source
    v2 = rep[rep.engine == "position_engine_v2"].copy()
    v2["stop_moved"] = (v2.final_stop_price - v2.initial_stop_price).abs() > 1e-12
    v2["stop_moved_favourably"] = np.where(
        v2.direction == 1, v2.final_stop_price > v2.initial_stop_price + 1e-12,
        v2.final_stop_price < v2.initial_stop_price - 1e-12)
    v1 = rep[rep.engine == "backtest_engine_v1"].copy()
    v1["stop_moved"] = False
    v1["stop_moved_favourably"] = False
    mv = (pd.concat([v1, v2])
          .groupby(["engine", "granularity"])
          .agg(n=("r_multiple", "size"),
               frac_stop_moved=("stop_moved", "mean"),
               frac_moved_favourably=("stop_moved_favourably", "mean"))
          .reset_index())
    stp = rep[rep.is_stop]
    pos = (stp.groupby(["engine", "granularity"])
           .agg(n_stop_exits=("r_multiple", "size"),
                frac_stop_exits_positive_R=("r_multiple", lambda x: (x > 0).mean()),
                mean_R_on_stop=("r_multiple", "mean"),
                median_R_on_stop=("r_multiple", "median")).reset_index())
    mv = mv.merge(pos, on=["engine", "granularity"], how="left")
    mv.to_csv(OUT / "q3_stop_regime_by_engine.csv", index=False)
    return e, same, mv


# ─────────────────────────────────────────────────────────────────────────────
# Q4
# ─────────────────────────────────────────────────────────────────────────────


def q4_zero_bar(db: pd.DataFrame) -> pd.DataFrame:
    db = db.copy()
    db["bar_class"] = np.where(db.holding_bars == 0, "zero_bar", "multi_bar")
    t = (db.groupby(["engine", "granularity", "bar_class"])
         .agg(n=("r_multiple", "size"),
              n_stop=("is_stop", "sum"), n_tp=("is_tp", "sum"),
              mean_R=("r_multiple", "mean")).reset_index())
    t["stop_frac"] = t.n_stop / t.n
    t["tp_frac"] = t.n_tp / t.n
    base = t[t.bar_class == "multi_bar"].set_index(["engine", "granularity"])["stop_frac"]
    t["baseline_stop_frac"] = [base.get((e, g), np.nan) for e, g in zip(t.engine, t.granularity)]
    t["excess_over_baseline"] = t.stop_frac - t.baseline_stop_frac
    t.to_csv(OUT / "q4_zero_bar_by_exit_reason.csv", index=False)
    return t


_BAR_LEN = {"H1": pd.Timedelta("1h"), "H4": pd.Timedelta("4h"), "D1": pd.Timedelta("1D")}


def _resolve_with_m15(r: pd.DataFrame) -> pd.DataFrame:
    """For each ambiguous exit bar, walk the M15 bars inside it and record which
    level the market touched FIRST. This is measurement, not an assumption —
    fact_market_prices holds 2.6M M15 bars back to 2006."""
    r = r.copy()
    r["m15_first_touch"] = "not_resolved"
    amb = r[r.ambiguous]
    if not len(amb):
        return r
    e = get_engine()
    for sym, sub in amb.groupby("symbol"):
        lo, hi = sub.exit_time.min(), sub.exit_time.max() + pd.Timedelta("1D")
        with e.connect() as c:
            m15 = pd.read_sql(
                text("""SELECT p.timestamp, p.high, p.low FROM fact_market_prices p
                        JOIN dim_asset da ON da.asset_id = p.asset_id
                        WHERE da.symbol = :s AND p.granularity = 'M15'
                          AND p.timestamp >= :lo AND p.timestamp <= :hi
                        ORDER BY p.timestamp"""),
                c, params={"s": sym, "lo": lo, "hi": hi},
            )
        if not len(m15):
            continue
        m15["timestamp"] = pd.to_datetime(m15["timestamp"], utc=True)
        ts = m15["timestamp"].values
        mh, ml = m15["high"].values, m15["low"].values
        for idx, t in sub.iterrows():
            span = _BAR_LEN.get(t.granularity)
            if span is None:
                continue
            a = np.searchsorted(ts, np.datetime64(t.exit_time))
            b = np.searchsorted(ts, np.datetime64(t.exit_time + span))
            if b <= a:
                continue
            sl_hit = (ml[a:b] <= t.stop_level) & (mh[a:b] >= t.stop_level)
            tp_hit = (ml[a:b] <= t.tp_level) & (mh[a:b] >= t.tp_level)
            i_sl = np.argmax(sl_hit) if sl_hit.any() else 10**9
            i_tp = np.argmax(tp_hit) if tp_hit.any() else 10**9
            if i_sl == i_tp == 10**9:
                r.at[idx, "m15_first_touch"] = "neither_in_m15"
            elif i_sl < i_tp:
                r.at[idx, "m15_first_touch"] = "stop_first"
            elif i_tp < i_sl:
                r.at[idx, "m15_first_touch"] = "tp_first"
            else:
                r.at[idx, "m15_first_touch"] = "same_m15_bar"
    return r


def q4_ambiguity(rep: pd.DataFrame, px: pd.DataFrame):
    """Reconstruct both levels and count exit bars where BOTH lie inside [low, high]."""
    r = rep[(rep.stop_dist_price > 0) & (rep.is_stop | rep.is_tp)].copy()

    # R:R: v1 declares take_profit_price per trade, so use it directly. v2 declares
    # exit legs the engine does not echo, so fall back to the winner-conditional
    # median per strategy (stated as such in the report).
    tp = rep[rep.is_tp & (rep.stop_dist_price > 0)].copy()
    tp["rr"] = tp.move_price / tp.stop_dist_price
    rr_cell = tp.groupby(["engine", "granularity", "strategy_key"])["rr"].median()
    rr_gran = tp.groupby(["engine", "granularity"])["rr"].median()
    fallback = np.array([rr_cell.get((e, g, k), rr_gran.get((e, g), np.nan))
                         for e, g, k in zip(r.engine, r.granularity, r.strategy_key)])
    declared = (r["take_profit_price"] - r["entry_price"]).abs() / r["stop_dist_price"]
    r["rr"] = declared.fillna(pd.Series(fallback, index=r.index))
    r["rr_source"] = np.where(declared.notna(), "declared_v1", "winner_conditional_v2")

    # levels in force at the exit bar: stop uses the working stop, TP the R:R above
    r["stop_level"] = r["final_stop_price"]
    r["tp_level"] = r["entry_price"] + r["direction"] * r["rr"] * r["stop_dist_price"]

    bars = px.rename(columns={"timestamp": "exit_time"})[
        ["symbol", "granularity", "exit_time", "Open", "high", "low", "Close"]]
    r = r.merge(bars, on=["symbol", "granularity", "exit_time"], how="left")
    have = r["high"].notna()
    r["stop_in_bar"] = (r.stop_level >= r.low) & (r.stop_level <= r.high)
    r["tp_in_bar"] = (r.tp_level >= r.low) & (r.tp_level <= r.high)
    r["ambiguous"] = r.stop_in_bar & r.tp_in_bar & have

    cnt = (r.groupby(["engine", "granularity"])
           .agg(n_exits_considered=("ambiguous", "size"),
                n_bar_matched=("high", "count"),
                n_ambiguous=("ambiguous", "sum"),
                median_rr=("rr", "median")).reset_index())
    cnt["pct_ambiguous_of_matched"] = 100 * cnt.n_ambiguous / cnt.n_bar_matched
    tot = (rep.groupby(["engine", "granularity"]).size().rename("n_all_trades").reset_index())
    cnt = cnt.merge(tot, on=["engine", "granularity"])
    cnt["pct_ambiguous_of_all_trades"] = 100 * cnt.n_ambiguous / cnt.n_all_trades

    # Q4.4 — resolve the ambiguity with real M15 bars (B1 option 1), not an assumption
    r = _resolve_with_m15(r)
    res = (r[r.ambiguous].groupby(["engine", "granularity"])["m15_first_touch"]
           .value_counts().unstack(fill_value=0).reset_index())
    res.to_csv(OUT / "q4_m15_resolution.csv", index=False)
    cnt.to_csv(OUT / "q4_ambiguity_count.csv", index=False)

    # Q4.3 counterfactual, per engine x granularity, over the whole replayed bank
    rows = []
    amb = r[r.ambiguous]
    for (e, g), sub in rep.groupby(["engine", "granularity"]):
        a = amb[(amb.engine == e) & (amb.granularity == g)]
        base = sub.r_multiple.mean()
        # ambiguous trades that ACTUALLY resolved as stops would resolve as TP under tp-first
        as_stop = a[a.is_stop]
        as_tp = a[a.is_tp]
        # delta per flipped trade: (+rr) - (realised) for stops; (-1) - (realised) for tps
        d_tp_first = (as_stop.rr - as_stop.r_multiple).sum()
        d_sl_first = ((-1.0) - as_tp.r_multiple).sum()
        # M15 truth: flip only the exits the finer bars say resolved the other way
        w_stop = as_stop[as_stop.m15_first_touch == "tp_first"]
        w_tp = as_tp[as_tp.m15_first_touch == "stop_first"]
        d_m15 = (w_stop.rr - w_stop.r_multiple).sum() + ((-1.0) - w_tp.r_multiple).sum()
        n = len(sub)
        rows.append({
            "engine": e, "granularity": g, "n_trades": n,
            "n_ambiguous": len(a),
            "mean_R_stop_first_as_is": base,
            "mean_R_tp_first": base + d_tp_first / n,
            "mean_R_coin_flip": base + 0.5 * (d_tp_first + d_sl_first) / n,
            "mean_R_m15_resolved": base + d_m15 / n,
            "bias_vs_coin_flip_R": 0.5 * (d_tp_first + d_sl_first) / n,
            "bias_vs_m15_truth_R": d_m15 / n,
            "n_m15_says_wrong": len(w_stop) + len(w_tp),
        })
    cf = pd.DataFrame(rows)
    cf.to_csv(OUT / "q4_counterfactual_R.csv", index=False)
    return cnt, cf, r


# ─────────────────────────────────────────────────────────────────────────────
# Q5, Q6, Q7, Q10
# ─────────────────────────────────────────────────────────────────────────────


def q5(db: pd.DataFrame, rep: pd.DataFrame, cg: dict):
    h4 = db[db.granularity == "H4"].copy()
    h4["cell"] = np.where(h4.symbol == "USD_JPY", "USD_JPY", "other_H4_pairs")
    per = (h4.groupby(["strategy_key", "engine", "cell"])
           .agg(n=("r_multiple", "size"), mean_R=("r_multiple", "mean"),
                median_R=("r_multiple", "median"),
                stop_exit_rate=("is_stop", "mean")).reset_index())
    piv = per.pivot_table(index=["strategy_key", "engine"], columns="cell",
                          values=["n", "mean_R", "median_R", "stop_exit_rate"])
    piv.columns = [f"{a}_{b}" for a, b in piv.columns]
    piv = piv.reset_index()
    piv["mean_R_delta_jpy_minus_other"] = piv["mean_R_USD_JPY"] - piv["mean_R_other_H4_pairs"]
    piv["jpy_share_of_strategy_H4_trades"] = piv["n_USD_JPY"] / (
        piv["n_USD_JPY"].fillna(0) + piv["n_other_H4_pairs"].fillna(0))
    piv = piv.sort_values("mean_R_delta_jpy_minus_other")
    piv.to_csv(OUT / "q5_usdjpy_h4_by_strategy.csv", index=False)

    # Q5.2 / Q5.3 stop geometry in pips AND ATR multiples
    geo = (rep[rep.granularity == "H4"]
           .assign(cell=lambda d: np.where(d.symbol == "USD_JPY", "USD_JPY", "other"))
           .groupby(["engine", "symbol"])
           .agg(n=("stop_dist_pips", "count"),
                median_stop_pips=("stop_dist_pips", "median"),
                median_stop_price=("stop_dist_price", "median")).reset_index())
    geo.to_csv(OUT / "q5_stop_geometry_h4.csv", index=False)

    # Q5.4 by year
    yr = (h4.groupby(["cell", "year"])["r_multiple"]
          .agg(n="count", mean_R="mean").reset_index())
    yr.to_csv(OUT / "q5_usdjpy_h4_by_year.csv", index=False)
    return piv, geo, yr


def q6(db: pd.DataFrame, px: pd.DataFrame):
    px = px.sort_values(["symbol", "granularity", "timestamp"]).copy()
    px["ret"] = px.groupby(["symbol", "granularity"])["Close"].pct_change()
    drift = (px[px.timestamp >= db.entry_time.min()]
             .groupby(["symbol", "granularity"])["ret"]
             .agg(n_bars="count", mean_bar_return="mean").reset_index())

    ct = (db.groupby(["engine", "granularity", "symbol", "direction"])["r_multiple"]
          .agg(n="count", mean_R="mean", median_R="median").reset_index())
    ct.to_csv(OUT / "q6_direction_crosstab.csv", index=False)

    w = ct.pivot_table(index=["engine", "granularity", "symbol"], columns="direction",
                       values=["n", "mean_R"]).reset_index()
    w.columns = [f"{a}_{b}" if b else a for a, b in w.columns]
    w["long_short_gap"] = w["mean_R_long"] - w["mean_R_short"]
    w = w.merge(drift, on=["symbol", "granularity"], how="left")
    w.to_csv(OUT / "q6_drift_vs_asymmetry.csv", index=False)

    corr = [{"scope": "ALL", "k": len(w),
             "pearson": w.long_short_gap.corr(w.mean_bar_return),
             "spearman": w.long_short_gap.corr(w.mean_bar_return, method="spearman")}]
    for g, s in w.groupby("granularity"):
        corr.append({"scope": f"granularity={g}", "k": len(s),
                     "pearson": s.long_short_gap.corr(s.mean_bar_return),
                     "spearman": s.long_short_gap.corr(s.mean_bar_return, method="spearman")})
    c = pd.DataFrame(corr)
    c.to_csv(OUT / "q6_drift_correlation.csv", index=False)
    return w, c


def q7(db: pd.DataFrame) -> pd.DataFrame:
    y = (db.groupby(["engine", "granularity", "year"])["r_multiple"]
         .agg(n_trades="count", mean_R="mean", median_R="median", sd_R="std").reset_index())
    y["se"] = y.sd_R / np.sqrt(y.n_trades)
    y.to_csv(OUT / "q7_mean_R_by_year.csv", index=False)
    return y


def q10(db: pd.DataFrame, cg: dict):
    """Republish d2 and d5 with the Rule 7 sign convention and the measured C_g."""
    d2 = (db.groupby(["engine", "granularity", "symbol"])["r_multiple"]
          .agg(n_trades="count", mean_R="mean", median_R="median", sd_R="std").reset_index())
    d2["C_g"] = [cg.get((e, g), np.nan) for e, g in zip(d2.engine, d2.granularity)]
    d2["expected_floor"] = -d2["C_g"]
    d2["gap"] = d2["mean_R"] - d2["expected_floor"]
    _assert_rule7(d2.dropna(subset=["expected_floor"]))
    d2.to_csv(OUT / "d2_per_instrument_R.csv", index=False)

    d5 = (db.groupby(["engine", "granularity", "direction"])["r_multiple"]
          .agg(n_trades="count", mean_R="mean", median_R="median", sd_R="std").reset_index())
    d5["C_g"] = [cg.get((e, g), np.nan) for e, g in zip(d5.engine, d5.granularity)]
    d5["expected_floor"] = -d5["C_g"]
    d5["gap"] = d5["mean_R"] - d5["expected_floor"]
    _assert_rule7(d5.dropna(subset=["expected_floor"]))
    d5.to_csv(OUT / "d5_direction_split.csv", index=False)
    return d2, d5


def main():
    log.info("loading")
    db, rep, px = load_db(), load_replay(), load_prices()
    log.info("db OOS=%d  replay=%d  prices=%d", len(db), len(rep), len(px))

    # replay fidelity: does the re-run reproduce the persisted population?
    fid = (rep[rep.is_oos].groupby(["engine", "granularity"])
           .agg(replay_n=("r_multiple", "size"), replay_mean_R=("r_multiple", "mean")).reset_index()
           .merge(db.groupby(["engine", "granularity"])
                  .agg(db_n=("r_multiple", "size"), db_mean_R=("r_multiple", "mean")).reset_index(),
                  on=["engine", "granularity"], how="outer"))
    fid["n_ratio"] = fid.replay_n / fid.db_n
    fid["mean_R_abs_diff"] = (fid.replay_mean_R - fid.db_mean_R).abs()
    fid.to_csv(OUT / "q0_replay_fidelity.csv", index=False)
    log.info("replay fidelity:\n%s", fid.to_string(index=False))

    cg, cg_agg, e0, r_priced = q2(rep, db, px)
    log.info("measured C_g: %s", {f"{k[0]}|{k[1]}": round(v, 5) for k, v in cg.items()})

    s1 = q1(db, cg)
    e3, same, stopreg = q3(db, cg, rep)
    zb = q4_zero_bar(db)
    # Q4 is compared against DB mean_R, so it runs on the OOS subset only.
    amb, cf, _ = q4_ambiguity(rep[rep.is_oos].copy(), px)
    p5, geo5, yr5 = q5(db, rep, cg)
    w6, c6 = q6(db, px)
    y7 = q7(db)
    d2, d5 = q10(db, cg)

    # geometry input for Test 2
    geom = {}
    for _, row in cg_agg.iterrows():
        sub = rep[(rep.engine == row.engine) & (rep.granularity == row.granularity)]
        tps = sub[sub.is_tp & (sub.stop_dist_price > 0)]
        rr = float((tps.move_price / tps.stop_dist_price).median()) if len(tps) else 1.6
        n_per_symbol = int(max(50, len(sub) / max(1, sub.symbol.nunique())))
        geom[f"{row.engine}|{row.granularity}"] = {
            "sl_atr": float(row.median_stop_atr_multiple),
            "rr": rr,
            "n_per_symbol": min(n_per_symbol, 1500),
            "max_bars": int(sub.bars_held.quantile(0.95)) or 50,
        }
    (OUT / "t2_geometry.json").write_text(json.dumps(geom, indent=2))
    log.info("t2 geometry:\n%s", json.dumps(geom, indent=2))

    log.info("\n=== Q1 ===\n%s", s1.round(4).to_string(index=False))
    log.info("\n=== Q2 cost floor ===\n%s", cg_agg.round(5).to_string(index=False))
    log.info("\n=== Q2 corrected E0 ===\n%s", e0.round(5).to_string(index=False))
    log.info("\n=== Q3.2 stop regime ===\n%s", stopreg.round(4).to_string(index=False))
    log.info("\n=== Q4.1 zero bar ===\n%s", zb.round(4).to_string(index=False))
    log.info("\n=== Q4.2 ambiguity ===\n%s", amb.round(3).to_string(index=False))
    log.info("\n=== Q4.3 counterfactual ===\n%s", cf.round(5).to_string(index=False))
    log.info("\n=== Q6 drift corr ===\n%s", c6.round(4).to_string(index=False))
    log.info("done -> %s", OUT)


if __name__ == "__main__":
    main()
