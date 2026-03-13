# config.py
SPREAD_ATR = {"EUR_USD": 0.12, "GBP_USD": 0.15, "USD_JPY": 0.18}  # realistic pips converted to ATR fraction
SLIPPAGE_ATR = {"Trend_EMA_ADX": 0.08, "Trend_Donchian": 0.20,  # breakouts need more slippage
                "Range_Bollinger": 0.05, "Range_Stochastic": 0.05}
COMMISSION_PER_TRADE_ATR = 0.03  # round-turn
MIN_TRADES = 30
WALK_FORWARD_SPLITS = 4  # number of rolling windows
MC_PATHS = 5000
SEED = 42