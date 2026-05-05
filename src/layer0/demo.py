"""Backward-compatible wrapper for the grouped Layer 0 demo script."""

try:
    from .qualification.demo import *  # noqa: F401,F403
    from .qualification.demo import main as _main
except ImportError:
    from qualification.demo import *  # type: ignore # noqa: F401,F403
    from qualification.demo import main as _main  # type: ignore

if __name__ == "__main__":
    _main()
