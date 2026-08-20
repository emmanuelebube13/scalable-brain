"""Run the legacy-9 (v1 engine) arms into the trial table.

The v2 runner covers the 43 new `StrategyV2` strategies. This covers the nine
regime-aware ports that run on `layer0.core_engine.BacktestEngine`, so the trial
has the continuity with T3 the owner asked for.

**These results are NOT poolable with the v2 results, and the report must say so.**
Two reasons, both structural:

1. **A different exit model.** The v1 engine applies a uniform ATR 1:3 harness; the
   v2 strategies run their own declared exits. `engine` on every row records which.
2. **A different intervention.** The v1 ports vary *parameters* per regime (channel
   period, ADX threshold, ATR multiples) as well as enabling/disabling. The v2 gate
   only enables and disables. So the v1 arms test a stronger, higher-degree-of-freedom
   intervention than the v2 arms and cannot be read as the same experiment.

The blind arm here is window-matched, exactly as on the v2 side: `RegimeParams.uniform`
leaves `UNKNOWN` enabled, so an unmodified baseline trades warm-up bars that every
aware arm refuses. Comparing those two measures the warm-up as if it were the
intervention. The blind arm below therefore takes the baseline block for every regime
with `UNKNOWN` disabled.

    python -m src.regime_aware.v1_trial              # dry run, prints counts
    python -m src.regime_aware.v1_trial --write      # persist to the trial table
"""

from __future__ import annotations

import argparse
import importlib
import logging
import uuid
from dataclasses import replace
from typing import Dict, List, Sequence

import pandas as pd

from src.regime_aware.context import (
    ALL_REGIMES,
    UNKNOWN,
    build_structural_labels,
    build_trend_labels,
    load_regime_labels,
    readonly_connection,
)
from src.regime_aware.contract import RegimeParams
from src.regime_aware.outcomes import write_trial_outcomes
from src.regime_aware.runner import STRATEGIES_LIST, run_arm
from src.layer0.qualify_strategies import preload_historical_data

logger = logging.getLogger("v1_trial")

ENGINE_TAG = "backtest_engine_v1"


def window_matched_blind(baseline) -> RegimeParams:
    """Baseline parameters everywhere, `UNKNOWN` disabled.

    This is the v1 counterpart of the v2 permissive gate: it makes the blind arm
    refuse exactly the bars every aware arm refuses, so the arms differ by the
    intervention and not by the label warm-up.
    """
    blocks = {r: baseline for r in ALL_REGIMES}
    blocks[UNKNOWN] = replace(baseline, enabled=False)
    return RegimeParams(blocks)


def _rows(trades: pd.DataFrame, *, arm: str, source: str, run_id: str,
          strategy_key: str, mask_json: str | None) -> List[Dict]:
    out: List[Dict] = []
    if trades is None or trades.empty:
        return out
    for _, t in trades.iterrows():
        out.append({
            "timestamp": pd.Timestamp(t["entry_time"]),
            "asset_id": int(t["asset_id"]),
            "granularity": str(t["granularity"]),
            "is_winner": int(t["is_winner"]),
            "r_multiple": float(t["r_multiple"]),
            "holding_bars": 0,
            "exit_reason": str(t["exit_reason"]),
            "arm": arm,
            "regime_at_entry": str(t.get("regime", UNKNOWN)),
            "regime_source": source,
            "run_id": run_id,
            "strategy_key": strategy_key,
            "mask_applied": mask_json,
            "engine": ENGINE_TAG,
            "is_oos": bool(t.get("is_oos", False)),
            "fold_id": t.get("fold_id"),
        })
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lookback-years", type=int, default=10)
    ap.add_argument("--write", action="store_true",
                    help="persist to fact_regime_trial_outcomes (default: dry run)")
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )
    run_id = args.run_id or f"v1-{uuid.uuid4()}"
    logger.info("v1 trial run_id=%s write=%s", run_id, args.write)

    conn = readonly_connection()
    cur = conn.cursor()
    cur.execute("SELECT symbol, asset_id FROM dim_asset WHERE is_active = true ORDER BY asset_id")
    asset_map = {s: a for s, a in cur.fetchall()}

    needed_gran = set()
    mods = {}
    for mod_name, strat_name in STRATEGIES_LIST:
        mod = importlib.import_module(f"src.regime_aware.strategies.{mod_name}")
        mods[mod_name] = (mod, strat_name)
        needed_gran.add(mod.build_baseline().config.primary_granularity)

    data = preload_historical_data(
        asset_symbols=list(asset_map),
        asset_symbol_map=asset_map,
        granularities=list(needed_gran.union({"D1"})),
        use_db=True,
        conn=conn,
        lookback_years=args.lookback_years,
    )
    hmm_by_gran = {g: load_regime_labels(conn, g) for g in needed_gran}
    conn.close()

    trend_labels = {
        asset_id: build_trend_labels(data[symbol]["D1"])
        for symbol, asset_id in asset_map.items()
        if data.get(symbol, {}).get("D1") is not None
    }
    # The structural label is the only one of the three that both expresses a four-state
    # mask and varies on every pair, so the legacy 9 are measured under it too — otherwise
    # "the whole fleet under the new regime system" would still have a nine-strategy hole.
    structural_labels = {
        asset_id: build_structural_labels(data[symbol]["D1"])
        for symbol, asset_id in asset_map.items()
        if data.get(symbol, {}).get("D1") is not None
    }

    total = 0
    for mod_name, (mod, strat_name) in mods.items():
        gran = mod.build_baseline().config.primary_granularity
        hmm_labels = hmm_by_gran[gran]
        cls = type(mod.build_baseline())

        blind = cls(window_matched_blind(mod.BASELINE), name=f"{strat_name}_blind")

        specs = (
            ("blind", blind, hmm_labels, "hmm_causal"),
            ("blind", blind, trend_labels, "d1_trend"),
            ("blind", blind, structural_labels, "structural"),
            ("aware", mod.build_regime_aware(), hmm_labels, "hmm_causal"),
            ("aware", mod.build_trend_aware(), trend_labels, "d1_trend"),
            # The structural arm reuses the HMM-tuned RegimeParams: both emit the same
            # four-state vocabulary, so the mask transfers unchanged.
            ("aware", mod.build_regime_aware(), structural_labels, "structural"),
        )
        rows: List[Dict] = []
        for arm, strategy, labels, source in specs:
            trades = run_arm(strategy, data, labels, asset_map, gran)
            logger.info("[%s] %s@%s: %d trades", strat_name, arm, source, len(trades))
            rows.extend(_rows(trades, arm=arm, source=source, run_id=run_id,
                              strategy_key=strat_name, mask_json=None))

        if args.write and rows:
            total += write_trial_outcomes(rows)
        elif rows:
            total += len(rows)

    logger.info("%s %d rows (engine=%s)", "wrote" if args.write else "would write",
                total, ENGINE_TAG)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
