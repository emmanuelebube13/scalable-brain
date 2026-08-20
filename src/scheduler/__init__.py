"""MODEL-009 — retraining scheduler / orchestrator.

Weekly (Sunday 00:00 UTC) + performance-triggered retraining (rolling-14d Sharpe < 0.3,
regime accuracy < 70%, or a circuit-breaker event), with cooldown debounce, single-flight
lock, deployment gates (candidate must beat incumbent), atomic promote via MODEL-007, and
full run lineage. Fail-safe: missing live metrics never fire a false trigger and never
promote a worse model.
"""
