import argparse
import json
import logging
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone

import pandas as pd
from typing import Dict, Any, List, Optional

from src.signals import ledger
from src.signals.watcher import BarWatcher
from src.signals.build import (
    load_model_set,
    build_signals,
    last_refusal as build_last_refusal,
)
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


def record_emitter_state(
    outcome: str,
    signals: int = 0,
    published: int = 0,
    tally: Optional[Dict[str, int]] = None,
    tally_by_regime: Optional[Dict[str, Dict[str, int]]] = None,
    shadow: Optional[Dict[str, int]] = None,
    dlq: Optional[Dict[str, Any]] = None,
) -> None:
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
            try:
                with open(EMITTER_STATE, encoding="utf-8") as fh:
                    prev = json.load(fh)
            except (OSError, json.JSONDecodeError) as e:
                # Self-heal rather than abort. This read used to sit bare inside the outer
                # try, so one unparseable file aborted the write on THIS run and every
                # future run — the file could never be rewritten. Meanwhile
                # publish_health._read_json returns {} for the same file, so the telemetry
                # Systems 2/3 see would show last_signal_emitted_at: null and
                # never_emitted: true. That is the FIX-S1-016 alarm shape, manufactured by
                # a local parse failure and attributed to nothing.
                #
                # Losing the cumulative totals is the lesser harm and it is visible: the
                # counters restart from zero, which reads as a reset, not as an outage.
                logger.error(
                    "Emitter state at %s is unreadable (%s) — rebuilding from zero. "
                    "Cumulative totals are lost; the ledger under results/signals/ is "
                    "the surviving per-signal record.",
                    EMITTER_STATE,
                    e,
                )
                prev = {}

        # A run that reached a verdict is a HEALTHY run, even when the verdict is "no
        # signals" — that is the normal state of a quiet market. Only an inability to
        # read the model set is a fault.
        #
        # This distinction exists because the file records the LAST run only. On
        # 2026-08-28 a single failing run at 12:19:21Z overwrote three successful cron
        # runs and left the shared telemetry advertising `no_model_set`, which reads
        # downstream as a hard outage. `consecutive_faults` and `last_healthy_run_at`
        # make one blip visibly different from a real outage without hiding either.
        # `map_inadmissible` counts as a fault alongside `no_model_set`: an expired,
        # stale or label-mismatched map is a condition someone must act on, and it must
        # drive `consecutive_faults` and freeze `last_healthy_run_at` exactly as a missing
        # model set does. A refusal that reported itself as healthy would reproduce the
        # FIX-S1-016 shape one layer up — green telemetry over a system that is not
        # trading and cannot say why.
        faulted = outcome in ("no_model_set", "map_inadmissible")
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

        # Gate-1 outcome counters. `signals_published_total` above answers "how many
        # reached the wire" and conflates scored with unscored — which is exactly the
        # question Systems 2/3 could not answer. These separate them, and add the
        # dropped count, which had no counter at all.
        #
        # NOTE the denominator caveat: an approval rate is scored/(scored+refused), and
        # `refused` in that sense does not exist yet — nothing compares a score to a
        # threshold (FIX-S1-018). `signals_dropped_total` counts corrupt-feature drops,
        # which are a data fault, NOT a gatekeeper verdict, and must not be used as the
        # denominator. Until the gate is wired the honest runtime approval rate is
        # undefined, not zero.
        counts = dict(tally or {})
        for key in ("scored", "unscored", "dropped"):
            n = int(counts.get(key, 0))
            state[f"last_run_signals_{key}"] = n
            state[f"signals_{key}_total"] = int(prev.get(f"signals_{key}_total", 0)) + n
        state["last_run_by_regime"] = tally_by_regime or {}

        # SHADOW MODE counters. These are what the gate WOULD have decided; nothing was
        # gated on them. They are deliberately named `shadow_*` at every level so no
        # consumer can pick one up and render it as the runtime rate — the two answer
        # different questions and only one of them describes what the system did.
        sh = dict(shadow or {})
        for key in ("would_pass", "would_refuse"):
            n = int(sh.get(key, 0))
            state[f"last_run_shadow_{key}"] = n
            state[f"shadow_{key}_total"] = int(prev.get(f"shadow_{key}_total", 0)) + n

        # DLQ counters (O-22, promised to Systems 2/3). Under Pub/Sub `dead_letter()`
        # publishes nothing to a DLQ topic — it logs locally — so without these the
        # consumer cannot tell a lost wire message from a dead-letter at all.
        #
        # NULL vs ZERO is the load-bearing distinction and it is why `dlq` is Optional:
        # `None` means the producer was never invoked this run (no signals to publish), so
        # nothing was measured. `0` means it ran and dropped nothing. Defaulting the
        # unmeasured case to 0 would report "no drops" for a run that never looked.
        if dlq is None:
            state["last_run_dlq_count"] = None
            state["last_run_dlq_by_reason"] = None
        else:
            by_reason = dict(dlq.get("dlq_by_reason") or {})
            state["last_run_dlq_count"] = int(dlq.get("dlq_count", 0))
            state["last_run_dlq_by_reason"] = by_reason
            state["dlq_count_total"] = int(prev.get("dlq_count_total", 0) or 0) + int(
                dlq.get("dlq_count", 0)
            )
            merged = dict(prev.get("dlq_by_reason_total") or {})
            for reason, n in by_reason.items():
                merged[reason] = int(merged.get(reason, 0)) + int(n)
            state["dlq_by_reason_total"] = merged
        # Cumulative totals carry forward untouched on an unmeasured run rather than
        # resetting — they are a running history, not a per-run reading.
        state.setdefault("dlq_count_total", prev.get("dlq_count_total"))
        state.setdefault("dlq_by_reason_total", prev.get("dlq_by_reason_total"))

        os.makedirs(os.path.dirname(EMITTER_STATE), exist_ok=True)
        # Atomic. This was a plain in-place read-modify-write, so a crash mid-write left
        # a truncated file — and the reload above does `prev.get(..., 0)`, which silently
        # resets every cumulative total to zero and backdates `last_signal_emitted_at` to
        # null. That field is load-bearing: a null there IS the FIX-S1-016 alarm, and
        # manufacturing one by crashing at the wrong moment would be a false outage.
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(EMITTER_STATE), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=2)
                fh.write("\n")
                # fsync BEFORE the rename, or the atomicity is only against a process
                # crash. os.replace is atomic w.r.t. other readers, but on ext4
                # data=ordered a power loss just after it can leave the destination
                # present and zero-length — which is exactly the "totals silently reset,
                # last_signal_emitted_at backdates to null" outcome this block exists to
                # prevent. ledger.append() already fsyncs; the file holding the cumulative
                # counters should not have the weaker guarantee.
                fh.flush()
                os.fsync(fh.fileno())
        except BaseException:
            # os.fdopen takes ownership of fd on success; if it raised, the raw descriptor
            # is still ours and leaks without this.
            try:
                os.close(fd)
            except OSError:
                pass
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        try:
            os.replace(tmp, EMITTER_STATE)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
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
        # R1.3 — "there is no model set" and "the model set's map is not allowed to route"
        # are different states and must not share an outcome name. The first is a
        # deployment condition; the second is an alarm about an artifact that exists and
        # is wrong (expired, stale, or selected under a different regime label than the
        # one we route on). Collapsing them is how a fail-open map would stay invisible.
        refusal = build_last_refusal()
        if refusal:
            logger.error(
                "Emitting nothing: model set map REFUSED (%s). Reasons: %s",
                refusal.get("model_set_id"),
                "; ".join(refusal.get("refusals") or []),
            )
            if not dry_run:
                record_emitter_state("map_inadmissible")
        else:
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

    # Minted BEFORE the loop, not at publish time, because the ledger records dropped
    # candidates too and those never reach the publish call. It identifies the run, so
    # the earlier mint is also the more correct one.
    score_run_id = str(uuid.uuid4())
    # gate1_outcome -> count, and (gate1_outcome, regime) -> count. Written to the emitter
    # state so the aggregate is readable without parsing the ledger.
    tally: Dict[str, int] = {"scored": 0, "unscored": 0, "dropped": 0}
    tally_by_regime: Dict[str, Dict[str, int]] = {}
    # SHADOW MODE: what the gate WOULD have decided. Counted only from rows that were
    # actually written, so this always reconciles against the ledger backing it.
    shadow: Dict[str, int] = {"would_pass": 0, "would_refuse": 0}

    def _tally(outcome: str, regime: Any) -> None:
        tally[outcome] = tally.get(outcome, 0) + 1
        per = tally_by_regime.setdefault(str(regime), {})
        per[outcome] = per.get(outcome, 0) + 1

    # Read once, before the loop, so a row can say `suppressed` instead of claiming
    # `published` on a run that sends nothing at all.
    emit_enabled = os.environ.get("DISABLE_LEGACY_SIGNALS") != "true"

    def _ledger(
        sig: Dict[str, Any], outcome: str, wire: str, reason: Any = None
    ) -> None:
        """Record one candidate, then count it. No-op under --dry-run.

        A dry run must leave no trace: it is the rehearsal command, and a rehearsal that
        writes rows into the audit trail makes the trail describe runs that never
        happened.
        """
        if dry_run:
            return
        if wire == "published" and not emit_enabled:
            wire = "suppressed"
        row = ledger.record(
            sig,
            gate1_outcome=outcome,
            wire_action=wire,
            score_run_id=score_run_id,
            models_dir=MODELS_DIR,
            refusal_reason=str(reason) if reason is not None else None,
        )
        # `row` is None when the append failed, and a test double may return None too.
        verdict = (row or {}).get("shadow_verdict")
        if verdict in shadow:
            shadow[verdict] += 1
        # Counter buckets are the three the emitter state persists. `unknown_status` is
        # emitted with a null score, so it counts as unscored — the ledger's
        # `gate1_outcome` keeps the finer distinction.
        _tally(
            {
                "dropped_corrupt_feature": "dropped",
                "unknown_status": "unscored",
            }.get(outcome, outcome),
            sig.get("regime"),
        )

    # D6(c) per-run dedup: a secondary guard against the same signal_id appearing twice
    # within a single run.  The primary defence is the stale-bar filter in build_signals()
    # and the watcher's state commit.  This set catches any path that defeats both — e.g.
    # two strategies that (mis)produce the same uuid5 key on the same bar, or a future code
    # change that somehow calls build_signals() twice for the same bar in the same run.
    # It is intentionally NOT persisted across runs: watcher state is the cross-run guard.
    emitted_signal_ids: set = set()

    for g in granularities:
        # Fetch without committing; we commit only after a successful publish.
        new_bars = watcher.get_new_closed_bars(g, commit=False)
        if new_bars.empty:
            continue

        logger.info("Found %d new closed %s bars", len(new_bars), g)

        # Build raw signals
        raw_signals = build_signals(new_bars, model_set, regimes)

        for sig in raw_signals:
            sig_id = str(sig.get("signal_id", ""))
            if sig_id and sig_id in emitted_signal_ids:
                logger.warning(
                    "D6 per-run dedup: signal_id %s appeared twice in this run "
                    "(strategy %s, %s %s) — discarding the second copy",
                    sig_id,
                    sig.get("strategy_id"),
                    sig.get("instrument"),
                    sig.get("granularity"),
                )
                continue
            if sig_id:
                emitted_signal_ids.add(sig_id)
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
                # PLACEHOLDER, and it is not the calibrated threshold. The champion's real
                # per-regime cutoffs (0.60-0.80) live in models/champion_manifest.json and
                # are never read at inference — Scorer sets self.manifest_path and _load()
                # never opens it — so nothing here compares the score to anything and the
                # signal is published regardless. 0.5 is below every calibrated value, so
                # this stamps a threshold that would have passed everything.
                #
                # Tracked as FIX-S1-018. The ledger records this value next to
                # `threshold_calibrated` so the gap is measurable from the data rather
                # than argued from the code. Do NOT quietly start applying the real
                # threshold here: that changes what reaches the wire and is its own
                # change set.
                sig["threshold_applied"] = 0.5
                _ledger(sig, "scored", "published")
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
                # CORRECTED 2026-08-30 — the paragraph that stood here was STALE and it
                # misled a downstream investigation. It said MISSING_FEATURE was the case
                # for EVERY live signal, because the champion trained on prob_causal_* /
                # regime_causal from fact_market_regime_v2, which are written
                # retrospectively and so are absent on a live bar.
                #
                # That described the PREVIOUS champion (gk-656f09e2). The champion live
                # since 2026-08-24 needs seven features — atr_value, adx_value,
                # regime_structural, strategy_id and three derived from them — and
                # `regime_structural` is computed on the fly from D1 closes, not read from
                # the table. `build.py` already assembles all of them via
                # `build_inference_features`.
                #
                # Measured 2026-08-30: 15 of 15 (pair x granularity) combinations scored,
                # and all 8 strategies in the live map are known to the preprocessor. The
                # gatekeeper is NOT out of the loop. Do not re-derive the old claim from
                # this branch merely existing.
                #
                # The branch still earns its place: NO_CHAMPION_MODEL, UNKNOWN_STRATEGY_ID
                # and a genuine feature gap are all real and all mean "no opinion" rather
                # than "bad signal". Logged at WARNING, not INFO, so a rise in unscored
                # cannot quietly become normal.
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
                    _ledger(sig, "unscored", "published", reason)
                else:
                    logger.warning(
                        "Refused signal for %s by gatekeeper: %s",
                        sig["instrument"],
                        score_res["reason"],
                    )
                    # The one exit that left NO record of any kind. A NAN_FEATURE drop
                    # used to be a single warning with no signal_id, so a dropped
                    # candidate was unrecoverable once the log rotated — and invisible in
                    # every counter, because last_run_signals_built is measured after the
                    # drop. This row is the reason the module exists.
                    _ledger(
                        sig,
                        "dropped_corrupt_feature",
                        "dropped",
                        score_res["reason"],
                    )
                    continue
            else:
                # Unreachable today — score() returns only "scored" or "refused". Pinned
                # anyway, because without it a third status would fall straight through to
                # all_signals.append() with no ledger row and no tally, silently breaking
                # both the one-row-per-candidate invariant and the counter reconciliation.
                # A new status is exactly the kind of change that would add one quietly.
                logger.error(
                    "Unknown scorer status %r for %s — emitting unscored and recording it",
                    score_res.get("status"),
                    sig["instrument"],
                )
                sig["model_score"] = None
                sig["threshold_applied"] = None
                _ledger(
                    sig,
                    "unknown_status",
                    "published",
                    f"UNKNOWN_STATUS:{score_res.get('status')!r}",
                )

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
            record_emitter_state(
                "suppressed_by_flag",
                signals=len(all_signals),
                tally=tally,
                shadow=shadow,
                tally_by_regime=tally_by_regime,
            )
        else:
            metrics = producer.publish_signals(all_signals, score_run_id)
            logger.info("Published signals: %s", metrics)
            published_count = int(metrics.get("published_count", 0))
            record_emitter_state(
                "published",
                signals=len(all_signals),
                published=published_count,
                tally=tally,
                shadow=shadow,
                tally_by_regime=tally_by_regime,
                # Only this branch actually invoked the producer, so it is the only one
                # that measured the DLQ. The others pass nothing, which records null.
                dlq=metrics,
            )
            if published_count > 0:
                watcher.commit()
            else:
                watcher.rollback()
    else:
        logger.info("No signals generated.")
        watcher.rollback()
        if not dry_run:
            # The tally still matters here. A run where every candidate was dropped for a
            # corrupt feature reaches this branch with all_signals empty, and looked
            # identical to a quiet market before the ledger existed.
            record_emitter_state(
                "no_signals_generated",
                tally=tally,
                shadow=shadow,
                tally_by_regime=tally_by_regime,
            )

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
