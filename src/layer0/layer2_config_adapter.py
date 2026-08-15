"""Backward-compatible wrapper for the grouped Layer 2 config adapter."""

try:
    from .promotion.layer2_config_adapter import *  # noqa: F401,F403
except ImportError as _relative_import_error:
    # Fallback for when ``src/`` itself is on sys.path and this module is
    # imported without its package context. If the fallback also fails, surface
    # the ORIGINAL error: a swallowed relative-import failure here is exactly
    # what hid the broken outcomes writer for a month
    # (see task/2026-July-week4/T1-reconnect-feedback-loop.md).
    try:
        from promotion.layer2_config_adapter import *  # type: ignore # noqa: F401,F403
    except ImportError:
        raise _relative_import_error
