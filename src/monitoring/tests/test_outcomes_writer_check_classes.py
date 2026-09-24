import json
from datetime import datetime, timezone
import pytest
from src.monitoring import heartbeat as hb
from src.monitoring.freshness import Status

NOW = datetime(2026, 9, 21, 0, tzinfo=timezone.utc)


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    state_file = tmp_path / "outcomes_writer_state.json"
    monkeypatch.setattr(hb, "OUTCOMES_WRITER_STATE", state_file)
    return state_file


def test_outcomes_writer_unexpected_ghosts_warns(state_file):
    state_file.write_text(
        json.dumps(
            {
                "last_healthy_run_at": "2026-09-20T23:00:00Z",
                "consecutive_faults": 0,
                "rows_written": 100,
                "strategies_ok": 39,
                "strategies_attempted": 46,
                "ghost_rows": {"unexpected": {"1": 10}, "retired": {}},
            }
        )
    )
    res = hb.check_outcomes_writer(NOW)
    assert res.status == Status.WARN
    assert "rows for 1 strategies that should have produced" in res.detail


def test_outcomes_writer_retired_ghosts_ok(state_file):
    state_file.write_text(
        json.dumps(
            {
                "last_healthy_run_at": "2026-09-20T23:00:00Z",
                "consecutive_faults": 0,
                "rows_written": 100,
                "strategies_ok": 39,
                "strategies_attempted": 46,
                "ghost_rows": {
                    "unexpected": {},
                    "retired": {"30": 1059, "46": 112, "49": 2745},
                },
            }
        )
    )
    res = hb.check_outcomes_writer(NOW)
    assert res.status == Status.OK
    assert (
        "3916 rows for 3 retired strategies (reconcile when convenient)" in res.detail
    )


def test_outcomes_writer_mixed_ghosts_warns(state_file):
    state_file.write_text(
        json.dumps(
            {
                "last_healthy_run_at": "2026-09-20T23:00:00Z",
                "consecutive_faults": 0,
                "rows_written": 100,
                "strategies_ok": 39,
                "strategies_attempted": 46,
                "ghost_rows": {"unexpected": {"1": 10}, "retired": {"30": 1059}},
            }
        )
    )
    res = hb.check_outcomes_writer(NOW)
    assert res.status == Status.WARN
    assert "10 rows for 1 strategies that should have produced" in res.detail
    assert "1059 rows for 1 retired strategies" in res.detail
