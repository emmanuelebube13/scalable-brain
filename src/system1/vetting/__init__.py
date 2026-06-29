"""MODEL-005 — Strategy vetting gate + regime→strategy map / weights.

Applies the strict per-regime gates (PF≥1.5, Sharpe≥0.8, MaxDD≤25%, WinRate≥40%,
Recovery≥3.0, OOS≥60mo; low-confidence cells always rejected) to MODEL-004's
attribution, ranks qualifying strategies per regime by a documented composite score,
and emits regime_strategy_map.json + strategy_weights.json (versioned, schema-validated).
"""
