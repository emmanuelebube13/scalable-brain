"""
Indicator Calculator - Vectorized indicator computation with caching.

Provides efficient calculation of technical indicators using pandas and ta library,
with support for lazy evaluation and result caching.
"""

import logging
import hashlib
import json
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass

import pandas as pd
import numpy as np

from signal_engine.indicators.registry import IndicatorRegistry, IndicatorDefinition
from signal_engine.indicators.dependency_graph import DependencyGraph, IndicatorNode

logger = logging.getLogger(__name__)


@dataclass
class IndicatorConfig:
    """Configuration for a single indicator instance."""
    instance_name: str
    indicator_key: str
    params: Dict[str, Any]
    output_column: Optional[str] = None
    output_columns: Optional[List[str]] = None


class IndicatorCalculator:
    """
    Vectorized indicator calculator with dependency-aware lazy evaluation.
    
    This class efficiently calculates technical indicators by:
    1. Building a dependency graph from strategy configurations
    2. Computing only required indicators (lazy evaluation)
    3. Vectorized operations using pandas/ta (no row iteration)
    4. Caching results to avoid redundant calculations
    
    Example:
        calculator = IndicatorCalculator()
        
        # Define what we need
        calculator.add_indicator_config(
            instance_name='EMA_50',
            indicator_key='EMA',
            params={'window': 50}
        )
        
        # Calculate all indicators
        results = calculator.calculate(df)
        
        # Access results
        ema_values = results['EMA_50']
    """
    
    def __init__(self, registry: Optional[IndicatorRegistry] = None):
        """
        Initialize the calculator.
        
        Args:
            registry: Optional custom indicator registry
        """
        self.registry = registry or IndicatorRegistry()
        self.dependency_graph = DependencyGraph()
        self._configs: Dict[str, IndicatorConfig] = {}
        self._cache: Dict[str, pd.Series] = {}
        self._cache_key: Optional[str] = None
        logger.debug("Initialized IndicatorCalculator")
    
    def add_indicator_config(
        self,
        instance_name: str,
        indicator_key: str,
        params: Dict[str, Any],
        output_column: Optional[str] = None,
        output_columns: Optional[List[str]] = None
    ) -> None:
        """
        Add an indicator configuration.
        
        Args:
            instance_name: Unique name for this instance
            indicator_key: Base indicator type
            params: Parameters for calculation
            output_column: Single output column name
            output_columns: Multiple output column names
        """
        config = IndicatorConfig(
            instance_name=instance_name,
            indicator_key=indicator_key,
            params=params,
            output_column=output_column,
            output_columns=output_columns
        )
        
        self._configs[instance_name] = config
        
        # Add to dependency graph
        self.dependency_graph.add_indicator(
            instance_name=instance_name,
            indicator_key=indicator_key,
            params=params,
            output_column=output_column
        )
        
        logger.debug(f"Added indicator config: {instance_name}")
    
    def add_configs_from_json(self, configs_json: List[Dict]) -> None:
        """
        Add multiple indicator configs from JSON (database format).
        
        Args:
            configs_json: List of indicator config dictionaries from database
        """
        for config in configs_json:
            instance_name = config['instance_name']
            indicator_key = config['indicator_key']
            params = config.get('params', {})
            
            # Handle single or multiple outputs
            output_column = config.get('output_column')
            output_columns = config.get('output_columns')
            
            self.add_indicator_config(
                instance_name=instance_name,
                indicator_key=indicator_key,
                params=params,
                output_column=output_column,
                output_columns=output_columns
            )
        
        logger.info(f"Added {len(configs_json)} indicator configs from JSON")
    
    def calculate(
        self,
        df: pd.DataFrame,
        required_indicators: Optional[Set[str]] = None,
        use_cache: bool = True
    ) -> Dict[str, pd.Series]:
        """
        Calculate all configured indicators.
        
        Args:
            df: DataFrame with price data (Open, High, Low, Close)
            required_indicators: Optional subset of indicators to calculate
            use_cache: Whether to use cached results
            
        Returns:
            Dictionary mapping instance names to Series of indicator values
        """
        # Generate cache key from DataFrame
        cache_key = self._generate_cache_key(df)
        
        # Clear cache if DataFrame changed
        if use_cache and cache_key != self._cache_key:
            self._cache.clear()
            self._cache_key = cache_key
        
        # Determine which indicators to calculate
        if required_indicators:
            to_calculate = self.dependency_graph.get_required_indicators(
                list(required_indicators)
            )
        else:
            to_calculate = set(self._configs.keys())
        
        # Get execution order
        execution_order = self.dependency_graph.get_execution_order()
        
        # Filter to only required indicators
        execution_order = [name for name in execution_order if name in to_calculate]
        
        results = {}
        
        for instance_name in execution_order:
            # Check cache first
            if use_cache and instance_name in self._cache:
                results[instance_name] = self._cache[instance_name]
                logger.debug(f"Using cached result for {instance_name}")
                continue
            
            config = self._configs.get(instance_name)
            if not config:
                logger.warning(f"No config found for {instance_name}, skipping")
                continue
            
            try:
                # Calculate the indicator
                indicator_results = self._calculate_single(df, config)
                
                # Store results
                for key, series in indicator_results.items():
                    results[key] = series
                    if use_cache:
                        self._cache[key] = series
                
                logger.debug(f"Calculated indicator: {instance_name}")
                
            except Exception as e:
                logger.error(f"Failed to calculate {instance_name}: {e}")
                raise
        
        logger.info(f"Calculated {len(results)} indicator series")
        return results
    
    def _calculate_single(
        self,
        df: pd.DataFrame,
        config: IndicatorConfig
    ) -> Dict[str, pd.Series]:
        """
        Calculate a single indicator instance.
        
        Args:
            df: DataFrame with price data
            config: Indicator configuration
            
        Returns:
            Dictionary of output names to Series
        """
        definition = self.registry.get(config.indicator_key)
        
        # Create indicator instance
        instance = self.registry.create(
            config.indicator_key,
            df,
            **config.params
        )
        
        results = {}
        
        # Determine which outputs to calculate
        if config.output_columns:
            outputs = config.output_columns
        elif config.output_column:
            outputs = [config.output_column]
        else:
            # Use all available outputs
            outputs = list(definition.output_methods.keys())
        
        # Calculate each output
        for output_name in outputs:
            if output_name not in definition.output_methods:
                logger.warning(
                    f"Unknown output '{output_name}' for {config.indicator_key}, "
                    f"available: {list(definition.output_methods.keys())}"
                )
                continue
            
            method_name = definition.output_methods[output_name]
            method = getattr(instance, method_name)
            series = method()
            
            # Store with instance prefix for uniqueness
            result_key = f"{config.instance_name}.{output_name}" if len(outputs) > 1 else config.instance_name
            results[result_key] = series
        
        return results
    
    def get_warmup_period(self, instance_names: Optional[List[str]] = None) -> int:
        """
        Calculate the maximum warmup period needed.
        
        Args:
            instance_names: Optional list of indicators to consider
            
        Returns:
            Maximum warmup period in bars
        """
        max_warmup = 0
        
        names = instance_names or list(self._configs.keys())
        
        for name in names:
            config = self._configs.get(name)
            if config:
                warmup = self.registry.get_warmup_period(config.indicator_key, **config.params)
                max_warmup = max(max_warmup, warmup)
        
        return max_warmup
    
    def clear_cache(self) -> None:
        """Clear the indicator cache."""
        self._cache.clear()
        self._cache_key = None
        logger.debug("Cleared indicator cache")
    
    def reset(self) -> None:
        """Reset calculator state."""
        self._configs.clear()
        self.dependency_graph.clear()
        self.clear_cache()
        logger.debug("Reset IndicatorCalculator")
    
    def _generate_cache_key(self, df: pd.DataFrame) -> str:
        """
        Generate a cache key from DataFrame characteristics.
        
        Args:
            df: DataFrame to hash
            
        Returns:
            Hash string representing DataFrame state
        """
        # Use shape and first/last timestamp for key
        key_data = {
            'shape': df.shape,
            'columns': list(df.columns),
            'start': str(df.index[0]) if len(df) > 0 else None,
            'end': str(df.index[-1]) if len(df) > 0 else None,
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()[:16]
    
    def get_dataframe_with_indicators(
        self,
        df: pd.DataFrame,
        required_indicators: Optional[Set[str]] = None,
        prefix: str = ""
    ) -> pd.DataFrame:
        """
        Get a DataFrame with indicator columns added.
        
        Args:
            df: Original DataFrame with price data
            required_indicators: Optional subset of indicators
            prefix: Optional prefix for indicator column names
            
        Returns:
            DataFrame with indicator columns added
        """
        results = self.calculate(df, required_indicators)
        
        df_copy = df.copy()
        
        for name, series in results.items():
            col_name = f"{prefix}{name}" if prefix else name
            df_copy[col_name] = series
        
        return df_copy
