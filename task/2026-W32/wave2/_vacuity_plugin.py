"""Pytest plugin that sabotages one strategy, so we can prove its fixture has teeth.

A golden fixture is worthless if it passes no matter what the strategy does. That is the
single most likely failure mode when a weaker model writes the fixture: it runs the code,
pastes the output into the assertions, and produces a test that asserts the code equals
itself. Such a test passes forever and proves nothing.

This plugin makes ``generate_orders`` return an empty list for the target strategy class
(and therefore for the fixture's subclass of it, which inherits the method). A fixture with
real assertions MUST then fail. If it still passes, the fixture is vacuous.

Driven by the ``VACUITY_TARGET`` env var, set to the strategy's module path. Used by
``audit_wave2.py``; not part of the normal test run.
"""

from __future__ import annotations

import importlib
import inspect
import os
from typing import Any, List, Mapping


def pytest_configure(config: Any) -> None:
    target = os.environ.get("VACUITY_TARGET")
    if not target:
        return

    module = importlib.import_module(target)

    from src.layer0.strategies.contract_v2 import StrategyV2

    def _no_orders(self: Any, frames: Mapping[str, Any]) -> List[Any]:
        return []

    for _, obj in inspect.getmembers(module, inspect.isclass):
        if (
            issubclass(obj, StrategyV2)
            and obj is not StrategyV2
            and obj.__module__ == target
        ):
            obj.generate_orders = _no_orders  # type: ignore[method-assign]
