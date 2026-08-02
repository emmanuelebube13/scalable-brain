"""T6 — the strategy contract.

One interface every research strategy implements, and the metadata that makes a
strategy idea auditable. Deliberately smaller than the legacy ``StrategyBase``:
the contract is the *promotion surface*, not the execution surface. A strategy
satisfies this to enter the sandbox; the existing backtest engine still drives it.

Two design rules, both enforced rather than documented:

1. **Trailing-only data.** ``generate_signals`` receives a frame and must return a
   signal series indexed identically. Any signal at bar *t* that depends on data
   after *t* is look-ahead. ``assert_no_lookahead`` proves the absence of that
   dependency empirically by truncating the frame and re-running — a strategy
   using ``shift(-1)`` cannot survive it. See the adversarial review in
   ``task/2026-W31/deliverables/T6/``.
2. **An author must state the hypothesis.** ``StrategyMetadata.hypothesis`` is
   required and non-trivial. A strategy nobody can explain the edge of is a
   curve fit waiting to be discovered; making the claim explicit up front is what
   lets a later reviewer check whether it held.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING, List, Sequence

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd


class Stage(str, Enum):
    """Where a strategy sits in the promotion pipeline.

    The ordering is meaningful: promotion may only move forward one step at a
    time, and only ``QUALIFIED`` is visible to the live vetting path.
    """

    RESEARCH = "research"
    STAGED = "staged"
    QUALIFIED = "qualified"

    @property
    def rank(self) -> int:
        return {"research": 0, "staged": 1, "qualified": 2}[self.value]


VALID_GRANULARITIES = ("H1", "H4", "D1")
_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")

# A hypothesis has to say something. This is a floor, not a quality bar.
_MIN_HYPOTHESIS_WORDS = 8


@dataclass(frozen=True)
class StrategyMetadata:
    """Identity and provenance. Everything a reviewer needs before reading code."""

    strategy_id: str
    name: str
    version: str
    author: str
    hypothesis: str
    granularities: Sequence[str]
    pairs: Sequence[str]
    stage: Stage = Stage.RESEARCH
    created: date = field(default_factory=date.today)

    def __post_init__(self) -> None:
        if not _ID_RE.match(self.strategy_id):
            raise ValueError(
                f"strategy_id {self.strategy_id!r} must be lower_snake_case, "
                "3-64 chars, starting with a letter"
            )
        if len(self.hypothesis.split()) < _MIN_HYPOTHESIS_WORDS:
            raise ValueError(
                f"{self.strategy_id}: hypothesis must state the claimed edge in at "
                f"least {_MIN_HYPOTHESIS_WORDS} words — an unexplained strategy is a "
                "curve fit nobody can later falsify"
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


class Strategy(ABC):
    """The contract. Implement this to enter the sandbox.

    A strategy is a pure function of trailing data. It does not read the
    database, does not know whether it is live, and cannot place an order —
    those are System-2/System-3 concerns and are structurally out of reach here.
    """

    @property
    @abstractmethod
    def metadata(self) -> StrategyMetadata:
        """Identity, hypothesis, and declared scope."""

    @property
    @abstractmethod
    def required_indicators(self) -> List[str]:
        """Indicator names this strategy needs, for pre-computation and audit."""

    @abstractmethod
    def generate_signals(self, df: "pd.DataFrame") -> "pd.Series":
        """Return one signal per bar: +1 long, -1 short, 0 flat.

        MUST be indexed identically to ``df`` and MUST depend only on rows at or
        before each bar. Enforced by ``assert_no_lookahead``.
        """

    @property
    def warmup_bars(self) -> int:
        """Bars to discard before signals are trustworthy. Override if needed."""
        return 200

    # Convenience so callers can treat metadata fields as strategy attributes.
    @property
    def strategy_id(self) -> str:
        return self.metadata.strategy_id


class LookAheadError(AssertionError):
    """Raised when a strategy's signals change retroactively."""


def assert_no_lookahead(
    strategy: Strategy, df: "pd.DataFrame", *, probes: int = 5
) -> None:
    """Prove empirically that signals do not depend on future bars.

    Method: compute signals on the full frame, then recompute on progressively
    truncated prefixes. For a trailing-only strategy the signal at bar *t* is
    identical whether or not bars after *t* exist. A strategy using ``shift(-1)``,
    a full-series ``rolling(center=True)``, or any normalisation over the whole
    frame produces different values and is rejected.

    This is the check that makes "no look-ahead" a property of the code rather
    than a claim in a docstring.
    """
    full = strategy.generate_signals(df)
    if len(full) != len(df):
        raise LookAheadError(
            f"{strategy.strategy_id}: returned {len(full)} signals for {len(df)} bars — "
            "the signal series must be indexed identically to the input"
        )

    n = len(df)
    start = max(strategy.warmup_bars + 10, n // 2)
    if start >= n:  # frame too short to probe; nothing to prove
        return
    cuts = [start + (n - start) * i // (probes + 1) for i in range(1, probes + 1)]

    covered_signals = 0
    for cut in cuts:
        prefix = strategy.generate_signals(df.iloc[:cut])
        if len(prefix) != cut:
            raise LookAheadError(
                f"{strategy.strategy_id}: truncated frame of {cut} bars produced "
                f"{len(prefix)} signals"
            )
        # Compare the tail, skipping warmup where indicators legitimately differ.
        lo = max(strategy.warmup_bars, cut - 50)
        a = full.iloc[lo:cut].to_numpy()
        b = prefix.iloc[lo:cut].to_numpy()
        covered_signals += int((a != 0).sum())
        if not (a == b).all():
            diffs = int((a != b).sum())
            raise LookAheadError(
                f"{strategy.strategy_id}: {diffs} signal(s) in bars [{lo}:{cut}] changed "
                f"when future bars were removed — the strategy is using look-ahead data "
                f"(shift(-1), centred rolling, or whole-series normalisation)"
            )

    # FIX-S1-013: the windowed probe above can pass vacuously. These strategies are rare
    # — Range_Stochastic_Divergence fires 352 times in 130,299 EUR_USD H1 bars — so five
    # 50-bar windows routinely contain NO signals, and comparing zeros to zeros proves
    # nothing. That is exactly how this strategy's look-ahead survived qualification: it
    # was never probed on a bar where it fired. If the windows covered no signal, re-probe
    # on bars where the strategy actually emits one.
    if covered_signals == 0:
        firing = [int(i) for i in range(strategy.warmup_bars, n) if full.iloc[i] != 0]
        if not firing:
            raise LookAheadError(
                f"{strategy.strategy_id}: emits no signals anywhere in {n} bars — "
                "look-ahead freedom cannot be demonstrated, so it must not qualify. "
                "(A strategy that never fires on the full series is either mis-specified "
                "or its entry condition is unreachable.)"
            )
        step = max(1, len(firing) // probes)
        for t in firing[::step][:probes]:
            live = strategy.generate_signals(df.iloc[: t + 1])
            if int(live.iloc[t]) != int(full.iloc[t]):
                raise LookAheadError(
                    f"{strategy.strategy_id}: the signal at bar {t} is "
                    f"{int(full.iloc[t])} with the full series but "
                    f"{int(live.iloc[t])} when computed from bars [0:{t}] — the entry "
                    "condition depends on bars that have not happened yet. The windowed "
                    "probe passed only because it covered no firing bars."
                )
