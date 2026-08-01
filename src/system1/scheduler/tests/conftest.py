"""Scheduler test guards.

The orchestrator refreshes the S1-EXPORT-002 analytics bundle after a successful
promote. Left un-stubbed that call ``build_bundle()``s against the REAL staging
directory (``results/state/analytics_staging/`` — a *tracked* path) off the live
database, and then attempts a real upload through ``build_storage()``.

Any scheduler test that reaches the promote branch therefore used to rewrite tracked
repo files as a side effect, and was one missing ``STORAGE_PROVIDER`` monkeypatch away
from publishing to the production bucket. The autouse fixture below makes the safe
behaviour the default for every test in this package, present and future.
"""

from __future__ import annotations

import pytest

from src.system1.scheduler import orchestrator as O


@pytest.fixture(autouse=True)
def _no_real_analytics_publish(monkeypatch):
    """Never touch the real analytics staging dir or storage backend from a test."""
    monkeypatch.setattr(
        O, "_default_analytics", lambda: {"version": "test-analytics-stub"}
    )
