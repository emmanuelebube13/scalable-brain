import json
import logging
import os
import time
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
#
# FIX-S1-016: retained ONLY as the artifact name inside the published bundle. This
# module no longer reads the local copy — see load_model_set().
MAP_ARTIFACT_NAME = "regime_strategy_map.json"
MAP_PATH = os.path.join(REPO_ROOT, "results", "state", MAP_ARTIFACT_NAME)


def load_model_set() -> Optional[Dict[str, Any]]:
    """Load the live model set from the STORAGE BACKEND, which is authoritative.

    FIX-S1-016. This function used to read the local ``results/state`` map and require
    ``status == "published"`` on it. That condition could never be true: ``vet.py``
    hardcodes ``"status": "proposed"`` and nothing anywhere writes ``"published"`` into
    that file. Publication status lives on the *model-set manifest* that
    ``serializer.publish_model_set`` flips in the backend — a different artifact with a
    different field. The producer therefore refused to emit on every run since the check
    was added, System 2 saw an empty queue for weeks, and the cause was invisible from
    the consuming side.

    Two artifacts, two meanings, and they must not be conflated again:

    * manifest ``status`` — ``published`` / ``withdrawn``. **Is this model set live?**
    * map ``status``      — ``proposed``. Vetting's own field. Never a publication state.

    Reading the backend also closes the staleness hole CLAUDE.md warns about: the local
    map is whatever the last ``vet`` run wrote, which may be newer *or* older than what
    consumers actually downloaded. The bundle behind the pointer is what System 3 and
    System 2 will really see.

    Fail-closed, per the default-safe posture: any of unreachable backend / missing
    pointer / non-published status / missing map artifact returns ``None`` and emits
    nothing.
    """
    try:
        from src.common.storage import build_storage
        from src.serializer.publish_model_set import POINTER_KEY, STATUS_PUBLISHED
    except Exception as e:  # pragma: no cover - import wiring
        logger.error("Cannot load storage backend: %s", e)
        return None

    try:
        storage = build_storage()
        manifest = _with_retry(
            lambda: _get_json(storage, POINTER_KEY), what=f"pointer {POINTER_KEY}"
        )
    except Exception as e:
        logger.error("Failed to read model-set pointer %s: %s", POINTER_KEY, e)
        return None

    if not manifest:
        logger.warning("No model set published at %s — emitting nothing", POINTER_KEY)
        return None

    status = manifest.get("status")
    if status != STATUS_PUBLISHED:
        logger.warning(
            "Model set %s status is '%s', not '%s' — emitting nothing",
            manifest.get("model_set_id"),
            status,
            STATUS_PUBLISHED,
        )
        return None

    artifacts = manifest.get("artifacts") or []
    map_path = next(
        (a.get("path") for a in artifacts if a.get("name") == MAP_ARTIFACT_NAME), None
    )
    if not map_path:
        logger.error(
            "Model set %s carries no %s artifact — emitting nothing",
            manifest.get("model_set_id"),
            MAP_ARTIFACT_NAME,
        )
        return None

    try:
        data = _with_retry(lambda: _get_json(storage, map_path), what=map_path)
    except Exception as e:
        logger.error("Failed to download %s: %s", map_path, e)
        return None

    if not data or not data.get("regimes"):
        logger.warning("Model set map %s has no regimes — emitting nothing", map_path)
        return None

    logger.info(
        "Loaded model set %s (published_at %s) from %s",
        manifest.get("model_set_id"),
        manifest.get("published_at"),
        map_path,
    )
    # Carry the manifest identity so every emitted signal can be traced to the exact
    # model set a consumer downloaded, not to whatever the local map happened to say.
    return {
        **data,
        "model_set_id": manifest.get("model_set_id"),
        "published_at": manifest.get("published_at"),
    }


def _with_retry(fn, what: str, attempts: int = 3, base_delay: float = 1.5):
    """Retry a backend READ a few times before treating the failure as real.

    Fail-closed is right for this module — an unreadable model set must never be guessed
    at. But there is a difference between "the model set is withdrawn" and "one HTTPS
    call to GCS timed out", and before this the two were indistinguishable: a single
    transient blip returned None, the producer recorded ``no_model_set``, and that outcome
    is published to the shared telemetry bucket where it reads as a hard outage. On
    2026-08-28 exactly that happened at 12:19:21Z — the cron run four minutes earlier had
    read the same pointer successfully, and so did the next one.

    Only genuine exceptions are retried. A pointer that is absent, or a manifest whose
    status is ``withdrawn``, is a DELIBERATE state and returns immediately — retrying a
    decision would just delay honouring it.

    Reads only. Nothing here mutates the backend, so a retry cannot double-write.
    """
    last: Optional[BaseException] = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - transient backend faults are the target
            last = e
            if i < attempts - 1:
                delay = base_delay * (2**i)
                logger.warning(
                    "Transient failure reading %s (attempt %d/%d): %s — retrying in %.1fs",
                    what,
                    i + 1,
                    attempts,
                    e,
                    delay,
                )
                time.sleep(delay)
    assert last is not None
    raise last


def _get_json(storage: Any, key: str) -> Optional[Dict[str, Any]]:
    """Download a JSON object from the backend. Returns None when the key is absent."""
    import tempfile

    if hasattr(storage, "exists") and not storage.exists(key):
        return None
    with tempfile.TemporaryDirectory() as tmp:
        local = os.path.join(tmp, "obj.json")
        storage.get_object(key, local)
        with open(local, "r", encoding="utf-8") as handle:
            result: Dict[str, Any] = json.load(handle)
            return result


def _atr_at(frames: Any, granularity: str, bar_ts: Any) -> Optional[float]:
    """ATR(14) on the decision bar, from the same implementation the strategies use.

    Imported from ``src.layer0.data_access.indicators`` deliberately: System 2's
    ``features.py`` hand-rolls ATR and ADX to stay byte-identical to MODEL-003 training,
    and a second implementation of the same indicator (a library, say) is train/serve
    skew reintroduced through the back door.

    Returns ``None`` rather than a fallback when it cannot be computed — a fabricated
    ATR is worse than no signal, because System 3 sizes against it.

    ``indicators.atr`` takes ``(high, low, close, period)`` as three Series, NOT a frame.
    This passed the whole DataFrame as ``high``, so every call raised TypeError, the
    ``except`` below turned it into "ATR unavailable", and the caller refused to emit.
    Since ATR is required for every signal, that made the producer structurally incapable
    of emitting anything: routing, scoring and the strategies were all working, and the
    last step dropped 100% of signals. It never showed up in the cron log because a bar
    only reaches here when a strategy actually fires (~3x/week/pair), and it presented as
    the same "No signals generated" line a quiet market produces.
    """
    from src.layer0.data_access.indicators import atr as calc_atr

    frame = frames.get(granularity) if hasattr(frames, "get") else None
    if frame is None or frame.empty:
        return None

    missing = {"High", "Low", "Close"} - set(frame.columns)
    if missing:
        # A shape problem, not a data problem — surface it loudly rather than letting it
        # read as a quiet market.
        logger.error(
            "ATR frame for %s is missing %s; cannot compute",
            granularity,
            sorted(missing),
        )
        return None

    try:
        series = calc_atr(frame["High"], frame["Low"], frame["Close"], period=14)
        upto = series.loc[series.index <= bar_ts].dropna()
        if upto.empty:
            return None
        value = float(upto.iloc[-1])
        return value if value > 0 else None
    except Exception as e:  # pragma: no cover - defensive
        logger.exception("ATR unavailable for %s at %s: %s", granularity, bar_ts, e)
        return None


def build_signals(
    bars_df: pd.DataFrame, model_set: Dict[str, Any], current_regimes: Dict[str, str]
) -> List[Dict[str, Any]]:
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
                logger.error(
                    "Unknown selection_basis '%s' for strategy %s",
                    selection_basis,
                    strat_meta["strategy_id"],
                )
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
                if (
                    row.get("granularity")
                    and row["granularity"] != meta.primary_granularity
                ):
                    continue  # wrong clock for this strategy

                frames = build_frames(
                    inst,
                    meta.primary_granularity,
                    meta.context_granularities,
                    lookback_years=3,
                )
                if frames is None:
                    logger.warning(
                        "No frames for %s %s", inst, meta.primary_granularity
                    )
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
                        logger.error(
                            "Refusing to emit: undecodable direction %r",
                            intent.direction,
                        )
                        continue
                    if direction_policy not in (None, "both", sig_dir):
                        continue  # the map restricts this strategy to one side

                    # Stop and target come from the strategy's OWN declaration. If either
                    # is absent we refuse rather than infer — inferring exits is what
                    # produced the 2026-08-02 incident.
                    stop = getattr(intent.stop, "price", None) if intent.stop else None
                    if stop is None:
                        logger.error(
                            "Refusing to emit %s %s: no stop price declared",
                            inst,
                            sig_dir,
                        )
                        continue

                    tp_legs = [e for e in (intent.exits or []) if e.price is not None]
                    if not tp_legs:
                        logger.error(
                            "Refusing to emit %s %s: no take-profit price declared",
                            inst,
                            sig_dir,
                        )
                        continue
                    target = tp_legs[0].price

                    entry_price = intent.entry_price
                    if entry_price is None:
                        entry_price = row[
                            "Close"
                        ]  # market entry fills at next open; close is the reference

                    # GATEKEEPER FEATURES ARE ENRICHMENT. THEY MUST NEVER BLOCK EMISSION.
                    #
                    # This block previously had four `continue` paths — missing frames,
                    # empty frames, empty features, any exception — each of which threw
                    # away a fully-formed, contract-valid signal because a *scoring* input
                    # could not be computed. That is the same mistake as the original ATR
                    # bug, one layer up: an optional step deleting the mandatory output.
                    #
                    # It fired immediately in practice. The D1 frame is looked up in
                    # `frames`, but `frames` only contains what the STRATEGY declared, and
                    # xard_ma_cross_daily_open — the cell most likely to fire — declares
                    # no context granularities. So d1_frame was always None and every one
                    # of its signals was refused.
                    #
                    # Now: D1 is loaded separately for features only (never added to the
                    # strategy's own frames, so strategy behaviour cannot change), and any
                    # failure leaves the features absent rather than killing the signal.
                    # The scorer then returns MISSING_FEATURE and the producer emits
                    # unscored, which System 3's contract handles explicitly.
                    atr_value = None
                    adx_value = None
                    regime_structural = None
                    try:
                        from src.gatekeeper.features import build_inference_features

                        decision_frame = frames.get(meta.primary_granularity)
                        d1_frame = build_frames(inst, "D1", (), lookback_years=3).get(
                            "D1"
                        )
                        if decision_frame is not None and d1_frame is not None:
                            df_upto = decision_frame.loc[decision_frame.index <= bar_ts]
                            d1_upto = d1_frame.loc[d1_frame.index <= bar_ts]
                            if not df_upto.empty and not d1_upto.empty:
                                feats = build_inference_features(df_upto, d1_upto)
                                if not feats.empty:
                                    last_feats = feats.iloc[-1]
                                    adx_value = float(last_feats["adx_value"])
                                    regime_structural = str(
                                        last_feats["regime_structural"]
                                    )
                                    candidate_atr = float(last_feats["atr_value"])
                                    if not pd.isna(candidate_atr) and candidate_atr > 0:
                                        atr_value = candidate_atr
                    except Exception as e:
                        logger.warning(
                            "Gatekeeper features unavailable for %s at %s (%s) — "
                            "emitting unscored rather than dropping the signal",
                            inst,
                            bar_ts,
                            e,
                        )

                    # ATR is the one genuinely mandatory field — System 3 sizes against
                    # it, so a fabricated value is worse than no signal. Fall back to the
                    # dedicated helper if the feature builder could not supply it.
                    if atr_value is None:
                        atr_value = _atr_at(frames, meta.primary_granularity, bar_ts)
                    if atr_value is None:
                        logger.error(
                            "Refusing to emit %s %s: no ATR available at %s",
                            inst,
                            sig_dir,
                            bar_ts,
                        )
                        continue

                    sig_key_str = f"{strat_meta['strategy_id']}_{inst}_{meta.primary_granularity}_{bar_ts.isoformat()}"
                    deterministic_id = str(uuid.uuid5(uuid.NAMESPACE_OID, sig_key_str))

                    signals.append(
                        {
                            "signal_id": deterministic_id,
                            "strategy_id": strat_meta["strategy_id"],
                            "strategy_key": strat_meta.get("strategy_key"),
                            "instrument": inst,
                            "granularity": meta.primary_granularity,
                            "signal_time_utc": bar_ts.isoformat(),
                            "direction": sig_dir,
                            "entry": float(entry_price),
                            "stop": float(stop),
                            "target": float(target),
                            "atr": float(atr_value),
                            # The manifest's real identifier, carried by load_model_set().
                            # NOT the map's generated_at_utc, which is a different
                            # artifact's timestamp and cannot identify a published set.
                            "model_set_id": model_set.get("model_set_id"),
                            "regime": regime,
                            "regime_probs": {
                                "trending_up": 0.25,
                                "trending_down": 0.25,
                                "ranging": 0.25,
                                "high_vol": 0.25,
                            },
                            "bundle_version": model_set.get("generated_at_utc"),
                            "selection_basis": selection_basis,
                        }
                    )

                    # Gatekeeper inputs are attached only when they were actually
                    # computed. An ABSENT key is what makes the scorer answer
                    # MISSING_FEATURE ("no input, so no opinion") rather than
                    # NAN_FEATURE ("corrupt"), which is the difference between the
                    # producer emitting the signal unscored and discarding it. Writing
                    # None here would invert that and silently drop the signal.
                    if atr_value is not None:
                        signals[-1]["atr_value"] = float(atr_value)
                    if adx_value is not None:
                        signals[-1]["adx_value"] = float(adx_value)
                    if regime_structural is not None:
                        signals[-1]["regime_structural"] = regime_structural
            except Exception as e:
                logger.error(
                    "Failed to build signal for strategy %s: %s",
                    strat_meta["strategy_id"],
                    e,
                )

    return signals
