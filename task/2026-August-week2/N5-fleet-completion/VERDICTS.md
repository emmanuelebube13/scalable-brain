# N5 — verdict ledger

One row per strategy, appended when its harness run completes. Never edited afterwards.
Gates (all must pass): PF >= 1.50 · Sharpe >= 0.80 · MaxDD <= 25% · WinRate >= 40% ·
Recovery >= 3.00 · OOS >= 60 months.

| batch | strategy_id | gran | pairs | cells pass/total | OOS trades | PF | Sharpe | MaxDD | verdict | note |
|--:|---|---|--:|---|--:|--:|--:|--:|---|---|
| 0 | kiss_h4 | H4 | 5 | 0/3 | 286 | 0.86 | -0.42 | 23.86% | FAIL | skipped EUR_JPY, GBP_JPY |
| 0 | janus_swing_system | D1 | 11 | 0/5 | 6 | 0.33 | -0.52 | 8.37% | INSUFFICIENT | only 6 OOS trades |
| 0 | kpl_donchian_breakout | D1 | 13 | 0/5 | 359 | 0.86 | -0.43 | 24.10% | FAIL | 8 pairs skipped |
| 1 | smash_days | D1 | 5 | 0/5 | 2 | 0.00 | -3.60 | 0.37% | INSUFFICIENT | only 2 OOS trades |
| 1 | macd_divergence | H4 | 5 | 0/5 | 441 | 1.10 | 0.16 | 5.82% | FAIL | |
| 1 | pinbar_nose_eyes | H4 | 5 | 0/5 | 14 | 0.92 | -0.05 | 3.07% | FAIL | |
| 1 | trending_retracement_daily | D1 | 5 | 0/5 | 4 | 0.98 | -0.01 | 1.00% | FAIL | |
| 1 | vshape_swing_breakout | H4 | 5 | 0/5 | 2369 | 0.91 | -0.58 | 42.66% | FAIL | |
| 1 | ma_crossover_swing | D1 | 3 | 0/3 | 69 | 1.21 | 0.27 | 6.30% | FAIL | |
| 1 | weekly_day_reversal_ea | D1 | 5 | 0/5 | 150 | 1.08 | 0.15 | 8.57% | FAIL | |
| 1 | precision_swing | H4 | 5 | 0/5 | 543 | 1.04 | 0.19 | 27.39% | FAIL | |
| 2 | long_wick_pinbar_8ema | D1 | 3 | 0/3 | 98 | 0.93 | -0.13 | 15.95% | FAIL | |
| 2 | liquidity_sweep_ob | H4 | 5 | 0/5 | 14 | 1.05 | 0.03 | 6.93% | FAIL | |
| 2 | pinbar_key_level_50pct | D1 | 5 | 0/5 | 53 | 0.76 | -0.23 | 25.34% | FAIL | |
| 2 | liquidity_grab_fade | H1 | 5 | 0/5 | 737 | 0.66 | -0.96 | 19.69% | FAIL | |
| 2 | three_candle_swing_reversal | D1 | 3 | 0/3 | 12 | 0.68 | -0.25 | 2.01% | FAIL | |
| 2 | psar_gbpjpy_daily | D1 | 1 | 0/0 | 0 | 0.00 | 0.00 | 0.00% | INSUFFICIENT | GBP_JPY missing |
| 2 | smashing_forex_2 | D1 | 5 | 0/5 | 1911 | 0.50 | -4.19 | 100.00% | FAIL | |
| 2 | xard_ma_cross_daily_open | H1 | 5 | 0/5 | 2115 | 1.00 | 0.02 | 72.18% | FAIL | |
| 3 | nzdjpy_median_ma_retrace | D1 | 1 | 0/0 | 0 | 0.00 | 0.00 | 0.00% | INSUFFICIENT | NZD_JPY missing |
| 3 | h4_crossover_21_89_macd | H4 | 5 | 0/5 | 200 | 1.00 | 0.01 | 12.36% | FAIL | |
| 3 | nnfx_backtrader | D1 | 5 | 0/5 | 113 | 1.63 | 0.94 | 12.37% | PASS | |
| 3 | mtf_swing_weekly_pivots | D1 | 5 | 0/5 | 233 | 0.93 | -0.20 | 19.27% | FAIL | |
| 3 | outside_hma_klinger | H4 | 5 | 0/5 | 1291 | 0.85 | -1.07 | 56.06% | FAIL | |
| 3 | smart_money_swing | H4 | 5 | 0/5 | 1246 | 0.92 | -0.44 | 33.74% | FAIL | |
| 3 | riding_trend_retracement | H4 | 5 | 0/5 | 40 | 0.57 | -0.55 | 24.62% | FAIL | |
| 4 | reps_donchian_pyramiding | D1 | 5 | 0/5 | 241 | 0.81 | -0.38 | 20.25% | FAIL | rebuilt 2026-08-16; prior module emitted 0 orders (invalid OrderIntent/ExitLeg) and was never measured — this is its first verdict |
| 3 | strong_weak_analysis | D1 | 5 | 0/5 | 295 | 1.24 | 0.36 | 7.94% | FAIL | strength-rank gate unreachable (one pair per call); trend+pullback skeleton only |
| 3 | weekly_range_reversal | H1 | 5 | 0/5 | 45 | 0.41 | -0.88 | 24.88% | FAIL | 8.9% win rate on a 1-pip-beyond-the-extreme stop; only ~1 trade/pair/year, an order of magnitude below the spec's §11 estimate |
| 3 | retail_sentiment_fade | D1 | 3 | 0/0 | 0 | 0.00 | 0.00 | 0.00% | UNMEASURABLE | retail positioning feed absent for every pair; emits 0 orders by design, no price proxy. Quick audit PASSes; full audit REALDATA fails on "emits no orders anywhere" — see batch review |
| 4 | sunday_breakout | H4 | 1 | 0/1 | 344 | 0.90 | -0.28 | 40.10% | FAIL | only GBP_USD exists (EUR_JPY absent); ~49 trades/yr vs the intended <=52 weekly cap — no OCO, so sibling stop-orders add same-week second entries (§10 #8) |
| 4 | weekly_gap_fade | H1 | 5 | 0/5 | 944 | 0.96 | -0.18 | 11.91% | FAIL | largest sample in the fleet; near-even coin (48.2% wins) with PF just under 1 across all 5 pairs; 5-pip threshold is looser than the author's 10-20 pip reality (no spread feed) |
