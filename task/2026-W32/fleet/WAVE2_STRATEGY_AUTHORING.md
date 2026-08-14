# WAVE 2 — Strategy authoring (paste this whole file as the prompt)

> **DO NOT SEND THIS UNTIL WAVE 1 IS REVIEWED AND THE INTERFACE IS FROZEN.**
> Strategies written against an interface that does not yet exist all need rework.

**Fleet size:** 51 agents, one per strategy. Fully parallel.
**Depends on:** Wave 0 (your spec) and Wave 1 (the working engine), both reviewed.
**Output:** one strategy module + one golden fixture test per agent.

---

## Uploaded files

- `SPEC-<your_strategy_id>.md` — **your** Wave-0 spec. This, not the CSV, is your source of
  truth. Every interpretive decision was already made and reviewed.
- `contract_v2.py`, `position_engine.py`, `causal_structure.py` — the frozen interface
- `indicators.py` — available indicators
- `REFERENCE_STRATEGY.py` — a complete worked example, **tested and passing**. Match its
  shape exactly. Its four numbered NOTES each mark a place where the obvious
  implementation is wrong; read them before writing a line.
- `REFERENCE_FIXTURE.py` — the golden fixture for that strategy, with the arithmetic
  worked by hand in comments. **This is the format your fixture must follow.**
- `DATA_AVAILABILITY.md` — pairs and granularities

---

## Your assignment

Implement **one** strategy, from its spec, as a `contract_v2.Strategy` subclass. This is
translation, not interpretation. If you find yourself making a judgement call the spec does
not cover, **stop and report it** rather than deciding — an unreviewed decision at this stage
is invisible to everyone downstream.

File: `src/layer0/strategies/research/<strategy_id>.py`

```python
from ..contract_v2 import (
    StrategyV2, StrategyMetadataV2, OrderIntent, ExitLeg, StopRule,
)
from ..causal_structure import confirmed_swing_points
from ...data_access.indicators import ema, atr


class YourStrategy(StrategyV2):
    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="your_strategy_id",
            name="...", version="0.1.0", author="wave2-fleet",
            hypothesis="<§1 of your spec, verbatim>",
            granularities=["D1"], pairs=[...],
            primary_granularity="D1", context_granularities=(),
            simulate_on="H1", source_row=<N>, source_url="...",
        )

    @property
    def required_indicators(self) -> list[str]:
        return ["ema", "atr"]

    def generate_orders(self, frames):
        # frames: Mapping[granularity -> DataFrame]. Trailing-only.
        ...
```

---

## The golden fixture — mandatory, not optional

Alongside your strategy, write
`src/layer0/strategies/research/tests/test_<strategy_id>_fixture.py`:

1. **30–50 hand-constructed OHLC bars** as a literal in the test file, engineered so your
   strategy fires **at least once long** and — if it trades short — **at least once short**.
   Not random data. Not loaded from the database. Bars you chose, for reasons you state.
2. **The expected `OrderIntent`, written out by hand**: entry type, entry level, stop level,
   every exit leg with its fraction and level. Compute these yourself from the spec and put
   the arithmetic in a comment.
3. **An assertion** that `generate_orders` produces exactly that.
4. **A comment block** mapping each assertion back to the numbered rule in your spec that
   requires it.

**Why this is non-negotiable:** a human will review 51 strategy files. Reading logic with no
ground truth is where errors survive review. Your fixture is what makes your strategy
*checkable* — it converts "does this code look right?" into "does this fixture encode the
spec correctly?", which is a question a reviewer can actually answer.

**A strategy without a passing golden fixture will be rejected without being read.**

---

## Hard rules

1. **`assert_no_lookahead_v2` must pass.** Prohibited outright: `shift(-n)`,
   `rolling(..., center=True)`, `.iloc[i+1:]`, whole-frame normalisation, `resample` without
   a causal offset.
2. **Never import `indicators.detect_swing_points`.** It is look-ahead. Use
   `causal_structure.confirmed_swing_points`, and honour the confirmation lag your spec §9
   states.
2b. **Any strategy reading a context frame MUST use `closed_context_frame`, never
   `index <= t`.** Bars are stamped at their OPEN, so `d1.loc[d1.index <= ts]` admits the
   daily bar that has not closed yet — whose High/Low/Close have not happened. During the
   Wave-1 review that exact line produced **108 phantom orders** off future data, and the
   look-ahead probe passed it clean (truncation never removes the offending row, so the
   probe agrees with itself). Either call
   `contract_v2.closed_context_frame(ctx, "D1", ts)`, or use the vectorised `merge_asof`
   form shown in NOTE 1 of `REFERENCE_STRATEGY.py`. This is the single most likely way for
   your strategy to be silently wrong.
3. **Do not edit any file outside your own two.** No shared-helper refactors. If your
   strategy needs a helper another strategy also needs, define it privately in your module
   and note it in your report — consolidation is the reviewer's call, not yours.
4. **Exit fractions sum to 1.0** exactly.
5. **No parameter tuning.** Use the parameters in your spec. If they look wrong, say so in
   the report; do not "improve" them. Tuning against the backtest is how research becomes
   curve fitting, and this system already has that scar tissue.
6. **Do not read the database.** `generate_orders` receives frames and returns orders. That
   is the entire surface.
7. **Type hints; mypy clean; black formatted.**

---

## Also deliver: `REPORT-<strategy_id>.md`

Short. Four sections:

- **Implemented** — what you built, and any place the spec was thinner than the code needed
- **Deviations** — anything you did differently from the spec, and why. Ideally empty
- **Uncertainties** — judgement calls the spec did not cover. **Do not resolve these
  silently.** List them; the reviewer decides
- **Fixture rationale** — why those bars, and what the strategy does on them

---

## Definition of done

- `research/<strategy_id>.py` implementing `StrategyV2`
- `research/tests/test_<strategy_id>_fixture.py` — golden fixture, passing
- `REPORT-<strategy_id>.md`
- `assert_no_lookahead_v2` passes on your strategy against real data
- `mypy` clean, `black` formatted, no files touched outside your own
