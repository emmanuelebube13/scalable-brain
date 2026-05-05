"""Backward-compatible wrapper for the grouped indicator helpers."""

try:
    from .data_access.indicators import *  # noqa: F401,F403
except ImportError:
    from data_access.indicators import *  # type: ignore # noqa: F401,F403
