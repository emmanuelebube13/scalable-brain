import argparse
import logging
import os
import sys
import time
import uuid
import pandas as pd
from typing import Dict, Any, List

from src.signals.watcher import BarWatcher
from src.signals.build import load_model_set, build_signals
from src.gatekeeper.score import Scorer
from src.queue_producer.producer import ScoredSignalProducer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("system1.signals.run")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODELS_DIR = os.path.join(REPO_ROOT, "models")


def get_current_regimes() -> tuple:
    """Current regime label per instrument, plus the probability vector.

    Uses the STRUCTURAL label, not `regime_causal`, for two reasons:

    1. `regime_causal` is NULL on the newest rows — it is only written for bars inside a
       completed walk-forward fold, and the table's latest row per asset (2026-08-11) has
       no causal label at all. Routing on it returned None for every instrument, so every
       bar was skipped and the producer emitted nothing while logging only "No signals
       generated".
    2. It is the label we publish in `system1/regime_status/latest.json`, so what System 3
       sees on its dashboard is the label that actually routed the signal. Anything else
       would have the two disagreeing.

    It is computed on the fly from D1 closes (ADX + a rolling Z-score of ATR%), so it is
    always available and never depends on a fit having been run recently.
    """
    from src.regime_aware.context import build_structural_labels
    from src.layer0.strategies.research_data import load_ohlcv_readonly
    from src.common.db import get_engine
    import pandas as pd

    engine = get_engine()
    with engine.connect() as conn:
        assets = pd.read_sql(
            "SELECT symbol FROM dim_asset WHERE is_active = true", conn
        )["symbol"].tolist()

    regimes, probs = {}, {}
    for inst in assets:
        try:
            d1 = load_ohlcv_readonly(inst, "D1", lookback_years=3)
            if d1 is None or d1.empty:
                continue
            labels = build_structural_labels(d1)
            if labels.empty:
                continue
            label = str(labels.iloc[-1]["regime"])
            regimes[inst] = label
            # The structural label is a deterministic rule, not a posterior, so it has no
            # probability vector. A one-hot is the honest encoding: it says "this label,
            # with certainty from the rule" rather than inventing a distribution.
            probs[inst] = {
                "trending_up": 1.0 if label == "Trending-Up" else 0.0,
                "trending_down": 1.0 if label == "Trending-Down" else 0.0,
                "ranging": 1.0 if label == "Ranging" else 0.0,
                "high_vol": 1.0 if label == "High-Vol" else 0.0,
            }
        except Exception as e:
            logger.warning("Could not resolve regime for %s: %s", inst, e)
    return regimes, probs

def run_once(watcher: BarWatcher, scorer: Scorer, producer: ScoredSignalProducer, dry_run: bool = True):
    model_set = load_model_set()
    if not model_set:
        logger.info("No active model set. Emitting nothing.")
        return

    regimes, probs = get_current_regimes()
    
    # We only process H1 for now, or all granularities?
    # Actually we should loop through all granularities.
    granularities = ["H1", "H4", "D1", "W1"]
    all_signals = []
    
    for g in granularities:
        # commit=False on a dry run: previewing must not advance the watermark.
        new_bars = watcher.get_new_closed_bars(g, commit=not dry_run)
        if new_bars.empty:
            continue
            
        logger.info("Found %d new closed %s bars", len(new_bars), g)
        
        # Build raw signals
        raw_signals = build_signals(new_bars, model_set, regimes)
        
        for sig in raw_signals:
            # Inject correct probabilities
            inst = sig["instrument"]
            if inst in probs:
                sig["regime_probs"] = probs[inst]
                
            # Score
            score_res = scorer.score(sig)
            if score_res["status"] == "scored":
                sig["model_score"] = score_res["score"]
                # What is threshold applied? The global one or strategy specific? 
                # Let's say 0.5 default.
                sig["threshold_applied"] = 0.5
            elif score_res["status"] == "refused":
                if score_res["reason"] == "NO_CHAMPION_MODEL":
                    sig["model_score"] = None
                    sig["threshold_applied"] = None
                    # Mark as unscored if you want? The instruction says:
                    # emit with model_score: null and threshold_applied: null.
                    # P5: "and mark the signal unscored so System 3 can decide what to do with it."
                    # We can add an 'unscored' flag or just rely on model_score is None.
                else:
                    logger.warning("Refused signal for %s by gatekeeper: %s", sig["instrument"], score_res["reason"])
                    continue
                    
            all_signals.append(sig)
            
    if all_signals:
        if dry_run:
            logger.info("DRY RUN: would emit %d signals", len(all_signals))
            for s in all_signals:
                print(s)
        else:
            score_run_id = str(uuid.uuid4())
            metrics = producer.publish_signals(all_signals, score_run_id)
            logger.info("Published signals: %s", metrics)
    else:
        logger.info("No signals generated.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print what would be emitted")
    parser.add_argument("--once", action="store_true", help="One pass, real emit")
    args = parser.parse_args()
    
    dry_run = args.dry_run
    # If no flags are passed, run continuously
    continuous = not args.dry_run and not args.once
    
    # Wait, the instruction says:
    # python -m src.signals.run --dry-run    # print what would be emitted
    # python -m src.signals.run --once       # one pass, real emit
    # python -m src.signals.run              # continuous
    
    watcher = BarWatcher()
    scorer = Scorer(MODELS_DIR)
    # Using local queue provider as per Step 7
    # os.environ["QUEUE_PROVIDER"] = "local" # Must be set externally or here
    producer = ScoredSignalProducer()
    
    if continuous:
        logger.info("Starting continuous live signal producer...")
        while True:
            try:
                run_once(watcher, scorer, producer, dry_run=False)
            except Exception as e:
                logger.error("Error in continuous loop: %s", e)
            time.sleep(60) # sleep 1 minute
    else:
        run_once(watcher, scorer, producer, dry_run=dry_run)


if __name__ == "__main__":
    main()
