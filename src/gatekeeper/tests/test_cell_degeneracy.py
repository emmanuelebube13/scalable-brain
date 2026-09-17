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

O-30 re-scope (owner decision 2026-09-17): with trade geometry in the basis and
``strategy_id`` out, a cell whose strategy has an R:R coefficient of variation below
``GEOMETRY_CV_FLOOR`` (0.10, audit §2.5) is EXPLAINED — its constancy is what a
geometry-keying model must produce for a fixed-geometry strategy. The verdict counts only
UNEXPLAINED degenerate cells against ``MAX_DEGENERATE_CELL_SHARE`` (untouched at 0.50),
and the exemption is disabled when ``strategy_id`` re-enters the basis.
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
    df = pd.DataFrame({"strategy_id": sids, "regime_structural": regs})
    # cal_df is frame.iloc[cut:], so the index does not start at 0 — a positional/label
    # mix-up would make the guard measure the wrong rows.
    df.index = np.arange(500, 500 + len(df))
    return df


def _geometry_frame(per_strategy):
    """Training-frame-shaped geometry columns from {strategy_id: (sl_list, tp_list)}."""
    sids, sls, tps = [], [], []
    for sid, (sl, tp) in per_strategy.items():
        sids += [sid] * len(sl)
        sls += list(sl)
        tps += list(tp)
    return pd.DataFrame(
        {"strategy_id": sids, "atr_sl_multiplier": sls, "atr_tp_multiplier": tps}
    )


def test_per_cell_approval_is_index_safe():
    df = _frame({("10", "Ranging"): 40, ("1", "Ranging"): 40})
    scores = np.concatenate([np.full(40, 0.9), np.full(40, 0.1)])
    out = T.per_cell_approval(df, scores, {"fallback": 0.5})
    assert out["10|Ranging"] == {"n": 40, "approval": 1.0}
    assert out["1|Ranging"] == {"n": 40, "approval": 0.0}


def test_bimodal_policy_is_refused():
    """The gk-656f09e2 shape: every cell pinned at 0 or 1, aggregate mid-band.

    No geometry CVs supplied -> nothing is explained -> the pre-O-30 behaviour stands.
    """
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

    out = T.check_cell_degeneracy(T.per_cell_approval(df, scores, thr))
    assert out["problems"], "a 0/1 bimodal policy must be refused"
    assert out["n_degenerate"] == 20
    assert out["n_explained"] == 0
    assert out["n_unexplained"] == 20
    assert "NOT explained by fixed strategy geometry" in out["problems"][0]


def test_healthy_spread_passes():
    cells = {(str(s), r): 60 for s in range(1, 6) for r in ["Ranging", "Trending-Down"]}
    df = _frame(cells)
    rng = np.random.default_rng(7)
    # every cell lands mid-band rather than pinned at an end
    scores = np.concatenate(
        [np.where(rng.random(60) < 0.3 + 0.04 * i, 0.9, 0.1) for i in range(len(cells))]
    )
    out = T.check_cell_degeneracy(T.per_cell_approval(df, scores, {"fallback": 0.5}))
    assert out["problems"] == []
    assert out["n_degenerate"] == 0
    assert out["n_unexplained"] == 0


def test_thin_cells_are_not_guarded():
    """A cell below MIN_REGIME_N is noise; failing a run on it would be a coin flip."""
    df = _frame({("10", "Ranging"): 5, ("1", "Ranging"): 5})
    scores = np.concatenate([np.full(5, 0.9), np.full(5, 0.1)])
    out = T.check_cell_degeneracy(T.per_cell_approval(df, scores, {"fallback": 0.5}))
    assert out["problems"] == []
    assert out["n_populated"] == 0


def test_single_populated_cell_does_not_crash():
    df = _frame({("10", "Ranging"): 40})
    scores = np.full(40, 0.9)
    out = T.check_cell_degeneracy(T.per_cell_approval(df, scores, {"fallback": 0.5}))
    assert out["problems"] and "1 of 1" in out["problems"][0]


# --------------------------------------------------------------------------------------
# O-30 re-scope: degeneracy residual to declared geometry
# --------------------------------------------------------------------------------------


def _bimodal(cells, approve_sids):
    """Frame + pinned-0/1 scores for the given cells; strategies in approve_sids -> 1."""
    df = _frame(cells)
    scores = np.array(
        [0.9 if s in approve_sids else 0.1 for s in df["strategy_id"]], dtype=float
    )
    return df, scores


def test_fixed_geometry_degeneracy_is_explained_and_passes():
    """CV 0 strategies (fixed sl/tp by design) with fully bimodal cells -> explained."""
    cells = {
        (str(s), r): 40 for s in range(1, 11) for r in ["Ranging", "Trending-Down"]
    }
    df, scores = _bimodal(cells, approve_sids={"7", "8", "9", "10"})
    # every strategy declares one fixed geometry -> rr CV exactly 0
    geom = _geometry_frame({str(s): ([1.5] * 10, [3.0] * 10) for s in range(1, 11)})
    cv = T.strategy_geometry_cv(geom)
    assert all(v == 0.0 for v in cv.values())

    out = T.check_cell_degeneracy(
        T.per_cell_approval(df, scores, {"fallback": 0.5}), cv
    )
    assert out["problems"] == [], "fixed-geometry constancy is intended behaviour"
    assert out["n_degenerate"] == 20
    assert out["n_explained"] == 20
    assert out["n_unexplained"] == 0
    assert all(d["explained"] for d in out["degenerate_cells"].values())
    assert all(
        d["strategy_cv"] == 0.0 for d in out["degenerate_cells"].values()
    ), "per-cell detail must carry the strategy's CV"


def test_varying_geometry_degeneracy_still_refused():
    """CV > 0.10 strategies with the SAME degenerate approvals -> unexplained, refused."""
    cells = {
        (str(s), r): 40 for s in range(1, 11) for r in ["Ranging", "Trending-Down"]
    }
    df, scores = _bimodal(cells, approve_sids={"7", "8", "9", "10"})
    rng = np.random.default_rng(3)
    geom = _geometry_frame(
        {
            str(s): (
                list(rng.uniform(1.0, 2.0, 50)),
                list(rng.uniform(1.5, 4.0, 50)),
            )
            for s in range(1, 11)
        }
    )
    cv = T.strategy_geometry_cv(geom)
    assert all(v > T.GEOMETRY_CV_FLOOR for v in cv.values()), "precondition"

    out = T.check_cell_degeneracy(
        T.per_cell_approval(df, scores, {"fallback": 0.5}), cv
    )
    assert out["problems"], "varying-geometry constancy is the FIX-S1-012 defect shape"
    assert out["n_explained"] == 0
    assert out["n_unexplained"] == 20


def test_mixed_population_at_the_boundary():
    """Unexplained share exactly at the 50% limit passes; one more cell refuses.

    10 populated cells, all degenerate. 5 strategies fixed-geometry (explained),
    5 varying -> unexplained share 5/10 = 50% == limit -> pass (<=). Dropping one
    strategy to varying makes it 6/10 = 60% -> refuse.
    """
    cells = {(str(s), "Ranging"): 40 for s in range(1, 11)}
    df, scores = _bimodal(cells, approve_sids={str(s) for s in range(6, 11)})
    fixed = {str(s): 0.0 for s in range(1, 6)}
    varying = {str(s): 0.5 for s in range(6, 11)}
    out = T.check_cell_degeneracy(
        T.per_cell_approval(df, scores, {"fallback": 0.5}), {**fixed, **varying}
    )
    assert out["n_unexplained"] == 5 and out["unexplained_share"] == 0.5
    assert out["problems"] == [], "exactly at the limit is <=, not >"

    fixed_minus_one = {str(s): 0.0 for s in range(1, 5)}
    varying_plus_one = {str(s): 0.5 for s in range(5, 11)}
    out = T.check_cell_degeneracy(
        T.per_cell_approval(df, scores, {"fallback": 0.5}),
        {**fixed_minus_one, **varying_plus_one},
    )
    assert out["n_unexplained"] == 6 and out["problems"]


def test_cv_exactly_at_floor_is_not_explained():
    """The exemption is strict: CV < 0.10, not <=."""
    cells = {(str(s), "Ranging"): 40 for s in range(1, 11)}
    df, scores = _bimodal(cells, approve_sids=set())
    cv = {str(s): T.GEOMETRY_CV_FLOOR for s in range(1, 11)}
    out = T.check_cell_degeneracy(
        T.per_cell_approval(df, scores, {"fallback": 0.5}), cv
    )
    assert out["n_explained"] == 0 and out["problems"]


def test_identity_in_basis_disables_the_exemption():
    """If strategy_id ever returns to the feature set, identity-keyed constancy would
    masquerade as geometry-explained — the exemption must not apply."""
    cells = {(str(s), "Ranging"): 40 for s in range(1, 11)}
    df, scores = _bimodal(cells, approve_sids={"7", "8", "9", "10"})
    cv = {str(s): 0.0 for s in range(1, 11)}  # all fixed geometry

    out = T.check_cell_degeneracy(
        T.per_cell_approval(df, scores, {"fallback": 0.5}), cv, identity_in_basis=True
    )
    assert out["problems"], "identity in the basis must void the geometry exemption"
    assert out["n_explained"] == 0
    assert "geometry exemption DISABLED" in out["problems"][0]

    # and strategy_id is genuinely absent from today's trained basis
    assert "strategy_id" not in T.NUMERIC_DERIVED + T.CATEGORICAL


def test_geometry_cv_edge_cases_fail_closed():
    """Div-by-zero / NaN geometry rows: no usable rr -> NaN CV -> never explained."""
    geom = _geometry_frame(
        {
            "zero_sl": ([0.0] * 20, [3.0] * 20),  # every rr is a div-by-zero
            "nan_tp": ([1.5] * 20, [np.nan] * 20),  # no declared target
            "one_row": (
                [1.5] + [0.0] * 19,
                [3.0] * 20,
            ),  # single usable row: sd undefined
            "mixed": (
                [1.5] * 10 + [0.0] * 10,
                [3.0] * 10 + [3.0] * 10,
            ),  # usable subset
        }
    )
    cv = T.strategy_geometry_cv(geom)
    assert np.isnan(cv["zero_sl"])
    assert np.isnan(cv["nan_tp"])
    assert np.isnan(cv["one_row"])
    assert cv["mixed"] == 0.0, "the usable rows are a genuine constant"

    cells = {("zero_sl", "Ranging"): 40, ("nan_tp", "Ranging"): 40}
    df, scores = _bimodal(cells, approve_sids=set())
    out = T.check_cell_degeneracy(
        T.per_cell_approval(df, scores, {"fallback": 0.5}), cv
    )
    assert out["n_explained"] == 0, "a NaN CV must never explain a cell"
    assert out["problems"] and "NaN" in out["problems"][0]


def test_unknown_strategy_in_cells_fails_closed():
    """A degenerate cell whose strategy has no measured geometry is unexplained."""
    cells = {("99", "Ranging"): 40}
    df, scores = _bimodal(cells, approve_sids=set())
    out = T.check_cell_degeneracy(
        T.per_cell_approval(df, scores, {"fallback": 0.5}), {"1": 0.0}
    )
    assert out["n_unexplained"] == 1 and out["problems"]
    assert np.isnan(out["degenerate_cells"]["99|Ranging"]["strategy_cv"])
