# Research Strategy Engine — design

**Status:** skeleton implemented 2026-07-29 (T6) · **Scope:** `src/layer0/strategies/`

A sandbox where a new strategy idea can be registered, backtested leak-free, and either
promoted through the *same gates the live system uses* or rejected with per-gate reasons.

The engine exists because of findings B and C in `docs/SYSTEM1_ANALYSIS_2026-07-01.md`: the
regime map doesn't discriminate between strategies, and the entire live model is one strategy
at one granularity. **The answer to concentration is more honest candidates, not a lower bar.**
Every design decision below follows from that: the sandbox makes it *easy to try* an idea and
*impossible to smuggle one through*.

---

## 1. The three stages and what each guarantees

```
   research/                 staged/                    qualified/
   ─────────                 ───────                    ──────────
   anything that             contract-compliant,        passed the LIVE
   implements the      ──►   no look-ahead,       ──►   vetting gates on
   contract                  produced real OOS          OOS folds only
                             trades
        │                         │                          │
        └── invisible to live ────┘                          └── the ONLY thing
                                                                 vet.py can see
```

| Stage | Entry requirement | Visible to live pipeline? |
|---|---|---|
| `research` | implements `Strategy`; id unique; hypothesis stated | **no** |
| `staged` | + `assert_no_lookahead` passes; ≥1 OOS trade across walk-forward folds | **no** |
| `qualified` | + `vetting.gates.evaluate_gates` returns pass on OOS-only metrics | **yes** |

**Stage is derived from directory, never self-declared.** `registry.py` overrides whatever
`metadata.stage` says with the package the file was found in. A strategy cannot promote itself
by editing a field — promotion is a `git mv` plus a report artifact.

## 2. The contract

`src/layer0/strategies/contract.py`

```python
class Strategy(ABC):
    metadata: StrategyMetadata          # id, name, version, author, hypothesis, granularities, pairs
    required_indicators: List[str]
    warmup_bars: int = 200
    def generate_signals(self, df) -> pd.Series: ...   # +1 / -1 / 0, indexed like df
```

Deliberately *smaller* than the legacy `StrategyBase`. The contract is the **promotion
surface**; `StrategyBase` is the **execution surface**. `engine_adapter.py` bridges them and
supplies uniform ATR stops (1×ATR SL, 3×ATR TP, ATR-14) to every research strategy, so no
candidate can flatter itself with bespoke exit logic. A research author writes ~30 lines and
structurally cannot reach execution concerns.

**`hypothesis` is required and must be ≥8 words.** A strategy whose edge nobody can articulate
is a curve fit waiting to be discovered; forcing the claim up front is what lets a later
reviewer check whether it held. This is research hygiene enforced by a `ValueError`.

## 3. No look-ahead, proven rather than promised

`assert_no_lookahead(strategy, df)` computes signals on the full frame, then recomputes on
progressively truncated prefixes. For a trailing-only strategy the signal at bar *t* is
identical whether or not bars after *t* exist. It catches both:

- the obvious cheat — `df["Close"].shift(-1)`
- the subtle one — whole-frame normalisation or `rolling(center=True)`, where no future value
  is referenced directly but early bars still depend on the end of the series

This runs inside `evaluate_walk_forward` before any promotion, so it is not optional.

## 4. Data access

`research_data.load_ohlcv_readonly(pair, granularity)` is the **only** door to market data.
One parameterised `SELECT`, no transaction, no write helper. Research that can mutate `fact_*`
tables contaminates the set the live pipeline trains on, so the module contains no write path
and a test asserts at source level that none appears later.

## 5. Promotion, and why there is no second qualification path

`staged → qualified` **imports `src.system1.vetting.gates` and calls `evaluate_gates`**. The
thresholds (PF≥1.5, Sharpe≥0.8, MaxDD≤25%, WinRate≥40%, Recovery≥3.0, OOS≥60mo) are never
copied into the sandbox — a test asserts no such literal appears in `promote.py`. If the live
bar moves, the sandbox bar moves with it.

Metrics come from `validation/walk_forward.py` folds (min_train 36mo, step 6mo, OOS 6mo,
anchored) — the same generator MODEL-003/004/006 use — so a research backtest cannot
accidentally be more generous than the live path. Thin samples set `low_confidence`, which the
live gates treat as an unconditional rejection: **the sandbox does not get a softer standard
for having less data.**

`vet.py` consumes `registry.qualified()`. One source of truth, one set of gates, one door.

## 6. Integration with MODEL-005

No second qualification path is created. MODEL-005 keeps deciding which *qualified* strategies
map to which regimes; T6 decides which strategies are *allowed to be candidates at all*. The
registry is the handoff point.

---

## Strategy author's guide

**1. Write the file.** Drop it in `src/layer0/strategies/research/your_idea.py`:

```python
from ..contract import Strategy, StrategyMetadata

class YourIdea(Strategy):
    @property
    def metadata(self):
        return StrategyMetadata(
            strategy_id="your_idea",              # lower_snake_case, unique across ALL stages
            name="Your Idea", version="0.1.0", author="you",
            hypothesis="State the edge you believe exists and why it should persist. "
                       "At least 8 words — this is what a reviewer will check later.",
            granularities=["H1"], pairs=["EUR_USD"],
        )

    @property
    def required_indicators(self): return ["rsi"]

    def generate_signals(self, df):
        # Trailing-only. Anything that peeks forward is caught before promotion.
        return (df["Close"] > df["Close"].rolling(20).mean()).astype(int)
```

**2. Check it registered.**

```bash
python -m src.layer0.strategies.promote --list
```

**3. Ask for a verdict.**

```bash
python -m src.layer0.strategies.promote your_idea --to staged      # backtest + look-ahead check
python -m src.layer0.strategies.promote your_idea --to qualified   # the real gates
```

Reports land in `results/research/your_idea/`. Add `--dry-run` to evaluate without moving files.

**A rejection is a successful run.** It comes with the per-gate numbers that caused it, e.g.
`PF=1.12 < 1.50`, `OOS=18mo < 60mo`. That is the pipeline doing its job — the gates exist
because a strategy that cannot clear them would lose money live, and the live account has
already demonstrated what that looks like (see `task/2026-W31/deliverables/T5/`).

---

## What is NOT built yet

1. **The 6 legacy strategies in `strategieStaged/` were deliberately NOT migrated.** They
   implement `StrategyBase`, not the contract, and they are the *currently live qualified set*
   consumed via `layer0.strategies` re-exports by `qualify_strategies.py`. Moving them into
   `staged/` would demote the live model and break the import chain T1 had just repaired. The
   correct next increment is a `LegacyStrategyAdapter` that wraps a `StrategyBase` as a
   contract `Strategy`, letting them be registered as `qualified` in place.
2. **Parameter sweeps / optimisation** inside the sandbox — currently one fixed parameter set
   per strategy.
3. **Regime-conditional evaluation** — the gates run on pooled OOS trades; per-regime cells
   are MODEL-004's job. Wiring the sandbox into regime attribution is the natural follow-on,
   and would let the sandbox answer finding B (do regimes discriminate?) for new candidates.
4. **Registry persistence** — the registry is discovered at import time, not stored. A DB or
   JSON manifest would let promotion history be queried without reading git log.
