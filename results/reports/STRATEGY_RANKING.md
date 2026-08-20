# Strategy ranking — pooled OOS trades

Generated 2026-08-17T01:28:43.731502+00:00 · 51 strategies with OOS trades
· **0 pass every gate** · 2 have a mean-R CI clear of zero

`tail` = share of total R that disappears when the top 3 winners are removed. `maxPair` = share of trades in the largest pair. Both are here because the composite score alone has twice pointed at something that was not real.

| # | strategy | n | meanR | 95% CI | PF | Sharpe | MaxDD | tail | maxPair | pairs | gates |
|--:|---|--:|--:|---|--:|--:|--:|--:|--:|--:|---|
| 1 | Range_Stochastic_Divergence | 90 | +0.4299 | [+0.249, +0.604] | 2.60 | 2.33 | 3.4% | 8% | 27% | 5 | DISQUALIFIED |
| 2 | nnfx_backtrader | 114 | +0.3376 | [+0.049, +0.620] | 1.61 | 1.22 | 12.4% | 18% | 24% | 5 | 1 fail |
| 3 | reference_pullback_continuation | 59 | +0.2511 | [-0.068, +0.565] | 1.56 | 0.83 | 4.1% | 40% | 56% | 2 | 1 fail |
| 4 | weekly_day_reversal_ea | 142 | +0.4764 | [-0.155, +1.151] | 1.56 | 0.72 | 17.4% | 80% | 25% | 5 | 3 fail |
| 5 | double_bottom_measured_move | 34 | +0.1494 | [-0.121, +0.415] | 1.46 | 0.57 | 3.1% | 56% | 29% | 5 | 4 fail |
| 6 | bb_midline_break | 775 | +0.0456 | [-0.040, +0.132] | 1.08 | 0.52 | 17.0% | 17% | 22% | 5 | 4 fail |
| 7 | ma_crossover_swing | 69 | +0.0911 | [-0.211, +0.399] | 1.17 | 0.32 | 10.1% | 127% | 35% | 3 | 5 fail |
| 8 | holy_grail_pullback | 32 | +0.0244 | [-0.220, +0.253] | 1.09 | 0.10 | 2.6% | 418% | 34% | 5 | 4 fail |
| 9 | macd_divergence | 441 | +0.0011 | [-0.027, +0.027] | 1.02 | 0.04 | 6.6% | 652% | 24% | 5 | 4 fail |
| 10 | precision_swing | 542 | +0.0260 | [-0.067, +0.120] | 1.05 | 0.27 | 27.4% | 30% | 22% | 5 | 5 fail |
| 11 | h4_crossover_21_89_macd | 198 | +0.0022 | [-0.134, +0.141] | 1.00 | 0.02 | 12.4% | 717% | 23% | 5 | 4 fail |
| 12 | long_wick_pinbar_8ema | 98 | -0.0228 | [-0.300, +0.260] | 0.97 | -0.08 | 15.1% | — | 38% | 3 | 5 fail |
| 13 | weekly_gap_fade | 941 | -0.0040 | [-0.025, +0.016] | 0.97 | -0.20 | 11.6% | — | 22% | 5 | 4 fail |
| 14 | h4_forex_system | 183 | -0.0234 | [-0.158, +0.112] | 0.95 | -0.17 | 15.9% | — | 100% | 1 | 4 fail |
| 15 | currency_momentum_factor | 300 | -0.0149 | [-0.050, +0.021] | 0.89 | -0.42 | 7.8% | — | 21% | 5 | 4 fail |
| 16 | engulfing_broken_level | 48 | -0.0609 | [-0.226, +0.093] | 0.73 | -0.38 | 4.3% | — | 29% | 5 | 4 fail |
| 17 | mtf_swing_weekly_pivots | 231 | -0.0538 | [-0.232, +0.126] | 0.92 | -0.30 | 19.3% | — | 22% | 5 | 5 fail |
| 18 | Range_Bollinger_H4 | 1281 | -0.0088 | [-0.063, +0.046] | 0.98 | -0.16 | 33.0% | — | 21% | 5 | 5 fail |
| 19 | pinbar_nose_eyes | 14 | -0.1015 | n/a | 0.61 | -0.55 | 2.5% | — | 36% | 5 | 4 fail |
| 20 | trending_retracement_daily | 50 | -0.0808 | [-0.239, +0.073] | 0.66 | -0.52 | 6.8% | — | 22% | 5 | 4 fail |
| 21 | strong_weak_analysis | 136 | -0.1106 | [-0.326, +0.119] | 0.81 | -0.50 | 21.8% | — | 24% | 5 | 5 fail |
| 22 | kiss_h4 | 286 | -0.0474 | [-0.134, +0.039] | 0.87 | -0.55 | 23.7% | — | 35% | 3 | 4 fail |
| 23 | kpl_donchian_breakout | 360 | -0.0554 | [-0.155, +0.048] | 0.86 | -0.54 | 23.9% | — | 21% | 5 | 5 fail |
| 24 | xard_ma_cross_daily_open | 2114 | +0.0019 | [-0.057, +0.062] | 1.00 | 0.03 | 72.2% | 176% | 22% | 5 | 6 fail |
| 25 | janus_swing_system | 6 | -0.9561 | n/a | 0.33 | -0.66 | 8.4% | — | 33% | 5 | 4 fail |
| 26 | inside_bar_continuation_ea | 352 | -0.0593 | [-0.156, +0.034] | 0.88 | -0.61 | 29.0% | — | 25% | 5 | 5 fail |
| 27 | demark_fractal_breakout | 2682 | -0.0113 | [-0.042, +0.020] | 0.96 | -0.36 | 58.5% | — | 21% | 5 | 5 fail |
| 28 | Range_Bollinger_Aggressive | 2563 | -0.0159 | [-0.053, +0.022] | 0.97 | -0.41 | 59.0% | — | 21% | 5 | 5 fail |
| 29 | smash_days | 350 | -0.1040 | [-0.235, +0.032] | 0.81 | -0.77 | 32.6% | — | 22% | 5 | 5 fail |
| 30 | inside_bar_pinbar_combo | 17 | -0.6510 | n/a | 0.41 | -1.01 | 14.6% | — | 24% | 5 | 5 fail |
| 31 | ema_cross_h4_filter_bot | 1808 | -0.0337 | [-0.099, +0.031] | 0.95 | -0.51 | 62.9% | — | 24% | 5 | 6 fail |
| 32 | vshape_swing_breakout | 1473 | -0.0326 | [-0.080, +0.018] | 0.91 | -0.66 | 58.6% | — | 21% | 5 | 6 fail |
| 33 | pinbar_key_level_50pct | 58 | -0.6231 | [-1.235, +0.135] | 0.50 | -0.89 | 38.2% | — | 31% | 5 | 6 fail |
| 34 | inside_bar_reversal | 460 | -0.1177 | [-0.240, +0.019] | 0.76 | -0.89 | 44.9% | — | 22% | 5 | 5 fail |
| 35 | weekly_range_reversal | 45 | -0.5476 | [-0.920, -0.043] | 0.41 | -1.25 | 24.9% | — | 24% | 5 | 5 fail |
| 36 | amazing_crossover | 3973 | -0.0152 | [-0.030, +0.000] | 0.91 | -0.98 | 54.3% | — | 24% | 5 | 5 fail |
| 37 | three_candle_swing_reversal | 145 | -0.3342 | [-0.661, -0.045] | 0.60 | -1.10 | 45.6% | — | 37% | 3 | 6 fail |
| 38 | outside_hma_klinger | 1290 | -0.0550 | [-0.093, -0.016] | 0.85 | -1.38 | 55.3% | — | 26% | 5 | 5 fail |
| 39 | Trend_Donchian_VCP | 1001 | -0.1202 | [-0.239, +0.002] | 0.85 | -1.01 | 80.3% | — | 21% | 5 | 6 fail |
| 40 | adx_trend_pullback_ea | 3433 | -0.0487 | [-0.093, -0.002] | 0.93 | -1.03 | 88.4% | — | 21% | 5 | 6 fail |
| 41 | riding_trend_retracement | 61 | -0.8235 | [-1.515, -0.199] | 0.36 | -1.62 | 45.3% | — | 34% | 5 | 6 fail |
| 42 | Trend_Donchian_H4 | 1834 | -0.0736 | [-0.136, -0.010] | 0.89 | -1.15 | 85.3% | — | 20% | 5 | 6 fail |
| 43 | Trend_EMA_ADX_H4 | 664 | -0.1403 | [-0.230, -0.049] | 0.79 | -1.47 | 68.3% | — | 21% | 5 | 6 fail |
| 44 | Trend_EMA_ADX_MultiTF | 664 | -0.1403 | [-0.230, -0.049] | 0.79 | -1.47 | 68.3% | — | 21% | 5 | 6 fail |
| 45 | liquidity_grab_fade | 735 | -0.0517 | [-0.076, -0.028] | 0.51 | -2.11 | 32.4% | — | 21% | 5 | 5 fail |
| 46 | liquidity_sweep_ob | 39 | -1.0432 | [-1.607, -0.608] | 0.13 | -2.34 | 34.6% | — | 26% | 5 | 6 fail |
| 47 | Range_Bollinger_H1 | 8312 | -0.0490 | [-0.071, -0.028] | 0.90 | -2.28 | 98.9% | — | 22% | 5 | 5 fail |
| 48 | reps_donchian_pyramiding | 216 | -0.5259 | [-0.697, -0.336] | 0.36 | -2.83 | 68.6% | — | 26% | 5 | 6 fail |
| 49 | Trend_Donchian_H1 | 14261 | -0.0816 | [-0.102, -0.061] | 0.87 | -3.85 | 100.0% | — | 21% | 5 | 6 fail |
| 50 | Trend_EMA_ADX_H1 | 7949 | -0.1004 | [-0.126, -0.075] | 0.83 | -3.86 | 100.0% | — | 21% | 5 | 6 fail |
| 51 | smashing_forex_2 | 1909 | -0.4867 | [-0.562, -0.407] | 0.47 | -6.12 | 100.0% | — | 46% | 5 | 6 fail |
