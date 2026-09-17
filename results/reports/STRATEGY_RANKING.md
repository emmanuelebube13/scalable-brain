# Strategy ranking — pooled OOS trades

Generated 2026-09-17T01:05:43.367568+00:00 · 42 strategies with OOS trades
· **0 pass every gate** · 1 have a mean-R CI clear of zero

`tail` = share of total R that disappears when the top 3 winners are removed. `maxPair` = share of trades in the largest pair. Both are here because the composite score alone has twice pointed at something that was not real.

| # | strategy | n | meanR | 95% CI | PF | Sharpe | MaxDD | tail | maxPair | pairs | gates |
|--:|---|--:|--:|---|--:|--:|--:|--:|--:|--:|---|
| 1 | double_bottom_measured_move | 14 | +0.1734 | n/a | 1.61 | 8.95 | 1.0% | 112% | 43% | 4 | 2 fail |
| 2 | strong_weak_analysis | 59 | +0.1223 | [-0.214, +0.487] | 1.24 | 6.54 | 7.7% | 142% | 24% | 5 | 4 fail |
| 3 | Range_Stochastic_Divergence | 41 | +0.5125 | [+0.242, +0.756] | 3.17 | 0.00 | 3.1% | 14% | 29% | 5 | DISQUALIFIED |
| 4 | reference_pullback_continuation | 26 | +0.2451 | [-0.233, +0.743] | 1.54 | 2.85 | 4.3% | 94% | 54% | 2 | 2 fail |
| 5 | long_wick_pinbar_8ema | 39 | +0.0638 | [-0.392, +0.523] | 1.10 | 3.59 | 6.1% | 259% | 38% | 3 | 4 fail |
| 6 | precision_swing | 246 | +0.0778 | [-0.058, +0.215] | 1.15 | 2.31 | 13.6% | 20% | 24% | 5 | 3 fail |
| 7 | h4_forex_system | 80 | +0.0562 | [-0.149, +0.255] | 1.13 | 1.87 | 8.0% | 67% | 100% | 1 | 3 fail |
| 8 | ma_crossover_swing | 31 | +0.2383 | [-0.220, +0.753] | 1.48 | 0.00 | 3.6% | 108% | 42% | 3 | 5 fail |
| 9 | h4_crossover_21_89_macd | 85 | +0.0299 | [-0.182, +0.241] | 1.06 | 1.05 | 11.7% | 120% | 25% | 5 | 3 fail |
| 10 | kpl_donchian_breakout | 165 | +0.0280 | [-0.120, +0.192] | 1.07 | 0.86 | 11.3% | 267% | 21% | 5 | 4 fail |
| 11 | kiss_h4 | 137 | +0.0225 | [-0.116, +0.156] | 1.06 | 0.64 | 9.6% | 182% | 37% | 3 | 4 fail |
| 12 | nnfx_backtrader | 49 | +0.1593 | [-0.258, +0.582] | 1.26 | 0.00 | 6.0% | 84% | 22% | 5 | 5 fail |
| 13 | mtf_swing_weekly_pivots | 101 | +0.0240 | [-0.246, +0.314] | 1.04 | 0.39 | 12.6% | 265% | 23% | 5 | 5 fail |
| 14 | vshape_swing_breakout | 686 | +0.0081 | [-0.064, +0.083] | 1.02 | 0.45 | 21.3% | 273% | 22% | 5 | 5 fail |
| 15 | currency_momentum_factor | 139 | +0.0013 | [-0.049, +0.055] | 1.01 | 0.17 | 6.0% | 1280% | 22% | 5 | 4 fail |
| 16 | holy_grail_pullback | 14 | +0.0119 | n/a | 1.04 | 0.00 | 1.2% | 1962% | 43% | 5 | 4 fail |
| 17 | pinbar_nose_eyes | 5 | -0.1944 | n/a | 0.41 | -0.00 | 1.6% | — | 40% | 4 | 4 fail |
| 18 | engulfing_broken_level | 19 | -0.1525 | n/a | 0.42 | -0.00 | 3.3% | — | 32% | 5 | 4 fail |
| 19 | trending_retracement_daily | 20 | -0.1908 | [-0.454, +0.065] | 0.39 | -0.00 | 5.0% | — | 30% | 5 | 4 fail |
| 20 | inside_bar_pinbar_combo | 7 | -0.7377 | n/a | 0.43 | -0.00 | 5.9% | — | 29% | 5 | 5 fail |
| 21 | xard_ma_cross_daily_open | 1040 | +0.0024 | [-0.080, +0.088] | 1.00 | 0.11 | 44.3% | 304% | 22% | 5 | 6 fail |
| 22 | janus_swing_system | 4 | -1.6271 | n/a | 0.24 | -0.00 | 8.4% | — | 50% | 3 | 5 fail |
| 23 | liquidity_sweep_ob | 17 | -0.8369 | n/a | 0.13 | -0.00 | 13.4% | — | 29% | 5 | 5 fail |
| 24 | bb_midline_break | 331 | -0.0207 | [-0.152, +0.108] | 0.97 | -0.61 | 22.8% | — | 24% | 5 | 4 fail |
| 25 | smash_days | 166 | -0.0407 | [-0.228, +0.159] | 0.92 | -0.97 | 20.2% | — | 24% | 5 | 4 fail |
| 26 | riding_trend_retracement | 43 | -1.0718 | [-2.047, -0.257] | 0.31 | -0.00 | 43.5% | — | 44% | 5 | 6 fail |
| 27 | weekly_day_reversal_ea | 71 | -0.1495 | [-0.926, +0.836] | 0.84 | -0.77 | 30.2% | — | 30% | 5 | 6 fail |
| 28 | ema_cross_h4_filter_bot | 848 | -0.0229 | [-0.115, +0.076] | 0.97 | -0.91 | 37.6% | — | 25% | 5 | 6 fail |
| 29 | macd_divergence | 204 | -0.0204 | [-0.070, +0.028] | 0.80 | -1.72 | 7.6% | — | 22% | 5 | 4 fail |
| 30 | weekly_gap_fade | 434 | -0.0140 | [-0.043, +0.017] | 0.89 | -1.85 | 9.9% | — | 25% | 5 | 4 fail |
| 31 | demark_fractal_breakout | 1273 | -0.0192 | [-0.064, +0.028] | 0.94 | -1.60 | 35.7% | — | 21% | 5 | 6 fail |
| 32 | inside_bar_reversal | 205 | -0.0979 | [-0.304, +0.155] | 0.82 | -1.81 | 30.6% | — | 21% | 5 | 5 fail |
| 33 | pinbar_key_level_50pct | 27 | -0.6433 | [-1.651, +0.737] | 0.52 | -2.74 | 20.1% | — | 41% | 5 | 5 fail |
| 34 | reps_donchian_pyramiding | 98 | -0.2026 | [-0.535, +0.189] | 0.73 | -2.82 | 32.4% | — | 22% | 5 | 6 fail |
| 35 | outside_hma_klinger | 635 | -0.0424 | [-0.100, +0.016] | 0.88 | -2.90 | 30.8% | — | 25% | 5 | 5 fail |
| 36 | inside_bar_continuation_ea | 170 | -0.0916 | [-0.235, +0.044] | 0.81 | -3.54 | 15.0% | — | 25% | 5 | 4 fail |
| 37 | liquidity_grab_fade | 328 | -0.0690 | [-0.123, -0.014] | 0.60 | -5.02 | 21.9% | — | 22% | 5 | 4 fail |
| 38 | amazing_crossover | 1868 | -0.0285 | [-0.051, -0.005] | 0.85 | -4.75 | 46.2% | — | 25% | 5 | 5 fail |
| 39 | three_candle_swing_reversal | 69 | -0.3192 | [-0.662, +0.012] | 0.58 | -5.65 | 25.0% | — | 38% | 3 | 6 fail |
| 40 | adx_trend_pullback_ea | 1584 | -0.0842 | [-0.151, -0.018] | 0.88 | -4.69 | 82.6% | — | 21% | 5 | 6 fail |
| 41 | weekly_range_reversal | 17 | -0.7543 | n/a | 0.21 | -10.15 | 15.1% | — | 41% | 5 | 5 fail |
| 42 | smashing_forex_2 | 959 | -0.4419 | [-0.546, -0.331] | 0.50 | -15.67 | 98.8% | — | 43% | 5 | 6 fail |
