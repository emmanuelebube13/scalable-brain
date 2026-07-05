"""Backward-compatible wrapper for the grouped backtest engine."""

try:
    from .core_engine.backtest_engine import *  # noqa: F401,F403
except ImportError:
    from core_engine.backtest_engine import *  # type: ignore # noqa: F401,F403
