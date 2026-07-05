"""Unit tests for the FIX-S1-002 walk-forward fold generator + OOS labeller (pure, no DB)."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest
from dateutil.relativedelta import relativedelta

from src.system1.validation import walk_forward as WF


def _utc(y: int, m: int, d: int = 1) -> datetime:
    return datetime(y, m, d, tzinfo=timezone.utc)


# --------------------------------------------------------------------------------------- folds


def test_fold_count_and_anchor():
    # 10 years of history, 36mo train, 6mo step/window => OOS spans months 36..120 = 84mo / 6 = 14.
    start, end = _utc(2016, 1, 1), _utc(2026, 1, 1)
    folds = WF.generate_folds(
        start, end, min_train=36, step=6, oos_window=6, mode="anchored"
    )
    assert len(folds) == 14
    assert folds[0].oos_start == start + relativedelta(months=36)  # cutoff anchor
    assert folds[0].fold_id == 1 and folds[-1].fold_id == 14


def test_oos_windows_contiguous_non_overlapping():
    start, end = _utc(2016, 1, 1), _utc(2026, 1, 1)
    folds = WF.generate_folds(start, end, min_train=36, step=6, oos_window=6)
    for a, b in zip(folds, folds[1:]):
        assert a.oos_end == b.oos_start  # touch, no gap
        assert a.oos_start < a.oos_end  # non-empty, non-overlapping ([start, end))


def test_anchored_vs_rolling_train_window():
    start, end = _utc(2016, 1, 1), _utc(2026, 1, 1)
    anchored = WF.generate_folds(start, end, min_train=36, step=6, mode="anchored")
    rolling = WF.generate_folds(start, end, min_train=36, step=6, mode="rolling")
    # Anchored train_start never moves; rolling train_start slides forward, keeping 36mo span.
    assert all(f.train_start == start for f in anchored)
    assert rolling[0].train_start == start
    assert rolling[-1].train_start > start
    for f in rolling:
        assert f.train_end == f.train_start + relativedelta(months=36)


def test_partial_trailing_fold_is_clamped():
    # 39 months total => one full 36mo train, then a single 3-month (partial) OOS window.
    start = _utc(2016, 1, 1)
    end = start + relativedelta(months=39)
    folds = WF.generate_folds(start, end, min_train=36, step=6, oos_window=6)
    assert len(folds) == 1
    assert folds[0].oos_start == start + relativedelta(months=36)
    assert folds[0].oos_end == end  # clamped to series_end, not 42 months


def test_min_train_ge_span_yields_empty():
    start, end = _utc(2020, 1, 1), _utc(2022, 1, 1)  # 24 months
    assert WF.generate_folds(start, end, min_train=36, step=6) == []
    # exactly equal cutoff == series_end is also empty (no OOS period)
    assert (
        WF.generate_folds(start, start + relativedelta(months=36), min_train=36, step=6)
        == []
    )


def test_invalid_args_raise():
    start, end = _utc(2016, 1, 1), _utc(2026, 1, 1)
    with pytest.raises(ValueError):
        WF.generate_folds(start, end, step=0)
    with pytest.raises(ValueError):
        WF.generate_folds(start, end, mode="bogus")


# --------------------------------------------------------------------------- oos_month_span


def test_oos_month_span_disjoint():
    folds = [
        WF.Fold(
            1, _utc(2016, 1, 1), _utc(2019, 1, 1), _utc(2019, 1, 1), _utc(2019, 7, 1)
        ),
        WF.Fold(
            2, _utc(2016, 1, 1), _utc(2020, 1, 1), _utc(2020, 1, 1), _utc(2020, 7, 1)
        ),
    ]
    # two disjoint 6-month windows ~= 12 months
    assert WF.oos_month_span(folds) == pytest.approx((181 + 182) / 30.44, abs=0.1)


def test_oos_month_span_merges_overlap():
    folds = [
        WF.Fold(
            1, _utc(2016, 1, 1), _utc(2019, 1, 1), _utc(2019, 1, 1), _utc(2019, 8, 1)
        ),
        WF.Fold(
            2, _utc(2016, 1, 1), _utc(2019, 6, 1), _utc(2019, 6, 1), _utc(2019, 12, 1)
        ),
    ]
    # overlapping [Jan..Aug] ∪ [Jun..Dec] = [Jan..Dec] ~= 11 months, NOT 13.
    merged_days = (_utc(2019, 12, 1) - _utc(2019, 1, 1)).days
    assert WF.oos_month_span(folds) == pytest.approx(merged_days / 30.44, abs=0.01)


def test_oos_month_span_single_and_empty():
    f = WF.Fold(
        1, _utc(2016, 1, 1), _utc(2019, 1, 1), _utc(2019, 1, 1), _utc(2024, 1, 1)
    )
    assert WF.oos_month_span([f]) == pytest.approx(
        (_utc(2024, 1, 1) - _utc(2019, 1, 1)).days / 30.44
    )
    assert WF.oos_month_span([]) == 0.0


def test_default_folds_span_is_about_84_months():
    # The headline expectation: ~10y of data shrinks oos_months from ~117 (full span) to <=84.
    start, end = _utc(2016, 6, 29), _utc(2026, 6, 23)
    span = WF.oos_month_span(WF.default_folds(start, end))
    assert span <= 84.5
    assert span >= 80.0


# ------------------------------------------------------------------------------- assign_oos


def _make_folds():
    start, end = _utc(2016, 1, 1), _utc(2026, 1, 1)
    return WF.generate_folds(start, end, min_train=36, step=6, oos_window=6), start


def test_assign_oos_boundary_at_cutoff():
    folds, start = _make_folds()
    cutoff = start + relativedelta(months=36)
    times = pd.Series(
        [
            cutoff - relativedelta(seconds=1),  # just before cutoff -> in-sample / NULL
            cutoff,  # exactly at cutoff -> OOS, fold 1
        ]
    )
    is_oos, fold_id = WF.assign_oos(times, folds)
    assert list(is_oos) == [False, True]
    assert pd.isna(fold_id.iloc[0])
    assert fold_id.iloc[1] == 1


def test_assign_oos_correct_bucketing():
    folds, start = _make_folds()
    cutoff = start + relativedelta(months=36)
    times = pd.Series(
        [
            cutoff + relativedelta(months=3),  # within fold 1 (months 36-42)
            cutoff + relativedelta(months=7),  # fold 2 (months 42-48)
            cutoff + relativedelta(months=13),  # fold 3 (months 48-54)
        ]
    )
    is_oos, fold_id = WF.assign_oos(times, folds)
    assert list(is_oos) == [True, True, True]
    assert list(fold_id) == [1, 2, 3]


def test_assign_oos_last_window_catches_series_end():
    folds, start = _make_folds()
    end = _utc(2026, 1, 1)
    is_oos, fold_id = WF.assign_oos(pd.Series([end]), folds)
    assert bool(is_oos.iloc[0]) is True
    assert int(fold_id.iloc[0]) == len(
        folds
    )  # trade exactly at series_end -> last fold


def test_assign_oos_empty_folds_all_in_sample():
    is_oos, fold_id = WF.assign_oos(pd.Series([_utc(2020, 1, 1), _utc(2021, 1, 1)]), [])
    assert not is_oos.any()
    assert fold_id.isna().all()
    assert str(fold_id.dtype) == "Int64"


def test_assign_oos_tz_handling_naive_input_coerced_utc():
    folds, start = _make_folds()
    cutoff = start + relativedelta(months=36)
    naive = pd.Series(
        [pd.Timestamp("2024-01-01 00:00:00")]
    )  # tz-naive => coerced to UTC
    is_oos, fold_id = WF.assign_oos(naive, folds)
    assert bool(is_oos.iloc[0]) is True
    # index preserved
    assert list(is_oos.index) == [0]


def test_assign_oos_handles_nat():
    folds, _ = _make_folds()
    times = pd.Series([pd.NaT, _utc(2024, 1, 1)])
    is_oos, fold_id = WF.assign_oos(times, folds)
    assert list(is_oos) == [False, True]
    assert pd.isna(fold_id.iloc[0])
