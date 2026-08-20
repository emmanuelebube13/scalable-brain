"""FIX-S1-012 — per-(strategy x regime) degeneracy guard.

The aggregate turnover band (MODEL-006) and the per-regime band (FIX-S1-010) are both
blind along the STRATEGY axis. The live 2026-07-05 champion (``gk-656f09e2``) passed both
while being a lookup table on strategy identity:

    strategy_id one-hot   96.78% of gain importance
    regime_causal         0.21%
    all numeric features  2.65%

    per (strategy x regime) at H1: 23/40 cells approved <=5%, 12/40 approved >=95%
    aggregate approval:            0.1717  -- comfortably inside [0.05, 0.60]

Downstream, System 2 traded the single vetting-qualified strategy (id 10), which sat in
the 100% group in every regime, and measured a live approval rate of 0.9995 against a
published ``oos_approval_rate`` of 0.3379. These tests pin the guard that refuses it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.gatekeeper import train as T


def _frame(cells):
    """Build a calibration-tail-shaped frame from {(strategy_id, regime): n}."""
    sids, regs = [], []
    for (sid, reg), n in cells.items():
        sids += [sid] * n
        regs += [reg] * n
    df = pd.DataFrame({"strategy_id": sids, "regime_causal": regs})
    # cal_df is frame.iloc[cut:], so the index does not start at 0 — a positional/label
    # mix-up would make the guard measure the wrong rows.
    df.index = np.arange(500, 500 + len(df))
    return df


def test_per_cell_approval_is_index_safe():
    df = _frame({("10", "Ranging"): 40, ("1", "Ranging"): 40})
    scores = np.concatenate([np.full(40, 0.9), np.full(40, 0.1)])
    out = T.per_cell_approval(df, scores, {"fallback": 0.5})
    assert out["10|Ranging"] == {"n": 40, "approval": 1.0}
    assert out["1|Ranging"] == {"n": 40, "approval": 0.0}


def test_bimodal_policy_is_refused():
    """The gk-656f09e2 shape: every cell pinned at 0 or 1, aggregate mid-band."""
    cells = {
        (str(s), r): 40 for s in range(1, 11) for r in ["Ranging", "Trending-Down"]
    }
    df = _frame(cells)
    # strategies 7-10 approve everything, 1-6 approve nothing -> aggregate 0.40, mid-band
    scores = np.array(
        [0.9 if int(s) >= 7 else 0.1 for s in df["strategy_id"]], dtype=float
    )
    thr = {"fallback": 0.5}

    aggregate = float((scores >= 0.5).mean())
    assert 0.05 <= aggregate <= 0.60, "precondition: the aggregate band must PASS"
    assert (
        T.check_regime_turnover(T.per_regime_approval(df, scores, thr)) == []
    ), "precondition: the per-regime band must also PASS"

    problems = T.check_cell_degeneracy(T.per_cell_approval(df, scores, thr))
    assert problems, "a 0/1 bimodal policy must be refused"
    assert "strategy identity" in problems[0]


def test_healthy_spread_passes():
    cells = {(str(s), r): 60 for s in range(1, 6) for r in ["Ranging", "Trending-Down"]}
    df = _frame(cells)
    rng = np.random.default_rng(7)
    # every cell lands mid-band rather than pinned at an end
    scores = np.concatenate(
        [np.where(rng.random(60) < 0.3 + 0.04 * i, 0.9, 0.1) for i in range(len(cells))]
    )
    assert (
        T.check_cell_degeneracy(T.per_cell_approval(df, scores, {"fallback": 0.5}))
        == []
    )


def test_thin_cells_are_not_guarded():
    """A cell below MIN_REGIME_N is noise; failing a run on it would be a coin flip."""
    df = _frame({("10", "Ranging"): 5, ("1", "Ranging"): 5})
    scores = np.concatenate([np.full(5, 0.9), np.full(5, 0.1)])
    assert (
        T.check_cell_degeneracy(T.per_cell_approval(df, scores, {"fallback": 0.5}))
        == []
    )


def test_single_populated_cell_does_not_crash():
    df = _frame({("10", "Ranging"): 40})
    scores = np.full(40, 0.9)
    problems = T.check_cell_degeneracy(
        T.per_cell_approval(df, scores, {"fallback": 0.5})
    )
    assert problems and "1 of 1" in problems[0]
