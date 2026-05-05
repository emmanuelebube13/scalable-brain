"""Backward-compatible wrapper for the grouped strategy analyzer."""

try:
    from .core_engine.strategy_analyzer import *  # noqa: F401,F403
except ImportError:
    from core_engine.strategy_analyzer import *  # type: ignore # noqa: F401,F403
