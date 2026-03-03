import pandas as pd
import pandas_ta as ta
from .base_strategy import BaseStrategy

class RangeMeanReversionStrategy(BaseStrategy):
    def __init__(self):
        super().__init__(
            name="Range_BB_RSI_v1",
            description="Bollinger Bands (20,2) Reversion with RSI Filter"
        )

    def generate_signals(self, df: pd.DataFrame):
        # 1. Calculate Indicators
        # Bollinger Bands (20, 2) [cite: 253]
        bb = ta.bbands(df['close'], length=20, std=2)
        df['BB_Upper'] = bb['BBU_20_2.0']
        df['BB_Lower'] = bb['BBL_20_2.0']
        
        # RSI (14) [cite: 253]
        df['RSI'] = ta.rsi(df['close'], length=14)
        
        df['Signal'] = 0
        
        # BUY SIGNAL (Oversold in Range)
        # Price touches Lower Band AND RSI < 30 [cite: 164]
        buy_condition = (
            (df['close'] <= df['BB_Lower']) & 
            (df['RSI'] < 30)
        )
        
        # SELL SIGNAL (Overbought in Range)
        # Price touches Upper Band AND RSI > 70 [cite: 165]
        sell_condition = (
            (df['close'] >= df['BB_Upper']) & 
            (df['RSI'] > 70)
        )
        
        df.loc[buy_condition, 'Signal'] = 1
        df.loc[sell_condition, 'Signal'] = -1
        
        return df
