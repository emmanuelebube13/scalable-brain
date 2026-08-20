"""MODEL-004 — Per-regime strategy attribution.

Tags each backtested trade (fact_trade_outcomes) with the point-in-time market regime
in force at entry (fact_market_regime_v2.regime_causal — the causal walk-forward label,
FIX-S1-005; NOT the reporting-only smoothed label) and computes, per
strategy × regime × granularity, win-rate / profit-factor / Sharpe (+ trade count,
expectancy, MaxDD, avg-R) with Bayesian shrinkage + low-confidence flags for thin cells.
"""
