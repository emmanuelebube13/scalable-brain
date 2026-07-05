"""FIX-S1-005 — causal regime-label leakage regression tests (pure, no DB / no network).

Three guarantees, mirroring the §2B demonstration in the fix doc, inverted into assertions:

  (a) the **filtered** forward-only posterior at bar ``t`` is invariant to any mutation of
      bars strictly after ``t`` (label + argmax unchanged);
  (b) GUARD-CAN-FIRE: the **smoothed** ``predict_proba`` posterior (the old, consumed path)
      DOES move at a bar ``<= t`` under the same future mutation — proving the test detects a
      real leak (an always-passing leakage test would itself be the bug, global rule #3);
  (c) walk-forward fold causality: with the per-fold refit, mutating bars beyond a position
      ``t`` leaves every causal label at positions ``<= t`` byte-for-byte unchanged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM

from src.system1.regime import hmm_regime as H
from src.system1.regime import mapping as M


def _fit_two_state_hmm(seed: int = 0):
    """Fit a 2-state Gaussian HMM on a regime-switching 1-D sequence.

    Emissions deliberately *overlap* (means ∓1, std ~1.3) so per-bar evidence is
    ambiguous and the smoothing (backward) pass carries real information from the
    future — the regime in which look-ahead leakage is observable (cf. fix doc §2B).
    """
    rng = np.random.RandomState(seed)
    blocks = []
    for _ in range(10):
        blocks.append(rng.normal(-1.0, 1.3, size=10))
        blocks.append(rng.normal(1.0, 1.3, size=10))
    x = np.concatenate(blocks).reshape(-1, 1)
    hmm = GaussianHMM(
        n_components=2, covariance_type="diag", n_iter=300, random_state=seed
    )
    hmm.fit(x)
    return hmm, x


# --------------------------------------------------- (a) filtered posterior is future-invariant


def _most_ambiguous_interior_bar(hmm, x) -> int:
    """Index (interior) whose filtered posterior is closest to 0.5 — the bar most
    sensitive to future evidence under smoothing."""
    flp = hmm._compute_log_likelihood(x)
    post = M.filtered_posteriors(hmm.startprob_, hmm.transmat_, flp)
    interior = post[20 : len(x) - 20, 0]
    return 20 + int(np.argmin(np.abs(interior - 0.5)))


def test_filtered_label_invariant_to_future_bars():
    hmm, x = _fit_two_state_hmm()
    t0 = 120
    flp = hmm._compute_log_likelihood(x)
    post = M.filtered_posteriors(hmm.startprob_, hmm.transmat_, flp)
    argmax = post.argmax(axis=1)

    x_mut = x.copy()
    x_mut[t0 + 1 :] += 50.0  # violently mutate ONLY the future
    flp_mut = hmm._compute_log_likelihood(x_mut)
    post_mut = M.filtered_posteriors(hmm.startprob_, hmm.transmat_, flp_mut)

    assert np.allclose(post[: t0 + 1], post_mut[: t0 + 1], atol=1e-12)
    assert np.array_equal(argmax[: t0 + 1], post_mut[: t0 + 1].argmax(axis=1))


# --------------------------------------------------- (b) GUARD-CAN-FIRE: the smoothed path leaks


def test_smoothed_predict_proba_leaks_so_guard_can_fire():
    """The consumed-by-mistake path (forward-backward ``predict_proba``) must visibly change
    a bar ``<= t0`` when only future bars are mutated — otherwise the leakage test above is
    vacuous. This is the counter-test proving the guard can fire."""
    hmm, x = _fit_two_state_hmm()
    t0 = _most_ambiguous_interior_bar(hmm, x)
    smoothed = hmm.predict_proba(x)

    # Force the immediate future strongly into one regime. Forward-backward propagates
    # this through the backward pass and shifts a PAST bar's smoothed posterior — the
    # exact look-ahead leak FIX-S1-005 removes from the consumed label.
    x_mut = x.copy()
    x_mut[t0 + 1 : t0 + 11] = 6.0
    smoothed_mut = hmm.predict_proba(x_mut)

    # At least one PAST bar's smoothed posterior moved — that is the look-ahead leak.
    max_past_change = np.abs(smoothed[: t0 + 1] - smoothed_mut[: t0 + 1]).max()
    assert max_past_change > 1e-6, (
        "smoothed posterior did not move under a future mutation — the leakage test would "
        "be vacuous (guard cannot fire)"
    )


# --------------------------------------------------- (c) walk-forward fold causality


def _synthetic_regime_df(n_months: int = 96, asset_id: int = 1) -> pd.DataFrame:
    """One instrument, monthly bars, regime-switching FEATURE_NAMES columns."""
    rng = np.random.RandomState(3)
    times = pd.date_range("2014-01-01", periods=n_months, freq="MS", tz="UTC")
    # Alternating high/low volatility + trend blocks so regimes are learnable.
    block = (np.arange(n_months) // 8) % 2
    atr = np.where(block == 1, 0.9, 0.2) + rng.normal(0, 0.02, n_months)
    vol = np.where(block == 1, 0.8, 0.15) + rng.normal(0, 0.02, n_months)
    adx = np.where(block == 1, 30.0, 18.0) + rng.normal(0, 0.5, n_months)
    ret = np.where(block == 1, 0.003, -0.001) + rng.normal(0, 0.0005, n_months)
    trend = np.where(block == 1, 0.004, -0.002) + rng.normal(0, 0.0005, n_months)
    return pd.DataFrame(
        {
            "asset_id": asset_id,
            "bar_time_utc": times,
            "atr_14": atr,
            "adx_14": adx,
            "volatility_20": vol,
            "returns_1": ret,
            "trend_20": trend,
        }
    )


def test_walk_forward_labels_invariant_to_future_mutation():
    df = _synthetic_regime_df()
    weights = np.array([H.FEATURE_WEIGHTS[f] for f in H.FEATURE_NAMES], dtype="float64")

    base = H.causal_labels(df, "D1", weights)
    # There must be real labelled (post-warm-up) bars to compare.
    assert base["regime_causal"].notna().sum() > 0

    # Pick a position inside the labelled OOS region and mutate everything strictly after it.
    labelled_pos = np.where(base["regime_causal_raw"].to_numpy() != None)[
        0
    ]  # noqa: E711
    t = int(labelled_pos[len(labelled_pos) // 2])

    df_mut = df.copy()
    feat_cols = H.FEATURE_NAMES
    df_mut.loc[df_mut.index[t + 1 :], feat_cols] = (
        df_mut.loc[df_mut.index[t + 1 :], feat_cols] + 100.0
    )
    mut = H.causal_labels(df_mut, "D1", weights)

    # Every causal label/posterior at positions <= t is unchanged by future mutation.
    assert (
        base["regime_causal_raw"].iloc[: t + 1].tolist()
        == mut["regime_causal_raw"].iloc[: t + 1].tolist()
    )
    assert (
        base["regime_causal"].iloc[: t + 1].tolist()
        == mut["regime_causal"].iloc[: t + 1].tolist()
    )
    for col in H.PROB_CAUSAL_COLUMNS:
        a = base[col].iloc[: t + 1].to_numpy()
        b = mut[col].iloc[: t + 1].to_numpy()
        assert np.allclose(a, b, atol=1e-9, equal_nan=True), col


def test_warmup_bars_are_unknown():
    """Bars before the first fold cutoff (36mo warm-up) carry no causal label."""
    df = _synthetic_regime_df()
    weights = np.array([H.FEATURE_WEIGHTS[f] for f in H.FEATURE_NAMES], dtype="float64")
    out = H.causal_labels(df, "D1", weights)
    # The first ~36 monthly bars precede the cutoff -> NULL causal label / fold id.
    assert out["regime_causal"].iloc[:30].isna().all()
    assert out["causal_fold_id"].iloc[:30].isna().all()
