"""Root conftest — makes the repo root importable during test collection.

Without this file pytest has no rootdir anchor: ``src/`` is not a package (no
``__init__.py``), so under the default *prepend* import mode pytest inserts
``src/`` on ``sys.path`` rather than the repo root, and every ``import
src.system1...`` in a test module fails with ``ModuleNotFoundError: No module
named 'src'``.

The practical symptom was that the documented command ``pytest src/system1``
died with 27 collection errors while ``python -m pytest src/system1`` (which
puts the CWD on ``sys.path``) passed. A conftest at the root is enough: pytest
adds this file's directory to ``sys.path``, so both invocations now behave the
same.
"""
