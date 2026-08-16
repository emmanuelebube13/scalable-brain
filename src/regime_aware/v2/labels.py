"""Regime label resolution for the v2 path."""

import pandas as pd
from typing import Dict
from src.regime_aware.context import (
    load_regime_labels,
    attach_regime,
    build_trend_labels,
    CAUSAL_COLUMN,
    UNKNOWN,
)
from src.layer0.strategies.research_data import load_ohlcv_readonly

def resolve_regime_labels(
    conn,
    pair: str,
    granularity: str,
    price_index: pd.DatetimeIndex,
    regime_source: str,
    lookback_years: int = 10,
) -> pd.Series:
    """
    Given a pair, a granularity and a frame index, return the label per bar
    under a stated regime_source.
    
    Joined backward onto the frame so bar t carries a label derived strictly from before t.
    """
    if regime_source not in ("d1_trend", "hmm_causal"):
        raise ValueError(f"Unknown regime_source: {regime_source}")

    labels_df = None

    if regime_source == "d1_trend":
        d1_df = load_ohlcv_readonly(pair, "D1", lookback_years=lookback_years)
        if d1_df is not None and not d1_df.empty:
            labels_df = build_trend_labels(d1_df)
    
    elif regime_source == "hmm_causal":
        cursor = conn.cursor()
        cursor.execute("SELECT asset_id FROM dim_asset WHERE symbol = %s", (pair,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Asset not found for pair {pair}")
        asset_id = int(row[0])
        
        all_labels = load_regime_labels(conn, granularity, CAUSAL_COLUMN)
        labels_df = all_labels.get(asset_id)

    # Convert the price index to a DataFrame for merging
    price_df = pd.DataFrame(index=price_index)
    
    # attach_regime handles the direction="backward" merge safely
    with_regime = attach_regime(price_df, labels_df)
    
    # attach_regime returns a DataFrame with the same index and a 'regime' column
    return pd.Series(with_regime["regime"].values, index=price_index)
