"""System-1 walk-forward validation primitives (FIX-S1-002).

Reusable fold generator + OOS labeller shared by MODEL-004 attribution and (future)
FIX-S1-005 HMM walk-forward refit. See ``walk_forward`` for the locked design.
"""

from __future__ import annotations

from src.system1.validation.walk_forward import (
    MODE,
    MIN_TRAIN_MONTHS,
    OOS_WINDOW_MONTHS,
    STEP_MONTHS,
    Fold,
    assign_oos,
    default_folds,
    generate_folds,
    oos_month_span,
    series_bounds,
)

__all__ = [
    "Fold",
    "generate_folds",
    "default_folds",
    "assign_oos",
    "oos_month_span",
    "series_bounds",
    "MIN_TRAIN_MONTHS",
    "STEP_MONTHS",
    "OOS_WINDOW_MONTHS",
    "MODE",
]
