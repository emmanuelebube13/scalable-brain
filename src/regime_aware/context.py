"""Regime labels → a column on the price frame, causally, over a read-only connection.

This is the only module in the package that talks to the database, and it can only read:
:func:`readonly_connection` issues ``SET default_transaction_read_only = on``, after which
PostgreSQL refuses any INSERT/UPDATE/DELETE/CREATE on that session. That makes the isolation
guarantee enforced by the database rather than promised by a code review.

Causality
---------
Only ``regime_causal`` is ever read. ``fact_market_regime_v2`` also carries ``regime_smoothed``,
which is a forward-backward HMM fit over the full history — a label for bar *t* computed partly
from bars after *t*. Feeding that to a strategy manufactures exactly the look-ahead that
disqualified ``Range_Stochastic_Divergence`` (FIX-S1-014). :func:`load_regime_labels` refuses any
other column by name, and :func:`attach_regime` joins **backward only** (``merge_asof`` with
``direction="backward"``), so bar *t* carries the most recent regime bar at or before *t*.

Warm-up bars, where the HMM has not yet produced a causal label, are ``UNKNOWN`` — never
back-filled from the future, never silently dropped. A strategy decides what to do with
``UNKNOWN``; the honest default is "do not trade".
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import pandas as pd

from src.common.db import get_psycopg2_connection

logger = logging.getLogger("regime_aware.context")

#: The ONLY regime column this package may read. See the module docstring.
CAUSAL_COLUMN = "regime_causal"

#: Label given to bars with no causal regime yet (HMM warm-up).
UNKNOWN = "UNKNOWN"

#: The four HMM states plus the warm-up label. A strategy must supply a parameter block for
#: every one of these, so a new/unseen label can never fall through to silent default behaviour.
ALL_REGIMES = ("Trending-Up", "Trending-Down", "Ranging", "High-Vol", UNKNOWN)


def readonly_connection():
    """A psycopg2 connection that PostgreSQL will not let us write through.

    ``default_transaction_read_only`` applies to every subsequent transaction on the session, so
    this survives the implicit commits psycopg2 issues between statements.
    """
    conn = get_psycopg2_connection()
    cur = conn.cursor()
    cur.execute("SET default_transaction_read_only = on")
    conn.commit()
    logger.info("opened READ-ONLY connection (writes will be refused by PostgreSQL)")
    return conn


def load_regime_labels(
    conn, granularity: str, column: str = CAUSAL_COLUMN
) -> Dict[int, pd.DataFrame]:
    """``{asset_id: DataFrame[bar_time, regime]}`` for one granularity, causal labels only.

    Raises on any column other than ``regime_causal`` — the guard is deliberately a hard error
    rather than a warning, because the failure it prevents is silent and looks like success.
    """
    if column != CAUSAL_COLUMN:
        raise ValueError(
            f"regime column {column!r} is not permitted: this package reads only "
            f"{CAUSAL_COLUMN!r}. 'regime_smoothed' is a forward-backward fit over full history "
            "and leaks future bars into past labels (see FIX-S1-014)."
        )
    sql = (
        f'SELECT asset_id, "timestamp" AS bar_time, {CAUSAL_COLUMN} AS regime '
        "FROM fact_market_regime_v2 "
        "WHERE granularity = %s AND regime_causal IS NOT NULL "
        "ORDER BY asset_id, bar_time"
    )
    df = pd.read_sql(sql, conn, params=(granularity,))
    df["bar_time"] = pd.to_datetime(df["bar_time"], utc=True)
    out = {int(aid): g.reset_index(drop=True) for aid, g in df.groupby("asset_id")}
    logger.info(
        "loaded %s causal regime labels for %d assets at %s",
        f"{len(df):,}",
        len(out),
        granularity,
    )
    return out


def attach_regime(
    price_df: pd.DataFrame, labels: Optional[pd.DataFrame]
) -> pd.DataFrame:
    """Return a copy of ``price_df`` with a ``regime`` column joined backward in time.

    ``merge_asof(direction="backward")`` guarantees bar *t* sees only regime bars at or before
    *t*. Bars earlier than the first label get :data:`UNKNOWN`. The input frame is never mutated —
    strategies downstream receive shared frames and must not be able to poison each other.
    """
    out = price_df.copy()
    if labels is None or labels.empty:
        out["regime"] = UNKNOWN
        return out

    left = pd.DataFrame({"bar_time": pd.to_datetime(out.index, utc=True)}).sort_values(
        "bar_time"
    )
    merged = pd.merge_asof(
        left,
        labels[["bar_time", "regime"]].sort_values("bar_time"),
        on="bar_time",
        direction="backward",
    )
    out["regime"] = merged["regime"].fillna(UNKNOWN).to_numpy()
    return out


def build_trend_labels(d1: pd.DataFrame, fast: int = 50, slow: int = 200) -> pd.DataFrame:
    """A second context source: D1 EMA alignment, expressed in the SAME label vocabulary.

    Motivation: the HMM labels are ~95% ``Ranging`` for four of the five pairs, so conditioning
    on them collapses to "is this USD_JPY" (see the T3 deliverable). This provider produces a
    label that varies on every pair, while emitting only ``Trending-Up`` / ``Trending-Down`` /
    ``UNKNOWN`` — a subset of :data:`ALL_REGIMES` — so strategies, parameter blocks and every
    test carry over unchanged. ``Ranging`` and ``High-Vol`` simply never occur under it.

    Causality: the EMA comparison is ``shift(1)``-ed, so the label stamped on D1 bar *d* is
    computed from bars strictly before *d*; :func:`attach_regime` then joins it backward onto
    intraday bars. A signal at bar *t* therefore sees daily information at least one full D1 bar
    old. Bars inside the EMA-slow warm-up are ``UNKNOWN`` rather than a guessed direction.
    """
    close = d1["Close"]
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()

    label = pd.Series(UNKNOWN, index=d1.index, dtype="object")
    label[ema_fast > ema_slow] = "Trending-Up"
    label[ema_fast < ema_slow] = "Trending-Down"
    label.iloc[:slow] = UNKNOWN  # EMA-slow warm-up: no opinion

    shifted = label.shift(1).fillna(UNKNOWN)
    return pd.DataFrame(
        {
            "bar_time": pd.to_datetime(d1.index, utc=True),
            "regime": shifted.to_numpy(),
        }
    ).reset_index(drop=True)


def regime_coverage(df: pd.DataFrame) -> Dict[str, float]:
    """Share of bars per regime — used by the report to show *why* an arm did what it did."""
    counts = df["regime"].value_counts(normalize=True)
    return {str(k): round(float(v) * 100, 2) for k, v in counts.items()}
