"""
Layer 2 Config Adapter
======================

Translates qualified Layer 0 strategies into PostgreSQL INSERT ... ON CONFLICT scripts that populate
the Layer 2 data-driven signal engine tables:
    - Dim_Strategy
    - Dim_Strategy_Config
    - Dim_Strategy_Asset_Mapping

This enables Option B (Automated) promotion from Layer 0 to Layer 2.
"""

import json
import hashlib
from typing import Dict, List, Any, Optional
from datetime import datetime

import pandas as pd


def _compute_config_hash(indicator_configs: List[Dict], 
                         signal_rules: List[Dict],
                         risk_filters: Optional[List[Dict]]) -> str:
    """Compute SHA-256 hash matching Layer 2 StrategyConfig.compute_hash()."""
    data = {
        "indicator_configs": indicator_configs,
        "signal_rules": signal_rules,
        "risk_filters": risk_filters
    }
    config_str = json.dumps(data, sort_keys=True)
    return hashlib.sha256(config_str.encode()).hexdigest()


def _safe_sql_string(value: str) -> str:
    """Escape single quotes for PostgreSQL strings."""
    return value.replace("'", "''")


# =============================================================================
# Strategy catalog: metadata, indicator configs, and signal rules
# =============================================================================

STRATEGY_CATALOG: Dict[str, Dict[str, Any]] = {
    # -------------------------------------------------------------------------
    # Trend EMA ADX family
    # -------------------------------------------------------------------------
    "Trend_EMA_ADX_H1": {
        "strategy_type": "TREND",
        "description": "H1 EMA crossover (10/20) with ADX filter.",
        "granularity": "H1",
        "indicators": [
            {"indicator_key": "EMA", "instance_name": "EMA_10", "params": {"window": 10}, "output_column": "ema_indicator"},
            {"indicator_key": "EMA", "instance_name": "EMA_20", "params": {"window": 20}, "output_column": "ema_indicator"},
            {"indicator_key": "ADX", "instance_name": "ADX_14", "params": {"window": 14}, "output_column": "adx"},
        ],
        "rules": [
            {
                "rule_id": "LONG_EMA_ADX",
                "description": "EMA10 crosses above EMA20 with ADX > 25",
                "signal_value": 1,
                "conditions": [
                    {"left": "EMA_10", "operator": "cross_above", "right": "EMA_20"},
                    {"left": "ADX_14", "operator": ">", "right": 25},
                ],
                "logic": "AND",
            },
            {
                "rule_id": "SHORT_EMA_ADX",
                "description": "EMA10 crosses below EMA20 with ADX > 25",
                "signal_value": -1,
                "conditions": [
                    {"left": "EMA_10", "operator": "cross_below", "right": "EMA_20"},
                    {"left": "ADX_14", "operator": ">", "right": 25},
                ],
                "logic": "AND",
            },
        ],
        "risk_filters": None,
    },
    "Trend_EMA_ADX_H4": {
        "strategy_type": "TREND",
        "description": "H4 EMA crossover (20/50) with ADX filter.",
        "granularity": "H4",
        "indicators": [
            {"indicator_key": "EMA", "instance_name": "EMA_20", "params": {"window": 20}, "output_column": "ema_indicator"},
            {"indicator_key": "EMA", "instance_name": "EMA_50", "params": {"window": 50}, "output_column": "ema_indicator"},
            {"indicator_key": "ADX", "instance_name": "ADX_14", "params": {"window": 14}, "output_column": "adx"},
        ],
        "rules": [
            {
                "rule_id": "LONG_EMA_ADX",
                "description": "EMA20 crosses above EMA50 with ADX > 25",
                "signal_value": 1,
                "conditions": [
                    {"left": "EMA_20", "operator": "cross_above", "right": "EMA_50"},
                    {"left": "ADX_14", "operator": ">", "right": 25},
                ],
                "logic": "AND",
            },
            {
                "rule_id": "SHORT_EMA_ADX",
                "description": "EMA20 crosses below EMA50 with ADX > 25",
                "signal_value": -1,
                "conditions": [
                    {"left": "EMA_20", "operator": "cross_below", "right": "EMA_50"},
                    {"left": "ADX_14", "operator": ">", "right": 25},
                ],
                "logic": "AND",
            },
        ],
        "risk_filters": None,
    },
    "Trend_EMA_ADX_MultiTF": {
        "strategy_type": "TREND",
        "description": "Multi-timeframe EMA crossover (H4 primary / H1 confirmation) with ADX filter.",
        "granularity": "H4",
        "indicators": [
            {"indicator_key": "EMA", "instance_name": "EMA_20", "params": {"window": 20}, "output_column": "ema_indicator"},
            {"indicator_key": "EMA", "instance_name": "EMA_50", "params": {"window": 50}, "output_column": "ema_indicator"},
            {"indicator_key": "ADX", "instance_name": "ADX_14", "params": {"window": 14}, "output_column": "adx"},
        ],
        "rules": [
            {
                "rule_id": "LONG_EMA_ADX",
                "description": "EMA20 crosses above EMA50 with ADX > 25",
                "signal_value": 1,
                "conditions": [
                    {"left": "EMA_20", "operator": "cross_above", "right": "EMA_50"},
                    {"left": "ADX_14", "operator": ">", "right": 25},
                ],
                "logic": "AND",
            },
            {
                "rule_id": "SHORT_EMA_ADX",
                "description": "EMA20 crosses below EMA50 with ADX > 25",
                "signal_value": -1,
                "conditions": [
                    {"left": "EMA_20", "operator": "cross_below", "right": "EMA_50"},
                    {"left": "ADX_14", "operator": ">", "right": 25},
                ],
                "logic": "AND",
            },
        ],
        "risk_filters": [
            {"note": "MultiTF variant: H1 confirmation and D1 macro alignment are enforced in Layer 0. Layer 2 runs H4 rules; combine with H1 config for full confluence."}
        ],
    },
    # -------------------------------------------------------------------------
    # Range Bollinger family
    # -------------------------------------------------------------------------
    "Range_Bollinger_H1": {
        "strategy_type": "RANGE",
        "description": "H1 Bollinger Band mean reversion (10,2) with RSI(7).",
        "granularity": "H1",
        "indicators": [
            {"indicator_key": "BB", "instance_name": "BB_10", "params": {"window": 10, "window_dev": 2}, "output_columns": ["bollinger_hband", "bollinger_lband"]},
            {"indicator_key": "RSI", "instance_name": "RSI_7", "params": {"window": 7}, "output_column": "rsi"},
        ],
        "rules": [
            {
                "rule_id": "LONG_BB_RSI",
                "description": "Price at lower Bollinger band with RSI oversold",
                "signal_value": 1,
                "conditions": [
                    {"left": "Close", "operator": "<=", "right": "BB_10.lband"},
                    {"left": "RSI_7", "operator": "<", "right": 30},
                ],
                "logic": "AND",
            },
            {
                "rule_id": "SHORT_BB_RSI",
                "description": "Price at upper Bollinger band with RSI overbought",
                "signal_value": -1,
                "conditions": [
                    {"left": "Close", "operator": ">=", "right": "BB_10.hband"},
                    {"left": "RSI_7", "operator": ">", "right": 70},
                ],
                "logic": "AND",
            },
        ],
        "risk_filters": [
            {"note": "Layer 0 squeeze filter and cross-into-zone logic are not expressed in current Layer 2 rule syntax."}
        ],
    },
    "Range_Bollinger_H4": {
        "strategy_type": "RANGE",
        "description": "H4 Bollinger Band mean reversion (20,2) with RSI(14).",
        "granularity": "H4",
        "indicators": [
            {"indicator_key": "BB", "instance_name": "BB_20", "params": {"window": 20, "window_dev": 2}, "output_columns": ["bollinger_hband", "bollinger_lband"]},
            {"indicator_key": "RSI", "instance_name": "RSI_14", "params": {"window": 14}, "output_column": "rsi"},
        ],
        "rules": [
            {
                "rule_id": "LONG_BB_RSI",
                "description": "Price at lower Bollinger band with RSI oversold",
                "signal_value": 1,
                "conditions": [
                    {"left": "Close", "operator": "<=", "right": "BB_20.lband"},
                    {"left": "RSI_14", "operator": "<", "right": 30},
                ],
                "logic": "AND",
            },
            {
                "rule_id": "SHORT_BB_RSI",
                "description": "Price at upper Bollinger band with RSI overbought",
                "signal_value": -1,
                "conditions": [
                    {"left": "Close", "operator": ">=", "right": "BB_20.hband"},
                    {"left": "RSI_14", "operator": ">", "right": 70},
                ],
                "logic": "AND",
            },
        ],
        "risk_filters": [
            {"note": "Layer 0 squeeze filter and cross-into-zone logic are not expressed in current Layer 2 rule syntax."}
        ],
    },
    "Range_Bollinger_Aggressive": {
        "strategy_type": "RANGE",
        "description": "Aggressive Bollinger Band (20,1.5) without RSI requirement.",
        "granularity": "H4",
        "indicators": [
            {"indicator_key": "BB", "instance_name": "BB_20", "params": {"window": 20, "window_dev": 1.5}, "output_columns": ["bollinger_hband", "bollinger_lband"]},
        ],
        "rules": [
            {
                "rule_id": "LONG_BB",
                "description": "Price at lower Bollinger band (aggressive)",
                "signal_value": 1,
                "conditions": [
                    {"left": "Close", "operator": "<=", "right": "BB_20.lband"},
                ],
                "logic": "AND",
            },
            {
                "rule_id": "SHORT_BB",
                "description": "Price at upper Bollinger band (aggressive)",
                "signal_value": -1,
                "conditions": [
                    {"left": "Close", "operator": ">=", "right": "BB_20.hband"},
                ],
                "logic": "AND",
            },
        ],
        "risk_filters": [
            {"note": "Aggressive variant: no RSI filter. Tighter stops (1.0 ATR)."}
        ],
    },
    # -------------------------------------------------------------------------
    # Trend Donchian family
    # -------------------------------------------------------------------------
    "Trend_Donchian_H1": {
        "strategy_type": "BREAKOUT",
        "description": "H1 Donchian Channel breakout (10) with ADX filter.",
        "granularity": "H1",
        "indicators": [
            {"indicator_key": "DONCHIAN", "instance_name": "DONCHIAN_10", "params": {"window": 10}, "output_columns": ["donchian_channel_hband", "donchian_channel_lband"]},
            {"indicator_key": "ADX", "instance_name": "ADX_14", "params": {"window": 14}, "output_column": "adx"},
        ],
        "rules": [
            {
                "rule_id": "LONG_DONCHIAN_ADX",
                "description": "Close breaks above Donchian high band with ADX > 25",
                "signal_value": 1,
                "conditions": [
                    {"left": "Close", "operator": ">=", "right": "DONCHIAN_10.hband"},
                    {"left": "ADX_14", "operator": ">", "right": 25},
                ],
                "logic": "AND",
            },
            {
                "rule_id": "SHORT_DONCHIAN_ADX",
                "description": "Close breaks below Donchian low band with ADX > 25",
                "signal_value": -1,
                "conditions": [
                    {"left": "Close", "operator": "<=", "right": "DONCHIAN_10.lband"},
                    {"left": "ADX_14", "operator": ">", "right": 25},
                ],
                "logic": "AND",
            },
        ],
        "risk_filters": [
            {"note": "Layer 0 uses a 1-bar shifted band to avoid look-ahead. Current Layer 2 evaluator does not support arbitrary shifts; verify execution logic."}
        ],
    },
    "Trend_Donchian_H4": {
        "strategy_type": "BREAKOUT",
        "description": "H4 Donchian Channel breakout (20) with ADX filter.",
        "granularity": "H4",
        "indicators": [
            {"indicator_key": "DONCHIAN", "instance_name": "DONCHIAN_20", "params": {"window": 20}, "output_columns": ["donchian_channel_hband", "donchian_channel_lband"]},
            {"indicator_key": "ADX", "instance_name": "ADX_14", "params": {"window": 14}, "output_column": "adx"},
        ],
        "rules": [
            {
                "rule_id": "LONG_DONCHIAN_ADX",
                "description": "Close breaks above Donchian high band with ADX > 25",
                "signal_value": 1,
                "conditions": [
                    {"left": "Close", "operator": ">=", "right": "DONCHIAN_20.hband"},
                    {"left": "ADX_14", "operator": ">", "right": 25},
                ],
                "logic": "AND",
            },
            {
                "rule_id": "SHORT_DONCHIAN_ADX",
                "description": "Close breaks below Donchian low band with ADX > 25",
                "signal_value": -1,
                "conditions": [
                    {"left": "Close", "operator": "<=", "right": "DONCHIAN_20.lband"},
                    {"left": "ADX_14", "operator": ">", "right": 25},
                ],
                "logic": "AND",
            },
        ],
        "risk_filters": [
            {"note": "Layer 0 uses a 1-bar shifted band to avoid look-ahead. Current Layer 2 evaluator does not support arbitrary shifts; verify execution logic."}
        ],
    },
    "Trend_Donchian_VCP": {
        "strategy_type": "BREAKOUT",
        "description": "Donchian VCP breakout (20) with squeeze filter.",
        "granularity": "H4",
        "indicators": [
            {"indicator_key": "DONCHIAN", "instance_name": "DONCHIAN_20", "params": {"window": 20}, "output_columns": ["donchian_channel_hband", "donchian_channel_lband"]},
            {"indicator_key": "ADX", "instance_name": "ADX_14", "params": {"window": 14}, "output_column": "adx"},
        ],
        "rules": [
            {
                "rule_id": "LONG_DONCHIAN_ADX",
                "description": "Close breaks above Donchian high band with ADX > 25",
                "signal_value": 1,
                "conditions": [
                    {"left": "Close", "operator": ">=", "right": "DONCHIAN_20.hband"},
                    {"left": "ADX_14", "operator": ">", "right": 25},
                ],
                "logic": "AND",
            },
            {
                "rule_id": "SHORT_DONCHIAN_ADX",
                "description": "Close breaks below Donchian low band with ADX > 25",
                "signal_value": -1,
                "conditions": [
                    {"left": "Close", "operator": "<=", "right": "DONCHIAN_20.lband"},
                    {"left": "ADX_14", "operator": ">", "right": 25},
                ],
                "logic": "AND",
            },
        ],
        "risk_filters": [
            {"note": "VCP squeeze filter is NOT expressible in Layer 2 rule syntax. Review before production: implement custom indicator or use Layer 3 ML gatekeeper."}
        ],
    },
    # -------------------------------------------------------------------------
    # Range Stochastic family
    # -------------------------------------------------------------------------
    "Range_Stochastic_H1": {
        "strategy_type": "MEAN_REVERSION",
        "description": "H1 Stochastic oscillator mean reversion (7,3).",
        "granularity": "H1",
        "indicators": [
            {"indicator_key": "STOCH", "instance_name": "STOCH_7", "params": {"window": 7, "smooth_window": 3}, "output_column": "stoch"},
        ],
        "rules": [
            {
                "rule_id": "LONG_STOCH_CROSS",
                "description": "Stochastic K crosses above 20 from oversold",
                "signal_value": 1,
                "conditions": [
                    {"left": "STOCH_7.prev", "operator": "<=", "right": 20},
                    {"left": "STOCH_7", "operator": ">", "right": 20},
                ],
                "logic": "AND",
            },
            {
                "rule_id": "SHORT_STOCH_CROSS",
                "description": "Stochastic K crosses below 80 from overbought",
                "signal_value": -1,
                "conditions": [
                    {"left": "STOCH_7.prev", "operator": ">=", "right": 80},
                    {"left": "STOCH_7", "operator": "<", "right": 80},
                ],
                "logic": "AND",
            },
        ],
        "risk_filters": None,
    },
    "Range_Stochastic_H4": {
        "strategy_type": "MEAN_REVERSION",
        "description": "H4 Stochastic oscillator mean reversion (14,3).",
        "granularity": "H4",
        "indicators": [
            {"indicator_key": "STOCH", "instance_name": "STOCH_14", "params": {"window": 14, "smooth_window": 3}, "output_column": "stoch"},
        ],
        "rules": [
            {
                "rule_id": "LONG_STOCH_CROSS",
                "description": "Stochastic K crosses above 20 from oversold",
                "signal_value": 1,
                "conditions": [
                    {"left": "STOCH_14.prev", "operator": "<=", "right": 20},
                    {"left": "STOCH_14", "operator": ">", "right": 20},
                ],
                "logic": "AND",
            },
            {
                "rule_id": "SHORT_STOCH_CROSS",
                "description": "Stochastic K crosses below 80 from overbought",
                "signal_value": -1,
                "conditions": [
                    {"left": "STOCH_14.prev", "operator": ">=", "right": 80},
                    {"left": "STOCH_14", "operator": "<", "right": 80},
                ],
                "logic": "AND",
            },
        ],
        "risk_filters": None,
    },
    "Range_Stochastic_Divergence": {
        "strategy_type": "MEAN_REVERSION",
        "description": "Stochastic divergence detection (14,3).",
        "granularity": "H4",
        "indicators": [
            {"indicator_key": "STOCH", "instance_name": "STOCH_14", "params": {"window": 14, "smooth_window": 3}, "output_column": "stoch"},
        ],
        "rules": [
            {
                "rule_id": "LONG_STOCH_CROSS",
                "description": "Stochastic K crosses above 20 from oversold",
                "signal_value": 1,
                "conditions": [
                    {"left": "STOCH_14.prev", "operator": "<=", "right": 20},
                    {"left": "STOCH_14", "operator": ">", "right": 20},
                ],
                "logic": "AND",
            },
            {
                "rule_id": "SHORT_STOCH_CROSS",
                "description": "Stochastic K crosses below 80 from overbought",
                "signal_value": -1,
                "conditions": [
                    {"left": "STOCH_14.prev", "operator": ">=", "right": 80},
                    {"left": "STOCH_14", "operator": "<", "right": 80},
                ],
                "logic": "AND",
            },
        ],
        "risk_filters": [
            {"note": "Divergence detection is NOT expressible in Layer 2 rule syntax. This config falls back to standard stochastic cross rules. Manual review required."}
        ],
    },
    # -------------------------------------------------------------------------
    # Support Resistance family (custom / not mappable to standard ta lib)
    # -------------------------------------------------------------------------
    "Support_Resistance_H1": {
        "strategy_type": "CUSTOM",
        "description": "H1 Support/Resistance price action (swing-point based).",
        "granularity": "H1",
        "indicators": [],
        "rules": [],
        "risk_filters": [
            {"note": "CUSTOM STRATEGY: Uses detect_swing_points which is not registered in Dim_Indicator_Library. Layer 2 signal rules cannot be auto-generated. Implement custom indicator or extend registry before activation."}
        ],
    },
    "Support_Resistance_H4": {
        "strategy_type": "CUSTOM",
        "description": "H4 Support/Resistance price action (swing-point based).",
        "granularity": "H4",
        "indicators": [],
        "rules": [],
        "risk_filters": [
            {"note": "CUSTOM STRATEGY: Uses detect_swing_points which is not registered in Dim_Indicator_Library. Layer 2 signal rules cannot be auto-generated. Implement custom indicator or extend registry before activation."}
        ],
    },
    "Support_Resistance_Breakout": {
        "strategy_type": "CUSTOM",
        "description": "S/R breakout variant (swing-point based).",
        "granularity": "H4",
        "indicators": [],
        "rules": [],
        "risk_filters": [
            {"note": "CUSTOM STRATEGY: Uses detect_swing_points which is not registered in Dim_Indicator_Library. Layer 2 signal rules cannot be auto-generated. Implement custom indicator or extend registry before activation."}
        ],
    },
    # -------------------------------------------------------------------------
    # VCP Breakout family (custom / partially mappable)
    # -------------------------------------------------------------------------
    "VCP_Breakout_H1": {
        "strategy_type": "BREAKOUT",
        "description": "H1 VCP breakout (10) with trend alignment.",
        "granularity": "H1",
        "indicators": [
            {"indicator_key": "EMA", "instance_name": "EMA_20", "params": {"window": 20}, "output_column": "ema_indicator"},
            {"indicator_key": "EMA", "instance_name": "EMA_50", "params": {"window": 50}, "output_column": "ema_indicator"},
            {"indicator_key": "DONCHIAN", "instance_name": "DONCHIAN_10", "params": {"window": 10}, "output_columns": ["donchian_channel_hband", "donchian_channel_lband"]},
            {"indicator_key": "ADX", "instance_name": "ADX_14", "params": {"window": 14}, "output_column": "adx"},
        ],
        "rules": [
            {
                "rule_id": "LONG_VCP",
                "description": "Breakout above Donchian band with trend up and ADX > 20",
                "signal_value": 1,
                "conditions": [
                    {"left": "Close", "operator": ">=", "right": "DONCHIAN_10.hband"},
                    {"left": "EMA_20", "operator": ">", "right": "EMA_50"},
                    {"left": "ADX_14", "operator": ">", "right": 20},
                ],
                "logic": "AND",
            },
            {
                "rule_id": "SHORT_VCP",
                "description": "Breakdown below Donchian band with trend down and ADX > 20",
                "signal_value": -1,
                "conditions": [
                    {"left": "Close", "operator": "<=", "right": "DONCHIAN_10.lband"},
                    {"left": "EMA_20", "operator": "<", "right": "EMA_50"},
                    {"left": "ADX_14", "operator": ">", "right": 20},
                ],
                "logic": "AND",
            },
        ],
        "risk_filters": [
            {"note": "VCP squeeze filter is NOT expressible in Layer 2 rules. This config approximates VCP with Donchian+EMA+ADX. Review before production."}
        ],
    },
    "VCP_Breakout_H4": {
        "strategy_type": "BREAKOUT",
        "description": "H4 VCP breakout (20) with trend alignment.",
        "granularity": "H4",
        "indicators": [
            {"indicator_key": "EMA", "instance_name": "EMA_20", "params": {"window": 20}, "output_column": "ema_indicator"},
            {"indicator_key": "EMA", "instance_name": "EMA_50", "params": {"window": 50}, "output_column": "ema_indicator"},
            {"indicator_key": "DONCHIAN", "instance_name": "DONCHIAN_20", "params": {"window": 20}, "output_columns": ["donchian_channel_hband", "donchian_channel_lband"]},
            {"indicator_key": "ADX", "instance_name": "ADX_14", "params": {"window": 14}, "output_column": "adx"},
        ],
        "rules": [
            {
                "rule_id": "LONG_VCP",
                "description": "Breakout above Donchian band with trend up and ADX > 20",
                "signal_value": 1,
                "conditions": [
                    {"left": "Close", "operator": ">=", "right": "DONCHIAN_20.hband"},
                    {"left": "EMA_20", "operator": ">", "right": "EMA_50"},
                    {"left": "ADX_14", "operator": ">", "right": 20},
                ],
                "logic": "AND",
            },
            {
                "rule_id": "SHORT_VCP",
                "description": "Breakdown below Donchian band with trend down and ADX > 20",
                "signal_value": -1,
                "conditions": [
                    {"left": "Close", "operator": "<=", "right": "DONCHIAN_20.lband"},
                    {"left": "EMA_20", "operator": "<", "right": "EMA_50"},
                    {"left": "ADX_14", "operator": ">", "right": 20},
                ],
                "logic": "AND",
            },
        ],
        "risk_filters": [
            {"note": "VCP squeeze filter is NOT expressible in Layer 2 rules. This config approximates VCP with Donchian+EMA+ADX. Review before production."}
        ],
    },
    "VCP_Breakout_Aggressive": {
        "strategy_type": "BREAKOUT",
        "description": "Aggressive VCP breakout (15,0.6) with earlier entry.",
        "granularity": "H4",
        "indicators": [
            {"indicator_key": "EMA", "instance_name": "EMA_20", "params": {"window": 20}, "output_column": "ema_indicator"},
            {"indicator_key": "DONCHIAN", "instance_name": "DONCHIAN_15", "params": {"window": 15}, "output_columns": ["donchian_channel_hband", "donchian_channel_lband"]},
            {"indicator_key": "ADX", "instance_name": "ADX_14", "params": {"window": 14}, "output_column": "adx"},
        ],
        "rules": [
            {
                "rule_id": "LONG_VCP_AGGRESSIVE",
                "description": "Close crosses above EMA20 after squeeze with trend up and ADX > 20",
                "signal_value": 1,
                "conditions": [
                    {"left": "Close", "operator": ">", "right": "EMA_20"},
                    {"left": "Close.prev", "operator": "<=", "right": "EMA_20.prev"},
                    {"left": "ADX_14", "operator": ">", "right": 20},
                ],
                "logic": "AND",
            },
            {
                "rule_id": "SHORT_VCP_AGGRESSIVE",
                "description": "Close crosses below EMA20 after squeeze with trend down and ADX > 20",
                "signal_value": -1,
                "conditions": [
                    {"left": "Close", "operator": "<", "right": "EMA_20"},
                    {"left": "Close.prev", "operator": ">=", "right": "EMA_20.prev"},
                    {"left": "ADX_14", "operator": ">", "right": 20},
                ],
                "logic": "AND",
            },
        ],
        "risk_filters": [
            {"note": "Aggressive VCP variant. Squeeze and EMA-cross rules are approximated. Review before production."}
        ],
    },
}


def _get_catalog_entry(strategy_name: str) -> Optional[Dict[str, Any]]:
    """Retrieve the Layer 2 catalog entry for a strategy name."""
    return STRATEGY_CATALOG.get(strategy_name)


def _build_merge_strategy_sql(key: str, entry: Dict[str, Any]) -> str:
    """Generate INSERT ... ON CONFLICT SQL for Dim_Strategy."""
    name = key  # Strategy_Name can match key for simplicity
    desc = _safe_sql_string(entry["description"])
    stype = entry["strategy_type"]
    return f"""
-- Strategy: {key}
INSERT INTO Dim_Strategy (Strategy_Key, Strategy_Name, "Description", Strategy_Type, Is_Active)
VALUES ('{key}', '{name}', '{desc}', '{stype}', TRUE)
ON CONFLICT (Strategy_ID) DO UPDATE SET
    Strategy_Name = EXCLUDED.Strategy_Name,
    "Description" = EXCLUDED."Description",
    Strategy_Type = EXCLUDED.Strategy_Type,
    Is_Active = EXCLUDED.Is_Active,
    Modified_Date = NOW();
"""


def _build_merge_config_sql(key: str, entry: Dict[str, Any], version: str = "1.0.0") -> str:
    """Generate INSERT ... ON CONFLICT SQL for Dim_Strategy_Config."""
    indicators = entry["indicators"]
    rules = entry["rules"]
    risk = entry.get("risk_filters")
    granularity = entry["granularity"]

    ind_json = _safe_sql_string(json.dumps(indicators))
    rules_json = _safe_sql_string(json.dumps(rules))
    risk_json = "NULL" if risk is None else f"'{_safe_sql_string(json.dumps(risk))}'"
    config_hash = _compute_config_hash(indicators, rules, risk)

    return f"""
INSERT INTO Dim_Strategy_Config (Strategy_ID, Config_Version, Config_Hash, Granularity, Indicator_Configs, Signal_Rules, Risk_Filters, Effective_From, Effective_To, Is_Active)
VALUES (
    (SELECT Strategy_ID FROM Dim_Strategy WHERE Strategy_Key = '{key}'),
    '{version}',
    '{config_hash}',
    '{granularity}',
    '{ind_json}',
    '{rules_json}',
    {risk_json},
    NOW(),
    NULL,
    TRUE
)
ON CONFLICT (Config_Hash) DO UPDATE SET
    Strategy_ID = EXCLUDED.Strategy_ID,
    Config_Version = EXCLUDED.Config_Version,
    Config_Hash = EXCLUDED.Config_Hash,
    Granularity = EXCLUDED.Granularity,
    Indicator_Configs = EXCLUDED.Indicator_Configs,
    Signal_Rules = EXCLUDED.Signal_Rules,
    Risk_Filters = EXCLUDED.Risk_Filters,
    Effective_From = EXCLUDED.Effective_From,
    Effective_To = EXCLUDED.Effective_To,
    Is_Active = EXCLUDED.Is_Active;
"""


def _build_merge_mapping_sql(key: str, asset_id: int, granularity: str, priority: int = 100) -> str:
    """Generate INSERT ... ON CONFLICT SQL for Dim_Strategy_Asset_Mapping."""
    return f"""
INSERT INTO Dim_Strategy_Asset_Mapping (Strategy_ID, Asset_ID, Granularity, Config_ID, Priority, Effective_From, Effective_To, Is_Active)
VALUES (
    (SELECT Strategy_ID FROM Dim_Strategy WHERE Strategy_Key = '{key}'),
    {asset_id},
    '{granularity}',
    (SELECT Config_ID FROM Dim_Strategy_Config
     WHERE Strategy_ID = (SELECT Strategy_ID FROM Dim_Strategy WHERE Strategy_Key = '{key}')
       AND Config_Version = '1.0.0'
       AND Granularity = '{granularity}'),
    {priority},
    NOW(),
    NULL,
    TRUE
)
ON CONFLICT (Strategy_ID, Asset_ID, Granularity) DO UPDATE SET
    Config_ID = EXCLUDED.Config_ID,
    Priority = EXCLUDED.Priority,
    Effective_From = EXCLUDED.Effective_From,
    Effective_To = EXCLUDED.Effective_To,
    Is_Active = EXCLUDED.Is_Active;
"""


def generate_sql_seed(
    qualified_results: List[Dict[str, Any]],
    asset_symbol_map: Dict[int, str]
) -> str:
    """
    Generate a complete PostgreSQL seed script for Layer 2 tables.

    Args:
        qualified_results: List of qualification result dicts from Layer 0.
        asset_symbol_map: Mapping of Asset_ID -> Symbol (from Dim_Asset).

    Returns:
        PostgreSQL INSERT ... ON CONFLICT script as a string.
    """
    lines = [
        "-- =============================================================================",
        "-- AUTO-GENERATED Layer 2 Strategy Seed Script",
        f"-- Generated: {datetime.now().isoformat()}",
        "-- Source: Layer 0 Strategy Qualification Engine",
        "-- =============================================================================",
        "-- Database: ForexBrainDB",
        "",
    ]

    warnings: List[str] = []
    processed_strategies: set = set()
    promotable_results: List[Dict[str, Any]] = []

    for result in qualified_results:
        if not result.get("overall_qualified"):
            continue

        strategy_name = result["strategy_name"]
        entry = _get_catalog_entry(strategy_name)

        if entry is None:
            warnings.append(f"-- WARNING: No Layer 2 catalog mapping for strategy '{strategy_name}'. Skipped.")
            continue

        if strategy_name in processed_strategies:
            continue
        processed_strategies.add(strategy_name)
        promotable_results.append(result)

    # Apply switch-over policy only when there is at least one strategy to promote.
    # This prevents accidentally deactivating everything on an empty promotion run.
    if promotable_results:
        lines.extend([
            "-- Deactivate currently active Layer 2 strategy records before promoting new ones",
            "UPDATE Dim_Strategy_Asset_Mapping",
            "SET Is_Active = FALSE,",
            "    Effective_To = COALESCE(Effective_To, NOW())",
            "WHERE Is_Active = TRUE;",
            "",
            "UPDATE Dim_Strategy_Config",
            "SET Is_Active = FALSE,",
            "    Effective_To = COALESCE(Effective_To, NOW())",
            "WHERE Is_Active = TRUE;",
            "",
            "UPDATE Dim_Strategy",
            "SET Is_Active = FALSE,",
            "    Modified_Date = NOW()",
            "WHERE Is_Active = TRUE;",
            "",
        ])

    for result in promotable_results:
        key = result["strategy_name"]
        entry = _get_catalog_entry(key)
        if entry is None:
            # Guard clause: should not happen because promotable_results is pre-filtered.
            continue

        # Dim_Strategy
        lines.append(_build_merge_strategy_sql(key, entry))

        # Dim_Strategy_Config
        lines.append(_build_merge_config_sql(key, entry))

        # Dim_Strategy_Asset_Mapping for each qualified asset+granularity
        qualified_assets = result.get("qualified_assets", [])
        for asset_symbol in qualified_assets:
            # Find Asset_ID by symbol
            asset_id = None
            for aid, sym in asset_symbol_map.items():
                if sym == asset_symbol:
                    asset_id = aid
                    break
            if asset_id is None:
                warnings.append(f"-- WARNING: Asset symbol '{asset_symbol}' not found in Dim_Asset. Skipped mapping for {key}.")
                continue

            lines.append(_build_merge_mapping_sql(key, asset_id, entry["granularity"]))

        lines.append("")

    if warnings:
        lines.insert(5, "")
        lines.insert(6, "-- WARNINGS:")
        for w in warnings:
            lines.insert(7, w)
        lines.insert(7 + len(warnings), "")

    lines.append("-- =============================================================================")
    lines.append("-- END OF SEED SCRIPT")
    lines.append("-- =============================================================================")
    lines.append("")

    return "\n".join(lines)


def generate_indicator_library_extension_sql() -> str:
    """
    Generate SQL to extend Dim_Indicator_Library with indicators required
    by the migrated Layer 0 strategies but missing from the base registry.

    Returns:
        PostgreSQL INSERT ... ON CONFLICT script as a string.
    """
    # ATR is heavily used by Layer 0 but not in the base Layer 2 registry.
    # We also note custom indicators that require Python extension.
    sql = """
-- =============================================================================
-- Extend Dim_Indicator_Library for Layer 0 strategies
-- =============================================================================

INSERT INTO Dim_Indicator_Library (
    Indicator_Key, Indicator_Name, Description,
    Category, Required_Price_Fields, Default_Parameters, Output_Columns,
    Warmup_Period_Min, Python_Class, Is_Active
)
VALUES (
    'ATR', 'Average True Range',
    'Measures market volatility by decomposing the entire range of an asset price for that period.',
    'VOLATILITY', 'High,Low,Close',
    '{"window": 14}', 'atr',
    50, 'ta.volatility.AverageTrueRange', TRUE
)
ON CONFLICT (Indicator_Key) DO UPDATE SET
    Indicator_Name = EXCLUDED.Indicator_Name,
    Description = EXCLUDED.Description,
    Category = EXCLUDED.Category,
    Required_Price_Fields = EXCLUDED.Required_Price_Fields,
    Default_Parameters = EXCLUDED.Default_Parameters,
    Output_Columns = EXCLUDED.Output_Columns,
    Warmup_Period_Min = EXCLUDED.Warmup_Period_Min,
    Python_Class = EXCLUDED.Python_Class,
    Is_Active = EXCLUDED.Is_Active;

-- NOTE: The following custom indicators are used by Layer 0 but are NOT available
-- in the standard 'ta' library registry. They require custom Python implementation
-- in layer2_signals/signal_engine/indicators/registry.py before Layer 2 can execute them:
--   - detect_swing_points   (used by Support_Resistance family)
--   - volatility_contraction_index / squeeze logic (used by VCP_Breakout family)
-- =============================================================================
"""
    return sql
