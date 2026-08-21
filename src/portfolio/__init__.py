"""Portfolio-level measurement for strategies whose edge is not visible per-pair.

Why this package exists
-----------------------
``v2_harness`` scores one ``(strategy x pair x regime x granularity)`` cell at a time,
and ``StrategyV2.generate_orders`` is handed a single pair's frames with no pair
identity. That is fine for a strategy that stands alone on each pair. It is
structurally unable to measure a strategy whose signal is a *comparison between*
pairs, or whose edge only appears once weakly-correlated pairs are combined.

``task/2026-August-week2/N5-fleet-completion/SUMMARY.md`` finding #5 records the
consequence: ``currency_momentum_factor`` and ``strong_weak_analysis`` both had their
headline mechanism replaced by the single-pair-reachable remainder, and their recorded
verdicts "say nothing about the mechanism their authors claimed". That document names
the fix — "pass a pair-keyed frame bundle" — and this package is it.

What this package is NOT
------------------------
It is **not** position sizing. System 1 never sizes (see ``contract_v2.OrderIntent``
and the inviolable principles in ``README.md``): System 3 owns risk and System 2 owns
execution. The weights here are *measurement* weights — the same kind of object
``vetting`` already emits as ``strategy_weights.json`` — used to build the portfolio
return series a strategy would have produced. Nothing here reaches an order.

It also does not promote anything. There is no write path to the live map from this
package by design; see ``task/OPEN.md`` item 5 on the absent v2 promotion path.
"""

from __future__ import annotations

__all__ = ["bundle", "schedule", "evaluate"]
