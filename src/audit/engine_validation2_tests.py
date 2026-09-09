"""Engine Validation Pass 2 — Test 1 (inversion) and Test 2 (random-entry floor).

Both tests run PER ENGINE (Rule 6) on a deduplicated, integrity-screened
population (Rule 5), and every validity claim ships a computed statistic (Rule 3).

Test 1 — inversion
  v1: two variants.
      `naive`  — flip every bar's signal (what pass 1 did). Path-dependent: the
                 flat/in-position mask changes, so trade counts diverge.
      `pinned` — zero everywhere except at the ORIGINAL run's realised entry
                 bars, where the sign is flipped. Designed to satisfy the
                 |n_inv - n_orig| / n_orig <= 0.05 precondition.
  v2: mirror each OrderIntent about its decision-bar close — direction flips,
      entry kind flips (buy_stop<->sell_stop, buy_limit<->sell_limit), and every
      absolute price (entry_price, stop.price, take_profit legs declared by
      `price`) is reflected p' = 2*close - p. atr_multiple/pips legs invert for
      free. This preserves trade geometry exactly, which the v1 signal flip
      cannot.

Test 2 — random-entry floor
  A zero-information entry, run through the real engine on the real bars, with
  stop/TP geometry drawn from the MEASURED distribution of the real bank (see
  q2_measured_cost_floor.csv). 200 replications, per engine, per granularity,
  including D1 on v2 — the granularity pass 1 blocked.

Read-only: no production table, artifact or config is written.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import sys
import types
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from src.common.db import get_psycopg2_connection  # noqa: E402
from src.layer0.core_engine.backtest_engine import BacktestConfig, BacktestEngine  # noqa: E402
from src.layer0.data_access.indicators import atr as atr_fn  # noqa: E402
from src.layer0.data_access.indicators import get_pip_value  # noqa: E402
from src.layer0.qualify_strategies import preload_historical_data  # noqa: E402
from src.layer0.strategies.contract_v2 import ExitLeg, OrderIntent, StopRule  # noqa: E402
from src.layer0.strategies.position_engine import PositionEngine  # noqa: E402
from src.registry.catalog import all_strategies, instantiate  # noqa: E402
from src.validation import walk_forward as WF  # noqa: E402

warnings.filterwarnings("ignore")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%H:%M:%S"
)
log = logging.getLogger("ev2.tests")

OUT = _REPO / "audit" / "reports" / "engine_validation_2"
OUT.mkdir(parents=True, exist_ok=True)

# Rule 5: excluded from every test population.
INTEGRITY_DISQUALIFIED = {"Range_Stochastic_Divergence"}
# Byte-identical OOS trade set to Trend_EMA_ADX_H4 (verified: 669 trades,
# trade-for-trade equal). One strategy registered twice; keep the lower id.
DUPLICATE_DROP = {"Trend_EMA_ADX_MultiTF"}


# ─────────────────────────────────────────────────────────────────────────────
# shared setup
# ─────────────────────────────────────────────────────────────────────────────


def _setup(lookback_years: int = 25):
    conn = get_psycopg2_connection()
    cur = conn.cursor()
    cur.execute("SELECT symbol, asset_id FROM dim_asset WHERE is_active = true ORDER BY asset_id")
    asset_map = {s: a for s, a in cur.fetchall()}
    symbols = list(asset_map)
    strats = [
        r
        for r in all_strategies()
        if r.strategy_key not in INTEGRITY_DISQUALIFIED and r.strategy_key not in DUPLICATE_DROP
    ]
    grans = {"H1", "H4", "D1"}
    for s in strats:
        if s.primary_granularity:
            grans.add(s.primary_granularity)
    data = preload_historical_data(
        asset_symbols=symbols,
        asset_symbol_map=asset_map,
        granularities=list(grans),
        use_db=True,
        conn=conn,
        lookback_years=lookback_years,
    )
    return strats, symbols, data


def _oos_mask(entry_times: pd.Series, granularity: str) -> np.ndarray:
    """Same walk-forward fold logic persist_all uses, applied per granularity."""
    smin, smax = WF.series_bounds(entry_times)
    folds = WF.default_folds(smin, smax)
    is_oos, _ = WF.assign_oos(entry_times, folds)
    return np.asarray(is_oos)


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — v1 inversion
# ─────────────────────────────────────────────────────────────────────────────


def _force_signals(strat, series: pd.Series):
    s = copy.deepcopy(strat)
    pre = series

    def _gen(self_inner, df, asset, granularity):
        return pre.reindex(df.index).fillna(0).astype(int)

    s.generate_signals = types.MethodType(_gen, s)
    return s


def _flip_signals(strat):
    s = copy.deepcopy(strat)
    orig = type(s).generate_signals

    def _gen(self_inner, df, asset, granularity):
        return orig(self_inner, df, asset, granularity).map(lambda x: -x if x != 0 else 0).astype(int)

    s.generate_signals = types.MethodType(_gen, s)
    return s


def _trades_to_rows(res, key, symbol, gran, variant):
    rows = []
    for t in res.trades:
        if t.exit_time is None:
            continue
        rows.append(
            {
                "variant": variant,
                "strategy_key": key,
                "symbol": symbol,
                "granularity": gran,
                "direction": int(t.direction),
                "entry_time": t.entry_time,
                "entry_price": float(t.entry_price),
                "exit_price": float(t.exit_price),
                "stop_loss": float(t.stop_loss),
                "r_multiple": float(t.r_multiple) if t.r_multiple is not None else np.nan,
                "bars_held": int(t.bars_held or 0),
                "exit_reason": str(t.exit_reason),
            }
        )
    return rows


def test1_v1(strats, symbols, data) -> pd.DataFrame:
    eng = BacktestEngine(BacktestConfig())
    rows = []
    for rec in strats:
        if rec.engine != "backtest_engine_v1":
            continue
        try:
            obj = instantiate(rec)
        except Exception as e:  # noqa: BLE001
            log.warning("skip %s: %s", rec.strategy_key, e)
            continue
        gran = rec.primary_granularity or getattr(obj.config, "primary_granularity", "H1")
        for sym in symbols:
            if sym not in data or gran not in data[sym]:
                continue
            df = data[sym][gran]
            warm = obj.get_required_warmup_bars()

            res_o = eng.run_backtest(copy.deepcopy(obj), df, sym, gran, warm)
            rows += _trades_to_rows(res_o, rec.strategy_key, sym, gran, "orig")

            res_n = eng.run_backtest(_flip_signals(obj), df, sym, gran, warm)
            rows += _trades_to_rows(res_n, rec.strategy_key, sym, gran, "inv_naive")

            # pinned: -direction only at the original run's realised entry bars
            pin = pd.Series(0, index=df.index, dtype=int)
            for t in res_o.trades:
                if t.entry_time in pin.index:
                    pin.loc[t.entry_time] = -int(t.direction)
            res_p = eng.run_backtest(_force_signals(obj, pin), df, sym, gran, warm)
            rows += _trades_to_rows(res_p, rec.strategy_key, sym, gran, "inv_pinned")
        log.info("  T1/v1 %s done (%d rows)", rec.strategy_key, len(rows))
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — v2 inversion by geometric mirror
# ─────────────────────────────────────────────────────────────────────────────

_ENTRY_FLIP = {
    "market": "market",
    "buy_stop": "sell_stop",
    "sell_stop": "buy_stop",
    "buy_limit": "sell_limit",
    "sell_limit": "buy_limit",
}


def _mirror_intent(it: OrderIntent, ref: float) -> OrderIntent:
    """Reflect an intent about `ref`. Geometry is preserved exactly."""

    def m(p):
        return None if p is None else 2.0 * ref - float(p)

    legs = []
    for leg in it.exits:
        legs.append(replace(leg, price=m(leg.price)) if leg.price is not None else leg)
    return replace(
        it,
        direction=-it.direction,
        entry=_ENTRY_FLIP[it.entry],
        entry_price=m(it.entry_price),
        stop=replace(it.stop, price=m(it.stop.price)),
        exits=tuple(legs),
        decision_close=ref,
        tag=(it.tag or "") + "|MIRRORED",
    )


def test1_v2(strats, symbols, data) -> pd.DataFrame:
    from src.layer0.strategies.v2_harness import assert_no_lookahead_v2

    eng = PositionEngine()
    rows = []
    mirror_fail = []
    for rec in strats:
        if rec.engine != "position_engine_v2":
            continue
        try:
            obj = instantiate(rec)
        except Exception as e:  # noqa: BLE001
            log.warning("skip %s: %s", rec.strategy_key, e)
            continue
        meta = obj.metadata
        gran = meta.primary_granularity
        for sym in meta.pairs:
            if sym not in data:
                continue
            frames = {gran: data[sym][gran]}
            ok = True
            for cg in meta.context_granularities:
                if cg not in data[sym]:
                    ok = False
                    break
                frames[cg] = data[sym][cg]
            if not ok:
                continue
            try:
                assert_no_lookahead_v2(obj, frames)
                intents = list(obj.generate_orders(frames))
            except Exception as e:  # noqa: BLE001
                log.warning("skip %s/%s: %s", rec.strategy_key, sym, e)
                continue
            if not intents:
                continue
            closes = frames[gran]["Close"]

            mirrored = []
            for it in intents:
                ref = it.decision_close
                if ref is None:
                    if it.decision_bar not in closes.index:
                        continue
                    ref = float(closes.loc[it.decision_bar])
                try:
                    mirrored.append(_mirror_intent(it, float(ref)))
                except Exception as e:  # noqa: BLE001
                    mirror_fail.append(
                        {"strategy_key": rec.strategy_key, "symbol": sym, "err": str(e)[:200]}
                    )

            for variant, ints in (("orig", intents), ("inv_mirror", mirrored)):
                if not ints:
                    continue
                res = eng.run(
                    frames[gran], ints, pair=sym, warmup_bars=obj.warmup_bars,
                    strategy=obj, granularity=gran,
                )
                for _, t in res.trades.iterrows():
                    if pd.isna(t["exit_time"]):
                        continue
                    rows.append(
                        {
                            "variant": variant,
                            "strategy_key": rec.strategy_key,
                            "symbol": sym,
                            "granularity": gran,
                            "direction": int(t["direction"]),
                            "entry_time": t["entry_time"],
                            "entry_price": float(t["entry_price"]),
                            "exit_price": float(t["exit_price"]),
                            "stop_loss": float(t["initial_stop_price"]),
                            "r_multiple": float(t["r_multiple"]),
                            "bars_held": int(t["bars_held"]),
                            "exit_reason": str(t["exit_reason"]),
                        }
                    )
        log.info("  T1/v2 %s done (%d rows)", rec.strategy_key, len(rows))
    pd.DataFrame(mirror_fail).to_csv(OUT / "q8_mirror_failures.csv", index=False)
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — random-entry floor, per engine, per granularity
# ─────────────────────────────────────────────────────────────────────────────


def test2(symbols, data, geom: dict, n_rep: int = 200, seed: int = 20260905) -> pd.DataFrame:
    """geom: {(engine, gran): {"sl_atr": x, "rr": y, "n_per_symbol": k, "max_bars": m}}"""
    from src.layer0.core_engine.strategy_base import StrategyBase, StrategyConfig

    v1_engine = BacktestEngine(BacktestConfig())
    v2_engine = PositionEngine()
    master = np.random.default_rng(seed)
    out = []

    class _RandomV1(StrategyBase):
        """Zero-information entries, ATR stop/TP at the measured geometry."""

        def __init__(self, cfg, sl_atr, rr, sigs):
            super().__init__(cfg)
            self._sl, self._rr, self._sigs = sl_atr, rr, sigs

        def calculate_indicators(self, df, asset, granularity):
            df = df.copy()
            df["ATR"] = atr_fn(df["High"], df["Low"], df["Close"], 14)
            return df

        def generate_signals(self, df, asset, granularity):
            return self._sigs.reindex(df.index).fillna(0).astype(int)

        def calculate_stop_loss(self, df, signal, entry_price, asset):
            a = float(df["ATR"].iloc[-1])
            return entry_price - signal * self._sl * a

        def calculate_take_profit(self, df, signal, entry_price, asset):
            a = float(df["ATR"].iloc[-1])
            return entry_price + signal * self._sl * self._rr * a

        def get_required_warmup_bars(self):
            return 100

        def get_entry_conditions(self, *a, **k):
            return {}

        def get_exit_conditions(self, *a, **k):
            return {}

    for (engine, gran), g in geom.items():
        for rep in range(n_rep):
            rng = np.random.default_rng(int(master.integers(0, 2**31)))
            for sym in symbols:
                if sym not in data or gran not in data[sym]:
                    continue
                df = data[sym][gran]
                n = min(g["n_per_symbol"], max(1, len(df) - 200))
                pos = rng.choice(np.arange(150, len(df)), size=n, replace=False)
                dirs = rng.choice([1, -1], size=n)

                if engine == "backtest_engine_v1":
                    sigs = pd.Series(0, index=df.index, dtype=int)
                    sigs.iloc[pos] = dirs
                    cfg = StrategyConfig(
                        name=f"rand_{gran}", primary_granularity=gran,
                        max_bars_hold=g["max_bars"], volatility_filter=False,
                        require_trend_alignment=False, use_multi_timeframe=False,
                    )
                    st = _RandomV1(cfg, g["sl_atr"], g["rr"], sigs)
                    res = v1_engine.run_backtest(st, df, sym, gran, 150)
                    for t in res.trades:
                        if t.exit_time is None or t.r_multiple is None:
                            continue
                        out.append({"engine": engine, "granularity": gran, "symbol": sym,
                                    "replication": rep, "entry_time": t.entry_time,
                                    "direction": int(t.direction), "r_multiple": float(t.r_multiple),
                                    "exit_reason": str(t.exit_reason), "bars_held": int(t.bars_held or 0)})
                else:
                    a = atr_fn(df["High"], df["Low"], df["Close"], 14)
                    intents = []
                    for p, d in zip(pos, dirs):
                        ts = df.index[p]
                        c = float(df["Close"].iloc[p])
                        av = float(a.iloc[p])
                        if not np.isfinite(av) or av <= 0:
                            continue
                        intents.append(
                            OrderIntent(
                                decision_bar=ts, direction=int(d), entry="market",
                                entry_price=None,
                                stop=StopRule(price=c - d * g["sl_atr"] * av),
                                exits=(ExitLeg(fraction=1.0, kind="take_profit",
                                               price=c + d * g["sl_atr"] * g["rr"] * av, label="TP"),),
                                time_exit_after_bars=g["max_bars"],
                                decision_close=c, strategy_id=f"rand_{gran}",
                            )
                        )
                    if not intents:
                        continue
                    intents.sort(key=lambda i: i.decision_bar)
                    res = v2_engine.run(df, intents, pair=sym, warmup_bars=150, granularity=gran)
                    for _, t in res.trades.iterrows():
                        if pd.isna(t["exit_time"]):
                            continue
                        out.append({"engine": engine, "granularity": gran, "symbol": sym,
                                    "replication": rep, "entry_time": t["entry_time"],
                                    "direction": int(t["direction"]), "r_multiple": float(t["r_multiple"]),
                                    "exit_reason": str(t["exit_reason"]), "bars_held": int(t["bars_held"])})
            if rep % 25 == 0:
                log.info("  T2 %s %s rep %d/%d (%d rows)", engine, gran, rep, n_rep, len(out))
    return pd.DataFrame(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--which", choices=["t1", "t2", "both"], default="both")
    ap.add_argument("--reps", type=int, default=200)
    ap.add_argument("--geom", type=str, default=str(OUT / "t2_geometry.json"))
    a = ap.parse_args()

    strats, symbols, data = _setup()
    log.info("population: %d strategies (Rule 5 applied), %d symbols", len(strats), len(symbols))

    if a.which in ("t1", "both"):
        d1 = test1_v1(strats, symbols, data)
        d1.to_parquet(OUT / "q8_trades_v1.parquet", index=False)
        log.info("Test1 v1: %d rows", len(d1))
        d2 = test1_v2(strats, symbols, data)
        d2.to_parquet(OUT / "q8_trades_v2.parquet", index=False)
        log.info("Test1 v2: %d rows", len(d2))

    if a.which in ("t2", "both"):
        geom_raw = json.loads(Path(a.geom).read_text())
        geom = {tuple(k.split("|")): v for k, v in geom_raw.items()}
        r = test2(symbols, data, geom, n_rep=a.reps)
        r.to_parquet(OUT / "q9_random_trades.parquet", index=False)
        log.info("Test2: %d rows", len(r))
