"""MODEL-008 tests: contract, idempotency, backpressure, DLQ, determinism, metrics."""

from __future__ import annotations

import json

from src.common.queue.local_durable import LocalDurableBackend
from src.queue_producer import producer as P


def make_signal(i, score=0.83, threshold=0.72, gran="H1", regime="Trending-Up"):
    return {
        "signal_id": f"sig-{i}",
        "pair": "EUR_USD",
        "granularity": gran,
        "signal_time_utc": "2026-06-23T14:00:00Z",
        "direction": "long",
        "model_score": score,
        "threshold_applied": threshold,
        "regime": regime,
        "regime_probs": {
            "trending_up": 0.72,
            "trending_down": 0.10,
            "ranging": 0.08,
            "high_vol": 0.10,
        },
        "producer": "system1",
        "model_set_id": "2026-06-23T00-00-00Z",
        "reference_vector_ok": True,
        "proposed_entry": 1.05,
        "proposed_sl": 1.04,
        "proposed_tp": 1.06,
        "atr": 0.0015,
        "strategy_id": "10",
        "scoring_status": "scored",
    }


def _backend(tmp_path, max_size=100000):
    return LocalDurableBackend(
        root=str(tmp_path / "q"), max_queue_size=max_size, dlq_name="scored_signal_dlq"
    )


def _read_queue(backend, queue):
    p = backend._log(queue)
    with open(p, encoding="utf-8") as fh:
        return [json.loads(line)["message"] for line in fh if line.strip()]


def test_message_id_deterministic():
    a = P.build_message_id("sig-1", "run-1")
    b = P.build_message_id("sig-1", "run-1")
    c = P.build_message_id("sig-1", "run-2")
    assert a == b and a != c


def test_publish_and_schema(tmp_path):
    b = _backend(tmp_path)
    prod = P.ScoredSignalProducer(backend=b, queue_name="scored_signal_queue")
    m = prod.publish_signals((make_signal(i) for i in range(100)), score_run_id="run-1")
    assert m["published_count"] == 100 and m["dlq_count"] == 0
    msgs = _read_queue(b, "scored_signal_queue")
    # System 3's deployed ScoredSignal v1 is additionalProperties: false, so this
    # asserts BOTH directions: every required field present, and nothing extra. The
    # second half is the one that matters -- a stray field dead-letters the message.
    contract = json.load(open(P.CONTRACT_PATH))
    required = set(contract["required"])
    allowed = set(contract["properties"])
    for msg in msgs:
        assert required.issubset(msg.keys())
        assert not (set(msg) - allowed), f"fields S3 would DLQ: {set(msg) - allowed}"
        assert msg["schema_version"] == "1"


def test_idempotency_dedupes(tmp_path):
    b = _backend(tmp_path)
    prod = P.ScoredSignalProducer(backend=b, queue_name="scored_signal_queue")
    sigs = [make_signal(1)]
    prod.publish_signals(sigs, score_run_id="run-1")
    m2 = prod.publish_signals(sigs, score_run_id="run-1")  # same signal+run → dedupe
    assert b.depth("scored_signal_queue") == 1
    assert m2["published_count"] == 0 and m2["deduped_count"] == 1
    # Dedupe is by signal_id: the idempotency key travels out-of-band as the publish
    # key, not in the payload, because System 3's contract has no message_id field.
    seen, delivered = set(), 0
    for msg in _read_queue(b, "scored_signal_queue"):
        if msg["signal_id"] not in seen:
            seen.add(msg["signal_id"])
            delivered += 1
    assert delivered == 1


def test_backpressure_caps_depth(tmp_path):
    b = _backend(tmp_path, max_size=5)
    prod = P.ScoredSignalProducer(
        backend=b,
        queue_name="scored_signal_queue",
        backpressure_timeout_ms=1,
        backpressure_max_retries=2,
    )
    m = prod.publish_signals((make_signal(i) for i in range(10)), score_run_id="run-1")
    assert b.depth("scored_signal_queue") <= 5  # never exceeds cap
    assert m["backpressure_events"] > 0
    assert m["published_count"] + m["dlq_count"] == 10  # nothing silently dropped
    assert b.depth("scored_signal_dlq") == m["dlq_count"]  # overflow went to DLQ


def test_dlq_on_invalid_message(tmp_path):
    b = _backend(tmp_path)
    prod = P.ScoredSignalProducer(backend=b, queue_name="scored_signal_queue")
    bad = make_signal(1, regime="Sideways")  # invalid regime enum
    m = prod.publish_signals([bad], score_run_id="run-1")
    assert m["dlq_count"] == 1 and m["published_count"] == 0
    dlq = _read_queue(b, "scored_signal_dlq")
    assert dlq and "dlq_reason" in dlq[0]


def test_granularity_preserved(tmp_path):
    b = _backend(tmp_path)
    prod = P.ScoredSignalProducer(backend=b, queue_name="scored_signal_queue")
    prod.publish_signals([make_signal(1, gran="H4")], score_run_id="run-1")
    assert _read_queue(b, "scored_signal_queue")[0]["granularity"] == "H4"


def test_metrics_present(tmp_path):
    b = _backend(tmp_path)
    prod = P.ScoredSignalProducer(backend=b, queue_name="scored_signal_queue")
    m = prod.publish_signals([make_signal(1)], score_run_id="run-1")
    for k in ("published_count", "dlq_count", "backpressure_events", "queue_depth"):
        assert k in m


# ── Provenance stamping: producer / bundle_id / drill ────────────────────────────
#
# Stamping shipped on 2026-08-28 with no tests and was disabled hours later (bb51a35)
# because the consumer's deployed schema rejected the fields. It is ON by default since
# 2026-08-29, once Systems 2 and 3 deployed both halves — a schema that accepts them and
# a short-circuit before the broker submit. These pin the two properties System 2 stated
# it depends on: the flag is present on EVERY message, and `true` means rehearsal.


def test_provenance_stamped_by_default(monkeypatch):
    monkeypatch.delenv("EMIT_PROVENANCE_FIELDS", raising=False)
    msg = P.build_message(make_signal(1), "run-1")
    assert msg["producer"] == "system-1"
    assert msg["bundle_id"] == "2026-06-23T00-00-00Z"
    # Present-and-False, not absent. System 2 reads absent as "real order"; that reading
    # is only unambiguous while we stamp the flag on real messages too.
    assert msg["drill"] is False


def test_drill_flag_is_carried(monkeypatch):
    monkeypatch.delenv("EMIT_PROVENANCE_FIELDS", raising=False)
    sig = make_signal(1)
    sig["drill"] = True
    assert P.build_message(sig, "run-1")["drill"] is True


def test_kill_switch_removes_all_three(monkeypatch):
    for value in ("false", "FALSE", "0", "off", "no"):
        monkeypatch.setenv("EMIT_PROVENANCE_FIELDS", value)
        msg = P.build_message(make_signal(1), "run-1")
        assert not ({"producer", "bundle_id", "drill"} & set(msg)), value


def test_kill_switch_drops_drill_true_silently(monkeypatch):
    """The hazard the drill emitter refuses on, pinned here.

    With stamping off, a signal marked as a rehearsal produces a message that is
    byte-identical to a real one. Nothing downstream can tell them apart, which is why
    ``emit_drill`` re-reads the built message and refuses rather than trusting its input.
    """
    monkeypatch.setenv("EMIT_PROVENANCE_FIELDS", "false")
    sig = make_signal(1)
    sig["drill"] = True
    assert "drill" not in P.build_message(sig, "run-1")


def test_bundle_id_omitted_when_unknown(monkeypatch):
    """Absent, never empty. A blank bundle_id fails minLength and DLQs the message."""
    monkeypatch.delenv("EMIT_PROVENANCE_FIELDS", raising=False)
    sig = make_signal(1)
    sig["model_set_id"] = None
    msg = P.build_message(sig, "run-1")
    assert "bundle_id" not in msg and msg["producer"] == "system-1"


def test_stamped_message_reaches_the_wire(tmp_path, monkeypatch):
    monkeypatch.delenv("EMIT_PROVENANCE_FIELDS", raising=False)
    b = _backend(tmp_path)
    prod = P.ScoredSignalProducer(backend=b, queue_name="scored_signal_queue")
    m = prod.publish_signals([make_signal(1)], score_run_id="run-1")
    assert m["published_count"] == 1 and m["dlq_count"] == 0
    wire = _read_queue(b, "scored_signal_queue")[0]
    assert {"producer", "bundle_id", "drill"}.issubset(wire)


def test_widening_did_not_loosen_the_contract():
    """Three named fields were added; unknown ones must still be rejected.

    Both consumers verified this against their own deployed copy on 2026-08-29. If our
    copy ever drifts to permissive, a producer typo stops being a loud rejection here and
    becomes a silent one at their relay.
    """
    contract = json.load(open(P.CONTRACT_PATH))
    assert contract["additionalProperties"] is False
    validator = P._load_validator()
    msg = P.build_message(make_signal(1), "run-1")
    validator(msg)  # valid as built
    import pytest

    with pytest.raises(Exception):
        validator({**msg, "producer_id": "system-1"})  # plausible typo, still rejected
