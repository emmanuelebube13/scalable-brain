"""Contract v2 — strategies declare complete trade plans; the engine executes them.

v1 (``contract.py``): ``generate_signals(df) -> pd.Series`` of {-1, 0, +1}. One frame,
one number per bar; the engine invents the entry and the exit.

v2 (this module): ``generate_orders(frames) -> Sequence[OrderIntent]``. The strategy
declares, per decision bar, the direction, entry mechanism, initial stop, exit legs,
expiry and relative sizing. The position engine (``position_engine.py``, owned
separately) resolves those intents against bar data under fill conventions F1–F12.

Two properties keep this safe, mirroring v1:

- It is **declarative**. The strategy describes intent at a decision bar; it never sees
  a fill, never sees its own P&L, and cannot react to outcomes.
- It is **testable identically**. ``assert_no_lookahead_v2`` truncates the frames and
  re-emits, comparing the order list element-for-element. A strategy using
  ``shift(-1)`` or a centred rolling window produces different orders and is rejected.

Contract for the ENGINE (position_engine.py), stated here so both sides implement
against the same words:

- ``OrderIntent.decision_close`` may be ``None``. When it is ``None`` (or when the
  intent was built without market context), the engine MUST re-validate at admission
  that a pending entry is not already through the market: ``buy_stop`` above,
  ``sell_stop`` below, ``buy_limit`` below, ``sell_limit`` above the price at the
  admission bar. An intent failing that check is an instant fill disguised as a
  pending order and must be rejected, not silently filled.
- ``OrderIntent.time_exit_after_bars`` is a full-remainder time exit at bar close,
  counted from the decision bar: if the position is still open ``N`` bars after
  ``decision_bar``, close the whole remainder at that bar's close. This exists so a
  v1 adapter can reproduce T6's ``max_bars_hold`` time stop, which closes the entire
  position rather than a fraction of it (a fractional ``ExitLeg(kind="time")`` cannot
  express that, since exit legs sum to 1.0).
- ``OrderIntent.close_on_opposite`` is how T6's signal-reversal exit is expressed:
  when the engine admits this intent while an opposite-direction position is open, it
  closes that position first (adverse slippage) at the fill bar's open, then fills
  this intent.

Strategies receive **trailing-only** frames, are **pure functions**, must **not
mutate** the frames they are handed, and must **not perform I/O** (no database, no
network, no files). All four are enforced: mutation by checksum inside
``assert_no_lookahead_v2``; the rest by this module exposing no I/O surface and by
the promotion path running the probe.
"""

from __future__ import annotations

import hashlib
import importlib
from abc import ABC, abstractmethod
from dataclasses import MISSING, dataclass
from typing import Dict, List, Literal, Mapping, Optional, Sequence, Tuple, cast

import numpy as np
import pandas as pd

from ..core_engine.strategy_base import StrategyConfig
from ..data_access.indicators import atr, get_pip_value
from .contract import (
    _ID_RE,
    _MIN_HYPOTHESIS_WORDS,
    LookAheadError,
    Stage,
    Strategy,
    StrategyMetadata,
)
from .engine_adapter import ContractStrategyAdapter

__all__ = [
    "VALID_GRANULARITIES",
    "Direction",
    "EntryKind",
    "ExitLegKind",
    "ExitLeg",
    "StopRule",
    "OrderIntent",
    "StrategyMetadataV2",
    "StrategyV2",
    "assert_no_lookahead_v2",
    "SignalStrategyAdapter",
    # re-exported from .contract so v2 users have one import surface
    "Stage",
    "StrategyMetadata",
    "Strategy",
    "LookAheadError",
]

# Spec §2.3: VALID_GRANULARITIES becomes ("H1", "H4", "D1", "W1") in the v2 module.
VALID_GRANULARITIES: Tuple[str, ...] = ("H1", "H4", "D1", "W1")

Direction = Literal[1, -1]
EntryKind = Literal["market", "buy_stop", "sell_stop", "buy_limit", "sell_limit"]
ExitLegKind = Literal["take_profit", "trailing", "time"]

_FRACTION_SUM_TOL = 1e-9


# ---------------------------------------------------------------------------
# Types (spec §2.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExitLeg:
    """One scale-out leg. Fractions across all legs of an OrderIntent MUST sum to 1.0.

    Exactly the fields relevant to ``kind`` may be set:

    - ``kind="take_profit"``: exactly one of ``price`` / ``atr_multiple`` / ``pips``.
    - ``kind="trailing"``: exactly one of ``atr_multiple`` / ``pips``.
    - ``kind="time"``: ``bars`` (positive).
    """

    fraction: float  # 0 < fraction <= 1
    kind: ExitLegKind
    price: Optional[float] = None  # absolute level, for take_profit
    atr_multiple: Optional[float] = None
    pips: Optional[float] = None
    bars: Optional[int] = None  # for kind="time"
    label: str = ""  # e.g. "TP2" — appears in reports

    def __post_init__(self) -> None:
        if not (0.0 < self.fraction <= 1.0):
            raise ValueError(
                f"ExitLeg {self.label!r}: fraction {self.fraction} not in (0, 1]"
            )
        if self.kind == "take_profit":
            set_count = sum(
                x is not None for x in (self.price, self.atr_multiple, self.pips)
            )
            if set_count != 1:
                raise ValueError(
                    f"ExitLeg {self.label!r}: kind='take_profit' needs exactly one of "
                    f"price/atr_multiple/pips set, found {set_count}"
                )
            if self.bars is not None:
                raise ValueError(
                    f"ExitLeg {self.label!r}: kind='take_profit' must not set bars"
                )
        elif self.kind == "trailing":
            set_count = sum(x is not None for x in (self.atr_multiple, self.pips))
            if set_count != 1:
                raise ValueError(
                    f"ExitLeg {self.label!r}: kind='trailing' needs exactly one of "
                    f"atr_multiple/pips set, found {set_count}"
                )
            if self.price is not None or self.bars is not None:
                raise ValueError(
                    f"ExitLeg {self.label!r}: kind='trailing' must not set price or bars"
                )
        elif self.kind == "time":
            if self.bars is None or self.bars <= 0:
                raise ValueError(
                    f"ExitLeg {self.label!r}: kind='time' needs a positive bars value"
                )
            if (
                self.price is not None
                or self.atr_multiple is not None
                or self.pips is not None
            ):
                raise ValueError(
                    f"ExitLeg {self.label!r}: kind='time' must not set "
                    "price/atr_multiple/pips"
                )
        else:  # pragma: no cover - unreachable via the Literal type
            raise ValueError(f"ExitLeg {self.label!r}: unknown kind {self.kind!r}")
        if self.atr_multiple is not None and self.atr_multiple <= 0.0:
            raise ValueError(f"ExitLeg {self.label!r}: atr_multiple must be positive")
        if self.pips is not None and self.pips <= 0.0:
            raise ValueError(f"ExitLeg {self.label!r}: pips must be positive")


@dataclass(frozen=True)
class StopRule:
    """The initial stop and how it is permitted to move. Stops NEVER widen."""

    price: float
    move_to_breakeven_on: Optional[str] = None  # ExitLeg.label that triggers it
    breakeven_offset_pips: float = 0.0
    trail_atr_multiple: Optional[float] = None  # None = static stop

    def __post_init__(self) -> None:
        if self.trail_atr_multiple is not None and self.trail_atr_multiple <= 0.0:
            raise ValueError("StopRule: trail_atr_multiple must be positive when set")
        if self.breakeven_offset_pips < 0.0:
            raise ValueError("StopRule: breakeven_offset_pips must be non-negative")


@dataclass(frozen=True)
class OrderIntent:
    """A complete trade plan declared at the close of ``decision_bar``.

    ``size_fraction`` is not position sizing — System 1 never sizes. It expresses
    *relative* allocation across legs of one idea, in units of R.

    ``decision_close`` is the close price at the decision bar. When both it and
    ``entry_price`` are present, ``__post_init__`` validates that a pending entry is
    not already through the market. When it is absent, that check is deferred: the
    ENGINE MUST re-validate at admission (see module docstring).

    ``time_exit_after_bars`` is a full-remainder time exit at bar close counted from
    the decision bar (needed to reproduce T6's whole-position time stop).

    ``close_on_opposite`` instructs the engine to close an open opposite-direction
    position first (adverse slippage, at the fill bar's open) before filling this
    intent (needed to reproduce T6's signal-reversal exit).
    """

    decision_bar: pd.Timestamp  # the bar whose CLOSE produced this decision
    direction: Direction
    entry: EntryKind
    entry_price: Optional[float]  # None only for entry="market"
    stop: StopRule
    exits: Sequence[ExitLeg]
    expires_after_bars: Optional[int] = 5  # pending-order lifetime; None = GTC
    size_fraction: float = 1.0  # of the standard unit; NOT position sizing
    tag: str = ""
    strategy_id: str = ""  # carried so every validation error can name its source
    decision_close: Optional[float] = None  # close at the decision bar, when known
    time_exit_after_bars: Optional[int] = (
        None  # full-remainder time stop from decision bar
    )
    close_on_opposite: bool = False  # close an open opposite position before filling

    def __post_init__(self) -> None:
        sid = self.strategy_id or "<unknown strategy>"

        def err(msg: str) -> None:
            raise ValueError(f"{sid}: {msg}")

        if self.direction not in (1, -1):
            err(f"direction must be +1 or -1, got {self.direction!r}")
        direction = cast(Direction, self.direction)

        if not self.exits:
            err("declare at least one exit leg")
        total = float(sum(leg.fraction for leg in self.exits))
        if abs(total - 1.0) > _FRACTION_SUM_TOL:
            err(
                f"exit-leg fractions sum to {total!r}; they must sum to 1.0 "
                f"± {_FRACTION_SUM_TOL}"
            )

        if self.entry == "market":
            if self.entry_price is not None:
                err("entry='market' must have entry_price=None")
        elif self.entry_price is None:
            err(f"pending entry {self.entry!r} requires an entry_price")

        # Stop on the correct side of entry, and every take-profit leg beyond entry,
        # when the entry price is known (otherwise the engine checks at fill).
        if self.entry_price is not None:
            entry_price = self.entry_price
            if direction == 1 and not self.stop.price < entry_price:
                err(f"long stop {self.stop.price} must be below entry {entry_price}")
            if direction == -1 and not self.stop.price > entry_price:
                err(f"short stop {self.stop.price} must be above entry {entry_price}")
            for leg in self.exits:
                if leg.kind != "take_profit" or leg.price is None:
                    continue
                if direction == 1 and not leg.price > entry_price:
                    err(
                        f"take-profit leg {leg.label!r} at {leg.price} must be beyond "
                        f"entry {entry_price} for a long"
                    )
                if direction == -1 and not leg.price < entry_price:
                    err(
                        f"take-profit leg {leg.label!r} at {leg.price} must be beyond "
                        f"entry {entry_price} for a short"
                    )

        # A pending entry must not already be through the market at the decision
        # bar — that is an instant fill disguised as a pending order. Deferred to
        # the engine when decision_close is absent (see module docstring).
        if self.entry_price is not None and self.decision_close is not None:
            entry_price = self.entry_price
            close = self.decision_close
            if self.entry == "buy_stop" and not entry_price > close:
                err(
                    f"buy_stop at {entry_price} is not above the decision-bar close "
                    f"{close} — an instant fill disguised as a pending order"
                )
            if self.entry == "sell_stop" and not entry_price < close:
                err(
                    f"sell_stop at {entry_price} is not below the decision-bar close "
                    f"{close} — an instant fill disguised as a pending order"
                )
            if self.entry == "buy_limit" and not entry_price < close:
                err(
                    f"buy_limit at {entry_price} is not below the decision-bar close "
                    f"{close} — an instant fill disguised as a pending order"
                )
            if self.entry == "sell_limit" and not entry_price > close:
                err(
                    f"sell_limit at {entry_price} is not above the decision-bar close "
                    f"{close} — an instant fill disguised as a pending order"
                )

        if self.stop.move_to_breakeven_on is not None:
            labels = {leg.label for leg in self.exits}
            if self.stop.move_to_breakeven_on not in labels:
                err(
                    f"stop.move_to_breakeven_on={self.stop.move_to_breakeven_on!r} "
                    f"matches no exit-leg label {sorted(labels)} — the breakeven "
                    "rule could move the stop before any triggering leg exists"
                )

        if self.expires_after_bars is not None and self.expires_after_bars <= 0:
            err("expires_after_bars must be positive when set (None = GTC)")
        if self.time_exit_after_bars is not None and self.time_exit_after_bars <= 0:
            err("time_exit_after_bars must be positive when set")
        if not (0.0 < self.size_fraction <= 1.0):
            err(f"size_fraction {self.size_fraction} not in (0, 1]")


# ---------------------------------------------------------------------------
# Metadata (spec §2.3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class StrategyMetadataV2(StrategyMetadata):
    """v1 identity/provenance plus the multi-frame execution declaration.

    Keyword-only because the v1 base has defaulted fields (``stage``, ``created``)
    and ``primary_granularity`` is required — positional inheritance cannot express
    that. ``granularities`` are validated against the v2 ``VALID_GRANULARITIES``
    (which adds ``W1``), not the v1 tuple.
    """

    primary_granularity: str  # the frame signals are emitted on
    context_granularities: Sequence[str] = ()  # e.g. ("D1",) for a D1 trend filter
    simulate_on: str = "H1"  # bar size used to RESOLVE fills (spec Part D)
    source_row: Optional[int] = None  # 1-based row in forex_swing_strategies.csv
    source_url: str = ""

    def __post_init__(self) -> None:
        # Re-run the v1 checks against the v2 granularity set (the v1 __post_init__
        # would reject W1). The id/hypothesis rules are unchanged and imported from
        # the v1 module so there is one source for them.
        if not _ID_RE.match(self.strategy_id):
            raise ValueError(
                f"strategy_id {self.strategy_id!r} must be lower_snake_case, "
                "3-64 chars, starting with a letter"
            )
        if len(self.hypothesis.split()) < _MIN_HYPOTHESIS_WORDS:
            raise ValueError(
                f"{self.strategy_id}: hypothesis must state the claimed edge in at "
                f"least {_MIN_HYPOTHESIS_WORDS} words"
            )
        if not self.granularities:
            raise ValueError(f"{self.strategy_id}: declare at least one granularity")
        bad = [g for g in self.granularities if g not in VALID_GRANULARITIES]
        if bad:
            raise ValueError(
                f"{self.strategy_id}: unsupported granularities {bad}; "
                f"valid: {list(VALID_GRANULARITIES)}"
            )
        if not self.pairs:
            raise ValueError(f"{self.strategy_id}: declare at least one pair")
        if self.primary_granularity not in VALID_GRANULARITIES:
            raise ValueError(
                f"{self.strategy_id}: primary_granularity "
                f"{self.primary_granularity!r} not in {list(VALID_GRANULARITIES)}"
            )
        bad_ctx = [
            g for g in self.context_granularities if g not in VALID_GRANULARITIES
        ]
        if bad_ctx:
            raise ValueError(
                f"{self.strategy_id}: unsupported context_granularities {bad_ctx}; "
                f"valid: {list(VALID_GRANULARITIES)}"
            )
        if self.simulate_on not in VALID_GRANULARITIES:
            raise ValueError(
                f"{self.strategy_id}: simulate_on {self.simulate_on!r} not in "
                f"{list(VALID_GRANULARITIES)}"
            )


# ---------------------------------------------------------------------------
# The v2 strategy ABC
# ---------------------------------------------------------------------------


class StrategyV2(ABC):
    """The v2 contract. Implement this to enter the declarative-orders sandbox.

    A strategy is a pure function of trailing data:

    - ``generate_orders`` receives **trailing-only** frames — one per granularity in
      ``metadata.granularities`` — keyed by granularity name.
    - It must be a **pure function**: same frames in, same orders out.
    - It must **not mutate** the frames it is handed (enforced by checksum in
      ``assert_no_lookahead_v2``).
    - It must **not perform I/O** — no database, no network, no files. The contract
      exposes no persistence surface, and the probe hands it in-memory frames only.
    """

    @property
    @abstractmethod
    def metadata(self) -> StrategyMetadataV2:
        """Identity, hypothesis, and declared execution scope."""

    @property
    @abstractmethod
    def required_indicators(self) -> List[str]:
        """Indicator names this strategy needs, for pre-computation and audit."""

    @abstractmethod
    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        """Emit the orders this strategy wants, given trailing data only.

        MUST depend only on rows at or before each decision bar. Enforced
        empirically by ``assert_no_lookahead_v2``.
        """

    @property
    def warmup_bars(self) -> int:
        """Bars to discard before signals are trustworthy. Override if needed."""
        return 200

    @property
    def max_concurrent_positions(self) -> int:
        """F12 default: one open position per (strategy, pair, granularity)."""
        return 1

    # Convenience so callers can treat metadata fields as strategy attributes.
    @property
    def strategy_id(self) -> str:
        return self.metadata.strategy_id


# ---------------------------------------------------------------------------
# Empirical look-ahead probe (spec §2.1, mirrors contract.assert_no_lookahead)
# ---------------------------------------------------------------------------


def _frame_checksum(df: pd.DataFrame) -> bytes:
    """Content hash of a frame: shape, columns, and per-row value/index hashes."""
    h = hashlib.sha256()
    h.update(str(df.shape).encode())
    h.update("|".join(str(c) for c in df.columns).encode())
    h.update(
        pd.util.hash_pandas_object(df, index=True).to_numpy().tobytes()  # type: ignore[attr-defined]
    )
    return h.digest()


#: Bar duration per granularity. Bars are stamped at their OPEN, so a bar at
#: timestamp ``t`` covers ``[t, t + GRANULARITY_INTERVAL[gran])`` and does not
#: close — is not knowable — until the end of that span.
GRANULARITY_INTERVAL: Dict[str, pd.Timedelta] = {
    "H1": pd.Timedelta(hours=1),
    "H4": pd.Timedelta(hours=4),
    "D1": pd.Timedelta(days=1),
    "W1": pd.Timedelta(weeks=1),
}


def closed_context_frame(
    context: pd.DataFrame, granularity: str, as_of: pd.Timestamp
) -> pd.DataFrame:
    """Rows of ``context`` whose bar has **closed** at or before ``as_of``.

    Spec §4, stated once: *a context bar may inform a decision only after that
    context bar has closed.* Because bars are stamped at their open, the naive
    ``index <= as_of`` admits the bar that is still forming — whose High, Low
    and Close have not happened yet. That is look-ahead, and it is invisible to
    a truncation probe: truncating never removes the offending row, so the
    strategy sees the same completed OHLC either way and the probe agrees with
    itself.

    Off by one bar here and every D1-filtered strategy in the set is inflated.
    This is the FIX-S1-005 bug class.
    """
    interval = GRANULARITY_INTERVAL.get(granularity)
    if interval is None:
        raise ValueError(
            f"unknown context granularity {granularity!r}; "
            f"valid: {sorted(GRANULARITY_INTERVAL)}"
        )
    return context.loc[context.index + interval <= as_of]


def _truncate_frames(
    frames: Mapping[str, pd.DataFrame], primary_name: str, cut: int
) -> Dict[str, pd.DataFrame]:
    """Primary frame to ``iloc[:cut]``; context frames to bars that have CLOSED
    by the last surviving primary timestamp (see ``closed_context_frame``)."""
    primary = frames[primary_name]
    last_ts = primary.index[cut - 1]
    out: Dict[str, pd.DataFrame] = {}
    for name, df in frames.items():
        if name == primary_name:
            out[name] = df.iloc[:cut]
        else:
            out[name] = closed_context_frame(df, name, last_ts)
    return out


def assert_no_lookahead_v2(
    strategy: StrategyV2, frames: Mapping[str, pd.DataFrame], *, probes: int = 5
) -> None:
    """Prove empirically that emitted orders do not depend on future bars.

    Method: emit orders on the full frames, then re-emit on truncated prefixes
    (primary frame truncated positionally; context frames truncated to rows at or
    before the last surviving primary timestamp). For a trailing-only strategy the
    orders in the comparison window are identical whether or not later bars exist.
    Mismatch → ``LookAheadError``.

    Every ``generate_orders`` call is bracketed by frame checksums; a strategy that
    mutates the frames it is handed (and thereby the next strategy's data) fails
    here, naming the strategy.

    FIX-S1-013 closure: if the windowed probes covered ZERO orders, the windows
    proved nothing (this is how centred-window look-ahead reached production in
    v1). The probe then re-emits at up to ``probes`` decision bars where the full
    run actually fired and requires the order at that bar to be identical. A
    strategy that emits no orders anywhere cannot demonstrate look-ahead freedom
    and is rejected.
    """
    meta = strategy.metadata
    sid = meta.strategy_id
    primary_name = meta.primary_granularity
    if primary_name not in frames:
        raise LookAheadError(
            f"{sid}: frames are missing the primary granularity "
            f"{primary_name!r} (have {sorted(frames)})"
        )
    primary = frames[primary_name]
    n = len(primary)
    if n == 0:
        raise LookAheadError(f"{sid}: primary frame {primary_name!r} is empty")

    def emit(fr: Mapping[str, pd.DataFrame]) -> List[OrderIntent]:
        before = {name: _frame_checksum(df) for name, df in fr.items()}
        orders = list(strategy.generate_orders(fr))
        for name, df in fr.items():
            if _frame_checksum(df) != before[name]:
                raise LookAheadError(
                    f"{sid}: generate_orders mutated frame {name!r} — strategies "
                    "receive shared trailing frames and must never write to them"
                )
        primary_index = fr[primary_name].index
        for order in orders:
            if order.decision_bar not in primary_index:
                raise LookAheadError(
                    f"{sid}: emitted an order with decision_bar "
                    f"{order.decision_bar!r} that is not a bar of the primary "
                    f"frame {primary_name!r} — decisions must be taken on primary "
                    "bars"
                )
        return orders

    full_orders = emit(frames)

    covered = 0
    start = max(strategy.warmup_bars + 10, n // 2)
    if start < n:
        cuts = [start + (n - start) * i // (probes + 1) for i in range(1, probes + 1)]
        for cut in cuts:
            prefix_orders = emit(_truncate_frames(frames, primary_name, cut))
            # Compare the tail, skipping warmup where indicators legitimately differ.
            lo = max(strategy.warmup_bars, cut - 50)
            window = set(primary.index[lo:cut])
            a = [o for o in full_orders if o.decision_bar in window]
            b = [o for o in prefix_orders if o.decision_bar in window]
            covered += len(a)
            if a != b:
                raise LookAheadError(
                    f"{sid}: orders with decision bars in [{primary.index[lo]} … "
                    f"{primary.index[cut - 1]}] changed when future bars were "
                    "removed — the strategy is using look-ahead data (shift(-1), "
                    "centred rolling, or whole-series normalisation)"
                )

    # FIX-S1-013: windowed probes comparing emptiness to emptiness prove nothing.
    if covered == 0:
        index_pos = {ts: i for i, ts in enumerate(primary.index)}
        firing = sorted(
            {
                index_pos[o.decision_bar]
                for o in full_orders
                if index_pos[o.decision_bar] >= strategy.warmup_bars
            }
        )
        if not firing:
            raise LookAheadError(
                f"{sid}: emits no orders anywhere in {n} bars — look-ahead freedom "
                "cannot be demonstrated, so it must not qualify. (A strategy that "
                "never fires on the full series is either mis-specified or its "
                "entry condition is unreachable.)"
            )
        step = max(1, len(firing) // probes)
        for t in firing[::step][:probes]:
            live_orders = emit(_truncate_frames(frames, primary_name, t + 1))
            decision_ts = primary.index[t]
            a = [o for o in full_orders if o.decision_bar == decision_ts]
            b = [o for o in live_orders if o.decision_bar == decision_ts]
            if a != b:
                raise LookAheadError(
                    f"{sid}: the order at decision bar {decision_ts} differs when "
                    f"computed from bars [0:{t}] — the entry condition depends on "
                    "bars that have not happened yet. The windowed probe passed "
                    "only because it covered no firing bars."
                )


# ---------------------------------------------------------------------------
# Backward compatibility (spec §2.4): wrap a v1 Strategy as a StrategyV2
# ---------------------------------------------------------------------------


def _t6_max_bars_hold() -> int:
    """T6's time-stop length: the ``max_bars_hold`` default on ``StrategyConfig``.

    Read from the dataclass field metadata so there is exactly one source for the
    value; never re-typed here.
    """
    default = StrategyConfig.__dataclass_fields__["max_bars_hold"].default
    if default is MISSING:  # pragma: no cover - the field has a default by contract
        raise TypeError("StrategyConfig.max_bars_hold lost its default")
    return int(cast(int, default))


def _t6_slippage_pips() -> float:
    """T6's entry slippage, from ``BacktestConfig`` in ``backtest_engine.py``.

    Imported dynamically (not statically) for one reason only: the read-only
    ``backtest_engine.py`` carries a legacy implicit-Optional annotation that the
    repo's mypy defaults flag, and a static import would pull that pre-existing
    error into this module's mypy report. The value is still read from the single
    source at runtime; nothing is re-typed here.
    """
    module = importlib.import_module("src.layer0.core_engine.backtest_engine")
    return float(module.BacktestConfig().slippage_pips)


class SignalStrategyAdapter(StrategyV2):
    """Wrap a v1 ``contract.Strategy`` as a ``StrategyV2``, reproducing T6 exactly.

    For each primary-frame bar ``t`` where the v1 strategy's signal is non-zero the
    adapter emits a market ``OrderIntent`` whose stop and single 100% take-profit
    leg reproduce the T6 execution path:

    - entry (for pricing the exits) = ``Close[t]`` plus direction-adverse slippage,
      ``BacktestConfig().slippage_pips * get_pip_value(pair)`` — matching
      ``BacktestEngine._simulate_trades``;
    - stop = entry ∓ ``ContractStrategyAdapter.STOP_LOSS_ATR`` × ATR[t];
    - take profit = entry ± ``ContractStrategyAdapter.TAKE_PROFIT_ATR`` × ATR[t];
    - ATR = ``indicators.atr(High, Low, Close, period=ContractStrategyAdapter.ATR_PERIOD)``
      computed on the frame as handed (the trailing ewm matches T6, which computes
      ATR on the full frame before slicing);
    - ``time_exit_after_bars`` = the ``StrategyConfig.max_bars_hold`` default (T6's
      whole-position time stop);
    - ``close_on_opposite=True`` (T6 exits on signal reversal; with the engine's
      max-concurrency of 1 this reproduces the one-position-at-a-time semantics).

    Bars where ATR[t] is NaN are skipped: T6's ``calculate_stop_loss`` cannot
    produce a stop there either, so no trade exists to reproduce.

    ``pair`` is a constructor argument because computing slippage in price units
    requires the pip value of the instrument (JPY pairs differ).

    Metadata synthesis: the v1 metadata is preserved field-for-field and the
    strategy_id gains the suffix ``__v1adapt`` (truncated to the id-length limit),
    so adapted strategies are distinguishable from — and cannot collide with —
    native v2 declarations of the same id. ``primary_granularity`` and
    ``simulate_on`` are the v1 strategy's first declared granularity.
    """

    def __init__(self, strategy: Strategy, pair: str) -> None:
        self._strategy = strategy
        self._pair = pair
        self._slippage = _t6_slippage_pips() * get_pip_value(pair)
        meta = strategy.metadata
        self._metadata = StrategyMetadataV2(
            strategy_id=f"{meta.strategy_id}__v1adapt"[:64],
            name=meta.name,
            version=meta.version,
            author=meta.author,
            hypothesis=meta.hypothesis,
            granularities=list(meta.granularities),
            pairs=list(meta.pairs),
            stage=meta.stage,
            created=meta.created,
            primary_granularity=list(meta.granularities)[0],
            context_granularities=(),
            simulate_on=list(meta.granularities)[0],
        )

    @property
    def metadata(self) -> StrategyMetadataV2:
        return self._metadata

    @property
    def required_indicators(self) -> List[str]:
        return self._strategy.required_indicators

    @property
    def warmup_bars(self) -> int:
        # T6 uses max(strategy warmup, ATR_PERIOD * 3); the factor matches
        # ContractStrategyAdapter.get_required_warmup_bars.
        return max(self._strategy.warmup_bars, ContractStrategyAdapter.ATR_PERIOD * 3)

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        df = frames[self._metadata.primary_granularity]
        # Same normalisation as ContractStrategyAdapter.generate_signals.
        signals = (
            self._strategy.generate_signals(df).reindex(df.index).fillna(0).astype(int)
        )
        atr_series = atr(
            df["High"],
            df["Low"],
            df["Close"],
            period=ContractStrategyAdapter.ATR_PERIOD,
        )
        close = df["Close"].to_numpy(dtype=float)
        atr_values = atr_series.to_numpy(dtype=float)
        index = df.index

        orders: List[OrderIntent] = []
        for i in np.flatnonzero(signals.to_numpy()):
            atr_t = float(atr_values[i])
            if np.isnan(atr_t):
                # T6 cannot compute a stop for this bar; there is no trade to
                # reproduce. Skip, per this class's docstring.
                continue
            direction: Direction = 1 if int(signals.iloc[i]) > 0 else -1
            close_t = float(close[i])
            # T6 entry = close + direction-adverse slippage (see docstring).
            entry = close_t + direction * self._slippage
            stop = entry - direction * ContractStrategyAdapter.STOP_LOSS_ATR * atr_t
            take_profit = (
                entry + direction * ContractStrategyAdapter.TAKE_PROFIT_ATR * atr_t
            )
            orders.append(
                OrderIntent(
                    decision_bar=index[i],
                    direction=direction,
                    entry="market",
                    entry_price=None,
                    decision_close=close_t,
                    stop=StopRule(price=stop),
                    exits=[
                        ExitLeg(
                            fraction=1.0,
                            kind="take_profit",
                            price=take_profit,
                            label="TP",
                        )
                    ],
                    expires_after_bars=None,
                    time_exit_after_bars=_t6_max_bars_hold(),
                    close_on_opposite=True,
                    tag="v1",
                    strategy_id=self.strategy_id,
                )
            )
        return orders
