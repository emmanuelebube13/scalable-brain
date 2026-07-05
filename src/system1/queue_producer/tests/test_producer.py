"""MODEL-008 tests: contract, idempotency, backpressure, DLQ, determinism, metrics."""
from __future__ import annotations

import json

from src.common.queue.local_durable import LocalDurableBackend
from src.system1.queue_producer import producer as P


def make_signal(i, score=0.83, threshold=0.72, gran="H1", regime="Trending-Up"):
    return {
        "signal_id": f"sig-{i}",
        "instrument": "EUR_USD",
        "granularity": gran,
        "signal_time_utc": "2026-06-23T14:00:00Z",
        "direction": "long",
        "model_score": score,
        "threshold_applied": threshold,
        "regime": regime,
        "regime_probs": {"trending_up": 0.72, "trending_down": 0.10, "ranging": 0.08, "high_vol": 0.10},
        "bundle_version": "2026-06-23T00-00-00Z",
    }


def _backend(tmp_path, max_size=100000):
    return LocalDurableBackend(root=str(tmp_path / "q"), max_queue_size=max_size, dlq_name="scored_signal_dlq")


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
    required = {
        "schema_version", "message_id", "signal_id", "instrument", "granularity",
        "signal_time_utc", "direction", "model_score", "approved", "threshold_applied",
        "regime", "regime_probs", "bundle_version", "produced_at_utc",
    }
    for msg in msgs:
        assert required.issubset(msg.keys())
        assert msg["approved"] is True  # 0.83 >= 0.72


def test_idempotency_dedupes(tmp_path):
    b = _backend(tmp_path)
    prod = P.ScoredSignalProducer(backend=b, queue_name="scored_signal_queue")
    sigs = [make_signal(1)]
    prod.publish_signals(sigs, score_run_id="run-1")
    m2 = prod.publish_signals(sigs, score_run_id="run-1")  # same signal+run → dedupe
    assert b.depth("scored_signal_queue") == 1
    assert m2["published_count"] == 0 and m2["deduped_count"] == 1
    # stub consumer dedupe by message_id
    seen, delivered = set(), 0
    for msg in _read_queue(b, "scored_signal_queue"):
        if msg["message_id"] not in seen:
            seen.add(msg["message_id"]); delivered += 1
    assert delivered == 1


def test_backpressure_caps_depth(tmp_path):
    b = _backend(tmp_path, max_size=5)
    prod = P.ScoredSignalProducer(
        backend=b, queue_name="scored_signal_queue",
        backpressure_timeout_ms=1, backpressure_max_retries=2,
    )
    m = prod.publish_signals((make_signal(i) for i in range(10)), score_run_id="run-1")
    assert b.depth("scored_signal_queue") <= 5            # never exceeds cap
    assert m["backpressure_events"] > 0
    assert m["published_count"] + m["dlq_count"] == 10     # nothing silently dropped
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
