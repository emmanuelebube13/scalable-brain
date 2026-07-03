"""Shared cross-layer utilities for Scalable Brain.

Currently exposes the canonical PostgreSQL/TimescaleDB connection module
(:mod:`src.common.db`). All layers must obtain database connections through
``src.common.db`` rather than constructing their own engines/DSNs (FND-004
Phase 3).
"""
