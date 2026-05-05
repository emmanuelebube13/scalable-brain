"""Backward-compatible wrapper for the grouped utility helpers."""

try:
    from .data_access.utils import *  # noqa: F401,F403
except ImportError:
    from data_access.utils import *  # type: ignore # noqa: F401,F403
