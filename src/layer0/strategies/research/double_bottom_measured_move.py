"""Double Bottom / Double Top — Measured Move — row 47 of forex_swing_strategies.csv.

Spec: task/2026-W32/fleet/upload/wave2/specs/SPEC-double_bottom_measured_move.md
Source: https://tradeciety.com/bottom-fishing-trading-how-to-find-reversals

D1-only pattern strategy (spec §2: ``context_granularities: none``). A
candidate is a classic W (long) or M (short) built entirely from causally
confirmed swing points (§3, §9):

* **A** — a confirmed swing low (long) / high (short), preceded by a decline
  / advance of >= 1.5x ATR14 over the ``DECLINE_LOOKBACK_BARS`` bars before
  it (§4 #1-2 / §5 #1-2).
* **C** — the FIRST confirmed swing high (long) / low (short) occurring
  after A, never re-picked (§4 #3 / §5 #3, the pattern-purity gate: exactly
  one confirmed swing of the opposite kind may occur between A and B).
  Height A-to-C must be >= 1.0x ATR14[C] (§4 #4 / §5 #4).
* **B** — the FIRST confirmed swing low (long) / high (short) occurring
  after C, never scanned forward for a "better" one (§4 #5 / §5 #5: "if this
  first post-C swing low fails the offset window, the pattern is dead").
  B must sit strictly beyond A and land in the 5-20% offset band of the
  A-C height (§4 #6 / §5 #6); price must never have dipped below A / risen
  above A' while the pattern formed (§4 #7 / §5 #7, formation integrity);
  and the whole A-to-B span must fit inside ``FORMATION_MAX_BARS`` bars
  (§4 #8 / §5 #8).

The setup activates at ``s = kB + SWING_PERIOD`` — B's own confirmation bar,
the first bar at which every pattern input (including B's own level) is
knowable (§9). From ``s`` it has ``TRIGGER_WINDOW_BARS`` closed bars to break
the C level on a strict close (§4 #9-11 / §5 #9-11); any completed bar since
activation that re-touches A first kills the setup outright, with no partial
credit and no re-scan. Entry is a market order at the close of the
qualifying bar (§4 #10 / §5 #10 — the literal source text, and the
later/more conservative of the two entry readings the spec discusses in
§10 #10).

Only ``causal_structure.confirmed_swing_points`` is used for structure —
never ``indicators.detect_swing_points``, which is centred (``center=True``)
and reads the future. Pattern geometry (the A/C/B levels, height, offset) is
private arithmetic per spec §3, not a shared indicator.

Stop = A -/+ 1 pip — the WIDER of the source's two stop readings (§6, §10
#13-14). Single take-profit leg at the 100% measured-move objective,
``2*C - A`` (§7, §10 #16). No breakeven, no trail (§6, §10 #15): the
source's post-fill stop management has no channel in this declarative
contract and is moot under a single leg placed at exactly the target.

**Pip size without a pair name** (the same interface gap documented in
``research/amazing_crossover.py`` and ``research/holy_grail_pullback.py``):
``generate_orders`` receives frames only, never the pair, so
``get_pip_value(metadata.pairs[0])`` would silently apply the EUR_USD pip
(0.0001) to USD_JPY trades too — and USD_JPY is one of this strategy's five
live pairs. ``_pip_size_from_price`` infers the quote convention from the
decision bar's own close instead, exactly as those two modules do.
"""

from __future__ import annotations

from typing import List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..causal_structure import confirmed_swing_points
from ..contract_v2 import (
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)
from ...data_access.indicators import atr, get_pip_value

# Same convention as amazing_crossover._pip_size_from_price /
# holy_grail_pullback._pip_size_from_price: every non-JPY pair this strategy
# declares trades well below this level; USD_JPY trades well above it.
_JPY_QUOTE_THRESHOLD = 20.0


def _pip_size_from_price(price: float) -> float:
    """Infer the pip size from a decision-bar close (see module docstring)."""
    pair = "USD_JPY" if price >= _JPY_QUOTE_THRESHOLD else "EUR_USD"
    return float(get_pip_value(pair))


def _occurrence_positions(confirmed: pd.Series, period: int) -> np.ndarray:
    """Occurrence-bar positions of every swing confirmed in ``confirmed``.

    ``confirmed_swing_points`` stamps a swing at its CONFIRMATION bar
    (occurrence + period) and carries the occurrence-bar level there, so the
    occurrence position is recovered by subtracting the constant lag.
    Positions come out sorted ascending because confirmation order matches
    occurrence order for a fixed lag.
    """
    values = confirmed.to_numpy(dtype=float)
    conf_pos = np.flatnonzero(~np.isnan(values))
    return conf_pos - period


def _find_double_bottoms(
    low: np.ndarray,
    high: np.ndarray,
    atr_values: np.ndarray,
    swing_low_occ: np.ndarray,
    swing_high_occ: np.ndarray,
    *,
    decline_lookback: int,
    decline_atr_mult: float,
    height_atr_mult: float,
    offset_min: float,
    offset_max: float,
    formation_max_bars: int,
    swing_period: int,
    n_bars: int,
) -> List[Tuple[int, int, int, int]]:
    """Spec §4 #1-8: every qualifying long setup as ``(kA, kC, kB, s)``.

    C is the FIRST confirmed swing high after A; B is the FIRST confirmed
    swing low after C. Neither is ever re-picked (§4 #4/#5 — "no scanning
    forward for a better B"); the purity, height, offset, integrity and
    formation-window gates are then checked once against that single
    deterministic choice.
    """
    patterns: List[Tuple[int, int, int, int]] = []
    for kA_pos in swing_low_occ:
        kA = int(kA_pos)
        if kA < decline_lookback:
            continue  # §4 #2 needs a full lookback window before A
        LA = float(low[kA])
        decline = float(np.max(high[kA - decline_lookback : kA])) - LA
        if not decline >= decline_atr_mult * atr_values[kA]:
            continue  # §4 #2 decline gate

        idx_c = int(np.searchsorted(swing_high_occ, kA, side="right"))
        if idx_c >= len(swing_high_occ):
            continue  # no confirmed swing high ever occurs after A
        kC = int(swing_high_occ[idx_c])

        idx_b = int(np.searchsorted(swing_low_occ, kC, side="right"))
        if idx_b >= len(swing_low_occ):
            continue  # no confirmed swing low ever occurs after C
        kB = int(swing_low_occ[idx_b])

        # §4 #3 purity: exactly one confirmed swing high in the OPEN interval
        # (kA, kB). idx_c is already the first index > kA; count up to kB.
        idx_b_high = int(np.searchsorted(swing_high_occ, kB, side="left"))
        if idx_b_high - idx_c != 1:
            continue

        LC = float(high[kC])
        H = LC - LA
        if H <= 0.0:
            continue  # degenerate geometry; also fails the height gate below
        if not H >= height_atr_mult * atr_values[kC]:
            continue  # §4 #4 minimum height

        LB = float(low[kB])
        if not LB > LA:
            continue  # §4 #6
        offset = (LB - LA) / H
        if not (offset_min <= offset <= offset_max):
            continue  # §4 #6 offset window

        if not float(np.min(low[kA + 1 : kB + 1])) >= LA:
            continue  # §4 #7 formation integrity

        if not (kB - kA) <= formation_max_bars:
            continue  # §4 #8 formation window

        s = kB + swing_period
        if s >= n_bars:
            continue  # the activation bar does not exist in this data
        patterns.append((kA, kC, kB, s))
    return patterns


def _find_double_tops(
    high: np.ndarray,
    low: np.ndarray,
    atr_values: np.ndarray,
    swing_high_occ: np.ndarray,
    swing_low_occ: np.ndarray,
    *,
    decline_lookback: int,
    decline_atr_mult: float,
    height_atr_mult: float,
    offset_min: float,
    offset_max: float,
    formation_max_bars: int,
    swing_period: int,
    n_bars: int,
) -> List[Tuple[int, int, int, int]]:
    """Spec §5 #1-8: the mirror of ``_find_double_bottoms`` for shorts."""
    patterns: List[Tuple[int, int, int, int]] = []
    for kA_pos in swing_high_occ:
        kA = int(kA_pos)
        if kA < decline_lookback:
            continue  # §5 #2
        LA = float(high[kA])
        advance = LA - float(np.min(low[kA - decline_lookback : kA]))
        if not advance >= decline_atr_mult * atr_values[kA]:
            continue  # §5 #2 advance gate

        idx_c = int(np.searchsorted(swing_low_occ, kA, side="right"))
        if idx_c >= len(swing_low_occ):
            continue  # no confirmed swing low ever occurs after A'
        kC = int(swing_low_occ[idx_c])

        idx_b = int(np.searchsorted(swing_high_occ, kC, side="right"))
        if idx_b >= len(swing_high_occ):
            continue  # no confirmed swing high ever occurs after C'
        kB = int(swing_high_occ[idx_b])

        # §5 #3 purity: exactly one confirmed swing low in (kA', kB').
        idx_b_low = int(np.searchsorted(swing_low_occ, kB, side="left"))
        if idx_b_low - idx_c != 1:
            continue

        LC = float(low[kC])
        H = LA - LC
        if H <= 0.0:
            continue
        if not H >= height_atr_mult * atr_values[kC]:
            continue  # §5 #4

        LB = float(high[kB])
        if not LB < LA:
            continue  # §5 #6
        offset = (LA - LB) / H
        if not (offset_min <= offset <= offset_max):
            continue  # §5 #6

        if not float(np.max(high[kA + 1 : kB + 1])) <= LA:
            continue  # §5 #7 formation integrity

        if not (kB - kA) <= formation_max_bars:
            continue  # §5 #8

        s = kB + swing_period
        if s >= n_bars:
            continue
        patterns.append((kA, kC, kB, s))
    return patterns


def _first_breakout_long(
    low: np.ndarray,
    close: np.ndarray,
    LA: float,
    LC: float,
    s: int,
    window: int,
    n_bars: int,
) -> Optional[int]:
    """Spec §4 #9-11: first bar with no invalidation and a strict close above
    C; ``None`` if the setup is cancelled or the trigger window elapses."""
    end = min(s + window, n_bars)
    for t in range(s, end):
        if low[t] < LA:
            return None  # §4 #9: invalidated since activation -- dead, no re-scan
        if close[t] > LC:
            return t  # §4 #10/#11: first qualifying close consumes the setup
    return None


def _first_breakdown_short(
    high: np.ndarray,
    close: np.ndarray,
    LA: float,
    LC: float,
    s: int,
    window: int,
    n_bars: int,
) -> Optional[int]:
    """Mirror of ``_first_breakout_long`` for §5 #9-11."""
    end = min(s + window, n_bars)
    for t in range(s, end):
        if high[t] > LA:
            return None
        if close[t] < LC:
            return t
    return None


class DoubleBottomMeasuredMove(StrategyV2):
    """W/M reversal pattern on D1, entered on the close-above/below-C breakout."""

    SWING_PERIOD = 5  # §3/§9: confirmed_swing_points period AND confirmation lag
    ATR_PERIOD = 14  # §3: Wilder-style ATR (indicators.atr's EWM approximation)
    DECLINE_LOOKBACK_BARS = 10  # §4 #2 / §5 #2: bars examined before A
    DECLINE_ATR_MULT = 1.5  # §4 #2 / §5 #2
    MIN_HEIGHT_ATR_MULT = 1.0  # §4 #4 / §5 #4
    OFFSET_MIN = 0.05  # §4 #6 / §5 #6
    OFFSET_MAX = 0.20  # §4 #6 / §5 #6
    FORMATION_MAX_BARS = 40  # §4 #8 / §5 #8
    TRIGGER_WINDOW_BARS = 20  # §4 trigger / §5 trigger window
    STOP_BUFFER_PIPS = 1.0  # §6

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="double_bottom_measured_move",
            name="Double Bottom / Top — Measured Move",
            version="0.1.0",
            author="wave2-fleet",
            hypothesis=(
                "A double bottom in which the second low holds meaningfully above "
                "the first — but not so far above that the market never really "
                "retested it — is the footprint of sellers failing twice at "
                "roughly the same level: the first flush found committed buyers, "
                "and the retest demonstrated that supply at that zone is "
                "exhausted rather than merely paused. When price then closes "
                "above the intervening reaction high, the last cohort of shorts "
                "is underwater and must cover while sidelined breakout buyers "
                "chase, producing a self-reinforcing repricing toward the "
                "measured-move objective (the pattern height projected upward — "
                "the distance bears forced price down, refunded). The edge "
                "should persist because it rests on a behavioural asymmetry "
                "(trapped sellers + failed retest = one-sided order flow at a "
                "known reference level) rather than on a fitted parameter, and "
                "because the 5-20% offset window specifically selects the "
                "retests that are shallow enough to show seller weakness yet "
                "deep enough to be a genuine test."
            ),
            granularities=["D1"],
            # §2 pairs_available, LIVE only. The eight Wave-1 "pending"
            # additions are deliberately excluded per the run brief ("never a
            # pair the spec lists as missing/pending"); AUD_CAD is the
            # declared genuine gap (DATA-GAP-double_bottom_measured_move.md).
            # See REPORT Uncertainties for the fleet-wide inconsistency on
            # this reading.
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="D1",
            context_granularities=(),  # §2: none
            simulate_on="H1",  # §2 / contract Part D
            source_row=47,
            source_url=(
                "https://tradeciety.com/bottom-fishing-trading-how-to-find-reversals"
            ),
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["confirmed_swing_points", "atr", "get_pip_value"]

    @property
    def warmup_bars(self) -> int:
        """A conservative floor, not a ceiling on when a pattern may complete.

        The fastest possible pattern needs ``DECLINE_LOOKBACK_BARS`` bars
        before A, then the tightest possible spacing to C and to B (one bar
        each), then B's own ``SWING_PERIOD`` confirmation lag to reach
        activation. Most real patterns take much longer (up to
        ``FORMATION_MAX_BARS`` + ``TRIGGER_WINDOW_BARS``) and fire long after
        this floor; it exists only so the look-ahead probe knows where
        indicators are first well-defined.
        """
        return self.DECLINE_LOOKBACK_BARS + 2 + self.SWING_PERIOD

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        d1 = frames[self.metadata.primary_granularity]
        high_s = d1["High"]
        low_s = d1["Low"]
        close_s = d1["Close"]

        high = high_s.to_numpy(dtype=float)
        low = low_s.to_numpy(dtype=float)
        close = close_s.to_numpy(dtype=float)
        index = d1.index
        n_bars = len(d1)

        atr_values = atr(high_s, low_s, close_s, period=self.ATR_PERIOD).to_numpy(
            dtype=float
        )

        # §3/§9: causal structure only -- never indicators.detect_swing_points.
        swing_highs_conf, swing_lows_conf = confirmed_swing_points(
            high_s, low_s, period=self.SWING_PERIOD
        )
        swing_high_occ = _occurrence_positions(swing_highs_conf, self.SWING_PERIOD)
        swing_low_occ = _occurrence_positions(swing_lows_conf, self.SWING_PERIOD)

        orders: List[OrderIntent] = []

        for kA, kC, _kB, s in _find_double_bottoms(
            low,
            high,
            atr_values,
            swing_low_occ,
            swing_high_occ,
            decline_lookback=self.DECLINE_LOOKBACK_BARS,
            decline_atr_mult=self.DECLINE_ATR_MULT,
            height_atr_mult=self.MIN_HEIGHT_ATR_MULT,
            offset_min=self.OFFSET_MIN,
            offset_max=self.OFFSET_MAX,
            formation_max_bars=self.FORMATION_MAX_BARS,
            swing_period=self.SWING_PERIOD,
            n_bars=n_bars,
        ):
            LA = float(low[kA])
            LC = float(high[kC])
            t = _first_breakout_long(
                low, close, LA, LC, s, self.TRIGGER_WINDOW_BARS, n_bars
            )
            if t is None:
                continue
            pip = _pip_size_from_price(float(close[t]))
            stop_price = LA - self.STOP_BUFFER_PIPS * pip  # §6
            tp_price = 2.0 * LC - LA  # §7: C + 1.00 x (C - A), the 100% target
            orders.append(
                OrderIntent(
                    decision_bar=index[t],
                    direction=1,
                    entry="market",  # §4: close-above-C market entry, §10 #10
                    entry_price=None,
                    decision_close=float(close[t]),
                    stop=StopRule(price=stop_price),  # §6: no breakeven, no trail
                    exits=[
                        ExitLeg(
                            fraction=1.0,
                            kind="take_profit",
                            price=tp_price,
                            label="TP1",
                        )
                    ],
                    expires_after_bars=None,  # §4: market order, no pending lifetime
                    tag="double_bottom_measured_move",
                    strategy_id=self.strategy_id,
                )
            )

        for kA, kC, _kB, s in _find_double_tops(
            high,
            low,
            atr_values,
            swing_high_occ,
            swing_low_occ,
            decline_lookback=self.DECLINE_LOOKBACK_BARS,
            decline_atr_mult=self.DECLINE_ATR_MULT,
            height_atr_mult=self.MIN_HEIGHT_ATR_MULT,
            offset_min=self.OFFSET_MIN,
            offset_max=self.OFFSET_MAX,
            formation_max_bars=self.FORMATION_MAX_BARS,
            swing_period=self.SWING_PERIOD,
            n_bars=n_bars,
        ):
            LA = float(high[kA])
            LC = float(low[kC])
            t = _first_breakdown_short(
                high, close, LA, LC, s, self.TRIGGER_WINDOW_BARS, n_bars
            )
            if t is None:
                continue
            pip = _pip_size_from_price(float(close[t]))
            stop_price = LA + self.STOP_BUFFER_PIPS * pip  # §6
            tp_price = 2.0 * LC - LA  # §7: C - 1.00 x (A - C), the 100% target
            orders.append(
                OrderIntent(
                    decision_bar=index[t],
                    direction=-1,
                    entry="market",
                    entry_price=None,
                    decision_close=float(close[t]),
                    stop=StopRule(price=stop_price),
                    exits=[
                        ExitLeg(
                            fraction=1.0,
                            kind="take_profit",
                            price=tp_price,
                            label="TP1",
                        )
                    ],
                    expires_after_bars=None,
                    tag="double_bottom_measured_move",
                    strategy_id=self.strategy_id,
                )
            )

        orders.sort(key=lambda o: o.decision_bar)
        return orders
