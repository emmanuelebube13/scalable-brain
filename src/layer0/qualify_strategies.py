"""Backward-compatible wrapper for the grouped qualification entrypoint.

The implementation lives in ``layer0/qualification/qualify_strategies.py``.
This module only re-exports it so the pre-reorg import path
``layer0.qualify_strategies`` keeps working.

Until 2026-07-29 this file also carried a verbatim copy of the entire
pre-reorg module body below the wrapper. That copy still imported the flat
pre-reorg paths (``layer0.strategy_base``, ``layer0.strategies``), so importing
this module executed the qualification code twice and then died on the stale
paths. Its ImportError was swallowed by the fallback below and resurfaced as a
misleading ``No module named 'qualification'``, which is why the real breakage
took a month to find. The duplicate body has been deleted; the two definitions
were verified identical (same 16 public names) before removal.
See ``task/2026-W31/T1-reconnect-feedback-loop.md``.
"""

try:
    from .qualification.qualify_strategies import *  # noqa: F401,F403
    from .qualification.qualify_strategies import main as _main
except ImportError as _relative_import_error:
    # Fallback for the case where ``src/`` itself is on sys.path and this file
    # is imported without its package context. If that also fails, surface the
    # ORIGINAL error — never let the fallback's "No module named 'qualification'"
    # hide a real breakage inside the qualification package.
    try:
        from qualification.qualify_strategies import *  # type: ignore # noqa: F401,F403
        from qualification.qualify_strategies import main as _main  # type: ignore
    except ImportError:
        raise _relative_import_error

if __name__ == "__main__":
    _main()
