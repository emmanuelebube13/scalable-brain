"""Emit ONE rehearsal (`drill: true`) ScoredSignal onto the live signal topic.

A drill is a message that traverses the entire downstream path — System 3's gate layers,
sizing, System 2's order construction, its §7.2 last-line validation and its backup
guard — and is dropped by System 2 immediately *before* the broker submit. System 2
verified that short-circuit end to end on 2026-08-29 (`S2-REPLY-2026-08-29`) and stated
two properties this tool depends on: a drill is not a bypass (it still fails any layer a
real order would fail), and it does not consume the idempotency key (a real order with
the same key may legitimately follow).

WHY A SEPARATE ENTRY POINT

`src.signals.run` emits only when a strategy actually fires on a newly closed bar, which
is roughly three times a week per pair. A rehearsal that can only be attempted when the
market happens to produce one is not a rehearsal. This builds a message from the SAME
real parts — the published model set, a real cell of the live map, real prices and a real
ATR(14) — and sets one field.

WHAT IS SYNTHETIC, STATED PLAINLY: no strategy generated this signal. Entry is the last
closed bar's close and the stop/target are ATR multiples, so the *levels* are plausible
rather than decided. Everything else — model_set_id, strategy_id, selection_basis,
gate_failures, regime, granularity, ATR — is read from the live artifacts, so the message
exercises the same routing and sizing arithmetic a real signal would.

    python -m src.queue_producer.emit_drill                    # dry run, prints the message
    python -m src.queue_producer.emit_drill --publish          # actually sends it

Dry run is the default because this publishes to a topic that ends at a broker.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from typing import Any, Dict, Optional

from src.queue_producer.producer import (
    ScoredSignalProducer,
    _load_validator,
    build_message,
)

logger = logging.getLogger("system1.queue_producer.drill")

# Stop and target as ATR multiples. They exist so the message carries a coherent
# risk shape for System 3 to size against; they are not a strategy's exit policy and
# must not be read as one.
SL_ATR_MULT = 1.5
TP_ATR_MULT = 3.0


def _pick_cell(
    model_set: Dict[str, Any], regime: Optional[str], strategy: Optional[str]
) -> tuple:
    """Return (regime, cell) from the live map, or raise with the reason.

    Prefers an explicitly named strategy so a drill can rehearse a specific cell — the
    one a real signal would most likely come from, rather than whichever happens to sort
    first.
    """
    regimes = model_set.get("regimes") or {}
    if not regimes:
        raise RuntimeError("live model set carries no regimes — nothing to rehearse")

    candidates = []
    for reg, cells in regimes.items():
        if regime and reg != regime:
            continue
        for cell in cells or []:
            candidates.append((reg, cell))

    if regime and not candidates:
        raise RuntimeError(
            f"regime {regime!r} has no cells in the live map "
            f"(have: {', '.join(sorted(regimes))})"
        )

    if strategy:
        matched = [
            (r, c)
            for r, c in candidates
            if str(c.get("strategy_key")) == strategy
            or str(c.get("strategy_id")) == strategy
        ]
        if not matched:
            raise RuntimeError(f"strategy {strategy!r} is not in the live map")
        candidates = matched

    return candidates[0]


def build_drill_signal(
    pair: Optional[str] = None,
    regime: Optional[str] = None,
    strategy: Optional[str] = None,
    direction: str = "long",
) -> Dict[str, Any]:
    """Assemble the drill's *signal* dict (pre-message) from live artifacts."""
    from src.signals.build import load_model_set
    from src.registry import catalog
    from src.vetting.vet import INTEGRITY_DISQUALIFIED
    from src.layer0.strategies.research_data import load_ohlcv_readonly
    from src.layer0.data_access.indicators import atr as calc_atr

    model_set = load_model_set()
    if not model_set:
        # Same fail-closed posture as the producer: no published set means no message,
        # and a drill built against a withdrawn or unreadable set would rehearse a
        # provenance claim that is not true.
        raise RuntimeError(
            "no published model set — refusing to build a drill without a real bundle_id"
        )

    reg, cell = _pick_cell(model_set, regime, strategy)
    strategy_id = int(cell["strategy_id"])

    # The same last line of defence build_signals() applies. A drill is not a real order,
    # but it is a real message on a shared topic, and a contaminated strategy id has no
    # business appearing on it even in a rehearsal.
    if strategy_id in INTEGRITY_DISQUALIFIED:
        raise RuntimeError(
            f"strategy {strategy_id} is INTEGRITY_DISQUALIFIED: "
            f"{INTEGRITY_DISQUALIFIED[strategy_id]}"
        )

    record = catalog.by_id(strategy_id)
    meta = catalog.instantiate(record).metadata
    granularity = meta.primary_granularity
    if pair and pair not in meta.pairs:
        raise RuntimeError(
            f"strategy {strategy_id} does not trade {pair} (declares: {', '.join(meta.pairs)})"
        )
    instrument = pair or meta.pairs[0]

    frame = load_ohlcv_readonly(instrument, granularity, lookback_years=1)
    if frame is None or frame.empty:
        raise RuntimeError(f"no {granularity} prices for {instrument}")

    # ATR from the implementation the strategies and MODEL-003 use — never a second
    # implementation, which is train/serve skew through the back door (see _atr_at in
    # src/signals/build.py).
    atr_series = calc_atr(
        frame["High"], frame["Low"], frame["Close"], period=14
    ).dropna()
    if atr_series.empty:
        raise RuntimeError(f"ATR unavailable for {instrument} {granularity}")
    atr_value = float(atr_series.iloc[-1])
    if atr_value <= 0:
        raise RuntimeError(f"non-positive ATR for {instrument} {granularity}")

    entry = float(frame["Close"].iloc[-1])
    bar_ts = frame.index[-1]
    if direction == "long":
        stop, target = entry - SL_ATR_MULT * atr_value, entry + TP_ATR_MULT * atr_value
    else:
        stop, target = entry + SL_ATR_MULT * atr_value, entry - TP_ATR_MULT * atr_value

    return {
        # A fresh uuid4, NOT the deterministic uuid5 a real signal derives from
        # (strategy, instrument, granularity, bar). A drill must never collide with the
        # identity of the real signal for the same bar.
        "signal_id": str(uuid.uuid4()),
        "drill": True,
        "strategy_id": strategy_id,
        "strategy_key": cell.get("strategy_key"),
        "instrument": instrument,
        "granularity": granularity,
        "signal_time_utc": bar_ts.isoformat(),
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "target": target,
        "atr": atr_value,
        "model_set_id": model_set.get("model_set_id"),
        "regime": reg,
        "selection_basis": cell.get("selection_basis"),
        "gate_failures": cell.get("gate_failures"),
        # Unscored on purpose. The gatekeeper scores a strategy's own signal; there is no
        # signal here to score, and a fabricated probability would be the one number in
        # this message that lies. NULL is "unscored", which System 3 branches on at
        # Layer P — the rehearsal exercises that branch honestly.
        "model_score": None,
        "threshold_applied": None,
    }


def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--pair", help="instrument; default = the strategy's first declared pair"
    )
    ap.add_argument(
        "--regime", help="map regime to rehearse; default = first with a cell"
    )
    ap.add_argument("--strategy", help="strategy_key or strategy_id from the live map")
    ap.add_argument("--direction", choices=["long", "short"], default="long")
    ap.add_argument(
        "--publish",
        action="store_true",
        help="actually send it. Without this the message is only built and printed.",
    )
    args = ap.parse_args(argv)

    try:
        signal = build_drill_signal(
            pair=args.pair,
            regime=args.regime,
            strategy=args.strategy,
            direction=args.direction,
        )
    except Exception as e:  # noqa: BLE001 — every failure here is a refusal to emit
        logger.error("Refusing to build a drill: %s", e)
        return 1

    score_run_id = f"drill-{uuid.uuid4()}"
    message = build_message(signal, score_run_id)

    # THE check this tool exists to make. Publishing `drill: true` while stamping is off
    # strips the flag, and the message that arrives is indistinguishable from a real
    # order — the exact failure the whole three-component change was built to prevent.
    # Refuse rather than send, in dry run too, so the dry run is a real rehearsal of the
    # publish decision.
    if message.get("drill") is not True:
        logger.error(
            "REFUSING to emit: the built message carries no `drill: true` "
            "(EMIT_PROVENANCE_FIELDS is off). This would arrive as a REAL order."
        )
        return 2

    # Validate here as well as in publish_signals, so the dry run answers the question it
    # is asked — "would this be accepted?" — rather than only showing what would be sent.
    # Against OUR copy of the contract: the consumers validate against their own deployed
    # copies, and assuming the two agree is what caused bb51a35.
    try:
        _load_validator()(message)
    except Exception as e:  # noqa: BLE001 — jsonschema ValidationError
        logger.error("Drill message fails the ScoredSignal contract: %s", e)
        return 4

    print(json.dumps(message, indent=2, sort_keys=True))

    if not args.publish:
        logger.info("Dry run — nothing published. Re-run with --publish to send it.")
        return 0

    producer = ScoredSignalProducer()
    metrics = producer.publish_signals([signal], score_run_id=score_run_id)
    logger.info(
        "DRILL published to %s: %s", producer.queue, json.dumps(metrics, sort_keys=True)
    )
    # published_count is 0 when the backend deduped or dead-lettered it; either way no
    # rehearsal reached the consumer, so it is a failure of this run, not a quiet success.
    return 0 if metrics.get("published_count") == 1 else 3


if __name__ == "__main__":
    sys.exit(main())
