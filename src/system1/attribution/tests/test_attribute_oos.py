"""FIX-S1-002 — OOS-only attribution + the mandatory 'overfit fails OOS' regression.

The pure (no-DB) tests build a synthetic tagged-trades frame and drive
``compute_attribution`` directly. DB-backed tests (backfill idempotency, schema-aware
fallback) skip automatically when ``ForexBrainDB`` is unreachable.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from src.common.db import test_connection as db_test_connection
from src.system1.attribution import attribute as A
from src.system1.attribution import metrics as _MET
from src.system1.validation import walk_forward as WF
from src.system1.vetting import gates as G

MET_BOUND_SHARPE = _MET.MAX_PLAUSIBLE_SHARPE


def _utc(y: int, m: int, d: int = 1) -> datetime:
    return datetime(y, m, d, tzinfo=timezone.utc)


def _tagged(entry_times, r_multiples, *, strategy_id=10, gran="H1", regime="Ranging"):
    """Build a tagged-trades frame with walk-forward OOS labels assigned from entry_times."""
    et = pd.Series(pd.to_datetime(list(entry_times), utc=True))
    smin, smax = WF.series_bounds(et)
    folds = WF.default_folds(smin, smax)
    is_oos, fold_id = WF.assign_oos(et, folds)
    r = np.asarray(r_multiples, dtype="float64")
    return pd.DataFrame(
        {
            "strategy_id": strategy_id,
            "granularity": gran,
            "regime": regime,
            "entry_time": et,
            "is_winner": (r > 0).astype(int),
            "r_multiple": r,
            "is_oos": is_oos.to_numpy(),
            "fold_id": fold_id,
        }
    )


def _cell_from_row(row: pd.Series) -> dict:
    """Project an attribution row to the dict shape evaluate_gates expects (cap inf like vet)."""

    def cap(v):
        v = float(v)
        if not np.isfinite(v):
            return 100.0 if v > 0 else 0.0
        return v

    return {
        "strategy_id": int(row["strategy_id"]),
        "variant": f"S{int(row['strategy_id'])}@{row['granularity']}",
        "regime": row["regime"],
        "granularity": row["granularity"],
        "profit_factor": cap(row["profit_factor"]),
        "sharpe": cap(row["sharpe"]),
        "max_drawdown": float(row["max_drawdown"]),
        "win_rate": float(row["win_rate"]),
        "recovery_factor": cap(row["recovery_factor"]),
        "oos_months": float(row["oos_months"] or 0.0),
        "trade_count": int(row["trade_count"]),
        "low_confidence": bool(row["low_confidence"]),
    }


# --------------------------------------------------------------- OOS-only metric filtering


def test_oos_metrics_use_oos_subset_not_full_span():
    # In-sample winners (2016-2018) + a real OOS history (2019-2026) of mixed trades.
    times, rs = [], []
    # in-sample: 36 monthly big winners, all strictly before the 2019-01 cutoff.
    for k in range(36):
        times.append(_utc(2016, 1, 1) + pd.DateOffset(months=k))
        rs.append(2.0)
    # OOS: 80 monthly modest winners (net positive but distinguishable from full set)
    for k in range(80):
        times.append(_utc(2019, 2, 1) + pd.DateOffset(months=k))
        rs.append(0.6 if k % 2 == 0 else -0.2)
    tagged = _tagged(times, rs)

    attribution = A.compute_attribution(tagged, run_id="t-oos")
    row = attribution.iloc[0]

    # trade_count is OOS-only (80), NOT the full 116.
    assert int(row["trade_count"]) == 80
    # oos_months == union span of the OOS folds, and is far below the full in-sample span.
    fids = sorted(
        {int(f) for f in tagged.loc[tagged["is_oos"], "fold_id"].dropna().unique()}
    )
    folds = {
        f.fold_id: f for f in WF.default_folds(*WF.series_bounds(tagged["entry_time"]))
    }
    expected = round(WF.oos_month_span([folds[i] for i in fids]), 2)
    assert row["oos_months"] == pytest.approx(expected)
    assert (
        row["oos_months"] < row["in_sample_span_months"]
    )  # OOS span << full trade span
    assert int(row["n_in_sample_trades"]) == 36


# ------------------------------------------------------ MANDATORY: overfit passes IS, fails OOS


def test_overfit_strategy_passes_in_sample_but_fails_oos_gates():
    """A curve-fit cell: spectacular in-sample, losing OOS. Full/in-sample metrics WOULD pass
    the gates; OOS-only metrics FAIL, and evaluate_gates on the OOS cell rejects with PF and
    Sharpe failures present. Proves the OOS gate is no longer inert (FIX-S1-002)."""
    times, rs = [], []
    # IN-SAMPLE (2016-01..2018-12): 200 big winners.
    for k in range(200):
        times.append(
            _utc(2016, 1, 1) + pd.DateOffset(days=5 * k)
        )  # stays before 2019 cutoff
        rs.append(3.0)
    # OOS (2019-02..2026-01): 100 net-losing trades spread across the whole OOS history,
    # so oos_months is comfortably >= 60 and the rejection is driven by PF/Sharpe, not coverage.
    for k in range(100):
        times.append(_utc(2019, 2, 1) + pd.DateOffset(days=25 * k))
        rs.append(
            -1.0 if k % 2 == 0 else 0.2
        )  # PF = (50*0.2)/(50*1.0) = 0.2, net loser
    tagged = _tagged(times, rs)

    # Full-history (the OLD, leaky measurement) WOULD pass PF + win-rate.
    full_r = np.asarray(rs, dtype="float64")
    from src.system1.attribution import metrics as MET

    assert (
        MET.profit_factor(full_r) >= G.GATES["profit_factor"]
    )  # in-sample looks great
    assert MET.win_rate((full_r > 0).astype(int)) >= G.GATES["win_rate"]

    attribution = A.compute_attribution(tagged, run_id="t-overfit")
    row = attribution.iloc[0]

    # OOS-only metrics are bad.
    assert int(row["trade_count"]) == 100
    assert row["profit_factor"] < G.GATES["profit_factor"]
    assert (
        row["oos_months"] >= G.GATES["oos_months"]
    )  # coverage is fine; quality is not

    oos_cell = _cell_from_row(row)
    passed, failures = G.evaluate_gates(oos_cell)
    assert passed is False
    assert any(f.startswith("PF") for f in failures)
    assert any(f.startswith("Sharpe") for f in failures)


# ----------------------------------------------- Gate-can-return-False (explicit, symmetric)


def test_oos_gate_fires_on_low_oos_months():
    """Hand-built healthy cell except oos_months=12 -> evaluate_gates rejects with the OOS<60
    failure; the symmetric oos_months=72 cell passes. Proves the (now-real) OOS gate can fire.
    """
    healthy = dict(
        profit_factor=2.0,
        sharpe=1.2,
        max_drawdown=0.10,
        win_rate=0.55,
        recovery_factor=5.0,
        oos_months=72,
        trade_count=120,
        low_confidence=False,
    )
    passed, failures = G.evaluate_gates(healthy)
    assert passed is True and failures == []

    starved = {**healthy, "oos_months": 12}
    passed, failures = G.evaluate_gates(starved)
    assert passed is False
    assert any(f.startswith("OOS") for f in failures)


# --------------------------------------- small-sample sanity-guard handling (FIX-S1-002 + S1-001)


def test_thin_oos_cell_sharpe_artifact_is_clamped_not_aborted():
    """A sub-N_MIN OOS cell with a near-constant return series produces an explosive
    small-sample Sharpe (the kind that aborted the run on the starved High-Vol regime).
    It must NOT abort attribution: the value is clamped to the sanity bound, the cell is
    flagged low_confidence, and the run completes. Mirrors the live strategy-10/High-Vol/H4
    case (2-4 trades, |Sharpe| in the thousands)."""
    # 3 OOS trades (< N_MIN=20), near-identical positive r -> tiny std -> huge raw Sharpe.
    times = [
        _utc(2016, 1, 1),  # in-sample anchor so series spans the 36mo min_train
        _utc(2021, 6, 1),
        _utc(2021, 6, 2),
        _utc(2021, 6, 3),
    ]
    rs = [0.5, 0.990, 0.991, 0.992]
    tagged = _tagged(times, rs)
    assert int(tagged["is_oos"].sum()) == 3  # 3 OOS, sub-N_MIN

    # Must not raise (this was the bug: hard abort on the thin cell).
    attribution = A.compute_attribution(tagged, run_id="t-thin")
    row = attribution.iloc[0]
    assert int(row["trade_count"]) == 3
    assert abs(float(row["sharpe"])) <= MET_BOUND_SHARPE  # clamped to the sanity bound
    assert bool(row["low_confidence"]) is True  # thin cell -> rejected downstream


def test_sanity_guard_still_aborts_on_corrupt_metric_with_enough_trades():
    """Global rule #3 — the guard can still fire. A cell with >= N_MIN OOS trades whose
    Sharpe is forced out of bounds must HARD-ABORT (corrupt math is not clamped away).
    Proves the relaxation is scoped to thin cells only."""
    times = [_utc(2016, 1, 1)] + [
        _utc(2020, 1, 1) + pd.DateOffset(days=10 * k) for k in range(40)
    ]
    rs = [0.5] + [0.3] * 40  # 40 OOS trades (>= N_MIN)
    tagged = _tagged(times, rs)
    assert int(tagged["is_oos"].sum()) >= A.N_MIN

    # Force a corrupt (out-of-bound) Sharpe on the well-populated cell.
    import src.system1.attribution.metrics as MET

    real = A._oos_cell_metrics

    def _corrupt(cell, folds):
        m = real(cell, folds)
        if len(cell) >= A.N_MIN:
            m["sharpe"] = MET.MAX_PLAUSIBLE_SHARPE + 5000.0
        return m

    import pytest as _pytest

    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(A, "_oos_cell_metrics", _corrupt)
        with _pytest.raises(RuntimeError, match="sanity bounds violated"):
            A.compute_attribution(tagged, run_id="t-corrupt")


# --------------------------------------------------------------------- empty OOS -> cannot pass


def test_zero_oos_trades_cell_fails_gates():
    # Everything in-sample (history shorter than min_train) -> no OOS trades at all.
    times = [_utc(2020, 1, 1) + pd.DateOffset(months=k) for k in range(12)]
    tagged = _tagged(times, [2.0] * 12)
    assert not tagged["is_oos"].any()
    attribution = A.compute_attribution(tagged, run_id="t-empty")
    row = attribution.iloc[0]
    assert int(row["trade_count"]) == 0
    assert row["oos_months"] == 0.0
    cell = _cell_from_row(row)
    passed, _ = G.evaluate_gates(cell)
    assert passed is False  # safe direction


# ------------------------------------------------------------------------------ DB-backed tests

_DB = db_test_connection()
_skip_db = pytest.mark.skipif(not _DB, reason="ForexBrainDB not reachable")


@_skip_db
def test_backfill_idempotent():
    """ensure + backfill run twice -> identical is_oos/fold_id distributions (FIX-S1-002)."""
    from sqlalchemy import text

    from src.common.db import get_engine
    from src.layer0 import persist_trade_outcomes as P

    P.ensure_oos_columns()
    P.backfill_oos()
    engine = get_engine()

    def snapshot() -> list:
        with engine.connect() as conn:
            return conn.execute(
                text(
                    "SELECT is_oos, fold_id, count(*) FROM fact_trade_outcomes "
                    "GROUP BY is_oos, fold_id ORDER BY is_oos, fold_id"
                )
            ).all()

    first = snapshot()
    P.backfill_oos()  # second pass must be a no-op in effect
    second = snapshot()
    assert first == second
    # And there must be no unclassified (NULL is_oos) rows after a backfill.
    with engine.connect() as conn:
        nulls = conn.execute(
            text("SELECT count(*) FROM fact_trade_outcomes WHERE is_oos IS NULL")
        ).scalar()
    assert nulls == 0


@_skip_db
def test_load_trades_schema_aware_fallback(monkeypatch):
    """When is_oos/fold_id are reported ABSENT, _load_trades must not crash and must treat
    every trade as in-sample (is_oos all False) so cells fail the OOS gate (safe direction).
    """
    from src.common.db import get_engine

    monkeypatch.setattr(A, "_column_exists", lambda conn, table, column: False)
    df = A._load_trades(get_engine())
    assert "is_oos" in df.columns and "fold_id" in df.columns
    assert not df["is_oos"].any()
    assert df["fold_id"].isna().all()


@_skip_db
def test_load_trades_schema_aware_present():
    """When is_oos/fold_id exist, _load_trades returns them typed (bool / Int64)."""
    from src.common.db import get_engine
    from src.layer0 import persist_trade_outcomes as P

    P.ensure_oos_columns()
    df = A._load_trades(get_engine())
    assert "is_oos" in df.columns and "fold_id" in df.columns
    assert df["is_oos"].dtype == bool
    assert str(df["fold_id"].dtype) == "Int64"
