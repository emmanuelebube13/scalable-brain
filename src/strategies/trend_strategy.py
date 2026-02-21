import pandas as pd
import pandas_ta as ta
from .base_strategy import BaseStrategy # Import the blueprint

class TrendFollowingStrategy(BaseStrategy):
    def __init__(self):
        super().__init__(
            name="Trend_EMA_ADX_v1", 
            description="50/200 EMA Crossover with ADX > 25 Filter"
        )

    def generate_signals(self, df: pd.DataFrame):
        """
        Applies the logic from the Research Report (Page 10 & 22).
        """
        # 1. Calculate Indicators
        df['EMA_50'] = ta.ema(df['close'], length=50)
        df['EMA_200'] = ta.ema(df['close'], length=200)
        adx = ta.adx(df['high'], df['low'], df['close'], length=14)
        df['ADX'] = adx['ADX_14']
        df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)

        # 2. Logic: The 'Golden Cross' (Bullish)
        # Condition 1: 50 EMA is above 200 EMA
        # Condition 2: ADX is strong (> 25) 
        # Condition 3: It just crossed recently (to avoid buying the top)
        
        df['Signal'] = 0 # Default is "Do Nothing"
        
        # BUY SIGNAL
        buy_condition = (
            (df['EMA_50'] > df['EMA_200']) &    # Trend is UP
            (df['EMA_50'].shift(1) <= df['EMA_200'].shift(1)) & # It JUST crossed
            (df['ADX'] > 25)                    # Trend is Strong 
        )
        
        # SELL SIGNAL
        sell_condition = (
            (df['EMA_50'] < df['EMA_200']) &    # Trend is DOWN
            (df['EMA_50'].shift(1) >= df['EMA_200'].shift(1)) & # It JUST crossed
            (df['ADX'] > 25)                    # Trend is Strong
        )
        
        df.loc[buy_condition, 'Signal'] = 1  # 1 = Buy
        df.loc[sell_condition, 'Signal'] = -1 # -1 = Sell
        
        # Calculate Dynamic Stop Loss (3 ATR) 
        df['Stop_Loss_Dist'] = df['ATR'] * 3
        
        return df
