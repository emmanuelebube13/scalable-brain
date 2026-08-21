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

        # Refuse NaN feature rows. (At least one numerical feature is NaN)
        # We need to know which features are expected by the preprocessor.
        expected = getattr(self.preprocessor, "feature_names_in_", None)
        if expected is not None:
            for f in expected:
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
