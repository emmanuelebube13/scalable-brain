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
        # That mattered because the live path supplied NONE of these features: the
        # champion trained on atr_value / adx_value / prob_causal_* / regime_causal read
        # from fact_market_regime_v2, and those rows are written retrospectively — a live
        # bar has no row there at all. So every live signal refused with
        # NAN_FEATURE:atr_value and was silently discarded, which is why nothing ever
        # reached the queue even once ATR construction was fixed.

        # Derive the interaction features before checking, so a caller only has to supply
        # the base inputs. Imported here rather than at module scope: src.gatekeeper.train
        # pulls in xgboost, sklearn and the DB engine, and score.py is imported by the
        # hourly producer on every run — deferring keeps the live signal path off the
        # training dependency graph. It is the SAME function training uses, deliberately;
        # a second implementation of the derived features is train/serve skew.
        from src.gatekeeper.train import _derive_features

        df = _derive_features(pd.DataFrame([features]))
        # Training does `frame["strategy_id"] = frame["strategy_id"].astype(str)` before
        # fitting, so the encoder's categories are strings. The live producer carries
        # strategy_id as an int, and passing it through raw made the transform raise
        # "'<' not supported between instances of 'int' and 'str'" — an INFERENCE_ERROR
        # that read as a bad signal rather than a type mismatch. Normalise on the serving
        # side exactly as training does.
        if "strategy_id" in df.columns:
            df["strategy_id"] = df["strategy_id"].astype(str)
        features = df.iloc[0].to_dict()

        # Check the derived row, not the caller's raw dict.
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
            X = self.preprocessor.transform(df)
            prob = self.model.predict_proba(X)[0, 1]
            return {"status": "scored", "score": float(prob)}
        except Exception as e:
            return {"status": "refused", "reason": f"INFERENCE_ERROR:{e}"}
