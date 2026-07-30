"""
Indicator Registry - Maps indicator keys to ta library implementations.

This module provides a clean abstraction between database indicator keys
and the actual ta library classes, enabling dynamic indicator instantiation.
"""

import logging
import importlib
from typing import Dict, Type, Callable, Any, Optional
from dataclasses import dataclass

import pandas as pd
from ta.trend import EMAIndicator, ADXIndicator
from ta.volatility import BollingerBands, DonchianChannel, AverageTrueRange
from ta.momentum import RSIIndicator, StochasticOscillator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndicatorDefinition:
    """
    Definition of a technical indicator.
    
    Attributes:
        key: Unique identifier (e.g., 'EMA', 'RSI')
        name: Human-readable name
        category: Indicator category (TREND, MOMENTUM, VOLATILITY, VOLUME)
        required_fields: List of price fields needed (Close, High, Low, etc.)
        ta_class: The ta library class
        output_methods: Mapping of output names to class methods
        default_params: Default parameters for the indicator
        warmup_period: Minimum bars needed for valid output
    """
    key: str
    name: str
    category: str
    required_fields: list
    ta_class: Type
    output_methods: Dict[str, str]
    default_params: Dict[str, Any]
    warmup_period: int


class IndicatorRegistry:
    """
    Central registry of all available technical indicators.
    
    Maps indicator keys to their ta library implementations and provides
    factory methods for creating indicator instances.
    
    Example:
        registry = IndicatorRegistry()
        ema_def = registry.get('EMA')
        ema_instance = registry.create('EMA', df['Close'], window=50)
    """
    
    # Built-in indicator definitions
    _INDICATORS: Dict[str, IndicatorDefinition] = {
        'EMA': IndicatorDefinition(
            key='EMA',
            name='Exponential Moving Average',
            category='TREND',
            required_fields=['Close'],
            ta_class=EMAIndicator,
            output_methods={'ema_indicator': 'ema_indicator'},
            default_params={'window': 20},
            warmup_period=20
        ),
        'ADX': IndicatorDefinition(
            key='ADX',
            name='Average Directional Index',
            category='TREND',
            required_fields=['High', 'Low', 'Close'],
            ta_class=ADXIndicator,
            output_methods={'adx': 'adx'},
            default_params={'window': 14},
            warmup_period=50
        ),
        'BB': IndicatorDefinition(
            key='BB',
            name='Bollinger Bands',
            category='VOLATILITY',
            required_fields=['Close'],
            ta_class=BollingerBands,
            output_methods={
                'hband': 'bollinger_hband',
                'lband': 'bollinger_lband',
                'mavg': 'bollinger_mavg',
                'bollinger_hband': 'bollinger_hband',
                'bollinger_lband': 'bollinger_lband',
                'bollinger_mavg': 'bollinger_mavg'
            },
            default_params={'window': 20, 'window_dev': 2},
            warmup_period=20
        ),
        'DONCHIAN': IndicatorDefinition(
            key='DONCHIAN',
            name='Donchian Channel',
            category='VOLATILITY',
            required_fields=['High', 'Low', 'Close'],
            ta_class=DonchianChannel,
            output_methods={
                'hband': 'donchian_channel_hband',
                'lband': 'donchian_channel_lband',
                'mband': 'donchian_channel_mband',
                'donchian_channel_hband': 'donchian_channel_hband',
                'donchian_channel_lband': 'donchian_channel_lband',
                'donchian_channel_mband': 'donchian_channel_mband'
            },
            default_params={'window': 20},
            warmup_period=20
        ),
        'RSI': IndicatorDefinition(
            key='RSI',
            name='Relative Strength Index',
            category='MOMENTUM',
            required_fields=['Close'],
            ta_class=RSIIndicator,
            output_methods={'rsi': 'rsi'},
            default_params={'window': 14},
            warmup_period=14
        ),
        'STOCH': IndicatorDefinition(
            key='STOCH',
            name='Stochastic Oscillator',
            category='MOMENTUM',
            required_fields=['High', 'Low', 'Close'],
            ta_class=StochasticOscillator,
            output_methods={
                'stoch': 'stoch',
                'signal': 'stoch_signal',
                'stoch_signal': 'stoch_signal'
            },
            default_params={'window': 14, 'smooth_window': 3},
            warmup_period=14
        ),
        'ATR': IndicatorDefinition(
            key='ATR',
            name='Average True Range',
            category='VOLATILITY',
            required_fields=['High', 'Low', 'Close'],
            ta_class=AverageTrueRange,
            output_methods={
                'atr': 'average_true_range',
                'average_true_range': 'average_true_range'
            },
            default_params={'window': 14},
            warmup_period=14
        ),
    }
    
    def __init__(self):
        """Initialize the indicator registry."""
        self._indicators = dict(self._INDICATORS)
        logger.debug(f"Initialized IndicatorRegistry with {len(self._indicators)} indicators")
    
    def get(self, key: str) -> IndicatorDefinition:
        """
        Get indicator definition by key.
        
        Args:
            key: Indicator key (e.g., 'EMA', 'RSI')
            
        Returns:
            IndicatorDefinition for the key
            
        Raises:
            KeyError: If indicator key is not found
        """
        key = key.upper()
        if key not in self._indicators:
            available = ', '.join(self._indicators.keys())
            raise KeyError(f"Unknown indicator key: '{key}'. Available: {available}")
        return self._indicators[key]
    
    def register(self, definition: IndicatorDefinition) -> None:
        """
        Register a new indicator definition.
        
        Args:
            definition: IndicatorDefinition to register
        """
        self._indicators[definition.key.upper()] = definition
        logger.info(f"Registered indicator: {definition.key}")
    
    def create(
        self, 
        key: str, 
        df: pd.DataFrame, 
        **params
    ) -> Any:
        """
        Create an indicator instance from a DataFrame.
        
        Args:
            key: Indicator key
            df: DataFrame with price data (Open, High, Low, Close)
            **params: Override parameters for the indicator
            
        Returns:
            Instantiated ta library indicator class
        """
        definition = self.get(key)
        
        # Merge default params with overrides
        merged_params = {**definition.default_params, **params}
        
        # Extract required price fields
        field_mapping = {
            'Close': 'Close',
            'High': 'High', 
            'Low': 'Low',
            'Open': 'Open',
            'Volume': 'Volume'
        }
        
        kwargs = {}
        for field in definition.required_fields:
            col_name = field_mapping.get(field)
            if col_name not in df.columns:
                raise ValueError(
                    f"Indicator '{key}' requires '{col_name}' column. "
                    f"Available columns: {list(df.columns)}"
                )
            kwargs[field.lower()] = df[col_name]
        
        # Add parameters
        kwargs.update(merged_params)
        
        # Create instance
        return definition.ta_class(**kwargs)
    
    def calculate(
        self,
        key: str,
        df: pd.DataFrame,
        output_column: Optional[str] = None,
        **params
    ) -> pd.Series:
        """
        Calculate indicator values directly.
        
        Args:
            key: Indicator key
            df: DataFrame with price data
            output_column: Specific output to retrieve (e.g., 'bollinger_hband')
            **params: Override parameters
            
        Returns:
            Series with indicator values
        """
        definition = self.get(key)
        instance = self.create(key, df, **params)
        
        # Determine which output method to call
        if output_column:
            if output_column not in definition.output_methods:
                available = ', '.join(definition.output_methods.keys())
                raise ValueError(
                    f"Unknown output '{output_column}' for '{key}'. "
                    f"Available: {available}"
                )
            method_name = definition.output_methods[output_column]
        else:
            # Use first output method as default
            method_name = list(definition.output_methods.values())[0]
        
        # Call the method
        method = getattr(instance, method_name)
        return method()
    
    def list_indicators(self, category: Optional[str] = None) -> list:
        """
        List available indicators, optionally filtered by category.
        
        Args:
            category: Optional category filter
            
        Returns:
            List of indicator keys
        """
        if category:
            return [
                k for k, v in self._indicators.items() 
                if v.category == category.upper()
            ]
        return list(self._indicators.keys())
    
    def get_warmup_period(self, key: str, **params) -> int:
        """
        Get the warmup period for an indicator.
        
        Args:
            key: Indicator key
            **params: Parameters that may affect warmup
            
        Returns:
            Minimum number of bars needed for valid output
        """
        definition = self.get(key)
        # Use window parameter if provided, otherwise default
        return params.get('window', definition.warmup_period)
