"""Gatekeeper scoring inference."""

import json
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
            self.thresholds = {}
            return

        self.model = joblib.load(self.model_path)
        self.preprocessor = joblib.load(self.preprocessor_path)

        # G2 — resolve strategy_id categories by inspecting feature_names_in_ across ALL
        # transformers, rather than matching by transformer name ("cat").  The previous
        # name-match meant a transformer rename silently emptied the set and every signal
        # refused with UNKNOWN_STRATEGY_ID without any load-time warning.
        self.known_strategies = set()
        for _name, trans, _cols in self.preprocessor.transformers_:
            if not hasattr(trans, "categories_"):
                continue
            # Use feature_names_in_ when available (sklearn >= 1.0); fall back to the
            # positional cols list that ColumnTransformer passes as the third element.
            _fni = getattr(trans, "feature_names_in_", None)
            col_names = list(_fni) if _fni is not None else list(_cols or [])
            if "strategy_id" in col_names:
                idx = col_names.index("strategy_id")
                self.known_strategies = set(trans.categories_[idx])
                break  # found — stop searching

        # G2 — raise at load time if the model is present but no strategy IDs were found.
        # An empty set is never correct when a trained preprocessor exists: it means the
        # strategy_id column could not be located in the transformer, which is a load
        # failure, not a valid cold-start state.  A cold start with an empty set silently
        # refuses every live signal with UNKNOWN_STRATEGY_ID until the next process restart.
        if not self.known_strategies:
            raise RuntimeError(
                f"Gatekeeper loaded {self.preprocessor_path} but found no strategy_id "
                "categories. The preprocessor may lack a categorical transformer for "
                "strategy_id, or the column was renamed. known_strategies must not be "
                "empty when a model is present."
            )

        # G1 — load the manifest's calibrated per-regime thresholds.
        # These are exposed as self.thresholds so the caller can compute would_pass without
        # re-reading the manifest. The manifest is opened here (not in __init__) so a
        # missing manifest does not prevent the model from loading.
        self.thresholds = {}
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, encoding="utf-8") as _mf:
                    _manifest = json.load(_mf)
                self.thresholds = dict(_manifest.get("dynamic_thresholds") or {})
            except (OSError, json.JSONDecodeError) as _e:
                import logging as _logging
                _logging.getLogger("system1.gatekeeper.score").warning(
                    "Could not read thresholds from %s: %s", self.manifest_path, _e
                )

        import logging as _logging
        _logging.getLogger("system1.gatekeeper.score").info(
            "Gatekeeper loaded: %d known strategy IDs, %d regime thresholds, from %s",
            len(self.known_strategies),
            len(self.thresholds),
            self.preprocessor_path,
        )

    def _threshold_for(self, regime: Optional[str]) -> Optional[float]:
        """The calibrated threshold for ``regime``, or the fallback, or None.

        Mirrors the lookup in ``ledger.calibrated_threshold`` and
        ``train._apply_thresholds`` so all three use the same rule.
        G1: exposed as a method so run.py can stamp the real threshold and would_pass
        per-signal without opening the manifest again.
        """
        if not self.thresholds:
            return None
        value = self.thresholds.get(str(regime) if regime is not None else "", None)
        if value is None:
            value = self.thresholds.get("fallback")
        return float(value) if value is not None else None

    def score(self, features: Dict[str, Any]) -> Dict[str, Union[Optional[float], str]]:
        """Score a single feature row.

        Returns a dict:
        {"status": "scored", "score": float, "threshold": Optional[float],
         "would_pass": Optional[bool]}
        OR
        {"status": "refused", "reason": str}

        ``threshold`` and ``would_pass`` are the calibrated per-regime values from the
        manifest (G1). They are SHADOW fields — the caller still publishes regardless, and
        must stamp them in the ledger so the gap between the measured score and the threshold
        is visible per-signal rather than only in aggregate. Wiring the gate (actually
        dropping signals) is a separate change set, gated on §1.5.
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
            # G1 — attach the shadow threshold and would_pass flag. The regime used here
            # is regime_structural (what the model consumed), not the routing regime.
            # run.py stamps threshold_applied separately (still 0.5 until §1.5 is done).
            regime_structural = features.get("regime_structural")
            threshold = self._threshold_for(regime_structural)
            would_pass = (float(prob) >= threshold) if threshold is not None else None
            return {
                "status": "scored",
                "score": float(prob),
                "threshold": threshold,
                "would_pass": would_pass,
            }
        except Exception as e:
            return {"status": "refused", "reason": f"INFERENCE_ERROR:{e}"}
