"""
Layer 3 ML Gatekeeper Module

Provides legacy inference-side feature alignment utilities.

FIX-S1-009: the root ``train_ml_gatekeeper`` module (a dead third feature
pipeline) was retired; this package no longer exports
``comprehensive_feature_engineering`` / ``SUPPORTED_GATEKEEPER_GRANULARITIES``
from it. The canonical feature pipeline is
``src/system1/features/feature_pipeline.py``; gatekeeper retraining/promotion
is governed by the System-1 orchestrator only.
"""

from .feature_alignment import (
    align_features_for_inference,
    safe_comprehensive_feature_engineering,
    prepare_inference_dataframe,
    validate_inference_data,
    get_feature_column_names,
)

__all__ = [
    'align_features_for_inference',
    'safe_comprehensive_feature_engineering',
    'prepare_inference_dataframe',
    'validate_inference_data',
    'get_feature_column_names',
]
