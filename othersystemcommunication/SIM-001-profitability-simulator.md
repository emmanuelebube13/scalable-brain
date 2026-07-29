# SIM-001 — Profitability Simulator with Deposits & Compounding (Agent Prompt)

**Run on: this machine. Prerequisite: S1-EXPORT-002 must be published**
(`gs://scalable-brain-artifacts/system1/analytics/latest.json`) — the simulator's
inputs are its `trade_returns.json` + `frequency_stats.json`. If it's not there yet,
stop and tell the operator to run the System 1 prompt first.

## Goal

Answer the operator's question 7 honestly: *"what is the yearly profit rate, and what
would MY deposit look like over time?"* — as a **distribution, never a single number**,
via Monte-Carlo resampling of the OOS per-trade returns, with:

- user-specified starting deposit ($)
- **compounding toggle** (risk % of current equity vs fixed % of initial)
- **recurring deposit** (amount + monthly/weekly cadence)
- horizon (1–10 years)

Deliverables: a `Simulator` screen on the telemetry dashboard (primary) + a CLI
(`bridge/tools/simulate.py` or similar) producing the same numbers (for
reproducibility/tests).

## Simulation model — replicate the LIVE pipeline, not an idealized one

Sample trades from `trade_returns.json` r_multiples per (regime, granularity) cell,
but weight the flow by what the live system actually does:

1. **Frequency**: expected trades/week from `frequency_stats.json` occupancy ×
   approval-rate, clipped to the live constraints: trading window Sun 20:00→Wed 18:00
   UTC (~70 H1 bars/wk), ≤3 tradeable pairs today (EUR_USD/GBP_USD/AUD_USD), margin
   cap ≈3 concurrent, dedup 1 trade/bar/strategy/pair. Read the current values from
   the repo configs (S3 `risk_config.json`, S2 `.env.system2`) — do NOT hard-code.
2. **Risk per trade**: replicate S3 sizing: kelly clamped to 2%, ×0.5 account-state
   (CAUTION) ×0.5 stage (paper) → 0.5% today; expose state/stage as scenario knobs
   (e.g. "NORMAL+micro" future). PnL per trade = risk × sampled R.
3. **Costs/haircuts**: subtract slippage (observed live: ~8–12 pips beyond tolerance
   on market orders — surface as a configurable haircut on R, default from the live
   journal's `slippage_pips` when n≥30) and apply a user-visible "live degradation"
   factor (default 0.7× on expectancy) — backtests flatter reality; say so on screen.
4. **Block bootstrap** (sample R's in chronological blocks of ~20) to preserve
   win/loss clustering; 10,000 paths; per path apply deposits/compounding rules,
   then report p5/p25/p50/p75/p95 equity bands, CAGR distribution, max-drawdown
   distribution, and P(ruin: equity < 50% of contributions).

## Screen requirements

- Inputs: deposit, recurring amount+cadence, horizon, compounding on/off, scenario
  (current: paper+CAUTION ×0.25 sizing | normal | custom risk %), degradation factor.
- Outputs: equity fan chart (p5–p95 band + median line), CAGR histogram or p5/p50/p95
  stat tiles, max-DD tile, expected trades/yr tile, total-contributed vs final-median.
- A permanent, visible caveat block: "Backtest-derived OOS estimate. Not a promise.
  Live sample to date: N trades." (pull live N from S3's `trade_journal`).
- Follow the dashboard's dataviz/theming conventions (see TELEM-002 notes);
  cloud + local modes; degrade to "needs System 1 analytics export" when input absent.

## CLI + tests

- CLI: `python simulate.py --deposit 10000 --monthly 500 --years 5 --compound
  --scenario current` → JSON + ASCII summary. Seeded RNG for reproducible tests.
- Tests: deterministic seed → known percentiles; zero-frequency cell → flat equity
  + warning; compounding on/off changes only sizing base; recurring deposits add
  exactly N×amount to contributions; degradation=1.0 reproduces raw backtest
  expectancy within tolerance.

## Honesty rules (non-negotiable)

- Never render a single "yearly profit %" without the band around it.
- OOS r_multiples only (the export guarantees this); label everything derived.
- If any live constraint (window/pairs/sizing) can't be read from config, fail the
  panel with "config unreadable" rather than silently assuming.
