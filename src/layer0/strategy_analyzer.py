"""Backward-compatible wrapper for the grouped strategy analyzer."""

try:
    from .core_engine.strategy_analyzer import *  # noqa: F401,F403
except ImportError as _relative_import_error:
    # Fallback for when ``src/`` itself is on sys.path and this module is
    # imported without its package context. If the fallback also fails, surface
    # the ORIGINAL error: a swallowed relative-import failure here is exactly
    # what hid the broken outcomes writer for a month
    # (see task/2026-July-week4/T1-reconnect-feedback-loop.md).
    try:
        from core_engine.strategy_analyzer import *  # type: ignore # noqa: F401,F403
    except ImportError:
        raise _relative_import_error
