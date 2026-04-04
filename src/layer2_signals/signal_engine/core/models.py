"""
Data models for the signal engine.
"""

import json
import hashlib
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd


@dataclass
class StrategyConfig:
    """
    Complete strategy configuration loaded from database.
    
    Attributes:
        strategy_id: Strategy identifier
        strategy_key: Business key
        strategy_name: Display name
        config_id: Configuration version ID
        config_version: Semantic version string
        config_hash: SHA-256 hash of config
        granularity: Time granularity
        asset_id: Asset identifier (for grouping)
        indicator_configs: List of indicator configurations
        signal_rules: List of signal rule definitions
        risk_filters: Optional risk management filters
    """
    strategy_id: int
    strategy_key: str
    strategy_name: str
    config_id: int
    config_version: str
    config_hash: str
    granularity: str
    asset_id: int
    indicator_configs: List[Dict[str, Any]]
    signal_rules: List[Dict[str, Any]]
    risk_filters: Optional[List[Dict[str, Any]]] = None
    
    @classmethod
    def from_db_row(cls, row: tuple, columns: List[str]) -> "StrategyConfig":
        """
        Create StrategyConfig from database query result.
        
        Args:
            row: Database row tuple
            columns: Column names
            
        Returns:
            StrategyConfig instance
        """
        data = dict(zip(columns, row))
        
        return cls(
            strategy_id=data['Strategy_ID'],
            strategy_key=data['Strategy_Key'],
            strategy_name=data['Strategy_Name'],
            config_id=data['Config_ID'],
            config_version=data['Config_Version'],
            config_hash=data['Config_Hash'],
            granularity=data['Granularity'],
            asset_id=data['Asset_ID'],
            indicator_configs=json.loads(data['Indicator_Configs']),
            signal_rules=json.loads(data['Signal_Rules']),
            risk_filters=json.loads(data['Risk_Filters']) if data.get('Risk_Filters') else None
        )
    
    def compute_hash(self) -> str:
        """
        Compute SHA-256 hash of configuration.
        
        Returns:
            Hash string for traceability
        """
        config_data = {
            'indicator_configs': self.indicator_configs,
            'signal_rules': self.signal_rules,
            'risk_filters': self.risk_filters
        }
        config_str = json.dumps(config_data, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()
    
    def validate(self) -> List[str]:
        """
        Validate configuration.
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        if not self.indicator_configs:
            errors.append("No indicator configurations defined")
        
        if not self.signal_rules:
            errors.append("No signal rules defined")
        
        # Validate indicator configs
        for i, config in enumerate(self.indicator_configs):
            if 'indicator_key' not in config:
                errors.append(f"Indicator config {i}: missing 'indicator_key'")
            if 'instance_name' not in config:
                errors.append(f"Indicator config {i}: missing 'instance_name'")
        
        # Validate signal rules
        for i, rule in enumerate(self.signal_rules):
            if 'rule_id' not in rule:
                errors.append(f"Signal rule {i}: missing 'rule_id'")
            if 'signal_value' not in rule:
                errors.append(f"Signal rule {i}: missing 'signal_value'")
            if 'conditions' not in rule:
                errors.append(f"Signal rule {i}: missing 'conditions'")
        
        return errors


@dataclass
class SignalResult:
    """
    Result of signal generation for a single strategy.
    
    Attributes:
        strategy_id: Strategy identifier
        config_id: Configuration version ID
        config_version: Config version string
        config_hash: Config hash for traceability
        granularity: Time granularity
        signals_df: DataFrame with signal data
        rows_generated: Number of non-zero signals
        execution_time_ms: Execution time in milliseconds
    """
    strategy_id: int
    config_id: int
    config_version: str
    config_hash: str
    granularity: str
    signals_df: pd.DataFrame
    rows_generated: int
    execution_time_ms: float
    
    def to_records(self) -> List[Dict[str, Any]]:
        """
        Convert to list of dictionary records for persistence.
        
        Returns:
            List of signal records
        """
        records = []
        
        for _, row in self.signals_df.iterrows():
            if row.get('Signal_Value', 0) == 0:
                continue
            
            record = {
                'Timestamp': row['Timestamp'],
                'Asset_ID': row['Asset_ID'],
                'Granularity': self.granularity,
                'Strategy_ID': self.strategy_id,
                'Signal_Value': row['Signal_Value'],
                'Strategy_Version': self.config_version,
                'Config_Hash': self.config_hash,
                'Signal_Reason': row.get('Signal_Reason'),
                'Rule_ID': row.get('Rule_ID'),
                'Indicator_Snapshot': row.get('Indicator_Snapshot'),
                'Confidence_Score': row.get('Confidence_Score'),
            }
            records.append(record)
        
        return records


@dataclass
class ProcessingSummary:
    """
    Summary of signal generation processing.
    
    Attributes:
        total_strategies: Number of strategies processed
        total_assets: Number of assets processed
        total_signals: Total signals generated
        execution_time_ms: Total execution time
        errors: List of errors encountered
        batch_id: Batch identifier
    """
    total_strategies: int
    total_assets: int
    total_signals: int
    execution_time_ms: float
    errors: List[str] = field(default_factory=list)
    batch_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'total_strategies': self.total_strategies,
            'total_assets': self.total_assets,
            'total_signals': self.total_signals,
            'execution_time_ms': self.execution_time_ms,
            'errors': self.errors,
            'batch_id': self.batch_id
        }
