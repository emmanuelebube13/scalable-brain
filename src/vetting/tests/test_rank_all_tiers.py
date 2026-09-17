"""Phase B evidence-tier classification tests for ``rank_all.classify_tier`` (no DB/network).

Rules under test are owner-approved 2026-09-17, recorded in
task/2026-September-week3/core-verification/PHASE-A-RESULTS.md, and restated as module
constants in ``rank_all.py`` (``TIER_1_MIN_N``, ``TIER_1_MIN_POSITIVE_FOLDS``,
``TIER_1_MAX_PAIR_SHARE``).
"""

from __future__ import annotations

from src.vetting import rank_all as RA


def make_rec(
    mean_r=0.05,
    ci_lo=None,
    ci_hi=None,
    trade_count=150,
    n_positive_folds=5,
    largest_pair_share=0.30,
    integrity_disqualified=False,
):
    return {
        "mean_r": mean_r,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "trade_count": trade_count,
        "n_positive_folds": n_positive_folds,
        "largest_pair_share": largest_pair_share,
        "integrity_disqualified": integrity_disqualified,
    }


def test_tier1_candidate_when_all_conditions_met():
    rec = make_rec(
        mean_r=0.10,
        ci_lo=0.02,
        ci_hi=0.18,
        trade_count=150,
        n_positive_folds=5,
        largest_pair_share=0.35,
    )
    assert RA.classify_tier(rec) == RA.TIER_CANDIDATE


def test_ci_positive_but_n_99_is_tier2_not_tier1():
    """n just below the 100 floor: CI is clear positive, everything else qualifies, but
    the n>=100 requirement is the one thing missing — must fall to Tier 2, not Tier 1.
    """
    rec = make_rec(
        mean_r=0.08,
        ci_lo=0.01,
        ci_hi=0.15,
        trade_count=99,
        n_positive_folds=5,
        largest_pair_share=0.30,
    )
    assert RA.classify_tier(rec) == RA.TIER_GROW_SAMPLE


def test_ci_negative_small_n_is_tier3():
    """CI clear of zero on the negative side qualifies for Tier 3 regardless of n — even
    well below the Tier-1 n>=100 floor."""
    rec = make_rec(
        mean_r=-0.20,
        ci_lo=-0.35,
        ci_hi=-0.05,
        trade_count=25,
        n_positive_folds=0,
        largest_pair_share=0.50,
    )
    assert RA.classify_tier(rec) == RA.TIER_RETIRE


def test_disqualified_overrides_everything_including_a_tier1_looking_record():
    """Integrity disqualification wins even over a record that otherwise satisfies every
    Tier 1 condition."""
    rec = make_rec(
        mean_r=0.10,
        ci_lo=0.02,
        ci_hi=0.18,
        trade_count=200,
        n_positive_folds=6,
        largest_pair_share=0.20,
        integrity_disqualified=True,
    )
    assert RA.classify_tier(rec) == RA.TIER_DISQUALIFIED


def test_fold_count_boundary_three_folds_is_tier2_four_is_tier1():
    base = dict(
        mean_r=0.10,
        ci_lo=0.02,
        ci_hi=0.18,
        trade_count=150,
        largest_pair_share=0.30,
    )
    below = make_rec(**base, n_positive_folds=RA.TIER_1_MIN_POSITIVE_FOLDS - 1)
    at = make_rec(**base, n_positive_folds=RA.TIER_1_MIN_POSITIVE_FOLDS)
    assert RA.classify_tier(below) == RA.TIER_GROW_SAMPLE
    assert RA.classify_tier(at) == RA.TIER_CANDIDATE


def test_max_pair_share_boundary():
    base = dict(
        mean_r=0.10, ci_lo=0.02, ci_hi=0.18, trade_count=150, n_positive_folds=5
    )
    at_threshold = make_rec(**base, largest_pair_share=RA.TIER_1_MAX_PAIR_SHARE)
    over_threshold = make_rec(
        **base, largest_pair_share=RA.TIER_1_MAX_PAIR_SHARE + 0.01
    )
    assert RA.classify_tier(at_threshold) == RA.TIER_CANDIDATE
    assert RA.classify_tier(over_threshold) == RA.TIER_GROW_SAMPLE


def test_no_ci_small_n_positive_mean_is_grow_sample_not_tier1():
    """A missing CI (small n, bootstrap_mean_ci returns None) can never be Tier 1."""
    rec = make_rec(
        mean_r=0.15, ci_lo=None, ci_hi=None, trade_count=10, n_positive_folds=1
    )
    assert RA.classify_tier(rec) == RA.TIER_GROW_SAMPLE


def test_no_ci_negative_mean_is_negative_inconclusive_not_tier3():
    """A missing CI can never be Tier 3 either — falls to Tier 4 on mean R alone."""
    rec = make_rec(
        mean_r=-0.05, ci_lo=None, ci_hi=None, trade_count=10, n_positive_folds=0
    )
    assert RA.classify_tier(rec) == RA.TIER_NEGATIVE_INCONCLUSIVE


def test_ci_straddles_zero_negative_mean_is_negative_inconclusive():
    rec = make_rec(mean_r=-0.02, ci_lo=-0.10, ci_hi=0.05, trade_count=150)
    assert RA.classify_tier(rec) == RA.TIER_NEGATIVE_INCONCLUSIVE


def test_ci_straddles_zero_positive_mean_is_grow_sample():
    """mean R > 0 but the CI is not clear of zero (straddles) — Tier 2, per the rule that
    Tier 2 is 'everything else with mean R > 0'."""
    rec = make_rec(mean_r=0.05, ci_lo=-0.01, ci_hi=0.11, trade_count=150)
    assert RA.classify_tier(rec) == RA.TIER_GROW_SAMPLE


def test_positive_fold_count_counts_only_folds_with_positive_mean():
    import pandas as pd

    df = pd.DataFrame(
        {
            "fold_id": pd.array([1, 1, 2, 2, 3, None], dtype="Int64"),
            "r_multiple": [1.0, -0.2, -1.0, -1.0, 0.1, 999.0],
        }
    )
    n_positive, n_folds = RA.positive_fold_count(df)
    # fold 1 mean = 0.4 (positive), fold 2 mean = -1.0 (negative), fold 3 mean = 0.1
    # (positive); the null-fold_id row is excluded from both counts.
    assert n_folds == 3
    assert n_positive == 2


def test_tier_counts_tallies_every_tier():
    rows = [
        {"tier": RA.TIER_CANDIDATE},
        {"tier": RA.TIER_CANDIDATE},
        {"tier": RA.TIER_GROW_SAMPLE},
        {"tier": RA.TIER_RETIRE},
        {"tier": RA.TIER_NEGATIVE_INCONCLUSIVE},
        {"tier": RA.TIER_DISQUALIFIED},
    ]
    counts = RA.tier_counts(rows)
    assert counts == {
        RA.TIER_CANDIDATE: 2,
        RA.TIER_GROW_SAMPLE: 1,
        RA.TIER_RETIRE: 1,
        RA.TIER_NEGATIVE_INCONCLUSIVE: 1,
        RA.TIER_DISQUALIFIED: 1,
    }
