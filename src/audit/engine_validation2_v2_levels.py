"""Capture the v2 engine's OWN resolved exit levels (read-only).

The winner-conditional R:R proxy used to reconstruct a v2 take-profit level is
wrong for fractional-leg strategies: `exit_price` in the trades frame is the
fraction-weighted average across ALL exit fills, so `|exit - entry| / stop_dist`
on a TAKE_PROFIT exit is not the TP distance. Reconstructing from it would put
the TP artificially close to entry and inflate any ambiguity count.

Rather than reconstruct, this instruments `PositionEngine._open_position` in an
audit-only subclass and records the level the engine actually resolved for every
take-profit leg (`position_engine.py:729-737`). No production code is modified.

Writes: audit/reports/engine_validation_2/v2_declared_levels.parquet
"""

from __future__ import annotations

import logging
import sys
import warnings
from datetime import timezone
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from src.common.db import get_psycopg2_connection  # noqa: E402
from src.layer0.qualify_strategies import preload_historical_data  # noqa: E402
from src.layer0.strategies.position_engine import PositionEngine  # noqa: E402
from src.layer0.strategies.v2_harness import assert_no_lookahead_v2  # noqa: E402
from src.registry.catalog import all_strategies, instantiate  # noqa: E402

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("ev2.v2levels")
OUT = _REPO / "audit" / "reports" / "engine_validation_2"


class _InstrumentedEngine(PositionEngine):
    """Records every resolved exit-leg level. Behaviour is otherwise identical."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.levels: list[dict] = []

    def _open_position(self, trade_id, intent, fill, fill_bar, checks_from,
                       decision_idx, atr_values, pip, pair, index, stop_rows):
        pos = super()._open_position(trade_id, intent, fill, fill_bar, checks_from,
                                     decision_idx, atr_values, pip, pair, index, stop_rows)
        tp_levels = [(ls.leg.fraction, ls.level) for ls in pos.legs
                     if ls.leg.kind == "take_profit" and ls.level is not None]
        first = tp_levels[0] if tp_levels else (np.nan, np.nan)
        self.levels.append({
            "trade_id": trade_id,
            "entry_time": index[fill_bar],
            "entry_price": fill,
            "direction": intent.direction,
            "declared_stop": intent.stop.price,
            "n_tp_legs": len(tp_levels),
            "tp1_fraction": first[0],
            "tp1_level": first[1],
            "tp_last_level": tp_levels[-1][1] if tp_levels else np.nan,
            "has_trailing": any(ls.leg.kind == "trailing" for ls in pos.legs)
                            or intent.stop.trail_atr_multiple is not None,
            "has_breakeven": intent.stop.move_to_breakeven_on is not None,
            "n_legs_total": len(pos.legs),
        })
        return pos


def main() -> None:
    conn = get_psycopg2_connection()
    cur = conn.cursor()
    cur.execute("SELECT symbol, asset_id FROM dim_asset WHERE is_active=true ORDER BY asset_id")
    amap = {s: a for s, a in cur.fetchall()}
    symbols = list(amap)
    recs = [r for r in all_strategies() if r.engine == "position_engine_v2"]
    grans = {"H1", "H4", "D1"}
    for r in recs:
        try:
            grans.add(instantiate(r).metadata.primary_granularity)
        except Exception:  # noqa: BLE001
            pass
    data = preload_historical_data(asset_symbols=symbols, asset_symbol_map=amap,
                                   granularities=list(grans), use_db=True, conn=conn,
                                   lookback_years=10)

    rows = []
    for rec in recs:
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
            eng = _InstrumentedEngine()
            res = eng.run(frames[gran], intents, pair=sym, warmup_bars=obj.warmup_bars,
                          strategy=obj, granularity=gran)
            lv = pd.DataFrame(eng.levels)
            if not len(lv):
                continue
            tr = res.trades[["trade_id", "exit_time", "exit_price", "exit_reason",
                             "r_multiple", "bars_held", "initial_stop_price",
                             "final_stop_price", "gapped"]]
            m = lv.merge(tr, on="trade_id", how="inner")
            m["strategy_key"] = rec.strategy_key
            m["strategy_id"] = rec.strategy_id
            m["symbol"] = sym
            m["granularity"] = gran
            rows.append(m)
        log.info("  %s done", rec.strategy_key)

    out = pd.concat(rows, ignore_index=True)
    for c in ("entry_time", "exit_time"):
        out[c] = pd.to_datetime(out[c], utc=True)
    out.to_parquet(OUT / "v2_declared_levels.parquet", index=False)
    log.info("wrote %d rows", len(out))
    log.info("\n%s", out.groupby("granularity").agg(
        n=("trade_id", "size"), n_tp_legs=("n_tp_legs", "median"),
        frac_multi_leg=("n_tp_legs", lambda x: (x > 1).mean()),
        frac_trailing=("has_trailing", "mean"),
        frac_breakeven=("has_breakeven", "mean")).round(4).to_string())


if __name__ == "__main__":
    main()
