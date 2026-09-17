# Strategy ranking — pooled OOS trades

Generated 2026-09-14T16:21:07.706184+00:00 · 51 strategies with OOS trades
· **0 pass every gate** · 1 have a mean-R CI clear of zero

`tail` = share of total R that disappears when the top 3 winners are removed. `maxPair` = share of trades in the largest pair. Both are here because the composite score alone has twice pointed at something that was not real.

| # | strategy | n | meanR | 95% CI | PF | Sharpe | MaxDD | tail | maxPair | pairs | gates |
|--:|---|--:|--:|---|--:|--:|--:|--:|--:|--:|---|
| 1 | double_bottom_measured_move | 14 | +0.1734 | n/a | 1.61 | 8.95 | 1.1% | 112% | 43% | 4 | 2 fail |
| 2 | strong_weak_analysis | 59 | +0.1223 | [-0.239, +0.476] | 1.24 | 6.54 | 10.9% | 142% | 24% | 5 | 4 fail |
| 3 | Range_Stochastic_Divergence | 41 | +0.5125 | [+0.231, +0.757] | 3.17 | 0.00 | 2.0% | 14% | 29% | 5 | DISQUALIFIED |
| 4 | reference_pullback_continuation | 26 | +0.2451 | [-0.232, +0.746] | 1.54 | 2.85 | 4.3% | 94% | 54% | 2 | 2 fail |
| 5 | long_wick_pinbar_8ema | 39 | +0.0638 | [-0.392, +0.520] | 1.10 | 3.59 | 8.2% | 259% | 38% | 3 | 4 fail |
| 6 | precision_swing | 246 | +0.0778 | [-0.059, +0.215] | 1.15 | 2.31 | 12.6% | 20% | 24% | 5 | 3 fail |
| 7 | h4_forex_system | 80 | +0.0562 | [-0.151, +0.244] | 1.13 | 1.87 | 9.9% | 67% | 100% | 1 | 3 fail |
| 8 | ma_crossover_swing | 31 | +0.2383 | [-0.218, +0.721] | 1.48 | 0.00 | 3.9% | 108% | 42% | 3 | 5 fail |
| 9 | h4_crossover_21_89_macd | 85 | +0.0299 | [-0.182, +0.242] | 1.06 | 1.05 | 10.7% | 120% | 25% | 5 | 3 fail |
| 10 | kpl_donchian_breakout | 165 | +0.0280 | [-0.131, +0.201] | 1.07 | 0.86 | 10.0% | 267% | 21% | 5 | 4 fail |
| 11 | kiss_h4 | 137 | +0.0225 | [-0.117, +0.156] | 1.06 | 0.64 | 7.8% | 182% | 37% | 3 | 4 fail |
| 12 | nnfx_backtrader | 49 | +0.1593 | [-0.259, +0.578] | 1.26 | 0.00 | 6.9% | 84% | 22% | 5 | 5 fail |
| 13 | mtf_swing_weekly_pivots | 101 | +0.0240 | [-0.246, +0.299] | 1.04 | 0.39 | 10.0% | 265% | 23% | 5 | 5 fail |
| 14 | currency_momentum_factor | 139 | +0.0013 | [-0.049, +0.055] | 1.01 | 0.17 | 5.2% | 1280% | 22% | 5 | 4 fail |
| 15 | holy_grail_pullback | 14 | +0.0119 | n/a | 1.04 | 0.00 | 1.5% | 1962% | 43% | 5 | 4 fail |
| 16 | vshape_swing_breakout | 686 | +0.0081 | [-0.064, +0.085] | 1.02 | 0.45 | 27.6% | 273% | 22% | 5 | 6 fail |
| 17 | pinbar_nose_eyes | 5 | -0.1944 | n/a | 0.41 | -0.00 | 1.1% | — | 40% | 4 | 4 fail |
| 18 | engulfing_broken_level | 19 | -0.1525 | n/a | 0.42 | -0.00 | 3.6% | — | 32% | 5 | 4 fail |
| 19 | inside_bar_pinbar_combo | 7 | -0.7377 | n/a | 0.43 | -0.00 | 7.8% | — | 29% | 5 | 5 fail |
| 20 | trending_retracement_daily | 20 | -0.1908 | [-0.455, +0.058] | 0.39 | -0.00 | 5.0% | — | 30% | 5 | 4 fail |
| 21 | xard_ma_cross_daily_open | 1041 | +0.0015 | [-0.087, +0.085] | 1.00 | 0.06 | 44.1% | 509% | 22% | 5 | 6 fail |
| 22 | janus_swing_system | 4 | -1.6271 | n/a | 0.24 | -0.00 | 8.4% | — | 50% | 3 | 5 fail |
| 23 | liquidity_sweep_ob | 17 | -0.8369 | n/a | 0.13 | -0.00 | 13.4% | — | 29% | 5 | 5 fail |
| 24 | bb_midline_break | 331 | -0.0207 | [-0.154, +0.108] | 0.97 | -0.61 | 18.9% | — | 24% | 5 | 4 fail |
| 25 | smash_days | 166 | -0.0407 | [-0.219, +0.157] | 0.92 | -0.97 | 14.7% | — | 24% | 5 | 4 fail |
| 26 | weekly_day_reversal_ea | 71 | -0.1495 | [-0.925, +0.830] | 0.84 | -0.77 | 19.0% | — | 30% | 5 | 5 fail |
| 27 | riding_trend_retracement | 43 | -1.0718 | [-2.014, -0.236] | 0.31 | -0.00 | 41.3% | — | 44% | 5 | 6 fail |
| 28 | ema_cross_h4_filter_bot | 848 | -0.0229 | [-0.115, +0.072] | 0.97 | -0.91 | 43.3% | — | 25% | 5 | 6 fail |
| 29 | Trend_Donchian_H4 | 856 | -0.0255 | [-0.120, +0.071] | 0.96 | -1.05 | 35.7% | — | 20% | 5 | 6 fail |
| 30 | macd_divergence | 204 | -0.0204 | [-0.070, +0.027] | 0.80 | -1.72 | 7.3% | — | 22% | 5 | 4 fail |
| 31 | weekly_gap_fade | 434 | -0.0140 | [-0.045, +0.016] | 0.89 | -1.85 | 8.2% | — | 25% | 5 | 4 fail |
| 32 | Range_Bollinger_Aggressive | 1227 | -0.0213 | [-0.078, +0.033] | 0.96 | -1.27 | 41.6% | — | 21% | 5 | 5 fail |
| 33 | demark_fractal_breakout | 1273 | -0.0192 | [-0.064, +0.026] | 0.94 | -1.60 | 38.6% | — | 21% | 5 | 6 fail |
| 34 | inside_bar_reversal | 205 | -0.0979 | [-0.306, +0.148] | 0.82 | -1.81 | 39.9% | — | 21% | 5 | 5 fail |
| 35 | pinbar_key_level_50pct | 27 | -0.6433 | [-1.681, +0.760] | 0.52 | -2.74 | 22.6% | — | 41% | 5 | 5 fail |
| 36 | reps_donchian_pyramiding | 98 | -0.2026 | [-0.550, +0.197] | 0.73 | -2.82 | 23.2% | — | 22% | 5 | 5 fail |
| 37 | outside_hma_klinger | 635 | -0.0424 | [-0.100, +0.013] | 0.88 | -2.90 | 31.9% | — | 25% | 5 | 5 fail |
| 38 | inside_bar_continuation_ea | 170 | -0.0916 | [-0.232, +0.043] | 0.81 | -3.54 | 17.2% | — | 25% | 5 | 4 fail |
| 39 | Range_Bollinger_H4 | 623 | -0.0719 | [-0.151, +0.003] | 0.86 | -3.10 | 45.6% | — | 21% | 5 | 5 fail |
| 40 | Trend_Donchian_VCP | 465 | -0.1439 | [-0.311, +0.034] | 0.82 | -3.26 | 64.7% | — | 21% | 5 | 6 fail |
| 41 | Trend_EMA_ADX_MultiTF | 307 | -0.1430 | [-0.277, -0.005] | 0.79 | -4.18 | 41.7% | — | 23% | 5 | 6 fail |
| 42 | Trend_EMA_ADX_H4 | 307 | -0.1430 | [-0.286, +0.002] | 0.79 | -4.18 | 42.1% | — | 23% | 5 | 6 fail |
| 43 | liquidity_grab_fade | 328 | -0.0690 | [-0.122, -0.014] | 0.60 | -5.02 | 21.3% | — | 22% | 5 | 4 fail |
| 44 | amazing_crossover | 1868 | -0.0285 | [-0.052, -0.006] | 0.85 | -4.75 | 44.6% | — | 25% | 5 | 5 fail |
| 45 | three_candle_swing_reversal | 69 | -0.3192 | [-0.666, +0.018] | 0.58 | -5.65 | 27.3% | — | 38% | 3 | 6 fail |
| 46 | adx_trend_pullback_ea | 1585 | -0.0848 | [-0.155, -0.014] | 0.88 | -4.70 | 79.4% | — | 21% | 5 | 6 fail |
| 47 | Range_Bollinger_H1 | 4011 | -0.0466 | [-0.077, -0.017] | 0.91 | -5.04 | 89.0% | — | 22% | 5 | 5 fail |
| 48 | weekly_range_reversal | 17 | -0.7543 | n/a | 0.21 | -10.15 | 13.3% | — | 41% | 5 | 5 fail |
| 49 | Trend_EMA_ADX_H1 | 3744 | -0.0952 | [-0.132, -0.058] | 0.84 | -9.48 | 98.4% | — | 22% | 5 | 6 fail |
| 50 | Trend_Donchian_H1 | 6828 | -0.0845 | [-0.114, -0.054] | 0.86 | -10.46 | 99.8% | — | 21% | 5 | 6 fail |
| 51 | smashing_forex_2 | 959 | -0.4419 | [-0.546, -0.333] | 0.50 | -15.67 | 99.1% | — | 43% | 5 | 6 fail |
