# S1-EXPORT-002 — Publish Strategy Analytics for Telemetry & Simulation (Agent Prompt)

## Instructions for the operator (read first)

**Run on: COMPUTER 1, the System 1 machine, in the `scalable-brain` repo** (the machine
with `system1-rw` GCS credentials and the backtest database). Give this whole file to
the Claude Code / agent session there. When it finishes, tell the operator of the
System 2 machine — the TELEM-002 screen and SIM-001 simulator consume what this
publishes, automatically, within one poll.

---

## Role & Mandate

You are extending System 1's serializer with a fourth publish step: an **analytics
bundle** that downstream telemetry can render and a Monte-Carlo simulator can sample.
You do NOT train, select, or promote anything (FIX-S1-009: the orchestrator is the only
champion writer). You read what already exists and publish derived, read-only JSON.

## Where the data lives (verify names against the actual schema first)

- `fact_trade_outcomes` — per-trade backtest results: `outcome_id, timestamp, asset_id,
  granularity, strategy_id, entry_signal_type, is_winner, r_multiple` (this is the
  table the gatekeeper trains on — see `src/system1/gatekeeper/train.py`).
- `fact_market_regime_v2` — causal regime per (asset, granularity, bar).
- The vetting/qualification run that produced `regime_strategy_map.json`
  (`qualification_run_id a5153ca0-…` for the 2026-07-01 bundle) — strategy catalog,
  gates, per-regime metrics.
- Strategy definitions/registry (names, descriptions, entry logic family) — wherever
  strategy_id 1–10 are defined (e.g. `src/system1/strategies/`).

## Deliverable: one JSON bundle in GCS

Publish to versioned prefix `system1/analytics/<UTC-version>/` + atomic pointer
`system1/analytics/latest.json` (same upload→verify-SHA256→flip-pointer discipline as
the other publishers). Files:

### 1. `strategy_catalog.json`
For EVERY strategy_id in the registry (1–10), not just qualified ones:
```json
{"schema_version": "1", "generated_at_utc": "...",
 "strategies": [{
   "strategy_id": "10", "name": "Range_Stochastic_Divergence",
   "family": "mean-reversion | trend | breakout | ...",
   "description": "one-paragraph human description of the entry/exit logic",
   "granularities": ["H1", "H4"],
   "qualified": true, "qualified_regimes": ["Trending-Up", "Trending-Down", "Ranging"],
   "qualification_run_id": "...", "gates_passed": {...}, "gates_failed": {...}
 }, ...]}
```

### 2. `trade_returns.json` — the simulator's raw material
Per qualified (strategy_id, regime, granularity, pair) cell, the OOS per-trade series:
```json
{"schema_version": "1",
 "cells": [{
   "strategy_id": "10", "regime": "Ranging", "granularity": "H1", "pair": "EUR_USD",
   "n_trades": 335, "oos_months": 83.8,
   "r_multiples": [0.31, -1.0, 2.7, ...],          // full OOS series, chronological
   "trade_timestamps": ["2019-03-01T10:00:00Z", ...] // same length; enables frequency + clustering
 }, ...]}
```
If per-pair splits are thin, also include the aggregated-across-pairs cell with
`"pair": "ALL"`. Cap file size sensibly (r_multiples rounded to 4dp).

### 3. `frequency_stats.json`
Per cell: trades per month (mean/p50/p90), mean/median holding time (hours), win rate,
avg win R, avg loss R, max consecutive losses, regime occupancy % (from
fact_market_regime_v2: fraction of bars in each regime per pair) — so expected
LIVE frequency = occupancy × signals/bar × gatekeeper approval rate (~0.34 OOS).

### 4. `manifest.json` — names, bytes, sha256 of the three files above.

## Rules

1. Versioned prefixes immutable; pointer flip last (after SHA256 round-trip verify).
2. Read-only w.r.t. training/promotion; no champion files touched.
3. Causal honesty: OOS trades only (walk-forward folds), clearly labeled; never mix
   in-sample rows into `trade_returns.json`.
4. Wire this into the retrain orchestrator AFTER promotion (like
   `publish_system2_manifest.py`) so it refreshes with every new champion; also
   runnable by hand.

## Verification

- `gcloud storage cat gs://scalable-brain-artifacts/system1/analytics/latest.json`
  resolves; all SHA256s verify after a fresh download.
- Spot-check: n_trades per cell matches the vetting report (e.g. Ranging@H1 = 335 for
  the 2026-07-01 bundle); sum of per-pair cells ≈ the ALL cell.
