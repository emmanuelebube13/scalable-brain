"""RETIRED under FIX-S1-009 (dead third feature pipeline).

This root-level module was a ~270-line feature-engineering/training pipeline
(``comprehensive_feature_engineering`` et al.) that was trained and served by
nobody. It diverged from both the legacy tournament trainer
(``src/layer3_ml/training/train_ml_gatekeeper.py``) and the canonical
single-source feature pipeline, and was only reachable via a stale shell
script pointing at a non-existent path.

Canonical feature pipeline: ``src/system1/features/feature_pipeline.py``
(versioned Parquet feature store; ``python -m src.system1.features.feature_pipeline``).

Retraining/promotion of the gatekeeper champion is governed exclusively by the
System-1 orchestrator: ``python -m src.system1.scheduler.orchestrator``.

No re-export is provided: the canonical pipeline's API (a versioned Parquet
feature-store builder) is not interchangeable with the old per-DataFrame
transform this module exposed, and importing it would pull heavy dependencies
as a side effect.
"""

raise ImportError(
    "src.layer3_ml.train_ml_gatekeeper was retired under FIX-S1-009. "
    "Use the canonical feature pipeline "
    "(src/system1/features/feature_pipeline.py) and the governed retrain path "
    "(python -m src.system1.scheduler.orchestrator) instead."
)
