"""Backward-compatible wrapper for the grouped multi-timeframe module."""

try:
    from .core_engine.multi_timeframe import *  # noqa: F401,F403
except ImportError:
    from core_engine.multi_timeframe import *  # type: ignore # noqa: F401,F403
