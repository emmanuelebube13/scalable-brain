"""Score a weight schedule as one portfolio instead of N independent cells.

The gap this closes
-------------------
``vetting`` asks whether a ``(strategy x pair x regime x granularity)`` cell clears
PF/Sharpe/MaxDD. A cross-sectional or diversified strategy has no edge in any single
cell by construction — its return comes from combining weakly-correlated legs, and the
legs individually look like noise. Scored cell-by-cell it fails everywhere while the
portfolio it describes may be perfectly sound. This module scores the portfolio.

The one-bar shift
-----------------
:mod:`src.portfolio.schedule` produces weights *decided at the close of* a rebalance
bar. Bar ``t``'s return ``close[t]/close[t-1] - 1`` is earned between ``t-1`` and ``t``,
so the weight that may claim it is the one decided at ``t-1``. Everything here therefore
uses ``weights.shift(1)``. ``tests/test_no_lookahead.py`` pins it: remove the shift and
the planted-signal control returns an impossibly high Sharpe, which is the signature of
exactly this bug.

Costs
-----
``cost_per_unit_turnover`` is charged on ``|w[t] - w[t-1]|`` summed across pairs. It is a
*fraction*, not pips: 0.0002 is 2 basis points of the notional traded. The measured H1
spreads on this account average 1.8-2.9 pips (roughly 1.5-2.5 bp of a major's price), and
CLAUDE.md documents the backtester's flat 1.0-pip assumption as understating that. The
default here is 0.0 so that a caller must state a cost explicitly and the reader of a
result always knows which one was used.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from src.validation.walk_forward import Fold, default_folds

logger = logging.getLogger("system1.portfolio.evaluate")

#: D1 bars per year, matching the 252-bar lookback in the momentum spec.
BARS_PER_YEAR = 252


@dataclass(frozen=True)
class PortfolioMetrics:
    """Aggregate metrics on a portfolio return series.

    ``profit_factor`` is computed on per-bar returns, not per-trade r-multiples, so it is
    not directly comparable to ``attribution.metrics.profit_factor``. A continuously
    held portfolio has no trades to factor; comparing its bar-level PF to a discrete
    strategy's trade-level PF is an apples-to-oranges error and the field name is kept
    distinct in reports for that reason.
    """

    bars: int
    years: float
    total_return: float
    annualized_return: float
    annualized_vol: float
    sharpe: float
    profit_factor: float
    max_drawdown: float
    recovery_factor: float
    hit_rate: float
    avg_turnover: float

    def as_dict(self) -> Dict[str, float]:
        return asdict(self)


def expand_weights(schedule: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    """Hold each rebalance's weights until the next one, on the price calendar.

    Forward-fill is correct *here* (unlike in price alignment): a position genuinely
    persists between rebalances. Bars before the first rebalance are flat, not NaN.
    """
    expanded = schedule.reindex(calendar.union(schedule.index)).ffill()
    expanded = expanded.reindex(calendar).fillna(0.0)
    return expanded


def inverse_vol_scale(
    weights: pd.DataFrame,
    returns: pd.DataFrame,
    lookback: int = 60,
    min_periods: int = 20,
) -> pd.DataFrame:
    """Scale each leg by the inverse of its own trailing volatility.

    This is what makes a multi-asset momentum portfolio work: without it the highest-
    volatility leg dominates the portfolio's risk and the diversification that the whole
    approach depends on never materialises.

    The volatility estimate uses ``rolling(...).std()`` on returns up to and including
    bar ``t``, then is shifted one bar before use, so a weight applied to bar ``t``'s
    return was scaled by volatility known at ``t-1``.
    """
    vol = returns.rolling(lookback, min_periods=min_periods).std().shift(1)
    inv = 1.0 / vol.replace(0.0, np.nan)
    scaled = weights * inv
    # Renormalise to the original gross exposure so vol-scaling changes the *mix*, not
    # the leverage — otherwise the metric would confound sizing with selection.
    gross_before = weights.abs().sum(axis=1)
    gross_after = scaled.abs().sum(axis=1).replace(0.0, np.nan)
    scaled = scaled.mul(gross_before / gross_after, axis=0)
    return scaled.fillna(0.0)


def portfolio_returns(
    closes: pd.DataFrame,
    schedule: pd.DataFrame,
    cost_per_unit_turnover: float = 0.0,
    vol_scaled: bool = False,
    vol_lookback: int = 60,
) -> tuple[pd.Series, pd.Series]:
    """Return ``(net_returns, turnover)`` per bar on the price calendar.

    Raises on a schedule whose columns do not match the price matrix — a silently
    mismatched universe would evaluate a different strategy from the one described.
    """
    if list(schedule.columns) != list(closes.columns):
        raise ValueError(
            f"portfolio_returns: schedule columns {list(schedule.columns)} != "
            f"price columns {list(closes.columns)}"
        )
    if cost_per_unit_turnover < 0.0:
        raise ValueError("portfolio_returns: cost must be >= 0")

    returns = closes.pct_change()
    weights = expand_weights(schedule, closes.index)
    if vol_scaled:
        weights = inverse_vol_scale(weights, returns, lookback=vol_lookback)

    # The weight that may claim bar t's return is the one decided at t-1.
    held = weights.shift(1).fillna(0.0)
    gross = (held * returns).sum(axis=1, skipna=True)

    turnover = held.diff().abs().sum(axis=1).fillna(0.0)
    net = gross - turnover * cost_per_unit_turnover
    net.name = "portfolio_return"
    turnover.name = "turnover"
    return net, turnover


def compute_metrics(
    returns: pd.Series, turnover: Optional[pd.Series] = None
) -> PortfolioMetrics:
    """Metrics on a per-bar return series. Empty or all-flat input returns zeros."""
    r = returns.dropna()
    n = int(len(r))
    if n == 0:
        return PortfolioMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    years = n / BARS_PER_YEAR
    equity = (1.0 + r).cumprod()
    total_return = float(equity.iloc[-1] - 1.0)
    ann_return = float(equity.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 else 0.0
    sd = float(r.std())
    ann_vol = sd * np.sqrt(BARS_PER_YEAR)
    sharpe = float(r.mean() / sd * np.sqrt(BARS_PER_YEAR)) if sd > 0 else 0.0

    gains = float(r[r > 0].sum())
    losses = float(-r[r < 0].sum())
    pf = gains / losses if losses > 0 else (float("inf") if gains > 0 else 0.0)

    peak = equity.cummax()
    dd = float((equity / peak - 1.0).min())
    max_dd = abs(dd)
    recovery = total_return / max_dd if max_dd > 0 else 0.0
    hit = float((r > 0).sum()) / n

    avg_turnover = (
        float(turnover.reindex(r.index).mean()) if turnover is not None else 0.0
    )

    return PortfolioMetrics(
        bars=n,
        years=round(years, 2),
        total_return=total_return,
        annualized_return=ann_return,
        annualized_vol=ann_vol,
        sharpe=sharpe,
        profit_factor=pf,
        max_drawdown=max_dd,
        recovery_factor=recovery,
        hit_rate=hit,
        avg_turnover=avg_turnover,
    )


def oos_mask(index: pd.DatetimeIndex, folds: Sequence[Fold]) -> pd.Series:
    """Boolean mask of bars falling inside any fold's OOS window.

    Note for the reader of a result: this strategy has **no fitted parameters** — the
    12-month lookback and tercile rule are pre-registered from the source, not tuned
    here — so the full sample is already out-of-sample in the sense that matters. The
    walk-forward mask is reported alongside it for comparability with the rest of
    System 1, not because it is doing statistical work.
    """
    mask = pd.Series(False, index=index)
    for fold in folds:
        mask |= (index >= fold.oos_start) & (index < fold.oos_end)
    return mask


def evaluate(
    closes: pd.DataFrame,
    schedule: pd.DataFrame,
    cost_per_unit_turnover: float = 0.0,
    vol_scaled: bool = False,
) -> Dict[str, object]:
    """Full-sample and walk-forward-OOS metrics for one weight schedule."""
    net, turnover = portfolio_returns(
        closes, schedule, cost_per_unit_turnover, vol_scaled=vol_scaled
    )
    full = compute_metrics(net, turnover)

    folds: List[Fold] = default_folds(
        closes.index[0].to_pydatetime(), closes.index[-1].to_pydatetime()
    )
    mask = oos_mask(net.index, folds)
    oos = compute_metrics(net[mask], turnover[mask])

    logger.info(
        "evaluate | vol_scaled=%s cost=%.5f | full Sharpe %.3f PF %.3f MaxDD %.1f%% | "
        "OOS Sharpe %.3f PF %.3f",
        vol_scaled,
        cost_per_unit_turnover,
        full.sharpe,
        full.profit_factor,
        full.max_drawdown * 100,
        oos.sharpe,
        oos.profit_factor,
    )
    return {
        "full_sample": full.as_dict(),
        "walk_forward_oos": oos.as_dict(),
        "folds": len(folds),
        "vol_scaled": vol_scaled,
        "cost_per_unit_turnover": cost_per_unit_turnover,
    }
