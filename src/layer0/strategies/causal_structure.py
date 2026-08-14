"""Causal market structure: swing points, ZigZag, and rolling access to them.

.. deprecated-path note ::
    Do NOT use ``src.layer0.data_access.indicators.detect_swing_points`` for new
    work. It computes ``rolling(window=period*2+1, center=True)`` — a centred
    window that at bar *t* spans ``[t-period … t+period]`` — and is therefore
    look-ahead. That exact mechanism contaminated ``Range_Stochastic_Divergence``
    (see ``docs/LOOKAHEAD_FINDINGS.md``, FIX-S1-013), the only strategy that
    reached production. The old function stays in place, unedited, because other
    code depends on it and the audit records its behaviour. Use this module.

The semantic difference is the whole point (spec §6): a swing high **occurs**
at bar *k* but is **knowable** only at bar *k+period*, once the ``period`` bars
after it have all failed to exceed it. Every function here stamps information at
the bar where it becomes knowable and carries the *level* from the occurrence
bar. A strategy may act on a swing from its confirmation bar onward using the
level set at the occurrence bar — that is what a live trader does. Knowing at
bar *k* that bar *k* was a swing high is the banned behaviour.

Strictness conventions (chosen here, relied on by tests):

- **Occurrence, left side (strict):** bar *k* is a swing-high candidate only if
  ``high[k]`` is *strictly greater* than every high in the prior window
  ``[k-period, k-1]`` (``>``, not ``>=``). Mirror: ``low[k]`` strictly below all
  prior-window lows. A flat-topped pair of equal highs produces no candidate.
- **Confirmation, right side (non-strict failure):** the candidate is confirmed
  at bar ``k+period`` iff *no* high in ``[k+1, k+period]`` **strictly exceeds**
  ``high[k]``. A later bar that merely *equals* ``high[k]`` does not break
  confirmation (``future_max <= high[k]``). Mirror: confirmation breaks only if
  a later low strictly undercuts ``low[k]``.
- **Window edges are inclusive** on both sides, so the confirmation stamp lands
  exactly at ``k+period`` and never earlier — even if the candidate is broken at
  ``k+1``, the (absent) mark is only decided at ``k+period``; a broken candidate
  simply never appears.
- **Tail:** the last ``period`` bars can never confirm anything (the window
  ``[k+1, k+period]`` does not exist yet), so they are always NaN. No future
  data is ever required.
- **NaN inputs** propagate through the rolling windows and suppress candidates
  conservatively; they never *create* marks.

Causality guarantee: recomputing any function in this module on a truncated
frame ``df.iloc[:m]`` yields results identical to the full-frame computation on
the shared index. Tests assert this directly, including truncations that land
*inside* a confirmation window.

Pure pandas/numpy. No I/O, no globals, deterministic.
"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd

__all__ = [
    "confirmed_swing_points",
    "zigzag_swings",
    "last_n_confirmed_highs",
    "last_n_confirmed_lows",
]

# Kind labels used in the zigzag_swings output frame.
_KIND_HIGH = "high"
_KIND_LOW = "low"


def _validate_pair(high: pd.Series, low: pd.Series, period: int) -> None:
    if not isinstance(high, pd.Series) or not isinstance(low, pd.Series):
        raise TypeError("high and low must be pandas Series")
    if not high.index.equals(low.index):
        raise ValueError("high and low must share the same index")
    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise ValueError(f"period must be a positive int, got {period!r}")


def confirmed_swing_points(
    high: pd.Series, low: pd.Series, period: int = 5
) -> Tuple[pd.Series, pd.Series]:
    """Swing points stamped at their CONFIRMATION bar, not their occurrence bar.

    A swing high at bar *k* (``high[k]`` strictly above the highs of the
    ``period`` bars before it) is confirmed only once the ``period`` bars after
    it have all failed to exceed it — i.e. at bar ``k+period``. The returned
    series marks ``k+period`` and carries the *level* that was set at *k*. At
    every bar *t*, the series reflects only information available at *t*.

    Args:
        high: High prices.
        low: Low prices (same index as ``high``).
        period: Bars on each side defining a swing and the confirmation lag.

    Returns:
        ``(swing_highs, swing_lows)``: float Series indexed like the inputs.
        Value at index ``k+period`` is the swing level ``high[k]`` / ``low[k]``
        from the occurrence bar; NaN everywhere else, including the last
        ``period`` bars (nothing can confirm there). Named
        ``confirmed_swing_high`` / ``confirmed_swing_low``.

    Strictness conventions are stated in the module docstring.
    """
    _validate_pair(high, low, period)

    # Left side: extremum of the `period` bars strictly before each bar.
    prior_max = high.rolling(window=period, min_periods=period).max().shift(1)
    prior_min = low.rolling(window=period, min_periods=period).min().shift(1)

    # Right side: extremum of the `period` bars strictly AFTER each bar.
    # `s[::-1].rolling(period).max()[::-1]` at label p is max(s[p .. p+period-1])
    # (a forward window starting at p), so shifting it left by one bar yields
    # max(s[k+1 .. k+period]) at label k. This is only ever used to decide the
    # mark stamped at k+period — a bar whose data all exists by then — so the
    # OUTPUT stays causal even though the intermediate is computed
    # right-to-left. Truncation invariance holds because the value stamped at
    # k+period depends only on bars [k-period, k+period]. The window is NaN
    # when fewer than `period` bars remain after k — exactly the tail rule.
    future_max = (
        high[::-1].rolling(window=period, min_periods=period).max()[::-1].shift(-1)
    )
    future_min = (
        low[::-1].rolling(window=period, min_periods=period).min()[::-1].shift(-1)
    )

    # NaN comparisons yield False, so warm-up bars and the tail never mark.
    is_swing_high = (high > prior_max) & (future_max <= high)
    is_swing_low = (low < prior_min) & (future_min >= low)

    # Carry the occurrence-bar level forward to the confirmation bar.
    swing_highs = high.where(is_swing_high).shift(period)
    swing_lows = low.where(is_swing_low).shift(period)

    swing_highs = swing_highs.rename("confirmed_swing_high")
    swing_lows = swing_lows.rename("confirmed_swing_low")
    return swing_highs, swing_lows


def zigzag_swings(
    high: pd.Series,
    low: pd.Series,
    depth: int = 5,
    deviation_pips: float = 0.0,
    backstep: int = 3,
    pip_value: float = 0.0001,
) -> pd.DataFrame:
    """Causal ZigZag: alternating confirmed pivots. Never repaints.

    Built directly on :func:`confirmed_swing_points` with ``period=depth``.
    Confirmed swing events are consumed in confirmation-bar order and appended
    to the output only at the bar where they become knowable, so recomputing on
    a truncated frame yields rows identical to the full-frame output up to the
    truncation. No pivot is ever revised after it appears.

    Algorithm (single forward pass over confirmation events):

    1. The first confirmed event of either kind becomes the first pivot
       unconditionally and fixes the direction we are ``seeking`` next
       (the opposite kind).
    2. An event of the ``seeking`` kind is accepted as the next pivot iff:
         - **deviation** — it moves at least ``deviation_pips * pip_value``
           away from the last pivot's level in the reversal direction (a new
           low at least that far *below* the last high, or a new high at least
           that far *above* the last low); and
         - **backstep** — its occurrence bar is at least ``backstep`` bars
           after the last pivot's occurrence bar.
       It is then stamped at its own confirmation bar. An event failing either
       check is skipped; ``seeking`` does not change.
    3. An event of the *same* kind as the last pivot is skipped. Classic
       ZigZag would *extend* the last leg to the more extreme point, but that
       revises an already-knowable pivot — repainting by the truncation
       definition — so this implementation enforces strict alternation
       instead.
    4. If both kinds confirm on the same bar, the event with the earlier
       occurrence bar is processed first; a full tie (an outside bar) breaks
       toward ``high`` first. Deterministic either way.

    Args:
        high: High prices.
        low: Low prices (same index as ``high``).
        depth: Swing definition / confirmation lag, forwarded as ``period``.
        deviation_pips: Minimum reversal size in pips. ``0.0`` accepts any
            confirmed reversal.
        backstep: Minimum bars between the occurrence bars of opposite pivots.
        pip_value: Price units per pip (e.g. 0.0001 for most FX pairs, 0.01
            for JPY pairs). A parameter, not a hardcoded pair convention, so
            the caller's instrument decides.

    Returns:
        DataFrame with columns ``confirm_time`` (the bar the pivot became
        knowable — index labels of the input), ``occur_time`` (the bar the
        pivot occurred on), ``kind`` (``"high"`` / ``"low"``), ``level`` (the
        price at the occurrence bar). One row per accepted pivot, ordered by
        ``confirm_time``. Empty input (or no confirmed swings) yields an empty
        frame with the same columns.
    """
    _validate_pair(high, low, depth)
    if isinstance(backstep, bool) or not isinstance(backstep, int) or backstep < 0:
        raise ValueError(f"backstep must be a non-negative int, got {backstep!r}")
    if not deviation_pips >= 0.0:
        raise ValueError(f"deviation_pips must be non-negative, got {deviation_pips!r}")
    if not pip_value > 0.0:
        raise ValueError(f"pip_value must be positive, got {pip_value!r}")

    columns = ["confirm_time", "occur_time", "kind", "level"]
    swing_highs, swing_lows = confirmed_swing_points(high, low, period=depth)
    index = high.index

    # Gather confirmation events as (confirm_pos, occur_pos, kind, level).
    events: List[Tuple[int, int, str, float]] = []
    high_values = swing_highs.to_numpy(dtype=float)
    low_values = swing_lows.to_numpy(dtype=float)
    for pos in np.flatnonzero(~np.isnan(high_values)):
        events.append((int(pos), int(pos) - depth, _KIND_HIGH, float(high_values[pos])))
    for pos in np.flatnonzero(~np.isnan(low_values)):
        events.append((int(pos), int(pos) - depth, _KIND_LOW, float(low_values[pos])))
    # Confirmation order; ties by occurrence order, then highs before lows.
    events.sort(key=lambda e: (e[0], e[1], 0 if e[2] == _KIND_HIGH else 1))

    if not events:
        return pd.DataFrame(
            {
                "confirm_time": pd.Series(dtype=index.dtype),
                "occur_time": pd.Series(dtype=index.dtype),
                "kind": pd.Series(dtype=object),
                "level": pd.Series(dtype=float),
            }
        )

    min_deviation = deviation_pips * pip_value

    confirm_times: List[object] = []
    occur_times: List[object] = []
    kinds: List[str] = []
    levels: List[float] = []

    seeking: str | None = None
    last_occur_pos = 0
    last_level = 0.0
    for confirm_pos, occur_pos, kind, level in events:
        if seeking is None:
            pass  # first pivot: accepted unconditionally below
        elif kind != seeking:
            continue  # same-kind extension would repaint; strict alternation
        else:
            if occur_pos - last_occur_pos < backstep:
                continue
            if seeking == _KIND_LOW:
                moved = last_level - level
            else:
                moved = level - last_level
            if moved < min_deviation:
                continue
        confirm_times.append(index[confirm_pos])
        occur_times.append(index[occur_pos])
        kinds.append(kind)
        levels.append(level)
        seeking = _KIND_LOW if kind == _KIND_HIGH else _KIND_HIGH
        last_occur_pos = occur_pos
        last_level = level

    return pd.DataFrame(
        {
            "confirm_time": pd.Series(confirm_times, dtype=index.dtype),
            "occur_time": pd.Series(occur_times, dtype=index.dtype),
            "kind": pd.Series(kinds, dtype=object),
            "level": pd.Series(levels, dtype=float),
        },
        columns=columns,
    )


def _last_n_confirmed(confirmed: pd.Series, n: int, period: int) -> pd.DataFrame:
    """Rolling last-n view over a confirmed-swing series.

    Row *t* holds the levels of the last *n* swings whose confirmation bar is
    ``<= t`` (``level_1`` most recent) and their occurrence-bar labels
    (``occur_1`` most recent). Built with a single forward pass, so row *t*
    depends only on events knowable at *t*.
    """
    index = confirmed.index
    values = confirmed.to_numpy(dtype=float)
    event_positions = np.flatnonzero(~np.isnan(values))
    event_levels = values[event_positions]
    n_events = len(event_positions)

    # The row state changes only at confirmation bars, so compute the last-n
    # window once per event (O(events * n)) and forward-fill the gaps —
    # avoids a per-bar Python loop on long frames.
    level_state = np.full((n_events, n), np.nan, dtype=float)
    occur_state: np.ndarray = np.empty((n_events, n), dtype=object)
    occur_state[:] = None
    occur_labels = np.asarray([index[int(p) - period] for p in event_positions])
    for i in range(n_events):
        lo = max(0, i - n + 1)
        k = i - lo + 1
        level_state[i, :k] = event_levels[lo : i + 1][::-1]
        occur_state[i, :k] = occur_labels[lo : i + 1][::-1]

    event_index = index[event_positions]
    data: dict[str, pd.Series] = {}
    for j in range(n):
        data[f"level_{j + 1}"] = (
            pd.Series(level_state[:, j], index=event_index).reindex(index).ffill()
        )
    is_datetime = isinstance(index, pd.DatetimeIndex)
    tz = index.tz if is_datetime else None
    for j in range(n):
        occur_values: object = list(occur_state[:, j])
        if is_datetime:
            # Convert before the forward-fill so the column is real datetime64
            # (NaT for unknown) rather than an object column of Timestamps.
            # An all-NaT conversion comes back naive; restore the input tz so
            # truncated frames and full frames carry identical dtypes.
            converted = pd.to_datetime(occur_values)
            if converted.tz is None and tz is not None:
                converted = converted.tz_localize(tz)
            occur_values = converted
        occur = pd.Series(occur_values, index=event_index).reindex(index).ffill()
        data[f"occur_{j + 1}"] = occur
    return pd.DataFrame(data, index=index)


def last_n_confirmed_highs(
    high: pd.Series, low: pd.Series, n: int, period: int = 5
) -> pd.DataFrame:
    """Rolling causal access to the last n confirmed swing highs.

    At each bar *t*: the levels of the last *n* swing highs KNOWABLE at *t*
    (confirmation bar ``<= t``). This is what "the second consecutive higher
    high" actually needs — compare ``level_1`` to ``level_2`` at bar *t*.

    Args:
        high: High prices.
        low: Low prices (same index; swing detection needs both for the
            mirrored sibling — kept in the signature for symmetry with
            :func:`confirmed_swing_points`).
        n: How many confirmed highs to carry (``>= 1``).
        period: Swing definition / confirmation lag.

    Returns:
        DataFrame indexed like the input with columns ``level_1 … level_n``
        (float, ``level_1`` = most recently confirmed, NaN until enough swings
        have confirmed) followed by ``occur_1 … occur_n`` (occurrence-bar
        index label of the corresponding swing; NaT/None until known). Row *t*
        never contains a level whose confirmation bar is after *t*.
    """
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError(f"n must be a positive int, got {n!r}")
    swing_highs, _ = confirmed_swing_points(high, low, period=period)
    return _last_n_confirmed(swing_highs, n, period)


def last_n_confirmed_lows(
    high: pd.Series, low: pd.Series, n: int, period: int = 5
) -> pd.DataFrame:
    """Mirror of :func:`last_n_confirmed_highs` for confirmed swing lows."""
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError(f"n must be a positive int, got {n!r}")
    _, swing_lows = confirmed_swing_points(high, low, period=period)
    return _last_n_confirmed(swing_lows, n, period)
