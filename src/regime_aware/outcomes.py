import json
import logging
from typing import List, Dict, Any

import pandas as pd

from src.common.db import bulk_upsert
from src.validation import walk_forward as WF

logger = logging.getLogger(__name__)

def write_trial_outcomes(trades: List[Dict[str, Any]]) -> int:
    """
    Write trial outcomes idempotently to fact_regime_trial_outcomes.
    Refuses to write if regime_source or arm is invalid.
    """
    if not trades:
        return 0

    for t in trades:
        arm = t.get("arm")
        rs = t.get("regime_source")
        if arm not in ("blind", "aware"):
            raise ValueError(f"Invalid or missing arm: {arm!r}. Must be 'blind' or 'aware'.")
        # Validate the source explicitly
        if rs not in ("d1_trend", "hmm_causal", "structural"):
            raise ValueError(f"Invalid or missing regime_source: {rs!r}. Must be 'd1_trend', 'hmm_causal', or 'structural'.")

    df = pd.DataFrame(trades)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    # Populate walk_forward columns if not present
    if "is_oos" not in df.columns or df["is_oos"].isnull().all():
        df["is_oos"] = False
        df["fold_id"] = pd.Series([None] * len(df), dtype="object")
        for gran, sub in df.groupby("granularity"):
            smin, smax = WF.series_bounds(sub["timestamp"])
            folds = WF.default_folds(smin, smax)
            if folds:
                is_oos, fold_id = WF.assign_oos(sub["timestamp"], folds)
                df.loc[sub.index, "is_oos"] = is_oos.to_numpy()
                df.loc[sub.index, "fold_id"] = fold_id

    rows = []
    for rec in df.to_dict("records"):
        if rec.get("mask_applied") is not None and not isinstance(rec["mask_applied"], str):
            rec["mask_applied"] = json.dumps(rec["mask_applied"])
            
        if isinstance(rec["timestamp"], pd.Timestamp):
            rec["timestamp"] = rec["timestamp"].to_pydatetime()
            
        if "leg_index" not in rec:
            rec["leg_index"] = 0
        if "is_terminal_leg" not in rec:
            rec["is_terminal_leg"] = True
            
        rows.append(rec)

    # Normalize keys for bulk_upsert
    all_keys = set()
    for r in rows:
        all_keys.update(r.keys())
    
    normalized_rows = []
    for r in rows:
        # replace NaN with None
        norm = {}
        for k in all_keys:
            val = r.get(k)
            if pd.isna(val):
                norm[k] = None
            else:
                norm[k] = val
        normalized_rows.append(norm)

    # Must match the table's primary key exactly. `regime_source` is in the key because
    # the same trade is evaluated under both label sources; `leg_index` because the
    # scale-out columns already exist and a later leg-aware writer must not need a key
    # change. Omitting either made the second label source silently unstorable.
    conflict_cols = [
        "run_id", "strategy_key", "asset_id", "granularity", "timestamp", "arm",
        "regime_source", "leg_index",
    ]
    
    return bulk_upsert(
        table="fact_regime_trial_outcomes",
        rows=normalized_rows,
        conflict_columns=conflict_cols
    )
