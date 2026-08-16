# R0 Discrimination Baseline Summary

Evaluated 43 v2 strategies with OOS evaluations.

## Omnibus Test (Spread >= 0.10)
- **hmm_causal**: 7 discriminating
- **d1_trend**: 1 discriminating

## Directional Test (Hypothesized Regimes Outperform)
- **hmm_causal**: 9 discriminating
- **d1_trend**: 0 discriminating

## Concentration Check

### amazing_crossover
- **hmm_causal**: {'GBP_USD': 508, 'USD_CAD': 463, 'EUR_USD': 429, 'AUD_USD': 303}

### currency_momentum_factor
- **hmm_causal**: {'USD_JPY': 10}

### engulfing_broken_level
- **hmm_causal**: {'AUD_USD': 1}

### holy_grail_pullback
- **hmm_causal**: {'USD_JPY': 1}

### inside_bar_continuation_ea
- **hmm_causal**: {'USD_JPY': 13}

### inside_bar_pinbar_combo
- **hmm_causal**: {'USD_JPY': 2, 'GBP_USD': 1}

### kpl_donchian_breakout
- **hmm_causal**: {'USD_JPY': 18, 'GBP_USD': 3, 'AUD_USD': 3}

### liquidity_grab_fade
- **hmm_causal**: {'USD_JPY': 16, 'AUD_USD': 4, 'USD_CAD': 2, 'GBP_USD': 1}

### macd_divergence
- **hmm_causal**: {'GBP_USD': 1, 'USD_JPY': 1}

### nnfx_backtrader
- **hmm_causal**: {'USD_JPY': 4, 'GBP_USD': 1, 'AUD_USD': 1}

### reps_donchian_pyramiding
- **hmm_causal**: {'USD_JPY': 27, 'AUD_USD': 1}

### riding_trend_retracement
- **hmm_causal**: {'AUD_USD': 1}
- **d1_trend**: {'GBP_USD': 9, 'AUD_USD': 5, 'EUR_USD': 4, 'USD_CAD': 2}

### strong_weak_analysis
- **hmm_causal**: {'USD_JPY': 11, 'EUR_USD': 1, 'GBP_USD': 1, 'AUD_USD': 1}

### trending_retracement_daily
- **hmm_causal**: {'USD_CAD': 1}

### vshape_swing_breakout
- **hmm_causal**: {'USD_JPY': 114, 'AUD_USD': 15, 'GBP_USD': 14, 'EUR_USD': 10, 'USD_CAD': 3}

## Verdict
The `hmm_causal` label appears to discriminate for several strategies, but the concentration check reveals this is overwhelmingly an artifact of `USD_JPY` dominating the favourable cells (as warned in README §3). Outside of that single pair, there is virtually no discrimination. The `d1_trend` label, which varies across all pairs, shows zero discrimination in the directional test and only 1 in the omnibus test. Overall, regime carries almost no genuine predictive information for these strategies' outcomes.