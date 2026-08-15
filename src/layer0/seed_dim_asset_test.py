"""Backward-compatible wrapper for the grouped Dim_Asset seeding script."""

try:
    from .qualification.seed_dim_asset_test import *  # noqa: F401,F403
    from .qualification.seed_dim_asset_test import main as _main
except ImportError as _relative_import_error:
    # Fallback for when ``src/`` itself is on sys.path and this module is
    # imported without its package context. If the fallback also fails, surface
    # the ORIGINAL error: a swallowed relative-import failure here is exactly
    # what hid the broken outcomes writer for a month
    # (see task/2026-July-week4/T1-reconnect-feedback-loop.md).
    try:
        from qualification.seed_dim_asset_test import *  # type: ignore # noqa: F401,F403
        from qualification.seed_dim_asset_test import main as _main  # type: ignore
    except ImportError:
        raise _relative_import_error


if __name__ == "__main__":
    _main()
