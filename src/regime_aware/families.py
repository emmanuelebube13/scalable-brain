"""
R2 — Strategy family taxonomy and pre-registered regime masks.
"""
from typing import Dict, TypedDict
from src.regime_aware.contract import ParamBlock

class FamilyAssignment(TypedDict):
    family: str
    universe: str
    evidence: str

STRATEGY_FAMILIES: Dict[str, FamilyAssignment] = {
    "adx_trend_pullback_ea": {"family": "trend_following", "universe": "v2", "evidence": 'ADX Trend Pullback EA — row 38 of ``forex_swing_strategies.'},
    "amazing_crossover": {"family": "mean_reversion", "universe": "v2", "evidence": 'Amazing Crossover — EMA(5)/EMA(10) cross confirmed by RSI(10, median) at 50.'},
    "bb_midline_break": {"family": "mean_reversion", "universe": "v2", "evidence": 'bb_midline_break — Bollinger 2-sigma excursion, then a decisive midline break.'},
    "bollinger_aggressive": {"family": "mean_reversion", "universe": "legacy", "evidence": 'Regime-aware port of Range_Bollinger_Aggressive.'},
    "bollinger_h1": {"family": "mean_reversion", "universe": "legacy", "evidence": 'Regime-aware port of Range_Bollinger_H1.'},
    "bollinger_h4": {"family": "mean_reversion", "universe": "legacy", "evidence": 'Regime-aware port of Range_Bollinger_H4.'},
    "currency_momentum_factor": {"family": "mean_reversion", "universe": "v2", "evidence": 'The two inversions cancel:          USD-quote pair (EUR_USD): mom_EUR = C(t)/C(t-252) - 1.'},
    "daily_fib_retracement": {"family": "trend_following", "universe": "v2", "evidence": 'There is **no context frame** (spec §2: `context_granularities: none`), so `closed_context_frame` / `merge_asof` do not appear here — the trend filter is an EMA on the D1 decision frame itself, and th'},
    "demark_fractal_breakout": {"family": "breakout", "universe": "v2", "evidence": 'demark_fractal_breakout — SPEC-demark_fractal_breakout (row 48).'},
    "donchian_h1": {"family": "breakout", "universe": "legacy", "evidence": 'Regime-aware port of Trend_Donchian_H1.'},
    "donchian_h4": {"family": "breakout", "universe": "legacy", "evidence": 'Regime-aware port of Trend_Donchian_H4.'},
    "donchian_vcp": {"family": "breakout", "universe": "legacy", "evidence": 'Regime-aware port of ``Trend_Donchian_VCP``.'},
    "double_bottom_measured_move": {"family": "mean_reversion", "universe": "v2", "evidence": 'com/bottom-fishing-trading-how-to-find-reversals  D1-only pattern strategy (spec §2: ``context_granularities: none``).'},
    "ema_adx_h1": {"family": "trend_following", "universe": "legacy", "evidence": 'Regime-aware port of Trend_EMA_ADX_H1.'},
    "ema_adx_h4": {"family": "trend_following", "universe": "legacy", "evidence": 'Regime-aware port of Trend_EMA_ADX_H4.'},
    "ema_adx_multitf": {"family": "trend_following", "universe": "legacy", "evidence": 'Regime-aware port of Trend_EMA_ADX_MultiTF.'},
    "ema_cross_h4_filter_bot": {"family": "trend_following", "universe": "v2", "evidence": 'ema_cross_h4_filter_bot — H1 EMA9/21 cross gated by an H4 EMA200 regime.'},
    "engulfing_broken_level": {"family": "mean_reversion", "universe": "v2", "evidence": 'D1 engulfing candle at a confirmed swing extreme that breaks a nearby confirmed swing level by close — the "trapped trader" reversal (spec §1).'},
    "h4_box_breakout": {"family": "breakout", "universe": "v2", "evidence": 'h4_box_breakout — weekly opening-range ("box") breakout on JPY crosses.'},
    "h4_crossover_21_89_macd": {"family": "unclassified", "universe": "v2", "evidence": 'No docstring available.'},
    "h4_forex_system": {"family": "trend_following", "universe": "v2", "evidence": 'h4_forex_system — 6 EMA / 13 SMA cross confirmed by a same-bar MACD cross and Parabolic SAR position, on H4 GBP pairs.'},
    "holy_grail_pullback": {"family": "trend_following", "universe": "v2", "evidence": 'Holy Grail Pullback — row 29 of ``forex_swing_strategies.'},
    "inside_bar_continuation_ea": {"family": "breakout", "universe": "v2", "evidence": 'INSIDE_BAR_CONTINUATION_EA — inside-bar breakout continuation.'},
    "inside_bar_pinbar_combo": {"family": "unclassified", "universe": "v2", "evidence": 'inside_bar_pinbar_combo strategy.'},
    "inside_bar_reversal": {"family": "mean_reversion", "universe": "v2", "evidence": 'inside_bar_reversal — counter-trend inside-bar reversal off the nearest confirmed swing.'},
    "janus_swing_system": {"family": "unclassified", "universe": "v2", "evidence": 'No docstring available.'},
    "kiss_h4": {"family": "unclassified", "universe": "v2", "evidence": 'No docstring available.'},
    "kpl_donchian_breakout": {"family": "unclassified", "universe": "v2", "evidence": 'No docstring available.'},
    "liquidity_grab_fade": {"family": "mean_reversion", "universe": "v2", "evidence": 'liquidity_grab_fade strategy  Source: row 46 of forex_swing_strategies.'},
    "liquidity_sweep_ob": {"family": "breakout", "universe": "v2", "evidence": 'liquidity_sweep_ob strategy from howtotrade.'},
    "long_wick_pinbar_8ema": {"family": "trend_following", "universe": "v2", "evidence": 'Long Wick Pinbar 8 EMA Strategy.'},
    "ma_crossover_swing": {"family": "trend_following", "universe": "v2", "evidence": 'ma_crossover_swing strategy.'},
    "macd_divergence": {"family": "mean_reversion", "universe": "v2", "evidence": 'MACD Divergence strategy: Buy lower lows in price with higher lows in MACD.'},
    "mtf_swing_weekly_pivots": {"family": "trend_following", "universe": "v2", "evidence": 'Trend-aligned pullback entry using D1 regime and H4 EMA pullbacks.'},
    "nnfx_backtrader": {"family": "unclassified", "universe": "v2", "evidence": 'No docstring available.'},
    "nzdjpy_median_ma_retrace": {"family": "trend_following", "universe": "v2", "evidence": 'Counter-trend-within-strength edge: when the fast median-price average dips below the slow median-price average (a short-term retrace) during the London morning window, price is statistically more lik'},
    "outside_hma_klinger": {"family": "unclassified", "universe": "v2", "evidence": 'Advanced OutSide with HMA and Klinger Forex Swing strategy.'},
    "pinbar_key_level_50pct": {"family": "unclassified", "universe": "v2", "evidence": 'Pin-bar key level 50% retracement strategy.'},
    "pinbar_nose_eyes": {"family": "unclassified", "universe": "v2", "evidence": 'Pinbar Trading System (Nose & Eyes).'},
    "precision_swing": {"family": "unclassified", "universe": "v2", "evidence": 'No docstring available.'},
    "psar_gbpjpy_daily": {"family": "mean_reversion", "universe": "v2", "evidence": 'GBP/JPY daily trends persist for weeks at a time.'},
    "reference_pullback_continuation": {"family": "trend_following", "universe": "v2", "evidence": 'It is a deliberately synthetic example that exercises every hard feature the real ones need, so there is one correct pattern to imitate instead of 51 inventions:  * a **multi-timeframe filter** (D1 tr'},
    "reps_donchian_pyramiding": {"family": "breakout", "universe": "v2", "evidence": 'REPS Donchian Pyramiding — implementation of SPEC-reps_donchian_pyramiding.'},
    "retail_sentiment_fade": {"family": "mean_reversion", "universe": "v2", "evidence": 'Retail Sentiment Fade — SPEC-retail_sentiment_fade.'},
    "riding_trend_retracement": {"family": "trend_following", "universe": "v2", "evidence": 'Riding Trend Retracement Strategy.'},
    "smart_money_swing": {"family": "unclassified", "universe": "v2", "evidence": 'No docstring available.'},
    "smash_days": {"family": "trend_following", "universe": "v2", "evidence": 'Smash Days Strategy.'},
    "smashing_forex_2": {"family": "trend_following", "universe": "v2", "evidence": 'Smashing Forex 2 strategy.'},
    "strong_weak_analysis": {"family": "trend_following", "universe": "v2", "evidence": 'Rank the 8 majors by relative strength, trade the strongest currency against the weakest, entering on a pullback to confirmed D1 structure in the direction of the D1 trend.'},
    "sunday_breakout": {"family": "breakout", "universe": "v2", "evidence": 'Sunday Breakout — SPEC-sunday_breakout.'},
    "three_candle_swing_reversal": {"family": "mean_reversion", "universe": "v2", "evidence": 'Daily Chart 3-Candle Swing Reversal Strategy.'},
    "trending_retracement_daily": {"family": "trend_following", "universe": "v2", "evidence": 'Trading in Trending with Retracement.'},
    "vshape_swing_breakout": {"family": "breakout", "universe": "v2", "evidence": 'vshape_swing_breakout strategy.'},
    "weekly_day_reversal_ea": {"family": "mean_reversion", "universe": "v2", "evidence": 'Weekly Day Reversal EA.'},
    "weekly_gap_fade": {"family": "mean_reversion", "universe": "v2", "evidence": 'Weekly Gap Fade — SPEC-weekly_gap_fade.'},
    "weekly_range_reversal": {"family": "mean_reversion", "universe": "v2", "evidence": 'Weekly Range Reversal — SPEC-weekly_range_reversal.'},
    "xard_ma_cross_daily_open": {"family": "trend_following", "universe": "v2", "evidence": 'Xard MA Cross Daily Open strategy.'},
}

# The mask vocabulary is the existing one — Trending-Up, Trending-Down, Ranging, High-Vol, UNKNOWN.
# Masks are derived from the strategy family. Parameter blocks differ only in 'enabled'.
# UNKNOWN is always disabled.
REGIME_MASKS: Dict[str, Dict[str, ParamBlock]] = {
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
