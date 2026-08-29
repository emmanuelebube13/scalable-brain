import pandas as pd
from src.layer0.data_access.indicators import atr, adx
from src.regime.structural import build_structural_labels


def build_inference_features(
    decision_frame: pd.DataFrame, d1_frame: pd.DataFrame
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

    labels = build_structural_labels(d1_frame).set_index("bar_time")

    # Merge D1 labels to the decision frame using point-in-time backward join
    decision_times = pd.DataFrame(index=decision_frame.index).reset_index()
    time_col = decision_times.columns[0]
    decision_times = decision_times.rename(columns={time_col: "bar_time"})

    labels = labels.sort_index().reset_index()
    merged = pd.merge_asof(
        decision_times.sort_values("bar_time"),
        labels,
        on="bar_time",
        direction="backward",
    ).set_index("bar_time")

    df["regime_structural"] = merged["regime"].values
    return df
