"""Gatekeeper scoring inference."""

import os
from typing import Any, Dict, Optional, Union
import numpy as np
import pandas as pd
import joblib


class Scorer:
    """Scorer applies the champion gatekeeper model to incoming signal feature rows."""

    def __init__(self, models_dir: str):
        self.model_path = os.path.join(models_dir, "champion_model.pkl")
        self.preprocessor_path = os.path.join(models_dir, "champion_preprocessor.pkl")
        self.manifest_path = os.path.join(models_dir, "champion_manifest.json")
        self._load()

    def _load(self):
        if not os.path.exists(self.model_path) or not os.path.exists(
            self.preprocessor_path
        ):
            self.model = None
            self.preprocessor = None
            self.known_strategies = set()
            return

        self.model = joblib.load(self.model_path)
        self.preprocessor = joblib.load(self.preprocessor_path)

        # Extract known strategy IDs from the preprocessor's categorical encoder
        # The preprocessor is a ColumnTransformer, we need to find the strategy_id column
        self.known_strategies = set()
        for name, trans, cols in self.preprocessor.transformers_:
            if name == "cat" and hasattr(trans, "categories_"):
                # cols are e.g. ['regime_causal', 'strategy_id', 'entry_signal_type']
                if "strategy_id" in cols:
                    idx = cols.index("strategy_id")
                    self.known_strategies = set(trans.categories_[idx])
                elif "strategy_id" in getattr(trans, "feature_names_in_", []):
                    idx = list(trans.feature_names_in_).index("strategy_id")
                    self.known_strategies = set(trans.categories_[idx])

    def score(self, features: Dict[str, Any]) -> Dict[str, Union[Optional[float], str]]:
        """Score a single feature row.

        Returns a dict:
        {"status": "scored", "score": float} OR {"status": "refused", "reason": str}
        """
        if self.model is None or self.preprocessor is None:
            return {"status": "refused", "reason": "NO_CHAMPION_MODEL"}

        strat_id = features.get("strategy_id")
        # Cold start policy: Refuse unknown strategy IDs.
        # F-103 remediation.
        if (
            strat_id not in self.known_strategies
            and str(strat_id) not in self.known_strategies
        ):
            return {"status": "refused", "reason": "UNKNOWN_STRATEGY_ID"}

        # ABSENT and NaN are different refusals and must not share a reason.
        #
        # A feature the caller never supplied means the gatekeeper has no input and
        # therefore no opinion — unscorable. A feature that is present but NaN means the
        # data is corrupt — genuinely untradeable. Both used to return NAN_FEATURE, so
        # the producer could not tell them apart and dropped the signal either way.
        #
        # That mattered because the live path supplies NONE of these features: the
        # champion trains on atr_value / adx_value / prob_causal_* / regime_causal read
        # from fact_market_regime_v2, and those rows are written retrospectively — a live
        # bar has no row there at all. So every live signal refused with
        # NAN_FEATURE:atr_value and was silently discarded, which is why nothing ever
        # reached the queue even once ATR construction was fixed.
        expected = getattr(self.preprocessor, "feature_names_in_", None)
        if expected is not None:
            for f in expected:
                if f not in features:
                    return {"status": "refused", "reason": f"MISSING_FEATURE:{f}"}
                val = features.get(f)
                if val is None or (isinstance(val, float) and np.isnan(val)):
                    return {"status": "refused", "reason": f"NAN_FEATURE:{f}"}

        # All good, score it
        try:
            df = pd.DataFrame([features])
            X = self.preprocessor.transform(df)
            prob = self.model.predict_proba(X)[0, 1]
            return {"status": "scored", "score": float(prob)}
        except Exception as e:
            return {"status": "refused", "reason": f"INFERENCE_ERROR:{e}"}
