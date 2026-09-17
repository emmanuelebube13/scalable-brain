"""Package-wide isolation: no test may touch the LIVE D9 setup-dedup state.

Same rule as ``isolated_emitter_state`` in test_producer.py, made autouse because
``run_once`` reads and writes the dedup state on every non-dry invocation — a test
that publishes a signal would otherwise poison ``results/state/published_setups.json``
and every later test (and the next REAL producer run) would see its fixtures as
already-published setups. That exact cross-contamination produced 10 spurious
failures on 2026-09-16 before this fixture existed.
"""

import pytest

from src.signals import setup_dedup


@pytest.fixture(autouse=True)
def isolated_setup_dedup_state(tmp_path, monkeypatch):
    monkeypatch.setattr(
        setup_dedup, "STATE_PATH", str(tmp_path / "published_setups.json")
    )
