"""Position engine — resolves ``OrderIntent``\\s against bar data (spec §3, F1–F12).

Pure simulation: frames and orders in, trades out. No I/O, no database, no
mutable module state, deterministic. This is the v2 execution path that runs
alongside — never replaces — the incumbent T6 engine
(``src/layer0/core_engine/backtest_engine.py``, read-only).

Cost model (F10)
----------------
Read from ``BacktestConfig`` in ``backtest_engine.py`` — the single source of
the live cost model — via the module-level constant block below. The dynamic
import mirrors ``contract_v2._t6_slippage_pips``: the read-only incumbent file
carries a legacy implicit-Optional annotation the repo's mypy defaults flag,
and a static import would pull that pre-existing error into this module's
mypy report. The semantics replicated (file:line in backtest_engine.py):

- slippage is applied adverse-to-price on ENTRY (227-231) and on every exit
  fill EXCEPT end-of-data (358-363; the EOD path at 259-278 has no slippage);
- spread + commission hit dollar P&L only, NEVER the prices (119-123). This
  engine reports r-multiples only, so they are spread-free by construction;
  the values are echoed in ``EngineConfigEcho`` for reports.

Execution semantics (decisions binding on this module)
------------------------------------------------------
- F1/F2: a decision at the close of bar *t* fills a market intent at the OPEN
  of bar *t+1* plus direction-adverse slippage. T6 fills at close[t]. On a
  no-gap fixture (Open[t+1] == Close[t]) every fill is bit-identical to T6 —
  that fixture is the equivalence bridge. On gapped data the t -> t+1 shift
  is the deliberate, documented semantic change.
- §3.2 literal per-bar order (expire, stops, legs, breakeven/trailing at
  close, pending fills, admission). Consequence: a PENDING intent decided at
  t-1 is admitted at the END of bar t and first attempts a fill at bar t+1 —
  one bar stricter than F1's literal minimum (pessimistic, as written).
- New positions filled INTRABAR (pending fills, §3.2 step 5) are not
  stop-checked on their fill bar: the fill happened somewhere inside the bar
  and the intrabar sequence is unknowable. Positions filled at the OPEN
  (market intents, step 0) ARE checked on their fill bar — the entire bar's
  range is after an open fill, so there is no intrabar ambiguity, and this is
  exactly what reproduces T6's "first exit check the bar after entry" on the
  equivalence fixture.
- ``time_exit_after_bars`` counts from the DECISION bar and exits at that
  bar's close with adverse slippage — reproducing T6's ``max_bars_hold``
  (decision at t, time-exit at close[t+N] == T6's close[i+N] for entry bar i).
- ``close_on_opposite`` (market intents): an open opposite-direction position
  is closed at the fill bar's OPEN with adverse slippage (reason ``OPPOSITE``)
  before the new intent fills at the same open — T6's signal-reversal exit on
  the no-gap fixture. For PENDING intents ``close_on_opposite`` is not
  honoured: pendings are only admitted while there is capacity (§3.2 step 6
  "subject to F12") and are cancelled if a position is open when they trigger.
- The r-multiple risk denominator is the INITIAL stop
  (``OrderIntent.stop.price`` at admission), even after breakeven/trailing
  moves the working stop. T6's stop never moves; for v2 the initial risk is
  the honest R basis. Computed in exactly one place: ``realized_r_multiple``.
- The trade-level r_multiple is scaled by ``size_fraction`` (relative
  allocation of the idea, in units of R; default 1.0).

Supported exit-leg kinds
------------------------
- ``take_profit`` legs: ``price`` (absolute), ``atr_multiple`` (resolved
  relative to the FILL price using the last completed ATR before the fill
  bar), or ``pips`` (via ``get_pip_value(pair)``).
- ``time`` legs (fractional): fill at the close of the bar ``bars`` after the
  fill bar, with adverse slippage.
- Whole-position trailing, declared either as ``StopRule.trail_atr_multiple``
  (F9) or as a single ``ExitLeg(kind="trailing", fraction=1.0)`` carrying an
  ``atr_multiple`` or a fixed ``pips`` distance. The leg form exists because a
  "trail until stopped out" strategy has no take-profit to declare, yet the
  contract requires at least one exit leg summing to 1.0. When both forms are
  present the StopRule wins, so one mechanism described twice trails once.
  Breakeven via ``StopRule.move_to_breakeven_on`` (F8), full-remainder time
  exit via ``OrderIntent.time_exit_after_bars``.
- **Fractional** ``ExitLeg(kind="trailing")`` legs (``fraction < 1.0``) are
  still NOT supported — trailing only part of a position is unimplemented —
  and intents carrying one are rejected with ``TRAILING_LEG_UNSUPPORTED``.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..data_access.indicators import atr, get_pip_value
from .contract_v2 import ExitLeg, OrderIntent, StrategyV2
from .engine_adapter import ContractStrategyAdapter

__all__ = [
    "SPREAD_PIPS",
    "SLIPPAGE_PIPS",
    "COMMISSION_PER_TRADE",
    "realized_r_multiple",
    "RejectedOrder",
    "EngineConfigEcho",
    "BacktestResult",
    "PositionEngine",
]


def _t6_cost_model() -> Tuple[float, float, float]:
    """(spread_pips, slippage_pips, commission) from ``BacktestConfig``.

    Read from the single source at runtime; nothing is re-typed here. Dynamic
    import only for the mypy reason documented in the module docstring.
    """
    module = importlib.import_module("src.layer0.core_engine.backtest_engine")
    cfg = module.BacktestConfig()
    return (
        float(cfg.spread_pips),
        float(cfg.slippage_pips),
        float(cfg.commission_per_trade),
    )


# F10 cost model — the single module-level constant block, sourced from
# BacktestConfig (backtest_engine.py:36-46). Never hardcode these values.
SPREAD_PIPS, SLIPPAGE_PIPS, COMMISSION_PER_TRADE = _t6_cost_model()

# Trailing-stop ATR period: from the uniform T6 adapter, never hardcoded (F9).
ATR_PERIOD = ContractStrategyAdapter.ATR_PERIOD

_REMAINING_TOL = 1e-9


def realized_r_multiple(
    direction: int,
    entry_price: float,
    initial_stop_price: float,
    leg_fills: Sequence[Tuple[float, float]],
) -> float:
    """The single computation site for trade r-multiples (spec §3.3).

    ``r = Σ fraction · direction · (exit − entry) / |entry − initial_stop|``
    over ``leg_fills`` as ``(fraction, exit_price)`` pairs. EVERY exit path
    (stop, take-profit legs, trailing, time, opposite-close, end-of-data)
    funnels through here, so scale-out arithmetic cannot drift. The INITIAL
    stop is the risk denominator even after breakeven/trailing moves.

    For a single 100% leg this is bit-identical to T6's
    ``price_diff / abs(entry - stop_loss)`` (backtest_engine.py:276-280,
    370-380): the fraction/direction multiplications by ±1.0 are exact in
    IEEE arithmetic.
    """
    risk = abs(entry_price - initial_stop_price)
    if risk <= 0.0:
        raise ValueError("realized_r_multiple: zero initial risk")
    pnl = 0.0
    for fraction, exit_price in leg_fills:
        pnl += fraction * direction * (exit_price - entry_price)
    return pnl / risk


# ---------------------------------------------------------------------------
# Public result types (spec §3.3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RejectedOrder:
    """An intent the engine refused (or an unfilled pending that expired).

    ``reason`` is a stable machine-readable token, e.g.
    ``DISGUISED_INSTANT_FILL``, ``MAX_CONCURRENT_POSITIONS``, ``EXPIRED``.
    """

    intent: OrderIntent
    reason: str
    bar: Optional[pd.Timestamp]  # resolution bar at which the decision happened


@dataclass(frozen=True)
class EngineConfigEcho:
    """Config echo for reports (spec §3.3): cost model, concurrency, granularity."""

    pair: str
    granularity: str
    warmup_bars: int
    max_concurrent_positions: int
    spread_pips: float
    slippage_pips: float
    commission_per_trade: float
    pip_value: float
    atr_period: int
    bars: int
    eligibility: str  # how eligible fill bars were derived


TRADES_COLUMNS = [
    "trade_id",
    "strategy_id",
    "tag",
    "pair",
    "direction",
    "decision_time",
    "entry_time",
    "entry_price",
    "initial_stop_price",
    "final_stop_price",
    "exit_time",
    "exit_price",
    "exit_reason",
    "r_multiple",
    "legs_filled",
    "max_adverse_excursion",
    "max_favourable_excursion",
    "bars_held",
    "gapped",
]

LEG_FILLS_COLUMNS = [
    "trade_id",
    "label",
    "kind",
    "fill_time",
    "fill_price",
    "fraction",
    "gapped",
    "slippage_applied",
]

STOP_HISTORY_COLUMNS = ["trade_id", "bar_time", "stop_price", "reason"]


@dataclass
class BacktestResult:
    """Engine output (spec §3.3).

    - ``trades``: one row per round-trip, columns ``TRADES_COLUMNS``.
      ``exit_price`` is the fraction-weighted average fill price across all
      exit fills (exactly consistent with ``r_multiple``); ``exit_reason`` is
      the reason of the FINAL fill: ``STOP``, ``TAKE_PROFIT``, ``TIME``,
      ``OPPOSITE`` or ``END_OF_DATA``. ``legs_filled`` counts declared
      ``ExitLeg`` fills (take_profit/time), not stop/EOD/OPPOSITE remainder
      closes. Excursions are in R, direction-aware, from bar high/low vs the
      entry fill, fill bar through exit bar inclusive (the fill bar of an
      intrabar pending fill is included — pessimistic). ``bars_held`` counts
      resolution bars from fill to exit. ``gapped`` marks any fill resolved
      at a bar open because the market gapped through its level (F3/F6).
    - ``leg_fills``: one row per individual exit execution (leg-level detail).
    - ``stop_history``: initial stop and every breakeven/trailing move, per
      trade. Stops never widen — this frame is the evidence.
    - ``rejected_orders`` / ``expired_orders``: intents the engine refused,
      and pendings cancelled by F4/end-of-data, each with a reason.
    - ``end_of_data_open``: count of positions force-closed at the final bar
      (F11); folds ending with many of these are suspect.
    - ``config``: cost model, concurrency, granularity echo.
    """

    trades: pd.DataFrame
    leg_fills: pd.DataFrame
    stop_history: pd.DataFrame
    rejected_orders: List[RejectedOrder]
    expired_orders: List[RejectedOrder]
    end_of_data_open: int
    config: EngineConfigEcho

    @property
    def end_of_data_flag(self) -> bool:
        """F11 flag: any position was still open at the final bar."""
        return self.end_of_data_open > 0


# ---------------------------------------------------------------------------
# Internal simulation state
# ---------------------------------------------------------------------------


@dataclass
class _LegState:
    """A declared ExitLeg resolved against the actual fill, plus its state."""

    leg: ExitLeg
    level: Optional[float]  # take_profit: the absolute trigger level
    time_bar: Optional[int]  # time leg: resolution bar index of the exit
    filled: bool = False


@dataclass
class _Position:
    """Mutable state of one open trade (created at fill, closed at exit)."""

    trade_id: int
    intent: OrderIntent
    direction: int
    entry_price: float
    fill_bar: int
    checks_from: int  # open fills: fill_bar; intrabar fills: fill_bar + 1
    decision_idx: int
    initial_stop: float
    stop: float
    time_exit_bar: Optional[int]
    legs: List[_LegState]
    pair: str
    remaining: float = 1.0
    legs_filled: int = 0
    gapped: bool = False
    max_high: float = 0.0
    min_low: float = 0.0
    breakeven_armed_bar: Optional[int] = None
    open_: bool = True
    # fills as (fraction, price, label, kind, bar_idx, gapped, slippage_applied)
    fills: List[Tuple[float, float, str, str, int, bool, bool]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.fills is None:
            self.fills = []


@dataclass
class _Pending:
    """An admitted, unfilled pending order."""

    intent: OrderIntent
    admitted_bar: int
    deadline: Optional[int]  # last bar index it may fill on; None = GTC


class PositionEngine:
    """Resolves OrderIntents against a resolution frame under F1–F12 / §3.2.

    Stateless across calls: every run is fully determined by its arguments.
    """

    def run(
        self,
        resolution_df: pd.DataFrame,
        intents: Sequence[OrderIntent],
        *,
        pair: str,
        warmup_bars: int = 0,
        max_concurrent_positions: Optional[int] = None,
        strategy: Optional[StrategyV2] = None,
        eligibility_fn: Optional[
            Callable[[OrderIntent], Optional[pd.Timestamp]]
        ] = None,
        granularity: str = "",
    ) -> BacktestResult:
        """Simulate ``intents`` on ``resolution_df`` and return a BacktestResult.

        Args:
            resolution_df: OHLC frame the fills are RESOLVED against (native
                or H1 bars, spec §5). Needs a sorted, unique DatetimeIndex and
                Open/High/Low/Close columns.
            intents: declared trade plans, processed in the order given (with
                concurrency 1 the first fillable intent of a bar wins).
            pair: instrument, for pip value (slippage, pips legs, breakeven).
            warmup_bars: intents decided before this bar position are rejected
                (``WARMUP``). The frame itself is NOT sliced — trailing-ewm
                ATR stays path-identical to T6, which computes indicators
                before slicing.
            max_concurrent_positions: F12 cap. Resolution order: this
                parameter, else ``strategy.max_concurrent_positions``, else 1.
            strategy: optional StrategyV2 the intents came from (supplies the
                F12 cap when the parameter is not given).
            eligibility_fn: optional hook for H1-resolution runs (spec §5):
                maps an intent to the earliest timestamp at which it may fill;
                the eligible bar is the first resolution bar at or after that
                timestamp (never earlier than decision_bar + 1). Default None:
                the first bar strictly after the decision bar — correct for
                native-resolution runs. The H1 harness passes a function
                returning ``decision_bar + native interval``.
            granularity: label echoed in the config (reporting only).
        """
        _validate_frame(resolution_df)
        df = resolution_df
        n = len(df)
        index = df.index
        opens = df["Open"].to_numpy(dtype=float)
        highs = df["High"].to_numpy(dtype=float)
        lows = df["Low"].to_numpy(dtype=float)
        closes = df["Close"].to_numpy(dtype=float)
        atr_values = atr(
            df["High"], df["Low"], df["Close"], period=ATR_PERIOD
        ).to_numpy(dtype=float)

        pip = float(get_pip_value(pair))
        slip = SLIPPAGE_PIPS * pip
        max_pos = _resolve_max_concurrent(max_concurrent_positions, strategy)
        pos_of: Dict[pd.Timestamp, int] = {ts: i for i, ts in enumerate(index)}

        rejected: List[RejectedOrder] = []
        expired: List[RejectedOrder] = []
        trade_rows: List[Dict[str, object]] = []
        leg_rows: List[Dict[str, object]] = []
        stop_rows: List[Dict[str, object]] = []

        # Classification: eligible bar per intent; unsupported/rejected early.
        markets_at: Dict[int, List[OrderIntent]] = {}
        pendings_at: Dict[int, List[OrderIntent]] = {}
        for intent in intents:
            eligible = self._eligible_bar(
                intent, pos_of, n, warmup_bars, eligibility_fn, index, rejected
            )
            if eligible is None:
                continue
            if any(
                leg.kind == "trailing" and leg.fraction < 1.0 for leg in intent.exits
            ):
                rejected.append(
                    RejectedOrder(
                        intent,
                        "TRAILING_LEG_UNSUPPORTED: FRACTIONAL trailing legs are "
                        "not supported (trailing only part of a position). Use a "
                        "whole-position trail: either StopRule.trail_atr_multiple "
                        "or a single ExitLeg(kind='trailing', fraction=1.0)",
                        index[eligible],
                    )
                )
                continue
            if intent.entry == "market":
                markets_at.setdefault(eligible, []).append(intent)
            else:
                pendings_at.setdefault(eligible, []).append(intent)

        positions: List[_Position] = []
        pendings: List[_Pending] = []
        next_trade_id = 0
        eod_open = 0

        for t in range(n):
            # -- step 0 (F1/F2): market fills at the OPEN of bar t ----------
            for intent in markets_at.get(t, ()):
                decision_idx = pos_of[intent.decision_bar]
                fill = opens[t] + intent.direction * slip
                if not _stop_geometry_ok(intent.direction, fill, intent.stop.price):
                    rejected.append(
                        RejectedOrder(
                            intent,
                            "INVALID_STOP_AT_FILL: stop not on the correct "
                            "side of the fill price (zero/negative risk)",
                            index[t],
                        )
                    )
                    continue
                if len(positions) >= max_pos:
                    opposite = [p for p in positions if p.direction != intent.direction]
                    if opposite and intent.close_on_opposite:
                        for pos in opposite:
                            self._close_remainder(
                                pos,
                                opens[t] - pos.direction * slip,
                                "OPPOSITE",
                                "opposite",
                                t,
                                False,
                                index,
                                leg_rows,
                                trade_rows,
                            )
                        positions = [p for p in positions if p.open_]
                    if len(positions) >= max_pos:
                        rejected.append(
                            RejectedOrder(
                                intent,
                                "MAX_CONCURRENT_POSITIONS: position open at "
                                "the eligible bar (F12)",
                                index[t],
                            )
                        )
                        continue
                pos = self._open_position(
                    next_trade_id,
                    intent,
                    fill,
                    t,
                    t,
                    decision_idx,
                    atr_values,
                    pip,
                    pair,
                    index,
                    stop_rows,
                )
                next_trade_id += 1
                positions.append(pos)
                pos.max_high = highs[t]
                pos.min_low = lows[t]

            # -- excursion update for positions carried into bar t ----------
            for pos in positions:
                if pos.fill_bar < t:
                    pos.max_high = max(pos.max_high, highs[t])
                    pos.min_low = min(pos.min_low, lows[t])

            # -- step 1 (F4): expire pendings past their lifetime -----------
            still: List[_Pending] = []
            for pend in pendings:
                if pend.deadline is not None and pend.deadline < t:
                    expired.append(RejectedOrder(pend.intent, "EXPIRED", index[t]))
                else:
                    still.append(pend)
            pendings = still

            # -- step 2 (F5/F6): stops, before targets, always --------------
            for pos in positions:
                if pos.open_ and pos.checks_from <= t:
                    self._check_stop(
                        pos, t, opens, lows, highs, slip, index, leg_rows, trade_rows
                    )
            positions = [p for p in positions if p.open_]

            # -- step 3 (F7): exit legs, nearest first; then time exits -----
            for pos in positions:
                if pos.open_ and pos.checks_from <= t:
                    self._check_exit_legs(
                        pos, t, highs, lows, closes, slip, index, leg_rows, trade_rows
                    )
            positions = [p for p in positions if p.open_]

            # -- step 4 (F8/F9): breakeven / trailing at bar t's close ------
            for pos in positions:
                self._update_stop(pos, t, closes, atr_values, pip, index, stop_rows)

            # -- step 5 (F3): pending fills ---------------------------------
            remaining_pendings: List[_Pending] = []
            for pend in pendings:
                if len(positions) >= max_pos:
                    expired.append(
                        RejectedOrder(
                            pend.intent,
                            "MAX_CONCURRENT_POSITIONS_AT_FILL: position open "
                            "when the pending triggered; cancelled (F12)",
                            index[t],
                        )
                    )
                    continue
                filled = self._try_pending_fill(
                    pend,
                    t,
                    opens,
                    highs,
                    lows,
                    slip,
                    atr_values,
                    pip,
                    pair,
                    index,
                    next_trade_id,
                    pos_of,
                    positions,
                    stop_rows,
                    leg_rows,
                    rejected,
                )
                if filled:
                    next_trade_id += 1
                else:
                    remaining_pendings.append(pend)
            pendings = remaining_pendings

            # -- step 6 (F1): admit pendings whose eligible bar is t --------
            for intent in pendings_at.get(t, ()):
                if len(positions) >= max_pos:
                    rejected.append(
                        RejectedOrder(
                            intent,
                            "MAX_CONCURRENT_POSITIONS: admission subject to "
                            "F12 (spec §3.2 step 6)",
                            index[t],
                        )
                    )
                    continue
                reason = self._revalidate_pending(intent, pos_of, closes)
                if reason is not None:
                    rejected.append(RejectedOrder(intent, reason, index[t]))
                    continue
                deadline = (
                    None
                    if intent.expires_after_bars is None
                    else t + intent.expires_after_bars
                )
                pendings.append(
                    _Pending(intent=intent, admitted_bar=t, deadline=deadline)
                )

        # -- F11: end of data -----------------------------------------------
        last = n - 1
        for pos in positions:
            self._close_remainder(
                pos,
                closes[last],
                "END_OF_DATA",
                "end_of_data",
                last,
                False,
                index,
                leg_rows,
                trade_rows,
                slippage_applied=False,
            )
            eod_open += 1
        for pend in pendings:
            expired.append(
                RejectedOrder(pend.intent, "UNFILLED_AT_END_OF_DATA", index[last])
            )

        config = EngineConfigEcho(
            pair=pair,
            granularity=granularity,
            warmup_bars=warmup_bars,
            max_concurrent_positions=max_pos,
            spread_pips=SPREAD_PIPS,
            slippage_pips=SLIPPAGE_PIPS,
            commission_per_trade=COMMISSION_PER_TRADE,
            pip_value=pip,
            atr_period=ATR_PERIOD,
            bars=n,
            eligibility=(
                "first bar strictly after decision_bar (default)"
                if eligibility_fn is None
                else "first resolution bar >= eligibility_fn(intent)"
            ),
        )
        return BacktestResult(
            trades=_frame_from_rows(trade_rows, TRADES_COLUMNS),
            leg_fills=_frame_from_rows(leg_rows, LEG_FILLS_COLUMNS),
            stop_history=_frame_from_rows(stop_rows, STOP_HISTORY_COLUMNS),
            rejected_orders=rejected,
            expired_orders=expired,
            end_of_data_open=eod_open,
            config=config,
        )

    # -- internal helpers ----------------------------------------------------

    def _eligible_bar(
        self,
        intent: OrderIntent,
        pos_of: Dict[pd.Timestamp, int],
        n: int,
        warmup_bars: int,
        eligibility_fn: Optional[Callable[[OrderIntent], Optional[pd.Timestamp]]],
        index: pd.DatetimeIndex,
        rejected: List[RejectedOrder],
    ) -> Optional[int]:
        """First resolution bar at which this intent may act (F1).

        Default: the bar strictly after the decision bar. With
        ``eligibility_fn``: the first bar at or after the returned timestamp,
        never earlier than decision_bar + 1. None return = rejected.
        """
        decision_idx = pos_of.get(intent.decision_bar)
        if decision_idx is None:
            rejected.append(
                RejectedOrder(
                    intent,
                    "DECISION_BAR_NOT_IN_FRAME: decision_bar is not a bar of "
                    "the resolution frame",
                    None,
                )
            )
            return None
        if decision_idx < warmup_bars:
            rejected.append(
                RejectedOrder(intent, "WARMUP: decided before warmup_bars", None)
            )
            return None
        eligible = decision_idx + 1
        if eligibility_fn is not None:
            ts = eligibility_fn(intent)
            if ts is not None:
                eligible = max(eligible, int(index.searchsorted(ts, side="left")))
        if eligible >= n:
            rejected.append(
                RejectedOrder(
                    intent,
                    "NO_ELIGIBLE_BAR: no resolution bar at/after eligibility "
                    "(decision on the final bar)",
                    None,
                )
            )
            return None
        return eligible

    def _revalidate_pending(
        self,
        intent: OrderIntent,
        pos_of: Dict[pd.Timestamp, int],
        closes: np.ndarray,
    ) -> Optional[str]:
        """Admission re-validation (attack #5): a pending must not be through
        the market at its decision bar — that is an instant fill disguised as
        a pending order. Checked against ``decision_close`` when the intent
        carries one, else the frame's actual close at the decision bar. The
        dataclass already performs this check when both fields are present;
        this is the engine-side backstop for intents built without market
        context. Returns a rejection reason or None."""
        ref = intent.decision_close
        if ref is None:
            ref = float(closes[pos_of[intent.decision_bar]])
        level = intent.entry_price
        assert level is not None  # pending entries always carry one (contract)
        ok = {
            "buy_stop": level > ref,
            "sell_stop": level < ref,
            "buy_limit": level < ref,
            "sell_limit": level > ref,
        }[intent.entry]
        if not ok:
            return (
                f"DISGUISED_INSTANT_FILL: {intent.entry} at {level} is "
                f"through the decision-bar close {ref}"
            )
        return None

    def _open_position(
        self,
        trade_id: int,
        intent: OrderIntent,
        fill: float,
        fill_bar: int,
        checks_from: int,
        decision_idx: int,
        atr_values: np.ndarray,
        pip: float,
        pair: str,
        index: pd.DatetimeIndex,
        stop_rows: List[Dict[str, object]],
    ) -> _Position:
        """Create position state: resolve legs against the fill, record stop."""
        legs: List[_LegState] = []
        atr_ref = float(atr_values[fill_bar - 1])  # fill_bar >= 1 (F1)
        for leg in intent.exits:
            level: Optional[float] = None
            time_bar: Optional[int] = None
            if leg.kind == "take_profit":
                if leg.price is not None:
                    level = leg.price
                elif leg.atr_multiple is not None:
                    # Resolved relative to the FILL price with the last ATR
                    # completed before the fill bar (module docstring).
                    level = fill + intent.direction * leg.atr_multiple * atr_ref
                else:
                    assert leg.pips is not None
                    level = fill + intent.direction * leg.pips * pip
            elif leg.kind == "time":
                assert leg.bars is not None
                time_bar = fill_bar + leg.bars
            legs.append(_LegState(leg=leg, level=level, time_bar=time_bar))
        time_exit_bar = (
            None
            if intent.time_exit_after_bars is None
            else decision_idx + intent.time_exit_after_bars
        )
        stop_rows.append(
            {
                "trade_id": trade_id,
                "bar_time": index[fill_bar],
                "stop_price": intent.stop.price,
                "reason": "initial",
            }
        )
        return _Position(
            trade_id=trade_id,
            intent=intent,
            direction=intent.direction,
            entry_price=fill,
            fill_bar=fill_bar,
            checks_from=checks_from,
            decision_idx=decision_idx,
            initial_stop=intent.stop.price,
            stop=intent.stop.price,
            time_exit_bar=time_exit_bar,
            legs=legs,
            pair=pair,
            max_high=float("-inf"),
            min_low=float("inf"),
        )

    def _record_fill(
        self,
        pos: _Position,
        fraction: float,
        price: float,
        label: str,
        kind: str,
        bar: int,
        gapped: bool,
        index: pd.DatetimeIndex,
        leg_rows: List[Dict[str, object]],
        slippage_applied: bool = True,
    ) -> None:
        pos.fills.append((fraction, price, label, kind, bar, gapped, slippage_applied))
        pos.remaining -= fraction
        if gapped:
            pos.gapped = True
        leg_rows.append(
            {
                "trade_id": pos.trade_id,
                "label": label,
                "kind": kind,
                "fill_time": index[bar],
                "fill_price": price,
                "fraction": fraction,
                "gapped": gapped,
                "slippage_applied": slippage_applied,
            }
        )

    def _maybe_finalize(
        self,
        pos: _Position,
        index: pd.DatetimeIndex,
        trade_rows: List[Dict[str, object]],
    ) -> None:
        """Close out the trade row once the whole position has filled out."""
        if pos.remaining > _REMAINING_TOL:
            return
        pos.open_ = False
        last_fill = pos.fills[-1]
        exit_bar = last_fill[4]
        risk = abs(pos.entry_price - pos.initial_stop)
        r = realized_r_multiple(
            pos.direction,
            pos.entry_price,
            pos.initial_stop,
            [(f, p) for f, p, *_ in pos.fills],
        )
        r *= pos.intent.size_fraction
        total_fraction = sum(f for f, *_ in pos.fills)
        avg_exit = sum(f * p for f, p, *_ in pos.fills) / total_fraction
        reason = {
            "take_profit": "TAKE_PROFIT",
            "time_leg": "TIME",
            "time": "TIME",
            "stop": "STOP",
            "opposite": "OPPOSITE",
            "end_of_data": "END_OF_DATA",
        }[last_fill[3]]
        if pos.direction == 1:
            mfe = (pos.max_high - pos.entry_price) / risk
            mae = (pos.entry_price - pos.min_low) / risk
        else:
            mfe = (pos.entry_price - pos.min_low) / risk
            mae = (pos.max_high - pos.entry_price) / risk
        trade_rows.append(
            {
                "trade_id": pos.trade_id,
                "strategy_id": pos.intent.strategy_id,
                "tag": pos.intent.tag,
                "pair": pos.pair,
                "direction": pos.direction,
                "decision_time": pos.intent.decision_bar,
                "entry_time": index[pos.fill_bar],
                "entry_price": pos.entry_price,
                "initial_stop_price": pos.initial_stop,
                "final_stop_price": pos.stop,
                "exit_time": index[exit_bar],
                "exit_price": avg_exit,
                "exit_reason": reason,
                "r_multiple": r,
                "legs_filled": pos.legs_filled,
                "max_adverse_excursion": mae,
                "max_favourable_excursion": mfe,
                "bars_held": exit_bar - pos.fill_bar,
                "gapped": pos.gapped,
            }
        )

    def _close_remainder(
        self,
        pos: _Position,
        price: float,
        label: str,
        kind: str,
        bar: int,
        gapped: bool,
        index: pd.DatetimeIndex,
        leg_rows: List[Dict[str, object]],
        trade_rows: List[Dict[str, object]],
        slippage_applied: bool = True,
    ) -> None:
        """Close ALL remaining fraction (F5: a stop closes everything)."""
        self._record_fill(
            pos,
            pos.remaining,
            price,
            label,
            kind,
            bar,
            gapped,
            index,
            leg_rows,
            slippage_applied=slippage_applied,
        )
        self._maybe_finalize(pos, index, trade_rows)

    def _check_stop(
        self,
        pos: _Position,
        t: int,
        opens: np.ndarray,
        lows: np.ndarray,
        highs: np.ndarray,
        slip: float,
        index: pd.DatetimeIndex,
        leg_rows: List[Dict[str, object]],
        trade_rows: List[Dict[str, object]],
    ) -> None:
        """F5/F6: stop before target; a bar covering stop and TP fills the
        stop only, closing ALL remaining fraction. Gap through stop fills at
        the open (losses can exceed 1R) and marks the trade ``gapped``."""
        hit = (pos.direction == 1 and lows[t] <= pos.stop) or (
            pos.direction == -1 and highs[t] >= pos.stop
        )
        if not hit:
            return
        gapped = (pos.direction == 1 and opens[t] < pos.stop) or (
            pos.direction == -1 and opens[t] > pos.stop
        )
        level = opens[t] if gapped else pos.stop
        # T6 fills at the stop level even when gapped; the engine fills at
        # the open (F6, pessimistic). On the no-gap equivalence fixture a gap
        # through the stop is impossible for a surviving position, so the two
        # paths never diverge there.
        self._close_remainder(
            pos,
            level - pos.direction * slip,
            "STOP",
            "stop",
            t,
            gapped,
            index,
            leg_rows,
            trade_rows,
        )

    def _check_exit_legs(
        self,
        pos: _Position,
        t: int,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        slip: float,
        index: pd.DatetimeIndex,
        leg_rows: List[Dict[str, object]],
        trade_rows: List[Dict[str, object]],
    ) -> None:
        """F7: take-profit legs, ascending distance from entry, each at its
        own level; then fractional time legs; then the full-remainder time
        exit (``time_exit_after_bars`` from the decision bar, at close). This
        mirrors T6's stop -> take-profit -> time-stop order."""
        tp_legs = [
            leg for leg in pos.legs if not leg.filled and leg.leg.kind == "take_profit"
        ]
        # Nearest to entry first, in the direction of the trade.
        tp_legs.sort(key=lambda leg: pos.direction * (leg.level or 0.0))
        for leg_state in tp_legs:
            level = leg_state.level
            assert level is not None
            touched = (pos.direction == 1 and highs[t] >= level) or (
                pos.direction == -1 and lows[t] <= level
            )
            if not touched:
                continue
            leg_state.filled = True
            pos.legs_filled += 1
            self._record_fill(
                pos,
                leg_state.leg.fraction,
                level - pos.direction * slip,
                leg_state.leg.label,
                "take_profit",
                t,
                False,
                index,
                leg_rows,
            )
            if leg_state.leg.label == pos.intent.stop.move_to_breakeven_on:
                pos.breakeven_armed_bar = t
            self._maybe_finalize(pos, index, trade_rows)
            if not pos.open_:
                return
        # Fractional time legs: fill at the close of the bar `bars` after the
        # fill bar, adverse slippage (T6's time-stop exit applies slippage).
        for leg_state in pos.legs:
            if leg_state.filled or leg_state.leg.kind != "time":
                continue
            assert leg_state.time_bar is not None
            if t < leg_state.time_bar:
                continue
            leg_state.filled = True
            pos.legs_filled += 1
            self._record_fill(
                pos,
                leg_state.leg.fraction,
                closes[t] - pos.direction * slip,
                leg_state.leg.label,
                "time_leg",
                t,
                False,
                index,
                leg_rows,
            )
            self._maybe_finalize(pos, index, trade_rows)
            if not pos.open_:
                return
        # Full-remainder time exit from the DECISION bar (T6 max_bars_hold).
        if pos.time_exit_bar is not None and t >= pos.time_exit_bar:
            self._close_remainder(
                pos,
                closes[t] - pos.direction * slip,
                "TIME",
                "time",
                t,
                False,
                index,
                leg_rows,
                trade_rows,
            )

    def _update_stop(
        self,
        pos: _Position,
        t: int,
        closes: np.ndarray,
        atr_values: np.ndarray,
        pip: float,
        index: pd.DatetimeIndex,
        stop_rows: List[Dict[str, object]],
    ) -> None:
        """F8/F9: breakeven and trailing updates at bar t's CLOSE.

        F8: when the leg named by ``move_to_breakeven_on`` filled on THIS bar,
        the stop moves now — at the close, after this bar's stop/leg checks —
        so the protection arrives one check late (attack #12: never before
        the triggering leg fills).
        F9: trailing candidate = close ∓ trail_atr_multiple · ATR[t] (that
        bar's completed ATR). Both moves are favourable-only by construction
        (max for longs, min for shorts): a stop can never widen.
        """
        rule = pos.intent.stop
        if rule.move_to_breakeven_on is not None and pos.breakeven_armed_bar == t:
            candidate = pos.entry_price + pos.direction * (
                rule.breakeven_offset_pips * pip
            )
            improved = (pos.direction == 1 and candidate > pos.stop) or (
                pos.direction == -1 and candidate < pos.stop
            )
            if improved:
                pos.stop = candidate
                stop_rows.append(
                    {
                        "trade_id": pos.trade_id,
                        "bar_time": index[t],
                        "stop_price": pos.stop,
                        "reason": "breakeven",
                    }
                )
        # F9 trail distance. ``StopRule.trail_atr_multiple`` is the primary
        # declaration; a single whole-position ``ExitLeg(kind="trailing",
        # fraction=1.0)`` is the equivalent expression for strategies whose only
        # exit IS the trail (there is no take-profit to declare, and the contract
        # requires at least one leg). The StopRule wins when both are present, so
        # a strategy that declares both — as several specs do, describing one
        # mechanism twice — trails once, not twice.
        trail_mult = rule.trail_atr_multiple
        trail_pips: Optional[float] = None
        if trail_mult is None:
            for leg in pos.intent.exits:
                if leg.kind != "trailing":
                    continue
                if leg.atr_multiple is not None:
                    trail_mult = leg.atr_multiple
                elif leg.pips is not None:
                    trail_pips = leg.pips
                break

        trail_candidate: Optional[float] = None
        if trail_mult is not None:
            atr_t = float(atr_values[t])
            if not np.isnan(atr_t):
                trail_candidate = closes[t] - pos.direction * (trail_mult * atr_t)
        elif trail_pips is not None:
            # A fixed-distance trail: an ATR multiple cannot express "R pips
            # behind the extreme", which is what several sources actually state.
            trail_candidate = closes[t] - pos.direction * (trail_pips * pip)

        if trail_candidate is not None:
            improved = (pos.direction == 1 and trail_candidate > pos.stop) or (
                pos.direction == -1 and trail_candidate < pos.stop
            )
            if improved:
                pos.stop = trail_candidate
                stop_rows.append(
                    {
                        "trade_id": pos.trade_id,
                        "bar_time": index[t],
                        "stop_price": pos.stop,
                        "reason": "trailing",
                    }
                )

    def _try_pending_fill(
        self,
        pend: _Pending,
        t: int,
        opens: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        slip: float,
        atr_values: np.ndarray,
        pip: float,
        pair: str,
        index: pd.DatetimeIndex,
        trade_id: int,
        pos_of: Dict[pd.Timestamp, int],
        positions: List[_Position],
        stop_rows: List[Dict[str, object]],
        leg_rows: List[Dict[str, object]],
        rejected: List[RejectedOrder],
    ) -> bool:
        """F3: stop entries fill at max(L, open)/min(L, open) — a gap through
        L fills at the open, which is worse; limits fill at L exactly (no
        price improvement). Adverse slippage applies to every entry (F10).
        Intrabar fills are not stop-checked on their fill bar (checks start
        next bar): the within-bar sequence is unknowable."""
        intent = pend.intent
        level = intent.entry_price
        assert level is not None
        fill: Optional[float] = None
        gapped = False
        if intent.entry == "buy_stop" and highs[t] >= level:
            fill = max(level, opens[t])
            gapped = opens[t] > level
        elif intent.entry == "sell_stop" and lows[t] <= level:
            fill = min(level, opens[t])
            gapped = opens[t] < level
        elif intent.entry == "buy_limit" and lows[t] <= level:
            fill = level
        elif intent.entry == "sell_limit" and highs[t] >= level:
            fill = level
        if fill is None:
            return False
        fill += intent.direction * slip
        if not _stop_geometry_ok(intent.direction, fill, intent.stop.price):
            rejected.append(
                RejectedOrder(
                    intent,
                    "INVALID_STOP_AT_FILL: stop not on the correct side of "
                    "the fill price (zero/negative risk)",
                    index[t],
                )
            )
            return True  # triggered but unfillable: consumed, not retried
        decision_idx = pos_of[intent.decision_bar]
        pos = self._open_position(
            trade_id,
            intent,
            fill,
            t,
            t + 1,
            decision_idx,
            atr_values,
            pip,
            pair,
            index,
            stop_rows,
        )
        pos.gapped = gapped
        pos.max_high = highs[t]
        pos.min_low = lows[t]
        positions.append(pos)
        return True


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _validate_frame(df: pd.DataFrame) -> None:
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("resolution frame must be indexed by a DatetimeIndex")
    if len(df) == 0:
        raise ValueError("resolution frame is empty")
    if not df.index.is_monotonic_increasing or not df.index.is_unique:
        raise ValueError(
            "resolution frame index must be strictly increasing and unique"
        )
    missing = {"Open", "High", "Low", "Close"} - set(df.columns)
    if missing:
        raise ValueError(f"resolution frame missing columns {sorted(missing)}")


def _resolve_max_concurrent(
    param: Optional[int], strategy: Optional[StrategyV2]
) -> int:
    """F12: explicit parameter, else the strategy property, else 1."""
    value = (
        param
        if param is not None
        else (strategy.max_concurrent_positions if strategy is not None else 1)
    )
    if value < 1:
        raise ValueError("max_concurrent_positions must be >= 1")
    return value


def _stop_geometry_ok(direction: int, fill: float, stop: float) -> bool:
    """Stop strictly on the losing side of the fill (positive initial risk)."""
    return (direction == 1 and stop < fill) or (direction == -1 and stop > fill)


def _frame_from_rows(rows: List[Dict[str, object]], columns: List[str]) -> pd.DataFrame:
    """Deterministic frame construction, including the empty case."""
    if not rows:
        return pd.DataFrame({c: pd.Series(dtype=object) for c in columns})
    return pd.DataFrame(rows, columns=columns)
