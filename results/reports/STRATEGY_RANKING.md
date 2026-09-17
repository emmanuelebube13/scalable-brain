# Strategy ranking — pooled OOS trades

Generated 2026-09-17T11:36:24.644148+00:00 · 42 strategies with OOS trades
· **0 pass every gate** · 1 have a mean-R CI clear of zero

`tail` = share of total R that disappears when the top 3 winners are removed. `maxPair` = share of trades in the largest pair. Both are here because the composite score alone has twice pointed at something that was not real.

Phase B evidence tiers (owner-approved 2026-09-17, PHASE-A-RESULTS.md): **candidate** 0 · **grow-sample** 10 · **retire** 8 · **negative-inconclusive** 23 · **disqualified** 1

| # | strategy | n | meanR | 95% CI | PF | Sharpe | MaxDD | tail | maxPair | pairs | gates | tier |
|--:|---|--:|--:|---|--:|--:|--:|--:|--:|--:|---|---|
| 1 | double_bottom_measured_move | 14 | +0.1642 | n/a | 1.57 | 8.46 | 1.1% | 117% | 43% | 4 | 2 fail | grow-sample |
| 2 | strong_weak_analysis | 59 | +0.1021 | [-0.238, +0.460] | 1.20 | 5.45 | 7.6% | 169% | 24% | 5 | 4 fail | grow-sample |
| 3 | Range_Stochastic_Divergence | 41 | +0.5125 | [+0.256, +0.757] | 3.17 | 0.00 | 3.1% | 14% | 29% | 5 | DISQUALIFIED | disqualified |
| 4 | reference_pullback_continuation | 26 | +0.2275 | [-0.242, +0.697] | 1.49 | 2.64 | 5.1% | 100% | 54% | 2 | 3 fail | grow-sample |
| 5 | precision_swing | 245 | +0.0503 | [-0.090, +0.192] | 1.09 | 1.51 | 15.8% | 30% | 23% | 5 | 3 fail | grow-sample |
| 6 | long_wick_pinbar_8ema | 39 | +0.0238 | [-0.428, +0.480] | 1.04 | 1.34 | 6.1% | 687% | 38% | 3 | 4 fail | grow-sample |
| 7 | ma_crossover_swing | 31 | +0.2148 | [-0.251, +0.717] | 1.42 | 0.00 | 3.7% | 119% | 42% | 3 | 5 fail | grow-sample |
| 8 | h4_forex_system | 80 | +0.0192 | [-0.179, +0.212] | 1.04 | 0.64 | 6.4% | 189% | 100% | 1 | 4 fail | grow-sample |
| 9 | h4_crossover_21_89_macd | 85 | +0.0205 | [-0.191, +0.232] | 1.04 | 0.72 | 12.0% | 173% | 25% | 5 | 4 fail | grow-sample |
| 10 | nnfx_backtrader | 49 | +0.1397 | [-0.272, +0.569] | 1.22 | 0.00 | 6.4% | 95% | 22% | 5 | 5 fail | grow-sample |
| 11 | kpl_donchian_breakout | 165 | +0.0129 | [-0.142, +0.182] | 1.03 | 0.39 | 12.2% | 579% | 21% | 5 | 5 fail | grow-sample |
| 12 | holy_grail_pullback | 14 | -0.0046 | n/a | 0.99 | -0.00 | 1.3% | — | 43% | 5 | 4 fail | negative-inconclusive |
| 13 | kiss_h4 | 136 | -0.0030 | [-0.141, +0.135] | 0.99 | -0.10 | 10.9% | — | 38% | 3 | 4 fail | negative-inconclusive |
| 14 | currency_momentum_factor | 139 | -0.0021 | [-0.051, +0.051] | 0.98 | -0.28 | 6.1% | — | 22% | 5 | 4 fail | negative-inconclusive |
| 15 | inside_bar_reversal | 205 | -0.0062 | [-0.211, +0.240] | 0.99 | -0.12 | 27.7% | — | 21% | 5 | 5 fail | negative-inconclusive |
| 16 | engulfing_broken_level | 19 | -0.1259 | n/a | 0.43 | -0.00 | 2.8% | — | 32% | 5 | 4 fail | negative-inconclusive |
| 17 | pinbar_nose_eyes | 5 | -0.2498 | n/a | 0.29 | -0.00 | 1.7% | — | 40% | 4 | 4 fail | negative-inconclusive |
| 18 | trending_retracement_daily | 20 | -0.2203 | [-0.492, +0.066] | 0.40 | -0.00 | 5.3% | — | 30% | 5 | 5 fail | negative-inconclusive |
| 19 | mtf_swing_weekly_pivots | 101 | -0.0252 | [-0.315, +0.260] | 0.96 | -0.41 | 13.5% | — | 23% | 5 | 5 fail | negative-inconclusive |
| 20 | inside_bar_pinbar_combo | 7 | -0.8004 | n/a | 0.40 | -0.00 | 6.2% | — | 29% | 5 | 5 fail | negative-inconclusive |
| 21 | janus_swing_system | 4 | -1.7432 | n/a | 0.22 | -0.00 | 8.7% | — | 50% | 3 | 5 fail | negative-inconclusive |
| 22 | vshape_swing_breakout | 685 | -0.0153 | [-0.088, +0.060] | 0.96 | -0.88 | 26.9% | — | 22% | 5 | 6 fail | negative-inconclusive |
| 23 | riding_trend_retracement | 44 | -1.1464 | [-2.096, -0.338] | 0.27 | -0.00 | 43.2% | — | 46% | 5 | 6 fail | retire |
| 24 | weekly_day_reversal_ea | 71 | -0.2107 | [-0.986, +0.775] | 0.79 | -1.09 | 26.0% | — | 30% | 5 | 6 fail | negative-inconclusive |
| 25 | smash_days | 166 | -0.0689 | [-0.257, +0.133] | 0.87 | -1.65 | 21.0% | — | 24% | 5 | 4 fail | negative-inconclusive |
| 26 | weekly_gap_fade | 434 | -0.0197 | [-0.049, +0.012] | 0.85 | -2.62 | 12.4% | — | 25% | 5 | 4 fail | negative-inconclusive |
| 27 | bb_midline_break | 329 | -0.0798 | [-0.211, +0.053] | 0.88 | -2.43 | 32.0% | — | 24% | 5 | 5 fail | negative-inconclusive |
| 28 | pinbar_key_level_50pct | 27 | -0.7017 | [-1.699, +0.712] | 0.49 | -2.99 | 20.9% | — | 41% | 5 | 5 fail | negative-inconclusive |
| 29 | xard_ma_cross_daily_open | 1040 | -0.0588 | [-0.143, +0.027] | 0.92 | -2.59 | 56.5% | — | 22% | 5 | 6 fail | negative-inconclusive |
| 30 | three_candle_swing_reversal | 69 | -0.1873 | [-0.522, +0.162] | 0.76 | -3.34 | 22.7% | — | 38% | 3 | 5 fail | negative-inconclusive |
| 31 | reps_donchian_pyramiding | 98 | -0.2269 | [-0.565, +0.167] | 0.70 | -3.15 | 31.0% | — | 22% | 5 | 6 fail | negative-inconclusive |
| 32 | ema_cross_h4_filter_bot | 846 | -0.0716 | [-0.163, +0.024] | 0.90 | -2.88 | 52.4% | — | 25% | 5 | 6 fail | negative-inconclusive |
| 33 | macd_divergence | 204 | -0.0425 | [-0.091, +0.002] | 0.58 | -3.80 | 10.1% | — | 22% | 5 | 4 fail | negative-inconclusive |
| 34 | outside_hma_klinger | 633 | -0.0570 | [-0.112, -0.001] | 0.84 | -4.02 | 39.7% | — | 25% | 5 | 5 fail | retire |
| 35 | demark_fractal_breakout | 1268 | -0.0504 | [-0.095, -0.004] | 0.84 | -4.28 | 51.4% | — | 21% | 5 | 6 fail | retire |
| 36 | liquidity_grab_fade | 331 | -0.0726 | [-0.126, -0.020] | 0.58 | -4.91 | 22.9% | — | 22% | 5 | 4 fail | retire |
| 37 | inside_bar_continuation_ea | 170 | -0.1453 | [-0.278, -0.004] | 0.71 | -5.65 | 23.0% | — | 25% | 5 | 4 fail | retire |
| 38 | liquidity_sweep_ob | 18 | -0.7907 | n/a | 0.21 | -6.73 | 13.4% | — | 28% | 5 | 5 fail | negative-inconclusive |
| 39 | amazing_crossover | 1868 | -0.0507 | [-0.073, -0.028] | 0.74 | -8.43 | 62.7% | — | 25% | 5 | 6 fail | retire |
| 40 | smashing_forex_2 | 975 | -0.3056 | [-0.428, -0.177] | 0.65 | -8.44 | 95.9% | — | 44% | 5 | 6 fail | retire |
| 41 | adx_trend_pullback_ea | 1583 | -0.1683 | [-0.236, -0.101] | 0.78 | -9.53 | 94.5% | — | 21% | 5 | 6 fail | retire |
| 42 | weekly_range_reversal | 17 | -0.8410 | n/a | 0.19 | -11.23 | 16.3% | — | 41% | 5 | 5 fail | negative-inconclusive |
