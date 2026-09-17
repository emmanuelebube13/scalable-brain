"""Gatekeeper scoring inference."""

import json
import os
from typing import Any, Dict, Optional, Union
import numpy as np
import pandas as pd
import joblib

# The 2.0.0 trade-geometry basis (FEATURE_SET_VERSION 2.0.0, train.py). A bundle fit on it
# demands these at inference; the live signal does not carry them by name, but it carries
# everything they derive from. `_geometry_from_signal` is the mapping (O-32).
GEOMETRY_FEATURES = ("atr_sl_multiplier", "atr_tp_multiplier", "entry_signal_type")


def _geometry_from_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Derive the 2.0.0 geometry features from a live signal's raw fields.

    Adopts the TRAINING definition verbatim — ``src/outcomes/geometry.py::multiples``
    (lines 138 and 142) computes UNSIGNED distances in ATR units::

        sl_mult = abs(float(entry_price) - float(stop_price)) / float(atr_ref)      # :138
        tp_mult = abs(float(take_profit_price) - float(entry_price)) / float(atr_ref)  # :142

    and is called here directly rather than re-implemented, so the two cannot drift.

    DO NOT substitute the ledger's ``risk_reward_ratio`` from ``signals/build.py`` (the
    signed reward/risk that returns ``None`` on a zero or inverted range). The two
    definitions disagree exactly on the pathological trades — a long whose target sits
    below entry has NO signed rr but perfectly well-defined unsigned multipliers, and
    training saw the unsigned number (the O-24 shape; O-32's "one definitional trap").

    ``entry_signal_type``: training's values come from the outcome writers —
    ``persist_trade_outcomes.py:321`` and ``persist_all.py:257/351`` both write
    ``"long" if direction > 0 else "short"`` (lowercase). The live signal's ``direction``
    is built from the same sign (``build.py:398`` — ``{1: "long", -1: "short"}``), so it
    maps across verbatim; anything else is left absent and refuses MISSING_FEATURE.

    Returns only the features that could actually be derived — an underivable feature
    must stay ABSENT so the scorer answers MISSING_FEATURE ("no input, no opinion")
    rather than NAN_FEATURE ("corrupt").
    """
    # Deferred like the train import below: keeps module import light for the producer.
    from src.outcomes.geometry import multiples

    derived: Dict[str, Any] = {}

    direction = signal.get("direction")
    if isinstance(direction, str) and direction.lower() in ("long", "short"):
        derived["entry_signal_type"] = direction.lower()

    try:
        sl_mult, tp_mult = multiples(
            signal.get("entry"),
            signal.get("stop"),
            signal.get("target"),
            signal.get("atr"),
        )
    except (TypeError, ValueError):
        sl_mult, tp_mult = None, None
    if sl_mult is not None:
        derived["atr_sl_multiplier"] = float(sl_mult)
    if tp_mult is not None:
        derived["atr_tp_multiplier"] = float(tp_mult)
    return derived


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

        # G2 — raise at load time if the artifact CONSUMES strategy_id but no categories
        # were found. An empty set is never correct when the shipped preprocessor's own
        # feature list demands the column: it means strategy_id could not be located in
        # the transformer — a load failure, not a valid cold-start state. A cold start
        # with an empty set silently refuses every live signal with UNKNOWN_STRATEGY_ID
        # until the next process restart.
        #
        # O-32 — the guard is scoped to the artifact's own basis. A 2.0.0 bundle
        # (FEATURE_SET_VERSION 2.0.0, train.py) removed strategy_id from the features by
        # design (WO-04B / FIX-S1-012), so "no categories" is its correct loaded state;
        # raising here would kill the producer at startup the moment a 2.0.0 champion is
        # promoted. When feature_names_in_ is unavailable we cannot tell a 2.0.0 apart
        # from a corrupt 1.0.0 and keep the conservative behaviour (raise).
        _expected_inputs = getattr(self.preprocessor, "feature_names_in_", None)
        _consumes_strategy_id = _expected_inputs is None or "strategy_id" in list(
            _expected_inputs
        )
        if _consumes_strategy_id and not self.known_strategies:
            raise RuntimeError(
                f"Gatekeeper loaded {self.preprocessor_path} but found no strategy_id "
                "categories despite the preprocessor listing strategy_id as an input. "
                "The preprocessor may lack a categorical transformer for strategy_id, "
                "or the column was renamed. known_strategies must not be empty when the "
                "shipped artifact consumes strategy_id."
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

        # O-32: read the shipped artifact's demands once, up front. Everything below —
        # the strategy-identity gate, the geometry mapping and the MISSING/NAN check —
        # is scoped to what THIS bundle was fit on, so either champion generation
        # (1.0.0 live now, 2.0.0 when promoted) scores the same live signal dict.
        expected = getattr(self.preprocessor, "feature_names_in_", None)

        # Cold start policy: Refuse unknown strategy IDs. F-103 remediation.
        # O-32: only when the loaded bundle actually discriminates on strategy identity
        # (known_strategies non-empty — 1.0.0). A 2.0.0 bundle has no strategy_id
        # feature and no categories BY DESIGN (WO-04B), so this gate does not apply;
        # applying it would refuse every signal from a model that never asked.
        if self.known_strategies:
            strat_id = features.get("strategy_id")
            if (
                strat_id not in self.known_strategies
                and str(strat_id) not in self.known_strategies
            ):
                return {"status": "refused", "reason": "UNKNOWN_STRATEGY_ID"}

        # O-32: map the live signal's raw fields onto the 2.0.0 geometry basis, only
        # where the shipped preprocessor demands a column the caller did not supply.
        # Runs BEFORE _derive_features so risk_reward_ratio can be derived from the
        # mapped multipliers. Works on a copy — the caller's dict is the wire signal,
        # and System 3's contract is additionalProperties:false (build.py D7/D8 notes).
        # For a 1.0.0 bundle none of these columns is expected, so this is a no-op and
        # the live champion's scores are bit-identical (pinned by test).
        if expected is not None:
            needed = [
                f for f in GEOMETRY_FEATURES if f in expected and f not in features
            ]
            if needed:
                derived = _geometry_from_signal(features)
                features = dict(features)
                for f in needed:
                    if f in derived:
                        features[f] = derived[f]

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
