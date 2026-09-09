import pandas as pd
from src.layer0.data_access.indicators import atr, adx
from src.regime.structural import build_structural_labels


from sqlalchemy import text
from src.common.db import get_engine

def build_inference_features(
    decision_frame: pd.DataFrame, granularity: str = "D1", symbol: str = None
) -> pd.DataFrame:
    """Build inference features for a sequence of decision bars.

    Returns a DataFrame indexed by the decision_frame's index with columns:
    - atr_value
    - adx_value
    - regime_structural
    """
    df = pd.DataFrame(index=decision_frame.index)
    df["atr_value"] = atr(
        decision_frame["High"],
        decision_frame["Low"],
        decision_frame["Close"],
        period=14,
    )
    df["adx_value"] = adx(
        decision_frame["High"],
        decision_frame["Low"],
        decision_frame["Close"],
        period=14,
    )

    if decision_frame.empty:
        df["regime_structural"] = None
        return df

    # Find the asset_id either from the frame or by looking up the symbol
    asset_id = None
    if "asset_id" in decision_frame.columns:
        asset_id = int(decision_frame["asset_id"].iloc[0])
    elif symbol is not None:
        with get_engine().connect() as conn:
            row = conn.execute(
                text("SELECT asset_id FROM dim_asset WHERE symbol = :sym"),
                {"sym": symbol}
            ).fetchone()
            if row:
                asset_id = int(row[0])
    
    if asset_id is None:
        raise ValueError("Could not determine asset_id for regime label lookup")

    sql = text("""
        SELECT bar_time_utc, regime 
        FROM fact_regime_structural 
        WHERE asset_id = :asset_id AND granularity = :granularity
    """)
    
    with get_engine().connect() as conn:
        labels_df = pd.read_sql(
            sql,
            conn,
            params={"asset_id": asset_id, "granularity": granularity}
        )

    if labels_df.empty:
        raise ValueError(
            f"No structural labels found in fact_regime_structural for asset {asset_id} at {granularity}. "
            "Never silently fallback."
        )

    labels_df["bar_time_utc"] = pd.to_datetime(labels_df["bar_time_utc"], utc=True)
    labels_df = labels_df.set_index("bar_time_utc")

    # Left join to preserve exact decision_frame rows
    joined = df.join(labels_df[["regime"]], how="left")
    
    if joined["regime"].isna().any():
        missing = joined[joined["regime"].isna()]
        raise ValueError(
            f"Missing structural labels in fact_regime_structural for asset {asset_id} at {granularity}. "
            f"Missing for {len(missing)} bars (e.g. {missing.index[0]}). Never silently fallback."
        )

    df["regime_structural"] = joined["regime"]
    return df
