"""S1-EXPORT-002 — read-only strategy analytics bundle for downstream telemetry/simulation.

Publishes strategy_catalog.json, trade_returns.json, frequency_stats.json + manifest.json
to ``system1/analytics/<version>/`` with an atomic ``latest.json`` pointer. Never touches
training or champion promotion (FIX-S1-009).
"""
