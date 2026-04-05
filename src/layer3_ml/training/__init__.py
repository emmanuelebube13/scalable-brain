"""
Layer 3 ML Training Module
"""

# Import key functions for external use
from .train_ml_gatekeeper import (
    comprehensive_feature_engineering,
    SUPPORTED_GATEKEEPER_GRANULARITIES,
    extract_indicator_snapshot_features,
    engineer_derived_features,
    calculate_strategy_performance_features,
    create_feature_interactions,
)

__all__ = [
    'comprehensive_feature_engineering',
    'SUPPORTED_GATEKEEPER_GRANULARITIES',
    'extract_indicator_snapshot_features',
    'engineer_derived_features',
    'calculate_strategy_performance_features',
    'create_feature_interactions',
]
