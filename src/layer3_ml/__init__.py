"""
Layer 3 ML Gatekeeper Module

Provides feature engineering and model inference capabilities
for both training (Layer 3) and live execution (Layer 4).
"""

from .train_ml_gatekeeper import (
    comprehensive_feature_engineering,
    SUPPORTED_GATEKEEPER_GRANULARITIES,
)

from .feature_alignment import (
    align_features_for_inference,
    safe_comprehensive_feature_engineering,
    prepare_inference_dataframe,
    validate_inference_data,
    get_feature_column_names,
)

__all__ = [
    'comprehensive_feature_engineering',
    'align_features_for_inference',
    'safe_comprehensive_feature_engineering',
    'prepare_inference_dataframe',
    'validate_inference_data',
    'get_feature_column_names',
    'SUPPORTED_GATEKEEPER_GRANULARITIES',
]
