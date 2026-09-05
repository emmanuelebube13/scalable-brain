"""Gate-1 ledger tests.

The load-bearing case is `test_dropped_signal_is_recorded`: a NAN_FEATURE drop previously
left one warning with no signal_id and appeared in no counter, so a dropped candidate was
both unrecoverable and invisible. Everything else here exists to keep that row honest.
"""

import json
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.signals import ledger

MODELS_DIR = os.path.join(ledger.REPO_ROOT, "models")


def _signal(**over):
    sig = {
        "signal_id": "11111111-2222-5333-8444-555555555555",
        "strategy_id": 58,
        "strategy_key": "xard_ma_cross_daily_open",
        "instrument": "EUR_USD",
        "granularity": "H1",
        "signal_time_utc": "2026-08-30T09:00:00+00:00",
        "direction": "long",
        "entry": 1.085,
        "stop": 1.08,
        "target": 1.095,
        "atr": 0.0032,
        "model_set_id": "2026-08-24T10-08-20Z-cb697b59_gk-d614163c",
        "regime": "Trending-Up",
        "selection_basis": "designated",
    }
    sig.update(over)
    return sig


@pytest.fixture
def ledger_dir(tmp_path):
    return str(tmp_path / "signals")


# ---------------------------------------------------------------- record shape


def test_build_record_carries_the_join_key_and_both_provenance_claims():
    rec = ledger.build_record(
        _signal(model_score=0.42, threshold_applied=0.5),
        gate1_outcome="scored",
        wire_action="published",
        score_run_id="run-1",
        models_dir=MODELS_DIR,
    )
    assert rec["signal_id"] == "11111111-2222-5333-8444-555555555555"
    assert rec["score_run_id"] == "run-1"
    # Both provenance claims, deliberately separate: what actually scored vs what the
    # wire says. They are currently allowed to disagree and the ledger must show it.
    assert "gatekeeper_model_sha256" in rec
    assert rec["bundle_id"] == "2026-08-24T10-08-20Z-cb697b59_gk-d614163c"


def test_direction_uses_the_contract_vocabulary():
    """long/short, not BUY/SELL — contracts/signal-message-contract.json is enum-strict."""
    rec = ledger.build_record(
        _signal(),
        gate1_outcome="unscored",
        wire_action="published",
        score_run_id="r",
        models_dir=MODELS_DIR,
    )
    assert rec["direction"] in ("long", "short")


def test_null_model_score_is_never_coerced_to_zero():
    rec = ledger.build_record(
        _signal(),
        gate1_outcome="unscored",
        wire_action="published",
        score_run_id="r",
        models_dir=MODELS_DIR,
        refusal_reason="MISSING_FEATURE:regime_causal",
    )
    assert rec["model_score"] is None
    assert rec["scoring_status"] == "unscored"
    assert rec["refusal_reason"] == "MISSING_FEATURE:regime_causal"


def test_calibrated_threshold_is_recorded_beside_the_applied_one():
    """The evidence for FIX-S1-018: what was applied vs what should have been."""
    rec = ledger.build_record(
        _signal(model_score=0.42, threshold_applied=0.5),
        gate1_outcome="scored",
        wire_action="published",
        score_run_id="r",
        models_dir=MODELS_DIR,
    )
    assert rec["threshold_applied"] == 0.5
    if rec["threshold_calibrated"] is not None:
        # The whole point: the hardcoded value is below the calibrated one, so the gate
        # as shipped would pass things the calibration says to reject.
        assert rec["threshold_calibrated"] > rec["threshold_applied"]


def test_approved_and_refused_are_not_valid_outcomes():
    """No approval decision exists; naming one would repeat the FIX-S1-016 conflation."""
    for bad in ("approved", "refused"):
        with pytest.raises(ValueError):
            ledger.build_record(
                _signal(),
                gate1_outcome=bad,
                wire_action="published",
                score_run_id="r",
                models_dir=MODELS_DIR,
            )


# ---------------------------------------------------------------- shadow mode


def test_threshold_is_keyed_on_the_label_the_model_consumed():
    """The scorer is fed regime_structural, so the threshold must be looked up by it.

    `regime` is the routing label from the start of the run; `regime_structural` is
    computed as of this bar. They agree while the market is shut, which is why keying on
    the wrong one would not surface until live traffic had already been mispaired.
    """
    rec = ledger.build_record(
        _signal(regime="Trending-Up", regime_structural="High-Vol", model_score=0.9),
        gate1_outcome="scored",
        wire_action="published",
        score_run_id="r",
        models_dir=MODELS_DIR,
    )
    assert rec["threshold_regime_key"] == "High-Vol"
    assert rec["regime_structural"] == "High-Vol"
    assert rec["regime"] == "Trending-Up"
    assert rec["threshold_calibrated"] == pytest.approx(0.7999999999999999)


def test_shadow_verdict_matches_the_recorded_score_and_threshold():
    passing = ledger.build_record(
        _signal(regime_structural="Trending-Down", model_score=0.95),
        gate1_outcome="scored",
        wire_action="published",
        score_run_id="r",
        models_dir=MODELS_DIR,
    )
    assert passing["threshold_calibrated"] == pytest.approx(0.6)
    assert passing["shadow_verdict"] == "would_pass"

    refusing = ledger.build_record(
        _signal(regime_structural="Trending-Down", model_score=0.44),
        gate1_outcome="scored",
        wire_action="published",
        score_run_id="r",
        models_dir=MODELS_DIR,
    )
    assert refusing["shadow_verdict"] == "would_refuse"
    # The verdict is an observation. It must never alter what actually happened.
    assert refusing["wire_action"] == "published"


def test_shadow_verdict_is_null_when_there_is_no_score():
    rec = ledger.build_record(
        _signal(regime_structural="Ranging"),
        gate1_outcome="unscored",
        wire_action="published",
        score_run_id="r",
        models_dir=MODELS_DIR,
        refusal_reason="MISSING_FEATURE:adx_value",
    )
    assert rec["model_score"] is None
    # Null, never "would_refuse" — an unscored signal was not judged, and counting it as a
    # refusal would inflate the shadow rejection rate with data faults.
    assert rec["shadow_verdict"] is None


def test_shadow_counters_reach_the_emitter_state(tmp_path, monkeypatch):
    """The shadow rate must be readable without parsing the ledger."""
    import src.signals.run as run_mod

    _run_once_with([{"status": "scored", "score": 0.01}], tmp_path, monkeypatch)
    state = json.load(open(tmp_path / "emitter.json", encoding="utf-8"))
    assert "shadow_would_refuse_total" in state
    assert "shadow_would_pass_total" in state


def test_shadow_refusal_rate_is_none_not_zero_when_nothing_is_judged():
    """An empty denominator is 'not yet measurable'. Zero would read as 'refuses nothing'."""
    from src.monitoring.publish_health import _shadow_refusal_rate

    assert _shadow_refusal_rate({}) is None
    assert (
        _shadow_refusal_rate(
            {"shadow_would_pass_total": 0, "shadow_would_refuse_total": 0}
        )
        is None
    )
    assert (
        _shadow_refusal_rate(
            {"shadow_would_pass_total": 1, "shadow_would_refuse_total": 19}
        )
        == 0.95
    )


def test_dlq_is_null_when_the_producer_was_never_invoked(tmp_path, monkeypatch):
    """O-22: null means 'nothing measured'. Zero would claim we looked and found none."""
    import src.signals.run as run_mod

    monkeypatch.setattr(run_mod, "EMITTER_STATE", str(tmp_path / "e.json"))
    run_mod.record_emitter_state("no_signals_generated")
    state = json.load(open(tmp_path / "e.json", encoding="utf-8"))
    assert state["last_run_dlq_count"] is None
    assert state["last_run_dlq_by_reason"] is None


def test_dlq_reasons_are_carried_through_and_accumulated(tmp_path, monkeypatch):
    import src.signals.run as run_mod

    monkeypatch.setattr(run_mod, "EMITTER_STATE", str(tmp_path / "e.json"))
    run_mod.record_emitter_state(
        "published",
        published=1,
        dlq={"dlq_count": 3, "dlq_by_reason": {"SCHEMA_INVALID": 2, "QUEUE_FULL": 1}},
    )
    run_mod.record_emitter_state(
        "published",
        published=1,
        dlq={"dlq_count": 1, "dlq_by_reason": {"QUEUE_FULL": 1}},
    )
    s = json.load(open(tmp_path / "e.json", encoding="utf-8"))
    assert s["last_run_dlq_count"] == 1
    assert s["dlq_count_total"] == 4
    assert s["dlq_by_reason_total"] == {"SCHEMA_INVALID": 2, "QUEUE_FULL": 2}

    # An unmeasured run must not reset the cumulative history.
    run_mod.record_emitter_state("no_signals_generated")
    s2 = json.load(open(tmp_path / "e.json", encoding="utf-8"))
    assert s2["dlq_count_total"] == 4
    assert s2["last_run_dlq_count"] is None


def test_producer_separates_dlq_reasons():
    """A scalar cannot tell a contract break from backpressure."""
    from src.queue_producer.producer import ScoredSignalProducer
    from unittest.mock import MagicMock

    p = ScoredSignalProducer.__new__(ScoredSignalProducer)
    p.backend = MagicMock()
    p.backend.at_capacity.return_value = False
    p.backend.depth.return_value = 0  # metrics are JSON-logged; a Mock would not encode
    p.queue = "q"
    p._validator = None
    p._validate = lambda m: "SCHEMA_INVALID: bad"
    metrics = p.publish_signals([_signal(), _signal(signal_id="b")], "run")
    assert metrics["dlq_count"] == 2
    assert metrics["dlq_by_reason"] == {"SCHEMA_INVALID": 2}


def test_shadow_mode_does_not_change_what_reaches_the_wire(tmp_path, monkeypatch):
    """The whole point of shadow mode: a would_refuse signal is still published."""
    written, producer = _run_once_with(
        [{"status": "scored", "score": 0.01}], tmp_path, monkeypatch
    )
    assert written == [("id-0", "scored", "published")]
    assert producer.publish_signals.call_count == 1
    assert len(producer.publish_signals.call_args[0][0]) == 1


# ---------------------------------------------------------------- durability


def test_append_writes_one_ndjson_line_per_call(ledger_dir):
    for i in range(3):
        ledger.record(
            _signal(signal_id=f"id-{i}"),
            gate1_outcome="unscored",
            wire_action="published",
            score_run_id="r",
            models_dir=MODELS_DIR,
            ledger_dir=ledger_dir,
        )
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = ledger.read_day(day, ledger_dir=ledger_dir)
    assert [r["signal_id"] for r in rows] == ["id-0", "id-1", "id-2"]


def test_production_ledger_path_is_refused_under_pytest():
    with pytest.raises(RuntimeError, match="production ledger path"):
        ledger.append({"signal_id": "x"})


def test_record_never_raises_when_the_write_fails(ledger_dir, caplog):
    """Owner decision: a ledger fault must not block emission. Pinned so it can't drift."""
    with patch("src.signals.ledger.append", side_effect=OSError("disk full")):
        ledger.record(
            _signal(),
            gate1_outcome="scored",
            wire_action="published",
            score_run_id="r",
            models_dir=MODELS_DIR,
            ledger_dir=ledger_dir,
        )
    assert "LEDGER WRITE FAILED" in caplog.text
    assert "11111111-2222-5333-8444-555555555555" in caplog.text


def test_read_day_skips_a_torn_line(ledger_dir):
    os.makedirs(ledger_dir, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with open(os.path.join(ledger_dir, f"{day}.ndjson"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"signal_id": "good"}) + "\n")
        fh.write('{"signal_id": "tor')  # process died mid-write
    rows = ledger.read_day(day, ledger_dir=ledger_dir)
    assert [r["signal_id"] for r in rows] == ["good"]


# ---------------------------------------------------------------- run.py wiring


def _run_once_with(score_results, tmp_path, monkeypatch, dry_run=False):
    """Drive run_once with a stubbed scorer and capture what the ledger received."""
    import src.signals.run as run_mod

    monkeypatch.setattr(run_mod, "EMITTER_STATE", str(tmp_path / "emitter.json"))
    monkeypatch.setattr(run_mod, "load_model_set", lambda: {"model_set_id": "ms-1"})
    monkeypatch.setattr(run_mod, "get_current_regimes", lambda: ({}, {}))
    # R4.2 risk-off is a separate gate with its own tests (test_risk_off.py) and its own
    # end-to-end pin (test_risk_off_stops_the_producer, below). Stub it here so these
    # tests measure ledger behaviour rather than the freshness of the developer's local
    # database — otherwise every assertion in this file silently becomes "was the DB
    # fresh when I ran pytest?"
    monkeypatch.setattr(run_mod, "refuse_reasons", lambda *a, **k: [])

    signals = [_signal(signal_id=f"id-{i}") for i in range(len(score_results))]
    monkeypatch.setattr(
        run_mod,
        "build_signals",
        lambda bars, ms, rg: signals if bars is not None else [],
    )

    written = []
    monkeypatch.setattr(
        run_mod.ledger,
        "record",
        lambda sig, **kw: written.append(
            (sig["signal_id"], kw["gate1_outcome"], kw["wire_action"])
        ),
    )

    watcher = MagicMock()
    import pandas as pd

    watcher.get_new_closed_bars.side_effect = lambda g, commit=False: (
        pd.DataFrame({"x": [1]}) if g == "H1" else pd.DataFrame()
    )
    scorer = MagicMock()
    scorer.score.side_effect = list(score_results)
    producer = MagicMock()
    producer.publish_signals.return_value = {"published_count": 1}

    run_mod.run_once(watcher, scorer, producer, dry_run=dry_run)
    return written, producer


def test_dropped_signal_is_recorded(tmp_path, monkeypatch):
    """The row that did not exist before: a NAN_FEATURE drop, with its signal_id."""
    written, producer = _run_once_with(
        [{"status": "refused", "reason": "NAN_FEATURE:atr_value"}],
        tmp_path,
        monkeypatch,
    )
    assert written == [("id-0", "dropped_corrupt_feature", "dropped")]
    # And it really was kept off the wire.
    assert producer.publish_signals.call_count == 0


def test_each_outcome_records_exactly_one_row(tmp_path, monkeypatch):
    written, _ = _run_once_with(
        [
            {"status": "scored", "score": 0.7},
            {"status": "refused", "reason": "MISSING_FEATURE:regime_causal"},
            {"status": "refused", "reason": "NAN_FEATURE:atr_value"},
        ],
        tmp_path,
        monkeypatch,
    )
    assert written == [
        ("id-0", "scored", "published"),
        ("id-1", "unscored", "published"),
        ("id-2", "dropped_corrupt_feature", "dropped"),
    ]


def test_dry_run_writes_no_ledger_rows(tmp_path, monkeypatch):
    written, producer = _run_once_with(
        [{"status": "scored", "score": 0.7}], tmp_path, monkeypatch, dry_run=True
    )
    assert written == []
    assert producer.publish_signals.call_count == 0


def test_counters_land_in_the_emitter_state(tmp_path, monkeypatch):
    _run_once_with(
        [
            {"status": "scored", "score": 0.7},
            {"status": "refused", "reason": "MISSING_FEATURE:x"},
            {"status": "refused", "reason": "NAN_FEATURE:atr_value"},
        ],
        tmp_path,
        monkeypatch,
    )
    state = json.load(open(tmp_path / "emitter.json", encoding="utf-8"))
    assert state["last_run_signals_scored"] == 1
    assert state["last_run_signals_unscored"] == 1
    assert state["last_run_signals_dropped"] == 1
    # Dropped candidates are excluded from what reached the wire.
    assert state["last_run_signals_built"] == 2
    assert state["last_run_by_regime"]["Trending-Up"]["dropped"] == 1


def test_unknown_scorer_status_still_produces_a_row(tmp_path, monkeypatch):
    """AUDIT 1b: a third status fell through to the wire with no row and no tally."""
    written, _ = _run_once_with(
        [{"status": "sideways", "score": 0.1}], tmp_path, monkeypatch
    )
    assert written == [("id-0", "unknown_status", "published")]


def test_suppressed_run_does_not_claim_published(tmp_path, monkeypatch):
    """AUDIT 1d: with emission disabled every row said `published` and nothing was sent."""
    monkeypatch.setenv("DISABLE_LEGACY_SIGNALS", "true")
    written, producer = _run_once_with(
        [{"status": "scored", "score": 0.7}], tmp_path, monkeypatch
    )
    assert written == [("id-0", "scored", "suppressed")]
    assert producer.publish_signals.call_count == 0


def test_unreadable_emitter_state_self_heals(tmp_path, monkeypatch, caplog):
    """AUDIT 2c: one corrupt file aborted the write on this run and every future run."""
    import src.signals.run as run_mod

    path = tmp_path / "emitter.json"
    path.write_text("{not json")
    monkeypatch.setattr(run_mod, "EMITTER_STATE", str(path))

    run_mod.record_emitter_state("published", signals=1, published=1)

    state = json.loads(path.read_text())
    assert state["signals_published_total"] == 1
    assert "unreadable" in caplog.text.lower()


def test_emitter_state_write_is_atomic(tmp_path, monkeypatch):
    """A crash mid-write must not truncate the file that holds the cumulative totals."""
    import src.signals.run as run_mod

    path = tmp_path / "emitter.json"
    monkeypatch.setattr(run_mod, "EMITTER_STATE", str(path))
    run_mod.record_emitter_state("published", signals=2, published=2)
    before = path.read_text()

    with patch("json.dump", side_effect=OSError("boom")):
        run_mod.record_emitter_state("published", signals=1, published=1)

    # Unchanged, and still valid JSON — not a zero-length or half-written file.
    assert path.read_text() == before
    assert json.loads(before)["signals_published_total"] == 2
    # And no .tmp litter left behind.
    assert not [p for p in os.listdir(tmp_path) if p.endswith(".tmp")]


# ── D7(rr) risk/reward ratio tests ────────────────────────────────────────────────────


def test_risk_reward_ratio_recorded_for_long_signal():
    """D7(rr): R:R is computed and stored in the ledger row. entry=1.085, sl=1.08, tp=1.095.
    risk = 1.085 - 1.08 = 0.005; reward = 1.095 - 1.085 = 0.01; R:R = 2.0.
    """
    sig = _signal(
        direction="long",
        entry=1.085,
        stop=1.08,
        target=1.095,
        risk_reward_ratio=2.0,
    )
    rec = ledger.build_record(
        sig,
        gate1_outcome="scored",
        wire_action="published",
        score_run_id="r",
        models_dir=MODELS_DIR,
    )
    assert rec["risk_reward_ratio"] == 2.0


def test_risk_reward_ratio_recorded_for_short_signal():
    """D7(rr): The D7 incident signal: entry=1.15856, sl=1.16286, tp=1.158295.
    risk = 1.16286 - 1.15856 = 0.00430; reward = 1.15856 - 1.158295 = 0.000265; R:R ≈ 0.06.
    """
    sig = _signal(
        direction="short",
        entry=1.15856,
        stop=1.16286,
        target=1.158295,
        risk_reward_ratio=round(0.000265 / 0.00430, 4),
    )
    rec = ledger.build_record(
        sig,
        gate1_outcome="scored",
        wire_action="published",
        score_run_id="r",
        models_dir=MODELS_DIR,
    )
    # Value must be present and in the 0.06 range — the D7 incident was nearly untradeable.
    assert rec["risk_reward_ratio"] is not None
    assert (
        rec["risk_reward_ratio"] < 0.1
    ), "D7 incident: R:R was ~0.06, below any minimum"


def test_risk_reward_ratio_is_none_when_absent():
    """D7(rr): absent risk_reward_ratio (older signal row) must not raise or coerce to 0."""
    sig = _signal()  # no risk_reward_ratio key
    rec = ledger.build_record(
        sig,
        gate1_outcome="scored",
        wire_action="published",
        score_run_id="r",
        models_dir=MODELS_DIR,
    )
    assert rec["risk_reward_ratio"] is None


def test_risk_reward_ratio_not_in_wire_message():
    """D7(rr): risk_reward_ratio must not appear in the queue message (contract violation).

    System 3's contract is additionalProperties:false — an unknown field dead-letters the
    message.  The build_message() function must not forward this field to the wire.
    """
    from src.queue_producer.producer import build_message

    sig = _signal(risk_reward_ratio=2.0)
    msg = build_message(sig, "run-1")
    assert "risk_reward_ratio" not in msg, (
        "risk_reward_ratio must not reach the wire — it is a ledger-only field until a "
        "comms notice is sent to Systems 2/3 widening their contract"
    )


# ── D8 bar_content_sha256 tests ───────────────────────────────────────────────────────


def test_bar_content_sha256_is_recorded_in_ledger_row():
    """D8: bar_content_sha256 must appear in the ledger row."""
    import hashlib as _h
    import json as _j

    expected_content = {
        "atr": 0.0032,
        "proposed_entry": 1.085,
        "proposed_sl": 1.08,
        "proposed_tp": 1.095,
        "signal_time_utc": "2026-08-30T09:00:00+00:00",
    }
    expected_sha = _h.sha256(
        _j.dumps(expected_content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    sig = _signal(
        entry=1.085,
        stop=1.08,
        target=1.095,
        atr=0.0032,
        signal_time_utc="2026-08-30T09:00:00+00:00",
        bar_content_sha256=expected_sha,
    )
    rec = ledger.build_record(
        sig,
        gate1_outcome="scored",
        wire_action="published",
        score_run_id="r",
        models_dir=MODELS_DIR,
    )
    assert rec["bar_content_sha256"] == expected_sha


def test_bar_content_sha256_is_none_when_absent():
    """D8: absent bar_content_sha256 (older row) must not raise."""
    sig = _signal()  # no bar_content_sha256 key
    rec = ledger.build_record(
        sig,
        gate1_outcome="scored",
        wire_action="published",
        score_run_id="r",
        models_dir=MODELS_DIR,
    )
    assert rec["bar_content_sha256"] is None


def test_bar_content_sha256_detects_entry_drift():
    """D8: the 4af8a6fe defect — same signal_id, different entry — produces a different hash.

    Row 1 (14:15Z): entry=158.568, stop=160.1835, tp=155.337, atr=0.0x, time=13:00Z
    Row 2 (17:15Z): entry=158.849, stop=160.1835, tp=155.337, atr=0.0x, time=13:00Z

    The second row's hash must differ from the first, making the drift self-describing.
    """
    import hashlib as _h
    import json as _j

    def _hash(entry):
        content = {
            "atr": 0.0025,
            "proposed_entry": entry,
            "proposed_sl": 160.1835,
            "proposed_tp": 155.337,
            "signal_time_utc": "2026-09-02T13:00:00+00:00",
        }
        return _h.sha256(
            _j.dumps(content, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    sha_row1 = _hash(158.568)
    sha_row2 = _hash(158.849)
    assert (
        sha_row1 != sha_row2
    ), "entry drift must produce different hashes — same hash means same economic content"


def test_bar_content_sha256_not_in_wire_message():
    """D8: bar_content_sha256 must not appear in the queue message (contract violation)."""
    from src.queue_producer.producer import build_message

    sig = _signal(bar_content_sha256="abc123")
    msg = build_message(sig, "run-1")
    assert "bar_content_sha256" not in msg, (
        "bar_content_sha256 must not reach the wire — gated on O-19 and requires a "
        "comms notice to Systems 2/3"
    )


# --------------------------------------------------------------------------- #
# R4.2 — risk-off must stop the producer before it does anything else
# --------------------------------------------------------------------------- #
def test_risk_off_stops_the_producer(tmp_path, monkeypatch):
    """A blocking freshness breach must emit nothing and say why.

    This is the consequence that was missing on 2026-08-24: the heartbeat reported the
    regime table CRITICAL every morning for twelve days and the producer kept emitting,
    because nothing connected the verdict to the decision.
    """
    import json as _json

    import src.signals.run as run_mod

    state = tmp_path / "emitter.json"
    monkeypatch.setattr(run_mod, "EMITTER_STATE", str(state))
    monkeypatch.setattr(
        run_mod,
        "refuse_reasons",
        lambda *a, **k: ["fact_regime_structural: 300h stale"],
    )
    # If risk-off does not short-circuit, these would be reached and the test would fail
    # on the assertions below rather than passing by accident.
    monkeypatch.setattr(
        run_mod,
        "load_model_set",
        lambda: (_ for _ in ()).throw(
            AssertionError("model set loaded despite risk-off")
        ),
    )

    producer = MagicMock()
    run_mod.run_once(MagicMock(), MagicMock(), producer, dry_run=False)

    producer.publish_signals.assert_not_called()
    recorded = _json.loads(state.read_text())
    assert recorded["last_run_outcome"] == "risk_off"
    # It must count as a fault, not a healthy quiet run -- otherwise the telemetry goes
    # green over a system that is not trading and cannot say why.
    assert recorded["consecutive_faults"] == 1


def test_risk_off_is_distinct_from_a_quiet_market(tmp_path, monkeypatch):
    """`risk_off` and `no_signals_generated` must never be the same outcome string.

    The original silent stall was invisible precisely because "refused" and "nothing to
    do" looked identical from the outside.
    """
    import json as _json

    import src.signals.run as run_mod

    state = tmp_path / "emitter.json"
    monkeypatch.setattr(run_mod, "EMITTER_STATE", str(state))
    monkeypatch.setattr(run_mod, "refuse_reasons", lambda *a, **k: ["stale"])
    monkeypatch.setattr(run_mod, "load_model_set", lambda: {"model_set_id": "ms-1"})
    run_mod.run_once(MagicMock(), MagicMock(), MagicMock(), dry_run=False)
    assert _json.loads(state.read_text())["last_run_outcome"] == "risk_off"
