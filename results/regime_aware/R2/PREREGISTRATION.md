# Strategy Family Taxonomy and Regime Masks Preregistration

**Timestamp:** 2026-08-16T19:07:41Z

**Explicit Statement:** No per-regime performance data was consulted during the assignment of these families or masks. The assignments are derived entirely from the declared strategy logic (code and docstrings), acting as hypotheses for regime-aware execution.

## Family Taxonomy

| Family | Favourable regimes | Sits out |
|---|---|---|
| `trend_following` | `Trending-Up`, `Trending-Down` | `Ranging`, `High-Vol`, `UNKNOWN` |
| `mean_reversion` | `Ranging` | `Trending-Up`, `Trending-Down`, `High-Vol`, `UNKNOWN` |
| `breakout` | `High-Vol`, `Trending-Up`, `Trending-Down` | `Ranging`, `UNKNOWN` |
| `unclassified` | `Trending-Up`, `Trending-Down`, `Ranging`, `High-Vol` | `UNKNOWN` |

## Derived Masks

```python
REGIME_MASKS = {
    "trend_following": {
        "Trending-Up": ParamBlock(enabled=True),
        "Trending-Down": ParamBlock(enabled=True),
        "Ranging": ParamBlock(enabled=False),
        "High-Vol": ParamBlock(enabled=False),
        "UNKNOWN": ParamBlock(enabled=False),
    },
    "mean_reversion": {
        "Trending-Up": ParamBlock(enabled=False),
        "Trending-Down": ParamBlock(enabled=False),
        "Ranging": ParamBlock(enabled=True),
        "High-Vol": ParamBlock(enabled=False),
        "UNKNOWN": ParamBlock(enabled=False),
    },
    "breakout": {
        "Trending-Up": ParamBlock(enabled=True),
        "Trending-Down": ParamBlock(enabled=True),
        "Ranging": ParamBlock(enabled=False),
        "High-Vol": ParamBlock(enabled=True),
        "UNKNOWN": ParamBlock(enabled=False),
    },
    "unclassified": {
        "Trending-Up": ParamBlock(enabled=True),
        "Trending-Down": ParamBlock(enabled=True),
        "Ranging": ParamBlock(enabled=True),
        "High-Vol": ParamBlock(enabled=True),
        "UNKNOWN": ParamBlock(enabled=False),
    }
}
```

## Strategy Assignments

| Strategy | Universe | Family | Evidence |
|---|---|---|---|
| `adx_trend_pullback_ea` | `v2` | `trend_following` | ADX Trend Pullback EA — row 38 of ``forex_swing_strategies. |
| `amazing_crossover` | `v2` | `mean_reversion` | Amazing Crossover — EMA(5)/EMA(10) cross confirmed by RSI(10, median) at 50. |
| `bb_midline_break` | `v2` | `mean_reversion` | bb_midline_break — Bollinger 2-sigma excursion, then a decisive midline break. |
| `bollinger_aggressive` | `legacy` | `mean_reversion` | Regime-aware port of Range_Bollinger_Aggressive. |
| `bollinger_h1` | `legacy` | `mean_reversion` | Regime-aware port of Range_Bollinger_H1. |
| `bollinger_h4` | `legacy` | `mean_reversion` | Regime-aware port of Range_Bollinger_H4. |
| `currency_momentum_factor` | `v2` | `mean_reversion` | The two inversions cancel:          USD-quote pair (EUR_USD): mom_EUR = C(t)/C(t-252) - 1. |
| `daily_fib_retracement` | `v2` | `trend_following` | There is **no context frame** (spec §2: `context_granularities: none`), so `closed_context_frame` / `merge_asof` do not appear here — the trend filter is an EMA on the D1 decision frame itself, and th |
| `demark_fractal_breakout` | `v2` | `breakout` | demark_fractal_breakout — SPEC-demark_fractal_breakout (row 48). |
| `donchian_h1` | `legacy` | `breakout` | Regime-aware port of Trend_Donchian_H1. |
| `donchian_h4` | `legacy` | `breakout` | Regime-aware port of Trend_Donchian_H4. |
| `donchian_vcp` | `legacy` | `breakout` | Regime-aware port of ``Trend_Donchian_VCP``. |
| `double_bottom_measured_move` | `v2` | `mean_reversion` | com/bottom-fishing-trading-how-to-find-reversals  D1-only pattern strategy (spec §2: ``context_granularities: none``). |
| `ema_adx_h1` | `legacy` | `trend_following` | Regime-aware port of Trend_EMA_ADX_H1. |
| `ema_adx_h4` | `legacy` | `trend_following` | Regime-aware port of Trend_EMA_ADX_H4. |
| `ema_adx_multitf` | `legacy` | `trend_following` | Regime-aware port of Trend_EMA_ADX_MultiTF. |
| `ema_cross_h4_filter_bot` | `v2` | `trend_following` | ema_cross_h4_filter_bot — H1 EMA9/21 cross gated by an H4 EMA200 regime. |
| `engulfing_broken_level` | `v2` | `mean_reversion` | D1 engulfing candle at a confirmed swing extreme that breaks a nearby confirmed swing level by close — the "trapped trader" reversal (spec §1). |
| `h4_box_breakout` | `v2` | `breakout` | h4_box_breakout — weekly opening-range ("box") breakout on JPY crosses. |
| `h4_crossover_21_89_macd` | `v2` | `unclassified` | No docstring available. |
| `h4_forex_system` | `v2` | `trend_following` | h4_forex_system — 6 EMA / 13 SMA cross confirmed by a same-bar MACD cross and Parabolic SAR position, on H4 GBP pairs. |
| `holy_grail_pullback` | `v2` | `trend_following` | Holy Grail Pullback — row 29 of ``forex_swing_strategies. |
| `inside_bar_continuation_ea` | `v2` | `breakout` | INSIDE_BAR_CONTINUATION_EA — inside-bar breakout continuation. |
| `inside_bar_pinbar_combo` | `v2` | `unclassified` | inside_bar_pinbar_combo strategy. |
| `inside_bar_reversal` | `v2` | `mean_reversion` | inside_bar_reversal — counter-trend inside-bar reversal off the nearest confirmed swing. |
| `janus_swing_system` | `v2` | `unclassified` | No docstring available. |
| `kiss_h4` | `v2` | `unclassified` | No docstring available. |
| `kpl_donchian_breakout` | `v2` | `unclassified` | No docstring available. |
| `liquidity_grab_fade` | `v2` | `mean_reversion` | liquidity_grab_fade strategy  Source: row 46 of forex_swing_strategies. |
| `liquidity_sweep_ob` | `v2` | `breakout` | liquidity_sweep_ob strategy from howtotrade. |
| `long_wick_pinbar_8ema` | `v2` | `trend_following` | Long Wick Pinbar 8 EMA Strategy. |
| `ma_crossover_swing` | `v2` | `trend_following` | ma_crossover_swing strategy. |
| `macd_divergence` | `v2` | `mean_reversion` | MACD Divergence strategy: Buy lower lows in price with higher lows in MACD. |
| `mtf_swing_weekly_pivots` | `v2` | `trend_following` | Trend-aligned pullback entry using D1 regime and H4 EMA pullbacks. |
| `nnfx_backtrader` | `v2` | `unclassified` | No docstring available. |
| `nzdjpy_median_ma_retrace` | `v2` | `trend_following` | Counter-trend-within-strength edge: when the fast median-price average dips below the slow median-price average (a short-term retrace) during the London morning window, price is statistically more lik |
| `outside_hma_klinger` | `v2` | `unclassified` | Advanced OutSide with HMA and Klinger Forex Swing strategy. |
| `pinbar_key_level_50pct` | `v2` | `unclassified` | Pin-bar key level 50% retracement strategy. |
| `pinbar_nose_eyes` | `v2` | `unclassified` | Pinbar Trading System (Nose & Eyes). |
| `precision_swing` | `v2` | `unclassified` | No docstring available. |
| `psar_gbpjpy_daily` | `v2` | `mean_reversion` | GBP/JPY daily trends persist for weeks at a time. |
| `reference_pullback_continuation` | `v2` | `trend_following` | It is a deliberately synthetic example that exercises every hard feature the real ones need, so there is one correct pattern to imitate instead of 51 inventions:  * a **multi-timeframe filter** (D1 tr |
| `reps_donchian_pyramiding` | `v2` | `breakout` | REPS Donchian Pyramiding — implementation of SPEC-reps_donchian_pyramiding. |
| `retail_sentiment_fade` | `v2` | `mean_reversion` | Retail Sentiment Fade — SPEC-retail_sentiment_fade. |
| `riding_trend_retracement` | `v2` | `trend_following` | Riding Trend Retracement Strategy. |
| `smart_money_swing` | `v2` | `unclassified` | No docstring available. |
| `smash_days` | `v2` | `trend_following` | Smash Days Strategy. |
| `smashing_forex_2` | `v2` | `trend_following` | Smashing Forex 2 strategy. |
| `strong_weak_analysis` | `v2` | `trend_following` | Rank the 8 majors by relative strength, trade the strongest currency against the weakest, entering on a pullback to confirmed D1 structure in the direction of the D1 trend. |
| `sunday_breakout` | `v2` | `breakout` | Sunday Breakout — SPEC-sunday_breakout. |
| `three_candle_swing_reversal` | `v2` | `mean_reversion` | Daily Chart 3-Candle Swing Reversal Strategy. |
| `trending_retracement_daily` | `v2` | `trend_following` | Trading in Trending with Retracement. |
| `vshape_swing_breakout` | `v2` | `breakout` | vshape_swing_breakout strategy. |
| `weekly_day_reversal_ea` | `v2` | `mean_reversion` | Weekly Day Reversal EA. |
| `weekly_gap_fade` | `v2` | `mean_reversion` | Weekly Gap Fade — SPEC-weekly_gap_fade. |
| `weekly_range_reversal` | `v2` | `mean_reversion` | Weekly Range Reversal — SPEC-weekly_range_reversal. |
| `xard_ma_cross_daily_open` | `v2` | `trend_following` | Xard MA Cross Daily Open strategy. |
