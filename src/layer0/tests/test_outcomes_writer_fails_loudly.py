"""The outcomes writer must refuse to run when its strategy imports fail.

Companion to ``test_strategies_package.py``. That module guards the imports
themselves; this one guards the *behaviour on failure* — the writer must never
degrade to "run with whatever strategies happened to load", because a partial
roster silently produces a partial ``fact_trade_outcomes``, which is
indistinguishable downstream from a genuinely thin trading period.

See ``task/2026-W31/T1-reconnect-feedback-loop.md``.
"""

from __future__ import annotations

import inspect

import pytest

import src.layer0.persist_trade_outcomes as writer


def test_run_propagates_strategy_import_failure(monkeypatch):
    """If the strategy roster can't be built, run() must raise, not continue."""

    def boom():
        raise ImportError("simulated strategy packaging break")

    monkeypatch.setattr(writer, "get_all_strategies", boom)

    with pytest.raises(ImportError, match="simulated strategy packaging break"):
        writer.run(granularities=["H1"], lookback_years=1)


def test_run_does_not_wrap_strategy_loading_in_a_bare_except():
    """Guard the source shape: no swallowing around the roster construction.

    A future `try: strategies = get_all_strategies() except Exception: []` would
    keep the pipeline green while writing an empty outcomes table — exactly the
    silent-failure mode this task exists to eliminate.
    """
    source = inspect.getsource(writer.run)
    call_line = next(
        (ln for ln in source.splitlines() if "get_all_strategies()" in ln), None
    )
    assert call_line is not None, "get_all_strategies() call disappeared from run()"

    lines = source.splitlines()
    idx = lines.index(call_line)
    preceding = "\n".join(lines[max(0, idx - 6) : idx])
    assert "try:" not in preceding, (
        "get_all_strategies() appears to be inside a try block in run(); a "
        "swallowed failure here writes an empty/partial fact_trade_outcomes "
        "with no error"
    )


def test_writer_deletes_before_insert_is_documented_as_destructive():
    """The DELETE-then-rebuild contract must stay visible to callers.

    run() commits a DELETE before re-running the backtests, so an interrupted
    run leaves the table empty. Anyone reading run() must see that.
    """
    source = inspect.getsource(writer.run)
    assert "DELETE FROM fact_trade_outcomes" in source
    assert "Idempotency" in source or "idempot" in source.lower(), (
        "the destructive DELETE in run() is undocumented; callers cannot tell "
        "that an interrupted run empties the table"
    )
