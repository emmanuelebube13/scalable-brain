"""
Feature Alignment for ML Gatekeeper
====================================

Robust feature engineering and alignment for training/inference compatibility.

This module handles:
1. Dynamic feature engineering with missing column fallbacks
2. Column alignment between training and inference
3. ColumnTransformer safe feature preparation
4. Data type conversion and validation

Key Problem Solved:
-  sklearn ColumnTransformer fitted with specific column names during training
-  During inference, those exact columns must exist
-  Feature engineering creates columns dynamically  
-  This module ensures consistency between training and inference
"""

import json
import pandas as pd
import numpy as np
from typing import List, Dict, Set, Tuple, Optional, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# SAFE FEATURE ENGINEERING WITH FALLBACKS
# ============================================================================

def extract_indicator_snapshot_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Safely extract features from Indicator_Snapshot JSON column.
    Returns DataFrame with NaN for missing values (preprocessor handles imputation).
    """
    if 'Indicator_Snapshot' not in df.columns:
        return df
    
    df = df.copy()
    
    def safe_json_load(x):
        if pd.isna(x) or x is None:
            return {}
        try:
            if isinstance(x, str):
                return json.loads(x)
            return x if isinstance(x, dict) else {}
        except:
            return {}
    
    snapshots = df['Indicator_Snapshot'].apply(safe_json_load)
    
    # Extract common indicator values - only add if at least one value exists
    common_indicators = [
        'RSI', 'EMA_9', 'EMA_21', 'EMA_50', 'EMA_200',
        'MACD', 'MACD_Signal', 'MACD_Histogram',
        'BB_Upper', 'BB_Lower', 'BB_Middle',
        'ATR', 'ADX', 'Stoch_K', 'Stoch_D',
        'CCI', 'Williams_R', 'MFI', 'Volume_SMA',
        'SMA_20', 'SMA_50', 'SMA_200'
    ]
    
    for indicator in common_indicators:
        values = snapshots.apply(lambda x: x.get(indicator) if isinstance(x, dict) else None)
        # Only add if we have some non-null values
        if values.notna().sum() > 0:
            df[f'Ind_{indicator}'] = values
    
    return df


def create_regime_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create binary regime flags and derived regime features with NaN fallbacks."""
    df = df.copy()
    
    if 'Regime_Label' in df.columns:
        # Create binary regime flags
        regime_dummies = pd.get_dummies(df['Regime_Label'], prefix='Regime')
        df = pd.concat([df, regime_dummies], axis=1)
    
    if 'ADX_Value' in df.columns:
        # Trend strength categorization
        df['Trend_Strength_Cat'] = pd.cut(
            df['ADX_Value'],
            bins=[0, 20, 40, 100],
            labels=['Weak', 'Moderate', 'Strong']
        )
    
    if 'Trend_Alignment_Score' in df.columns:
        df['Is_Trend_Aligned'] = (df['Trend_Alignment_Score'] > 0).astype(float)
    
    return df


def create_volatility_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create volatility features with safe division and NaN handling."""
    df = df.copy()
    
    if 'ATR_Value' in df.columns and 'ATR_Percentile_20D' in df.columns:
        df['ATR_vs_Percentile'] = df['ATR_Value'] / (df['ATR_Percentile_20D'] + 1e-8)
    
    if 'Volatility_Regime' in df.columns:
        vol_dummies = pd.get_dummies(df['Volatility_Regime'], prefix='VolRegime')
        df = pd.concat([df, vol_dummies], axis=1)
    
    return df


def create_session_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create session and time-based features with NaN handling."""
    df = df.copy()
    
    if 'Signal_Hour' in df.columns:
        df['Session_Category'] = pd.cut(
            df['Signal_Hour'],
            bins=[0, 7, 12, 16, 20, 24],
            labels=['Asian', 'London_Early', 'London_US_Overlap', 'US', 'Late'],
            include_lowest=True
        )
        session_dummies = pd.get_dummies(df['Session_Category'], prefix='Session')
        df = pd.concat([df, session_dummies], axis=1)
    
    if 'Signal_DayOfWeek' in df.columns:
        df['Is_Monday'] = (df['Signal_DayOfWeek'] == 1).astype(float)
        df['Is_Friday'] = (df['Signal_DayOfWeek'] == 5).astype(float)
    
    return df


def create_signal_quality_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create signal quality interaction features."""
    df = df.copy()
    
    if 'Signal_Confidence' in df.columns and 'Signal_Value' in df.columns:
        df['Confidence_x_Signal'] = df['Signal_Confidence'] * df['Signal_Value']
    
    return df


def create_momentum_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create momentum and technical indicator-based features."""
    df = df.copy()
    
    # EMA spread
    ema_cols = sorted([c for c in df.columns if c.startswith('Ind_EMA_')])
    if len(ema_cols) >= 2:
        df['EMA_Spread'] = df[ema_cols[0]] - df[ema_cols[1]]
    
    # RSI categorization
    if 'Ind_RSI' in df.columns:
        df['RSI_Category'] = pd.cut(
            df['Ind_RSI'],
            bins=[0, 30, 45, 55, 70, 100],
            labels=['Oversold', 'Bullish_Neutral', 'Neutral', 'Bearish_Neutral', 'Overbought']
        )
        rsi_dummies = pd.get_dummies(df['RSI_Category'], prefix='RSI')
        df = pd.concat([df, rsi_dummies], axis=1)
    
    return df


def create_interaction_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create high-impact interaction features."""
    df = df.copy()
    
    if 'ADX_Value' in df.columns and 'Signal_Confidence' in df.columns:
        df['ADX_x_Confidence'] = df['ADX_Value'] * df['Signal_Confidence']
    
    if 'ATR_Value' in df.columns and 'Trend_Alignment_Score' in df.columns:
        df['ATR_x_TrendAlign'] = df['ATR_Value'] * df['Trend_Alignment_Score']
    
    if 'Is_London_NY_Session' in df.columns and 'Strategy_ID' in df.columns:
        df['LondonSession_x_Strategy'] = df['Is_London_NY_Session'] * df['Strategy_ID']
    
    return df


def safe_comprehensive_feature_engineering(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply comprehensive feature engineering with safe fallbacks.
    
    This ensures:
    - All features are created even if input columns are missing
    - Missing values are represented as NaN (handled by preprocessor imputation)
    - No exceptions thrown during inference
    
    Args:
        df: Input DataFrame with potentially sparse features
        
    Returns:
        DataFrame with all generated features (NaN where unavailable)
    """
    logger.debug(f"Feature engineering start: {len(df)} rows, {len(df.columns)} columns")
    
    # Step 1: Indicator snapshot extraction
    df = extract_indicator_snapshot_features(df)
    logger.debug(f"After indicators: {len(df.columns)} columns")
    
    # Step 2: Regime features
    df = create_regime_features(df)
    logger.debug(f"After regime: {len(df.columns)} columns")
    
    # Step 3: Volatility features
    df = create_volatility_features(df)
    logger.debug(f"After volatility: {len(df.columns)} columns")
    
    # Step 4: Session/time features
    df = create_session_features(df)
    logger.debug(f"After session: {len(df.columns)} columns")
    
    # Step 5: Signal quality features
    df = create_signal_quality_features(df)
    logger.debug(f"After signal quality: {len(df.columns)} columns")
    
    # Step 6: Momentum features
    df = create_momentum_features(df)
    logger.debug(f"After momentum: {len(df.columns)} columns")
    
    # Step 7: Interaction features
    df = create_interaction_features(df)
    logger.debug(f"After interactions: {len(df.columns)} columns (final)")
    
    return df


# ============================================================================
# FEATURE ALIGNMENT FOR INFERENCE
# ============================================================================

def align_features_for_inference(
    df: pd.DataFrame,
    expected_columns: List[str],
    fill_value: float = 0.0
) -> pd.DataFrame:
    """
    Align inference DataFrame to match expected training columns.
    
    This function:
    1. Keeps only columns that match expected_columns
    2. Adds missing columns with NaN values (preprocessor will impute)
    3. Reorders to match expected_columns order
    4. Converts data types to numeric where possible
    
    Args:
        df: Input DataFrame from inference
        expected_columns: Column names from training (in preprocessor)
        fill_value: Value to use for missing columns (default: NaN via 0.0 which becomes NaN)
        
    Returns:
        DataFrame with exactly expected_columns in correct order
    """
    logger.debug(f"Aligning features: {len(df.columns)} input -> {len(expected_columns)} expected")
    
    # Convert all columns to numeric where possible
    for col in df.columns:
        if df[col].dtype == 'object':
            try:
                df[col] = pd.to_numeric(df[col], errors='ignore')
            except:
                pass
    
    # Create output dataframe with all expected columns
    result = pd.DataFrame(index=df.index)
    
    for col in expected_columns:
        if col in df.columns:
            # Use existing column
            result[col] = df[col]
        else:
            # Add missing column with NaN (preprocessor will impute)
            result[col] = np.nan
            logger.debug(f"Adding missing column with NaN: {col}")
    
    logger.debug(
        f"Alignment complete: {result.shape[0]} rows, {result.shape[1]} columns\n"
        f"  Missing columns added: {len([c for c in expected_columns if c not in df.columns])}\n"
        f"  Data types: {result.dtypes.value_counts().to_dict()}"
    )
    
    return result


def ensure_feature_columns_exist(df: pd.DataFrame, required_columns: List[str]) -> pd.DataFrame:
    """
    Ensure all required feature columns exist in DataFrame.
    
    Creates missing columns with NaN values.
    
    Args:
        df: Input DataFrame
        required_columns: List of column names that must exist
        
    Returns:
        DataFrame with all required columns present
    """
    df = df.copy()
    
    missing = set(required_columns) - set(df.columns)
    if missing:
        for col in missing:
            df[col] = np.nan
            logger.debug(f"Added missing column: {col}")
    
    return df


# ============================================================================
# COLUMN INSPECTION AND VALIDATION
# ============================================================================

def get_feature_column_names(preprocessor) -> List[str]:
    """
    Extract feature column names from sklearn ColumnTransformer.
    
    Args:
        preprocessor: Fitted sklearn ColumnTransformer
        
    Returns:
        List of feature column names
    """
    feature_columns = []
    
    # Try to get from transformers
    if hasattr(preprocessor, 'transformers_'):
        for name, transformer, columns in preprocessor.transformers_:
            if name != 'remainder':
                if isinstance(columns, list):
                    feature_columns.extend(columns)
                elif hasattr(columns, 'tolist'):
                    feature_columns.extend(columns.tolist())
    
    return list(set(feature_columns))  # Remove duplicates


def validate_inference_data(
    df: pd.DataFrame,
    expected_columns: List[str],
    raise_on_error: bool = False
) -> Tuple[bool, List[str], List[str]]:
    """
    Validate that inference data has (or can have) all expected columns.
    
    Args:
        df: Inference DataFrame
        expected_columns: Expected feature columns from training
        raise_on_error: If True, raise ValueError on missing columns
        
    Returns:
        Tuple of (is_valid, missing_columns, extra_columns)
    """
    df_cols = set(df.columns)
    expected = set(expected_columns)
    
    missing = expected - df_cols
    extra = df_cols - expected
    
    is_valid = len(missing) == 0
    
    if missing and raise_on_error:
        raise ValueError(
            f"Missing {len(missing)} required columns: {sorted(missing)}"
        )
    
    return is_valid, sorted(list(missing)), sorted(list(extra))


# ============================================================================
# INTEGRATION UTILITIES
# ============================================================================

def prepare_inference_dataframe(
    raw_data: pd.DataFrame,
    expected_columns: Optional[List[str]] = None,
    apply_feature_engineering: bool = True
) -> pd.DataFrame:
    """
    Complete inference pipeline: feature engineering + alignment.
    
    Args:
        raw_data: Raw signal data from DB
        expected_columns: Expected columns from trained model
        apply_feature_engineering: Whether to apply feature engineering
        
    Returns:
        Ready-to-predict DataFrame
    """
    df = raw_data.copy()
    
    if apply_feature_engineering:
        df = safe_comprehensive_feature_engineering(df)
    
    if expected_columns:
        df = align_features_for_inference(df, expected_columns)
    
    return df


if __name__ == "__main__":
    # Example usage and testing
    logging.basicConfig(level=logging.DEBUG)
    
    # Create sample data
    sample = pd.DataFrame({
        'Timestamp': pd.date_range('2026-01-01', periods=100),
        'Asset_ID': [1] * 100,
        'Strategy_ID': [1] * 100,
        'Signal_Value': [1, -1] * 50,
        'Signal_Confidence': np.random.rand(100),
        'Regime_Label': ['Trending'] * 50 + ['Ranging'] * 50,
        'ATR_Value': np.random.rand(100) * 100,
        'ADX_Value': np.random.rand(100) * 100,
        'Indicator_Snapshot': ['{}'] * 100,
    })
    
    # Feature engineering
    engineered = safe_comprehensive_feature_engineering(sample)
    print(f"Engineered features: {engineered.shape}")
    print(f"Columns: {list(engineered.columns)[:10]}...")
    
    # Alignment example
    expected = list(engineered.columns)
    sparse = engineered.drop(10)  # Remove some columns
    aligned = align_features_for_inference(sparse, expected)
    print(f"\nAligned from {sparse.shape[1]} to {aligned.shape[1]} columns")
    print(f"Missing: {len(set(expected) - set(sparse.columns))}")
