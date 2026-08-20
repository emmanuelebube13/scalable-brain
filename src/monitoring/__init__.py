"""T4 — freshness heartbeat.

A daily watchdog over every critical System-1 data flow. Exists because two
failures ran silently this summer: the OANDA price ingest was dead for 16 days
(2026-07-04 → 07-20) and `fact_trade_outcomes` was frozen for five weeks
(2026-06-23 → 07-29). In both cases the pipeline kept reporting success.

The contract is deliberately small: a non-zero exit code, an alert log line, and
a flag file at ``results/state/HEARTBEAT_ALERT``. No integrations.
"""
