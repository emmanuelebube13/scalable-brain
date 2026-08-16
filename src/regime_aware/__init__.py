"""Regime-aware strategies (model 1) — EXPERIMENT, isolated from the production pipeline.

The production system is model 2 ("gatekeeper"): strategies trade blind, and regime is applied
afterwards as attribution and a filter. This package tests the opposite architecture — the
regime label is a **first-class input to the strategy**, which decides for itself how to behave
under each market condition.

Isolation contract
------------------
Nothing in this package writes to the production database or to production state files. The
database connection is opened with ``SET default_transaction_read_only = on``, so a write is
refused by PostgreSQL itself rather than by convention. All output lands in
``results/regime_aware/``. Nothing outside ``src/regime_aware/`` was modified to build this.

To archive the experiment wholesale (per ``STRUCTURE.md``: a zip and its manifest, never an
unpacked tree)::

    zip -r archieved/regime_aware_<date>.zip src/regime_aware/ results/regime_aware/
    sha256sum archieved/regime_aware_<date>.zip > archieved/regime_aware_<date>.zip.sha256
    rm -rf src/regime_aware/ results/regime_aware/

Why the legacy engine and not contract_v2
-----------------------------------------
This builds on ``layer0.core_engine.BacktestEngine`` — the same engine, cost model and strategy
classes that produced every number in ``fact_trade_outcomes``. The point of the experiment is a
like-for-like A/B: regime-blind arm versus regime-aware arm, identical in every respect except
whether the strategy can see the regime. Porting to the v2 contract at the same time would
change several things at once and make any difference uninterpretable.

The cost is that ``assert_no_lookahead_v2`` is unavailable here, so this package carries its own
truncation-based causality test (``tests/test_causality.py``).
"""
