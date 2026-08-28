import argparse
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone

import pandas as pd
from typing import Dict, Any, List

from src.signals.watcher import BarWatcher
from src.signals.build import load_model_set, build_signals
from src.gatekeeper.score import Scorer
from src.queue_producer.producer import ScoredSignalProducer

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
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
    # FIX-S1-016: was src.regime_aware.context, removed with the failed R3 experiment.
    # The label math survives it (task/OPEN.md §8) and now lives in src/regime/.
    from src.regime.structural import build_structural_labels
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


EMITTER_STATE = os.path.join(REPO_ROOT, "results", "state", "signal_emitter_state.json")


def record_emitter_state(outcome: str, signals: int = 0, published: int = 0) -> None:
    """Record what the producer actually DID, for telemetry.

    This exists because of FIX-S1-016. The producer ran on schedule for weeks and emitted
    nothing — the cron fired, the process started, the log said "No signals generated", and
    every liveness signal available was green. A heartbeat would have reported healthy the
    entire time, because the process genuinely was healthy; it was the *outcome* that was
    absent.

    So the fields here are outcomes, not liveness. ``last_signal_emitted_at`` staying null
    while ``last_run_at`` advances every hour is the exact shape of that failure, and it is
    the one thing a reader can act on. Written locally on every run and published to the
    telemetry bucket by :mod:`src.monitoring.publish_health`; never blocks the run.
    """
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        prev: Dict[str, Any] = {}
        if os.path.exists(EMITTER_STATE):
            with open(EMITTER_STATE, encoding="utf-8") as fh:
                prev = json.load(fh)

        # A run that reached a verdict is a HEALTHY run, even when the verdict is "no
        # signals" — that is the normal state of a quiet market. Only an inability to
        # read the model set is a fault.
        #
        # This distinction exists because the file records the LAST run only. On
        # 2026-08-28 a single failing run at 12:19:21Z overwrote three successful cron
        # runs and left the shared telemetry advertising `no_model_set`, which reads
        # downstream as a hard outage. `consecutive_faults` and `last_healthy_run_at`
        # make one blip visibly different from a real outage without hiding either.
        faulted = outcome == "no_model_set"
        prior_faults = int(prev.get("consecutive_faults", 0))
        state = {
            "last_run_at": now,
            "last_run_outcome": outcome,
            "last_run_signals_built": signals,
            "last_run_signals_published": published,
            "consecutive_faults": (prior_faults + 1) if faulted else 0,
            "last_healthy_run_at": prev.get("last_healthy_run_at") if faulted else now,
            # Only advanced by a real publish, so it is the age of the last SIGNAL, not of
            # the last run. Null means "has never emitted", which is a reportable state.
            "last_signal_emitted_at": (
                now if published > 0 else prev.get("last_signal_emitted_at")
            ),
            "signals_published_total": int(prev.get("signals_published_total", 0))
            + published,
            "emitter_enabled": os.environ.get("DISABLE_LEGACY_SIGNALS") != "true",
        }
        os.makedirs(os.path.dirname(EMITTER_STATE), exist_ok=True)
        with open(EMITTER_STATE, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
    except Exception as e:  # never let telemetry break the producer
        logger.warning("Could not record emitter state: %s", e)


def run_once(
    watcher: BarWatcher,
    scorer: Scorer,
    producer: ScoredSignalProducer,
    dry_run: bool = True,
):
    model_set = load_model_set()
    if not model_set:
        logger.info("No active model set. Emitting nothing.")
        if not dry_run:
            record_emitter_state("no_model_set")
        return

    regimes, probs = get_current_regimes()

    # We only process H1 for now, or all granularities?
    # Actually we should loop through all granularities.
    # W1 is deliberately absent. System 3's ScoredSignal contract enumerates
    # {M15, M30, H1, H4, D, D1} and is additionalProperties/enum-strict, so a W1 signal
    # cannot be accepted — emitting one only fills a dead-letter queue. Add it back here
    # in the same change that adds it to their enum, not before.
    granularities = ["H1", "H4", "D1"]
    all_signals = []

    for g in granularities:
        # Fetch without committing; we commit only after a successful publish.
        new_bars = watcher.get_new_closed_bars(g, commit=False)
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

            # Score.
            #
            # A crash in the scorer must never take down the producer. On 2026-08-24 a
            # bad edit left `_derive_features` unimported in score.py: every call raised
            # NameError, which would have propagated out of run_once and killed the whole
            # hourly run — no signals AND no heartbeat, the exact blind spot FIX-S1-016
            # was about. Scoring is an ENRICHMENT step; the signal is already fully valid
            # without it, and the contract has a first-class representation for "not
            # scored". So an unexpected scorer fault degrades to unscored and is logged
            # loudly, rather than silently deleting the run's output.
            try:
                score_res = scorer.score(sig)
            except Exception as e:
                logger.exception(
                    "Scorer raised on %s (%s) — emitting UNSCORED rather than losing the run",
                    sig["instrument"],
                    e,
                )
                score_res = {
                    "status": "refused",
                    "reason": "MISSING_FEATURE:scorer_error",
                }

            if score_res["status"] == "scored":
                sig["model_score"] = score_res["score"]
                # What is threshold applied? The global one or strategy specific?
                # Let's say 0.5 default.
                sig["threshold_applied"] = 0.5
            elif score_res["status"] == "refused":
                # UNSCORABLE, NOT UNTRADEABLE.
                #
                # These reasons mean the gatekeeper declined to have an opinion, not
                # that it judged the signal bad. NO_CHAMPION_MODEL: no champion is live.
                # UNKNOWN_STRATEGY_ID: the strategy was not in the champion's training set
                # — which is exactly what happens the moment a newly-selected strategy is
                # added to the map before the next gatekeeper retrain.
                # MISSING_FEATURE: the live path does not supply that input at all.
                #
                # Dropping those was a silent-failure generator of the worst kind. A
                # freshly-promoted strategy would emit nothing, the producer would log one
                # warning nobody reads, and every health signal would stay green — the
                # precise shape of FIX-S1-016, rebuilt one layer up.
                #
                # MISSING_FEATURE is currently the case for EVERY live signal, and that is
                # a standing condition rather than an edge case: the champion trains on
                # atr_value / adx_value / prob_causal_* / regime_causal from
                # fact_market_regime_v2, which are written retrospectively for bars inside
                # a completed walk-forward fold. A live bar has no row there, so the
                # feature vector cannot be assembled at inference time and the ML
                # gatekeeper is out of the loop until it is retrained on inputs that exist
                # live. Emitting unscored keeps that visible and auditable downstream;
                # dropping made it invisible. It is logged at WARNING, not INFO, so the
                # condition cannot quietly become normal.
                #
                # A present-but-NaN feature is NOT in this set — that is corrupt data and
                # is still refused.
                #
                # System 3's contract is explicit that model_score NULL means "unscored,
                # never scored zero" and that it branches on it (see ScoredSignal v1). So
                # emit and let the risk layer decide, which is its job, not ours.
                # INFERENCE_ERROR is here too: the model failed to produce a number, which
                # is the gatekeeper having no opinion, not a verdict on the signal. It was
                # excluded, and on 2026-08-24 an int/str mismatch on strategy_id made every
                # score raise it — which would have silently discarded every signal again.
                # The only refusal that still DROPS is NAN_FEATURE: data supplied and
                # corrupt. Anything that merely means "could not score" emits unscored.
                reason = str(score_res["reason"])
                if (
                    reason in ("NO_CHAMPION_MODEL", "UNKNOWN_STRATEGY_ID")
                    or reason.startswith("MISSING_FEATURE:")
                    or reason.startswith("INFERENCE_ERROR:")
                ):
                    sig["model_score"] = None
                    sig["threshold_applied"] = None
                    logger.warning(
                        "Emitting %s UNSCORED (%s) — gatekeeper had no opinion, System 3 decides",
                        sig["instrument"],
                        reason,
                    )
                else:
                    logger.warning(
                        "Refused signal for %s by gatekeeper: %s",
                        sig["instrument"],
                        score_res["reason"],
                    )
                    continue

            all_signals.append(sig)

    if all_signals:
        if dry_run:
            logger.info("DRY RUN: would emit %d signals", len(all_signals))
            for s in all_signals:
                print(s)
        elif os.environ.get("DISABLE_LEGACY_SIGNALS") == "true":
            logger.info(
                "Legacy signal emission disabled. Only heartbeats will be sent."
            )
            record_emitter_state("suppressed_by_flag", signals=len(all_signals))
        else:
            score_run_id = str(uuid.uuid4())
            metrics = producer.publish_signals(all_signals, score_run_id)
            logger.info("Published signals: %s", metrics)
            published_count = int(metrics.get("published_count", 0))
            record_emitter_state(
                "published",
                signals=len(all_signals),
                published=published_count,
            )
            if published_count > 0:
                watcher.commit()
            else:
                watcher.rollback()
    else:
        logger.info("No signals generated.")
        watcher.rollback()
        if not dry_run:
            record_emitter_state("no_signals_generated")

    if not dry_run:
        producer.emit_heartbeat(model_set)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run", action="store_true", help="Print what would be emitted"
    )
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
            time.sleep(60)  # sleep 1 minute
    else:
        run_once(watcher, scorer, producer, dry_run=dry_run)


if __name__ == "__main__":
    main()
