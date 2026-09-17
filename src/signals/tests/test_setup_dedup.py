"""D9 setup dedup — the 15-copies incident must not be reproducible.

Evidence base: 2026-09-14T09:00Z → 2026-09-16T17:00Z, strategy 43 published one EUR_USD
H4 buy-stop 15 times with byte-identical entries and fresh signal_ids. These tests pin
the suppression semantics: same economic content suppresses, changed stop/target on the
same entry still suppresses (same trade idea), a cold key re-publishes, weekends cannot
expire a setup, and a corrupt state file fails toward publishing.
"""

import json
from datetime import datetime, timedelta, timezone

from src.signals import setup_dedup


def _sig(**over):
    base = {
        "signal_id": "sig-1",
        "strategy_id": 43,
        "instrument": "EUR_USD",
        "granularity": "H4",
        "direction": "long",
        "entry": 1.16564,
        "stop": 1.15873,
        "target": 1.17255,
    }
    base.update(over)
    return base


# A Tuesday, well inside market hours.
NOW = datetime(2026, 9, 15, 13, 0, tzinfo=timezone.utc)


def test_first_emission_is_not_a_duplicate():
    assert setup_dedup.duplicate_of({}, _sig(), NOW) is None


def test_rearm_next_bar_is_suppressed():
    state = {}
    setup_dedup.note_published(state, _sig(), NOW)
    later = NOW + timedelta(hours=4)  # the next H4 close
    assert setup_dedup.duplicate_of(state, _sig(signal_id="sig-2"), later) is not None


def test_changed_stop_and_target_on_same_entry_still_suppresses():
    # A revised stop on the same pending level is the same trade idea — this is the
    # second (sl, tp) pair observed in the incident, which also must not re-publish.
    state = {}
    setup_dedup.note_published(state, _sig(), NOW)
    revised = _sig(signal_id="sig-2", stop=1.15181, target=1.17947)
    assert (
        setup_dedup.duplicate_of(state, revised, NOW + timedelta(hours=4)) is not None
    )


def test_different_entry_is_a_new_setup():
    state = {}
    setup_dedup.note_published(state, _sig(), NOW)
    other = _sig(signal_id="sig-2", entry=1.17)
    assert setup_dedup.duplicate_of(state, other, NOW + timedelta(hours=4)) is None


def test_continuous_rearm_never_expires():
    # 15 re-arms at 4h intervals, each refreshing last_seen_at: every one suppressed.
    state = {}
    setup_dedup.note_published(state, _sig(), NOW)
    ts = NOW
    for i in range(15):
        ts += timedelta(hours=4)
        dup = setup_dedup.duplicate_of(state, _sig(signal_id=f"sig-{i}"), ts)
        assert dup is not None, f"re-arm {i} at {ts} escaped suppression"
        setup_dedup.note_suppressed(state, _sig(), ts)
    key = setup_dedup.setup_key(_sig())
    assert state[key]["suppressed_count"] == 15


def test_cold_key_republished():
    state = {}
    setup_dedup.note_published(state, _sig(), NOW)
    # 13 open-market hours later > the 12h H4 window: the setup went away and came back.
    later = NOW + timedelta(hours=13)
    assert setup_dedup.duplicate_of(state, _sig(signal_id="sig-2"), later) is None


def test_weekend_does_not_expire_a_setup():
    # Published at the Friday 20:00Z close; re-armed at the Sunday 21:00Z open. That is
    # 49 wall-clock hours but ~1 open-market hour — the weekend must not launder a
    # re-arm into a "new" setup. 2026-09-18 is a Friday.
    friday = datetime(2026, 9, 18, 20, 0, tzinfo=timezone.utc)
    sunday_open = datetime(2026, 9, 20, 21, 30, tzinfo=timezone.utc)
    state = {}
    setup_dedup.note_published(state, _sig(), friday)
    assert (
        setup_dedup.duplicate_of(state, _sig(signal_id="sig-2"), sunday_open)
        is not None
    )


def test_corrupt_state_fails_toward_publishing(tmp_path):
    p = tmp_path / "published_setups.json"
    p.write_text("{not json")
    assert setup_dedup.load_state(str(p)) == {}
    # A malformed prior record is likewise not a duplicate.
    bad = {setup_dedup.setup_key(_sig()): {"last_seen_at": "not-a-timestamp"}}
    assert setup_dedup.duplicate_of(bad, _sig(), NOW) is None
    # tz-naive timestamps are refused, not assumed UTC.
    naive = {setup_dedup.setup_key(_sig()): {"last_seen_at": "2026-09-15T12:00:00"}}
    assert setup_dedup.duplicate_of(naive, _sig(), NOW) is None


def test_save_and_load_round_trip(tmp_path):
    p = tmp_path / "published_setups.json"
    state = {}
    setup_dedup.note_published(state, _sig(), NOW)
    setup_dedup.save_state(state, str(p))
    loaded = setup_dedup.load_state(str(p))
    assert (
        setup_dedup.duplicate_of(loaded, _sig(), NOW + timedelta(hours=1)) is not None
    )
    # The write is atomic: no temp files left behind.
    assert [f.name for f in tmp_path.iterdir()] == ["published_setups.json"]


def test_prune_drops_cold_keys_only():
    state = {}
    setup_dedup.note_published(state, _sig(), NOW - timedelta(days=45))
    setup_dedup.note_published(state, _sig(entry=1.2), NOW - timedelta(days=1))
    setup_dedup.prune(state, NOW)
    assert len(state) == 1
    assert setup_dedup.setup_key(_sig(entry=1.2)) in state


def test_ledger_accepts_suppressed_duplicate_action():
    from src.signals import ledger

    assert "suppressed_duplicate" in ledger.WIRE_ACTIONS


def test_reconcile_does_not_count_suppressed_duplicate_as_published():
    from src.signals import reconcile

    field, values = reconcile._LEDGER_RULES["signals_published_total"]
    assert field == "wire_action"
    assert "suppressed_duplicate" not in values
