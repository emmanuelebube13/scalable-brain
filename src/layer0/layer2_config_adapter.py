"""Backward-compatible wrapper for the grouped Layer 2 config adapter."""

try:
    from .promotion.layer2_config_adapter import *  # noqa: F401,F403
except ImportError:
    from promotion.layer2_config_adapter import *  # type: ignore # noqa: F401,F403
