"""
Layer 3 ML Gatekeeper - Swing Trading Signal Filter
===================================================

🚀 SWING TRADING SYSTEM | ML-based quality filtering for swing trade signals

This module provides comprehensive feature engineering and model training
for the Layer 3 ML Gatekeeper, filtering low-probability swing trade setups.
It can be imported by Layer 4 for real-time inference on new signals.
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Optional
import warnings
import json

# Suppress warnings
warnings.filterwarnings('default')

# Configuration
SUPPORTED_GATEKEEPER_GRANULARITIES = {'H1', 'H4'}


def safe_json_load(x):
    """Safely parse JSON string or return empty dict."""
    if pd.isna(x) or x is None:
        return {}
    try:
        if isinstance(x, str):
            return json.loads(x)
        return x
    except:
        return {}


def extract_indicator_snapshot_features(df: pd.DataFrame) -> pd.DataFrame:
    """Extract features from Indicator_Snapshot JSON column."""
    if 'Indicator_Snapshot' not in df.columns:
        return df
    
    snapshots = df['Indicator_Snapshot'].apply(safe_json_load)
    
    # Extract common indicator values
    common_indicators = [
        'RSI', 'EMA_9', 'EMA_21', 'EMA_50', 'EMA_200',
        'MACD', 'MACD_Signal', 'MACD_Histogram',
        'BB_Upper', 'BB_Lower', 'BB_Middle',
        'ATR', 'ADX', 'Stoch_K', 'Stoch_D',
        'CCI', 'Williams_R', 'MFI', 'Volume_SMA',
        'SMA_20', 'SMA_50', 'SMA_200'
    ]
    
    indicator_features = {}
    for indicator in common_indicators:
        values = snapshots.apply(lambda x: x.get(indicator) if isinstance(x, dict) else None)
        if values.notna().sum() > 0:
            indicator_features[f'Ind_{indicator}'] = values
    
    if indicator_features:
        indicator_df = pd.DataFrame(indicator_features, index=df.index)
        df = pd.concat([df, indicator_df], axis=1)
    
    return df


def engineer_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """Engineer derived features from base features."""
    df = df.copy()
    
    # 1. REGIME DUMMIES (explicit columns instead of categories)
    if 'Regime_Label' in df.columns:
        regime_dummies = pd.get_dummies(df['Regime_Label'], prefix='Regime')
        df = pd.concat([df, regime_dummies], axis=1)
    
    # 2. TREND STRENGTH
    if 'ADX_Value' in df.columns:
        df['Trend_Strength_Cat'] = pd.cut(
            df['ADX_Value'],
            bins=[0, 20, 40, 100],
            labels=['Weak', 'Moderate', 'Strong']
        )
    
    if 'Trend_Alignment_Score' in df.columns:
        df['Is_Trend_Aligned'] = (df['Trend_Alignment_Score'] > 0).astype(int)
    
    # 3. VOLATILITY FEATURES
    if 'ATR_Value' in df.columns and 'ATR_Percentile_20D' in df.columns:
        df['ATR_vs_Percentile'] = df['ATR_Value'] / (df['ATR_Percentile_20D'] + 1e-8)
    
    # 4. SESSION/TIME FEATURES
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
        df['Is_Monday'] = (df['Signal_DayOfWeek'] == 1).astype(int)
        df['Is_Friday'] = (df['Signal_DayOfWeek'] == 5).astype(int)
    
    # 5. STRATEGY CATEGORY
    if 'Strategy_ID' in df.columns:
        df['Strategy_Category'] = df['Strategy_ID'].apply(
            lambda x: f'Strat_{int(x)}' if pd.notna(x) else 'Unknown'
        )
    
    # 6. EMA SPREAD (from indicator snapshot)
    if 'Ind_EMA_50' in df.columns and 'Ind_EMA_200' in df.columns:
        df['EMA_Spread'] = df['Ind_EMA_50'] - df['Ind_EMA_200']
    
    return df


def calculate_strategy_performance_features(
    df: pd.DataFrame,
    lookback_windows: List[int] = [20, 50, 100]
) -> pd.DataFrame:
    """Calculate rolling strategy performance features."""
    df = df.copy()
    
    # Initialize with NaN
    for window in lookback_windows:
        df[f'Strat_WinRate_{window}'] = np.nan
        df[f'Strat_Expectancy_{window}'] = np.nan
        df[f'Strat_Trades_{window}'] = np.nan
    
    df['Bars_Since_Last_Trade'] = np.nan
    
    # Calculate per strategy
    for strategy_id in df['Strategy_ID'].unique():
        if pd.isna(strategy_id):
            continue
        
        mask = df['Strategy_ID'] == strategy_id
        strat_df = df[mask].copy().sort_values('Timestamp')
        
        if len(strat_df) < 5:
            continue
        
        for window in lookback_windows:
            # Rolling win rate
            if 'Is_Winner' in strat_df.columns:
                rolling_wins = strat_df['Is_Winner'].rolling(window=window, min_periods=3).mean()
                df.loc[mask, f'Strat_WinRate_{window}'] = rolling_wins.values
            
            # Rolling count
            rolling_count = strat_df['Is_Winner'].rolling(window=window, min_periods=1).count()
            df.loc[mask, f'Strat_Trades_{window}'] = rolling_count.values
            
            # Rolling expectancy
            if 'R_Multiple' in strat_df.columns:
                rolling_exp = strat_df['R_Multiple'].rolling(window=window, min_periods=3).mean()
                df.loc[mask, f'Strat_Expectancy_{window}'] = rolling_exp.values
        
        # Bars since last trade
        df.loc[mask, 'Bars_Since_Last_Trade'] = strat_df.groupby('Strategy_ID')['Timestamp'].diff().dt.total_seconds() / 3600
    
    # Fill NaN with 0.5 for win rates (neutral), 0 for others
    for window in lookback_windows:
        df[f'Strat_WinRate_{window}'] = df[f'Strat_WinRate_{window}'].fillna(0.5)
        df[f'Strat_Expectancy_{window}'] = df[f'Strat_Expectancy_{window}'].fillna(0)
        df[f'Strat_Trades_{window}'] = df[f'Strat_Trades_{window}'].fillna(0)
    
    df['Bars_Since_Last_Trade'] = df['Bars_Since_Last_Trade'].fillna(999)
    
    return df


def create_feature_interactions(df: pd.DataFrame) -> pd.DataFrame:
    """Create interaction features."""
    df = df.copy()
    
    if 'ADX_Value' in df.columns and 'Signal_Confidence' in df.columns:
        df['ADX_x_Confidence'] = df['ADX_Value'] * df['Signal_Confidence']
    
    if 'ATR_Value' in df.columns and 'Trend_Alignment_Score' in df.columns:
        df['ATR_x_TrendAlign'] = df['ATR_Value'] * df['Trend_Alignment_Score']
    
    if 'Is_London_NY_Session' in df.columns and 'Strategy_ID' in df.columns:
        df['LondonSession_x_Strategy'] = df['Is_London_NY_Session'] * df['Strategy_ID']
    
    return df


def add_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add temporal features from Timestamp."""
    df = df.copy()
    
    if 'Timestamp' in df.columns:
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        df['Signal_Hour'] = df['Timestamp'].dt.hour
        df['Signal_DayOfWeek'] = df['Timestamp'].dt.dayofweek + 1  # 1=Monday
        df['Signal_Month'] = df['Timestamp'].dt.month
        df['Signal_Quarter'] = df['Timestamp'].dt.quarter
        
        # Session flags
        df['Is_London_NY_Session'] = df['Signal_Hour'].between(8, 16).astype(int)
        df['Is_Asian_Session'] = df['Signal_Hour'].between(0, 7).astype(int)
        df['Is_US_Session'] = df['Signal_Hour'].between(12, 20).astype(int)
    
    return df


def comprehensive_feature_engineering(df: pd.DataFrame) -> pd.DataFrame:
    """
    Main entry point for comprehensive feature engineering.
    This is called by both Layer 3 training AND Layer 4 inference.
    """
    df = df.copy()
    
    # 1. Add temporal features first (needed by other steps)
    df = add_temporal_features(df)
    
    # 2. Extract indicator snapshot
    df = extract_indicator_snapshot_features(df)
    
    # 3. Engineer derived features
    df = engineer_derived_features(df)
    
    # 4. Calculate strategy performance
    df = calculate_strategy_performance_features(df)
    
    # 5. Create interactions
    df = create_feature_interactions(df)
    
    return df


def align_features_for_inference(
    df: pd.DataFrame,
    expected_columns: List[str]
) -> pd.DataFrame:
    """
    Align DataFrame to match expected feature columns.
    Used by Layer 4 to ensure features match training.
    """
    # Apply comprehensive feature engineering
    df = comprehensive_feature_engineering(df)
    
    # Add expected regime dummy columns if they don't exist
    regime_cols = [c for c in expected_columns if c.startswith('Regime_')]
    for col in regime_cols:
        if col not in df.columns:
            df[col] = 0
    
    # Add expected session dummy columns if they don't exist
    session_cols = [c for c in expected_columns if c.startswith('Session_')]
    for col in session_cols:
        if col not in df.columns:
            df[col] = 0
    
    # Ensure all other expected columns exist
    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0
    
    # Select only expected columns in correct order
    df = df[expected_columns]
    
    return df


# For backward compatibility - re-export training function
if __name__ == "__main__":
    # Import and run training
    from training.train_ml_gatekeeper import main
    main()
