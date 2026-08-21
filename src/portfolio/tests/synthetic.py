"""Synthetic price worlds with a *known* answer, for controlling the evaluator.

Every negative result this package produces is uninterpretable unless the pipeline can
be shown to detect an edge that is known to exist. "No edge found" and "the measurement
cannot see edge" produce identical output otherwise. These builders create both cases:
a world with a planted, exploitable cross-sectional trend, and a world with none.

Construction is via **currency strength indices**, not by drawing pair prices directly.
A pair is then a ratio of two strength indices, which is what a currency pair actually
is. That matters because it makes the USD-base inversion real: if JPY strengthens,
``USD_JPY = USD/JPY`` falls, so a test that mishandles the ``USD_BASE_PAIRS`` sign
convention produces a *negative* Sharpe rather than a merely smaller one.
"""

from __future__ import annotations

from typing import Dict, Sequence

import numpy as np
import pandas as pd

#: The live universe: four currencies quoted against USD plus USD itself.
CURRENCIES: Sequence[str] = ("USD", "EUR", "GBP", "JPY", "AUD", "CAD")

#: pair -> (base currency, quote currency). EUR_USD = EUR/USD.
PAIR_LEGS: Dict[str, tuple[str, str]] = {
    "EUR_USD": ("EUR", "USD"),
    "GBP_USD": ("GBP", "USD"),
    "AUD_USD": ("AUD", "USD"),
    "USD_JPY": ("USD", "JPY"),
    "USD_CAD": ("USD", "CAD"),
}


def _calendar(n_bars: int) -> pd.DatetimeIndex:
    """Business-day UTC calendar, long enough to exercise the 252-bar warmup."""
    return pd.bdate_range("2006-01-02", periods=n_bars, tz="UTC", name="timestamp")


def _strength_paths(
    n_bars: int,
    drift_per_bar: np.ndarray,
    noise_sd: float,
    seed: int,
) -> Dict[str, np.ndarray]:
    """Cumulative log-strength per currency: drift + iid noise, exponentiated."""
    rng = np.random.default_rng(seed)
    paths: Dict[str, np.ndarray] = {}
    for j, ccy in enumerate(CURRENCIES):
        shocks = rng.normal(0.0, noise_sd, size=n_bars)
        log_level = np.cumsum(drift_per_bar[:, j] + shocks)
        paths[ccy] = np.exp(log_level)
    return paths


def _to_pairs(paths: Dict[str, np.ndarray], index: pd.DatetimeIndex) -> pd.DataFrame:
    data = {
        pair: paths[base] / paths[quote] for pair, (base, quote) in PAIR_LEGS.items()
    }
    return pd.DataFrame(data, index=index)


def planted_trend_world(
    n_bars: int = 6000,
    block_bars: int = 756,
    drift_scale: float = 0.0010,
    noise_sd: float = 0.0035,
    seed: int = 20260821,
) -> pd.DataFrame:
    """A world where cross-sectional momentum *must* work.

    Currencies are assigned persistent per-bar drifts that hold for ``block_bars``
    (three years by default) and are then re-permuted. Because a block is far longer
    than the 252-bar lookback, a momentum ranking formed inside a block is correct for
    the remainder of that block. USD's drift is pinned to zero so the cross-section is
    a comparison among the non-dollar currencies, matching the real universe.

    An evaluator that scores this near zero is broken; that is the whole point.
    """
    index = _calendar(n_bars)
    n_ccy = len(CURRENCIES)
    # Evenly spaced drifts, strongest positive to strongest negative.
    ladder = np.linspace(drift_scale, -drift_scale, n_ccy - 1)

    rng = np.random.default_rng(seed)
    drift = np.zeros((n_bars, n_ccy))
    for start in range(0, n_bars, block_bars):
        stop = min(start + block_bars, n_bars)
        permuted = rng.permutation(ladder)
        # Column 0 is USD and stays at zero drift.
        drift[start:stop, 1:] = permuted
    return _to_pairs(_strength_paths(n_bars, drift, noise_sd, seed), index)


def random_walk_world(
    n_bars: int = 6000, noise_sd: float = 0.0035, seed: int = 7
) -> pd.DataFrame:
    """A world with no cross-sectional signal at all. Expect Sharpe near zero."""
    index = _calendar(n_bars)
    drift = np.zeros((n_bars, len(CURRENCIES)))
    return _to_pairs(_strength_paths(n_bars, drift, noise_sd, seed), index)
