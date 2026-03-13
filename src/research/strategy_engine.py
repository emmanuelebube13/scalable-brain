# strategy_engine.py
import pandas as pd
import ta
from trade_simulator import RealTradeSimulator

class StrategyQualificationEngine:
    def __init__(self, data: pd.DataFrame, symbol: str):
        self.data = data.copy()
        self.symbol = symbol
        self.calculate_indicators()

    def calculate_indicators(self):
        df = self.data
        df['ATR'] = ta.volatility.AverageTrueRange(df['High'], df['Low'], df['Close'], window=14).average_true_range()
        df['EMA_50'] = ta.trend.ema_indicator(df['Close'], window=50)
        df['EMA_200'] = ta.trend.ema_indicator(df['Close'], window=200)
        df['ADX'] = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close'], window=14).adx()
        
        bb = ta.volatility.BollingerBands(df['Close'], window=20, window_dev=2)
        df['BB_LOWER'] = bb.bollinger_lband()
        df['BB_UPPER'] = bb.bollinger_hband()
        df['RSI'] = ta.momentum.rsi(df['Close'], window=14)
        
        df['DONCHIAN_HIGH'] = df['High'].rolling(20).max()
        df['DONCHIAN_LOW'] = df['Low'].rolling(20).min()
        
        stoch = ta.momentum.StochasticOscillator(df['High'], df['Low'], df['Close'], window=14, smooth_window=3)
        df['STOCH_K'] = stoch.stoch()
        df.dropna(inplace=True)

    def get_entry_indices(self, strategy: str) -> list:
        df = self.data
        indices = []
        max_idx = len(df) - 2
        for i in range(1, max_idx):
            adx_ok = df['ADX'].iloc[i] > 30                     # stronger filter
            rsi_low = df['RSI'].iloc[i] < 25
            rsi_high = df['RSI'].iloc[i] > 75
            stoch_cross_up = (df['STOCH_K'].iloc[i] > 20) and (df['STOCH_K'].iloc[i-1] <= 20)
            stoch_cross_down = (df['STOCH_K'].iloc[i] < 80) and (df['STOCH_K'].iloc[i-1] >= 80)

            if strategy == "Trend_EMA_ADX_Long" and (df['EMA_50'].iloc[i] > df['EMA_200'].iloc[i] and df['EMA_50'].iloc[i-1] <= df['EMA_200'].iloc[i-1] and adx_ok):
                indices.append(i)
            elif strategy == "Trend_EMA_ADX_Short" and (df['EMA_50'].iloc[i] < df['EMA_200'].iloc[i] and df['EMA_50'].iloc[i-1] >= df['EMA_200'].iloc[i-1] and adx_ok):
                indices.append(i)

            elif strategy == "Range_Bollinger_Long" and (df['Close'].iloc[i] <= df['BB_LOWER'].iloc[i] and rsi_low):
                indices.append(i)
            elif strategy == "Range_Bollinger_Short" and (df['Close'].iloc[i] >= df['BB_UPPER'].iloc[i] and rsi_high):
                indices.append(i)

            elif strategy == "Trend_Donchian_Long" and (df['Close'].iloc[i] > df['DONCHIAN_HIGH'].iloc[i-1] and adx_ok):
                indices.append(i)
            elif strategy == "Trend_Donchian_Short" and (df['Close'].iloc[i] < df['DONCHIAN_LOW'].iloc[i-1] and adx_ok):
                indices.append(i)

            elif strategy == "Range_Stochastic_Long" and stoch_cross_up and rsi_low:
                indices.append(i)
            elif strategy == "Range_Stochastic_Short" and stoch_cross_down and rsi_high:
                indices.append(i)
        return indices

    def evaluate(self, strategy_name: str):
        entries = self.get_entry_indices(strategy_name)
        simulator = RealTradeSimulator(self.data, self.symbol, strategy_name)
        return simulator.run_backtest(entries)