"""Tests for the FIX-S1-003 regime-discrimination study.

Mirrors the repo's "a gate must be able to fire" principle (FIX-S1-001/002/006): the
discrimination measurement must be able to BOTH detect real discrimination and report its
absence — otherwise it could not honestly answer FIX-S1-003. All tests are pure (no DB).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.system1.attribution.attribute import UNKNOWN_REGIME
from src.system1.attribution import discrimination as DISC


def _frame(records):
    return pd.DataFrame(records)


def test_detects_strong_discrimination():
    """A strategy that wins only in Ranging must read as discriminating (the test can fire)."""
    rows = []
    for _ in range(200):
        rows.append({"strategy_id": 1, "regime": "Ranging", "is_winner": 1})
        rows.append({"strategy_id": 1, "regime": "Trending-Up", "is_winner": 0})
    table = DISC.win_rate_spread_table(_frame(rows), "regime")
    row = table.iloc[0]
    assert row["spread"] == 1.0
    assert row["chi2_p"] is not None and row["chi2_p"] < 1e-6
    assert bool(row["discriminates"]) is True


def test_reports_no_discrimination_when_flat():
    """A flat strategy (same win-rate in every regime) must read as non-discriminating."""
    rng = np.random.default_rng(0)
    regimes = ["Ranging", "Trending-Up", "Trending-Down", "High-Vol"]
    rows = []
    for r in regimes:
        wins = rng.integers(0, 2, size=500)  # ~50% in every regime, no regime effect
        for w in wins:
            rows.append({"strategy_id": 7, "regime": r, "is_winner": int(w)})
    table = DISC.win_rate_spread_table(_frame(rows), "regime")
    row = table.iloc[0]
    assert row["spread"] < 0.10
    assert bool(row["discriminates"]) is False


def test_significant_but_immaterial_does_not_count_as_discriminating():
    """Huge-n tiny-spread (statistically sig, economically trivial) must NOT discriminate."""
    rows = []
    # 0.50 vs 0.52 win-rate over 20k trades each: chi2 significant, spread 0.02 < MATERIAL.
    for _ in range(10000):
        rows.append({"strategy_id": 9, "regime": "Ranging", "is_winner": 1})
        rows.append({"strategy_id": 9, "regime": "Ranging", "is_winner": 0})
    for _ in range(5200):
        rows.append({"strategy_id": 9, "regime": "Trending-Up", "is_winner": 1})
    for _ in range(4800):
        rows.append({"strategy_id": 9, "regime": "Trending-Up", "is_winner": 0})
    table = DISC.win_rate_spread_table(_frame(rows), "regime")
    row = table.iloc[0]
    assert row["chi2_p"] is not None and row["chi2_p"] < 0.05  # significant
    assert row["spread"] < DISC.MATERIAL_SPREAD  # but immaterial
    assert bool(row["discriminates"]) is False  # so not "earning its place"


def test_unknown_regime_excluded():
    rows = [
        {"strategy_id": 3, "regime": UNKNOWN_REGIME, "is_winner": 1} for _ in range(10)
    ]
    rows += [{"strategy_id": 3, "regime": "Ranging", "is_winner": 0} for _ in range(10)]
    table = DISC.win_rate_spread_table(_frame(rows), "regime")
    assert table.iloc[0]["n"] == 10  # only the Ranging rows counted
    assert "Ranging" in table.iloc[0]["win_rate_by_regime"]
    assert UNKNOWN_REGIME not in table.iloc[0]["win_rate_by_regime"]


def test_single_regime_pvalue_none():
    """One regime -> chi-square undefined -> p None -> not discriminating."""
    rows = [
        {"strategy_id": 5, "regime": "Ranging", "is_winner": i % 2} for i in range(40)
    ]
    table = DISC.win_rate_spread_table(_frame(rows), "regime")
    assert table.iloc[0]["chi2_p"] is None
    assert bool(table.iloc[0]["discriminates"]) is False


def test_dominant_regime_takes_modal_over_window():
    """Dominant tag = most frequent causal label inside [entry, exit]."""
    base = np.datetime64("2024-01-01T00:00:00")
    hour = np.timedelta64(1, "h")
    bar_times = base + np.arange(6) * hour
    # bars: Ranging, Ranging, Ranging, Trending-Up, Trending-Up, High-Vol
    bar_reg = np.array(
        ["Ranging", "Ranging", "Ranging", "Trending-Up", "Trending-Up", "High-Vol"],
        dtype=object,
    )
    entry = base  # window [t0, t4] -> 3 Ranging vs 2 Trending-Up -> Ranging
    exit_ = base + 4 * hour
    assert DISC.dominant_regime_in_window(bar_times, bar_reg, entry, exit_) == "Ranging"


def test_dominant_regime_window_can_flip_the_label():
    """A trade entered in Ranging but spent mostly in Trending-Up -> Trending-Up dominant."""
    base = np.datetime64("2024-01-01T00:00:00")
    hour = np.timedelta64(1, "h")
    bar_times = base + np.arange(6) * hour
    bar_reg = np.array(
        [
            "Ranging",
            "Trending-Up",
            "Trending-Up",
            "Trending-Up",
            "Trending-Up",
            "High-Vol",
        ],
        dtype=object,
    )
    entry = base  # entry bar is Ranging
    exit_ = base + 4 * hour  # but window is dominated by Trending-Up
    assert (
        DISC.dominant_regime_in_window(bar_times, bar_reg, entry, exit_)
        == "Trending-Up"
    )


def test_dominant_regime_same_bar_falls_back_to_entry():
    """holding_bars==0 (window collapses to entry) -> most recent regime at/<= entry."""
    base = np.datetime64("2024-01-01T00:00:00")
    hour = np.timedelta64(1, "h")
    bar_times = base + np.arange(3) * hour
    bar_reg = np.array(["Ranging", "Trending-Up", "High-Vol"], dtype=object)
    entry = base + 1 * hour  # at a Trending-Up bar; exit == entry (no window)
    assert (
        DISC.dominant_regime_in_window(bar_times, bar_reg, entry, entry)
        == "Trending-Up"
    )


def test_dominant_regime_no_prior_bar_is_unknown():
    base = np.datetime64("2024-01-01T05:00:00")
    hour = np.timedelta64(1, "h")
    bar_times = base + np.arange(3) * hour
    bar_reg = np.array(["Ranging", "Trending-Up", "High-Vol"], dtype=object)
    early = np.datetime64("2024-01-01T00:00:00")  # before any bar
    assert (
        DISC.dominant_regime_in_window(bar_times, bar_reg, early, early)
        == UNKNOWN_REGIME
    )


def test_summarize_counts_discriminators():
    table = pd.DataFrame(
        [
            {"strategy_id": 1, "spread": 0.5, "discriminates": True},
            {"strategy_id": 2, "spread": 0.02, "discriminates": False},
        ]
    )
    s = DISC.summarize(table)
    assert s["n_strategies"] == 2
    assert s["n_discriminating"] == 1
    assert s["max_spread"] == 0.5
