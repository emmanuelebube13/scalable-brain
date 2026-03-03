from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategy(ABC):
    """
    The Blueprint for all future strategies.
    Enforces that every strategy must have a specific structure.
    """
    
    def __init__(self, name, description):
        self.name = name
        self.description = description
    
    @abstractmethod
    def generate_signals(self, df: pd.DataFrame):
        """
        Input: A DataFrame with price history (Open, High, Low, Close).
        Output: A DataFrame with 'Signal' column (1=Buy, -1=Sell, 0=Hold).
        """
        pass

    def calculate_position_size(self, account_balance, risk_per_trade, stop_loss_pips, pip_value):
        """
        Standard Risk Management Rule:
        Never risk more than X% of the account on a single trade.
        """
        risk_amount = account_balance * risk_per_trade
        if stop_loss_pips == 0:
            return 0
        
        # Standard Lot Size Formula
        lot_size = risk_amount / (stop_loss_pips * pip_value)
        return round(lot_size, 2)
