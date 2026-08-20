import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional
import pandas as pd

from src.registry import catalog
from src.layer0.strategies.v2_harness import build_frames
from src.vetting.vet import INTEGRITY_DISQUALIFIED

logger = logging.getLogger("system1.signals.build")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
# results/state/, NOT results/. A stray results/regime_strategy_map.json written during
# P5 testing designated strategy 10 — Range_Stochastic_Divergence, the look-ahead
# contaminated strategy that is INTEGRITY_DISQUALIFIED and whose removal caused the
# 2026-08-15 withdrawal. This module read that file. Had signals been flowing, System 1
# would have emitted orders for a strategy whose metrics are known to be fiction.
MAP_PATH = os.path.join(REPO_ROOT, "results", "state", "regime_strategy_map.json")

def load_model_set() -> Optional[Dict[str, Any]]:
    if not os.path.exists(MAP_PATH):
        logger.warning("No model set found at %s", MAP_PATH)
        return None
        
    try:
        with open(MAP_PATH, "r") as f:
            data = json.load(f)
            if data.get("status") != "published":
                logger.warning("Model set status is '%s', not 'published'", data.get("status"))
                return None
            return data
    except Exception as e:
        logger.error("Failed to read model set: %s", e)
        return None

def build_signals(bars_df: pd.DataFrame, model_set: Dict[str, Any], current_regimes: Dict[str, str]) -> List[Dict[str, Any]]:
    """Build signals for closed bars using the active strategies in the model set.
    
    current_regimes: dict mapping instrument -> regime label (e.g. "Trending-Up")
    """
    signals = []
    
    if bars_df.empty:
        return signals
        
    # Get active strategies per regime
    regimes = model_set.get("regimes", {})
    
    for _, row in bars_df.iterrows():
        inst = row["instrument"]
        regime = current_regimes.get(inst)
        
        if not regime:
            # We don't have a regime for this instrument, cannot route
            continue
            
        strats = regimes.get(regime, [])
        for strat_meta in strats:
            selection_basis = strat_meta.get("selection_basis")
            if selection_basis not in ["qualified", "designated"]:
                logger.error("Unknown selection_basis '%s' for strategy %s", selection_basis, strat_meta["strategy_id"])
                continue

            # Last line of defence. A strategy barred for a look-ahead defect must never
            # reach the wire, whatever a map says — a map file can be stale, hand-edited,
            # or written by a test, and one such file (results/regime_strategy_map.json,
            # from P5 testing) did designate strategy 10. Integrity is checked here, at
            # the point of emission, because that is the only place no upstream mistake
            # can route around.
            if int(strat_meta["strategy_id"]) in INTEGRITY_DISQUALIFIED:
                logger.error(
                    "REFUSING to emit for INTEGRITY_DISQUALIFIED strategy %s: %s",
                    strat_meta["strategy_id"],
                    INTEGRITY_DISQUALIFIED[int(strat_meta["strategy_id"])],
                )
                continue
                
            try:
                record = catalog.by_id(strat_meta["strategy_id"])
                strategy = catalog.instantiate(record)

                direction_policy = strat_meta.get("direction")
                bar_ts = pd.to_datetime(row["timestamp"], utc=True)

                # A contract-v2 strategy exposes generate_orders(frames) — NOT
                # process_closed_bar() or generate_signal(), which is what this module
                # used to call. Neither method exists on StrategyV2 or on any strategy in
                # the fleet, so both branches missed and the function returned an empty
                # list without logging why. Verified 2026-08-17.
                #
                # Orders are generated over the strategy's full declared frames rather
                # than the single new bar, because indicators need their warm-up (nnfx
                # needs 200+ D1 bars for its filter). We then keep only the intent whose
                # decision_bar IS this newly closed bar. That is exactly how v2_harness
                # attributes trades, so live and backtest agree by construction.
                if not hasattr(strategy, "generate_orders"):
                    logger.error(
                        "Strategy %s exposes no generate_orders(); refusing to guess an API",
                        strat_meta["strategy_id"],
                    )
                    continue

                meta = strategy.metadata
                if inst not in meta.pairs:
                    continue  # this strategy does not trade this pair
                if row.get("granularity") and row["granularity"] != meta.primary_granularity:
                    continue  # wrong clock for this strategy

                frames = build_frames(
                    inst,
                    meta.primary_granularity,
                    meta.context_granularities,
                    lookback_years=3,
                )
                if frames is None:
                    logger.warning("No frames for %s %s", inst, meta.primary_granularity)
                    continue

                intents = [
                    i
                    for i in strategy.generate_orders(frames)
                    if pd.Timestamp(i.decision_bar).tz_convert("UTC") == bar_ts
                ]

                for intent in intents:
                    # contract_v2 encodes direction as +1 / -1.
                    sig_dir = {1: "long", -1: "short"}.get(int(intent.direction))
                    if sig_dir is None:
                        logger.error("Refusing to emit: undecodable direction %r", intent.direction)
                        continue
                    if direction_policy not in (None, "both", sig_dir):
                        continue  # the map restricts this strategy to one side

                    # Stop and target come from the strategy's OWN declaration. If either
                    # is absent we refuse rather than infer — inferring exits is what
                    # produced the 2026-08-02 incident.
                    stop = getattr(intent.stop, "price", None) if intent.stop else None
                    if stop is None:
                        logger.error("Refusing to emit %s %s: no stop price declared", inst, sig_dir)
                        continue

                    tp_legs = [e for e in (intent.exits or []) if e.price is not None]
                    if not tp_legs:
                        logger.error("Refusing to emit %s %s: no take-profit price declared", inst, sig_dir)
                        continue
                    target = tp_legs[0].price

                    entry_price = intent.entry_price
                    if entry_price is None:
                        entry_price = row["Close"]  # market entry fills at next open; close is the reference

                    signals.append({
                        "signal_id": str(uuid.uuid4()),
                        "strategy_id": strat_meta["strategy_id"],
                        "strategy_key": strat_meta.get("strategy_key"),
                        "instrument": inst,
                        "granularity": meta.primary_granularity,
                        "signal_time_utc": bar_ts.isoformat(),
                        "direction": sig_dir,
                        "entry": float(entry_price),
                        "stop": float(stop),
                        "target": float(target),
                        "regime": regime,
                        "regime_probs": {"trending_up": 0.25, "trending_down": 0.25,
                                         "ranging": 0.25, "high_vol": 0.25},
                        "bundle_version": model_set.get("generated_at_utc"),
                        "selection_basis": selection_basis,
                    })
            except Exception as e:
                logger.error("Failed to build signal for strategy %s: %s", strat_meta["strategy_id"], e)
                
    return signals
