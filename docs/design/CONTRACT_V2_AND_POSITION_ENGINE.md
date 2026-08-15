# Contract v2 + Position Engine — build specification

**Status:** specification, not yet implemented · **Author:** System-1 design · **Date:** 2026-08-09
**Supersedes nothing.** This is an *additive, parallel path* alongside the T6 sandbox
(`docs/design/RESEARCH_STRATEGY_ENGINE.md`), which stays exactly as it is.

This document is the **trunk**. Everything else in this initiative — 51 strategy
implementations, the fleet prompts, the review passes — is a leaf hanging off the interfaces
defined here. It is written to be precise enough that fifty independent authors cannot
diverge. Where it says MUST, it means a test asserts it.

---

## 0. Why this exists

The T6 sandbox backtests every research strategy under a **uniform** harness:
`engine_adapter.py` forces `SL = 1.0×ATR(14)`, `TP = 3.0×ATR(14)`, one position at a time.
That is deliberate and correct for comparing raw signal edge — a strategy cannot flatter
itself with bespoke exits.

But we now want to evaluate 51 documented strategies whose **exits are the edge**:
three-lot scale-outs at 200/400/600 pips, breakeven-on-TP2, pending buy-stops two pips above
the second consecutive higher high. Backtesting those under a uniform ATR harness measures
something that is not the strategy.

So we build a second, faithful path. Both survive:

| Path | Harness | Answers |
|---|---|---|
| **T6 (existing)** `engine_adapter.py` | Uniform ATR 1:3, one position | "Does the raw signal have edge?" |
| **v2 (this spec)** `position_engine.py` | The strategy's own declared orders | "Does the strategy as documented have edge?" |

Running both and reporting the delta is more informative than either alone. A strategy that
passes only under its bespoke exits is telling you the exit logic carries the edge; one that
passes under both is far more credible.

---

## 1. Inviolable constraints

These are not style preferences. Violating any of them fails review.

1. **Do not modify `src/layer0/core_engine/backtest_engine.py`.** It produced the live
   134,520 `fact_trade_outcomes` rows. It is the incumbent's provenance. Read it for
   reference; never edit it.
2. **Do not modify `src/layer0/strategies/contract.py`, `engine_adapter.py`, `promote.py`,
   or `registry.py`.** New modules only. The T6 path must still pass its 15 tests unchanged.
3. **Gates and metrics are imported, never reimplemented.** `src/system1/vetting/gates.py`
   and `src/system1/attribution/metrics.py` are the only sources of thresholds and metric
   math. A test asserts no threshold literal appears in the new modules. (This rule exists
   because it has already been broken twice — see the T6 failure log: a reimplemented
   drawdown reported 1650%.)
4. **Nothing writes to a `fact_*` table.** Research reads. `research_data.py` is the only
   door to market data, and it has no write path by construction.
5. **Walk-forward folds come from `src/system1/validation/walk_forward.py`.** Do not
   reimplement fold boundaries (min_train 36mo, step 6mo, OOS 6mo, anchored).
6. **No strategy in `research/` or `staged/` is importable by the live pipeline.**

---

## 2. Part A — Contract v2

New file: `src/layer0/strategies/contract_v2.py`. Imports and re-exports from `contract.py`
where types are unchanged (`Stage`, `StrategyMetadata` base, `LookAheadError`).

### 2.1 The core change

v1: `generate_signals(df) -> pd.Series` of {-1, 0, +1}. One frame, one number per bar.
The engine invents the entry and exit.

v2: the strategy **declares a complete trade plan** and the engine executes it.

```python
def generate_orders(
    self, frames: Mapping[str, "pd.DataFrame"]
) -> Sequence[OrderIntent]:
    """Emit the orders this strategy wants, given trailing data only."""
```

Two properties make this safe:

- It is **declarative**. The strategy describes intent at a decision bar; it never sees a
  fill, never sees its own P&L, and cannot react to outcomes. There is no channel through
  which look-ahead can enter that the truncation probe won't catch.
- It is **testable identically**. `assert_no_lookahead_v2` truncates the frames and
  re-emits, comparing the order list. A strategy using `shift(-1)` or a centred rolling
  window produces different orders and is rejected — same principle as v1, richer payload.

### 2.2 Types

```python
@dataclass(frozen=True)
class ExitLeg:
    """One scale-out leg. Fractions across all legs MUST sum to 1.0."""
    fraction: float                 # 0 < fraction <= 1
    kind: Literal["take_profit", "trailing", "time"]
    # exactly one of the following, per kind:
    price: float | None = None      # absolute level, for take_profit
    atr_multiple: float | None = None
    pips: float | None = None
    bars: int | None = None         # for kind="time"
    label: str = ""                 # e.g. "TP2" — appears in reports


@dataclass(frozen=True)
class StopRule:
    """The initial stop and how it is permitted to move. Stops NEVER widen."""
    price: float
    move_to_breakeven_on: str | None = None   # ExitLeg.label that triggers it
    breakeven_offset_pips: float = 0.0
    trail_atr_multiple: float | None = None   # None = static stop


@dataclass(frozen=True)
class OrderIntent:
    decision_bar: "pd.Timestamp"    # the bar whose CLOSE produced this decision
    direction: Literal[1, -1]
    entry: Literal["market", "buy_stop", "sell_stop", "buy_limit", "sell_limit"]
    entry_price: float | None       # None only for entry="market"
    stop: StopRule
    exits: Sequence[ExitLeg]
    expires_after_bars: int | None = 5   # pending-order lifetime; None = GTC
    size_fraction: float = 1.0      # of the standard unit; NOT position sizing
    tag: str = ""

    def __post_init__(self) -> None:
        # MUST validate: fractions sum to 1.0 ± 1e-9; stop on the correct side of
        # entry for the direction; every take_profit leg beyond entry in the
        # direction of the trade; pending entry_price not already through the
        # market at decision_bar close. Raise ValueError with the strategy_id.
```

**`size_fraction` is not position sizing.** System 1 never sizes — that is System 3's job
(see CLAUDE.md, "no downstream recomputation"). It expresses *relative* allocation across
legs of one idea (the "3 lots" language in the source strategies) in units of R, so
backtest results stay in r-multiples.

### 2.3 Metadata additions

`StrategyMetadataV2` extends `StrategyMetadata`:

```python
primary_granularity: str          # the frame signals are emitted on
context_granularities: Sequence[str] = ()   # e.g. ("D1",) for a D1 trend filter
simulate_on: str = "H1"           # bar size used to RESOLVE fills (see Part D)
source_row: int | None = None     # 1-based row in forex_swing_strategies.csv
source_url: str = ""
```

`VALID_GRANULARITIES` becomes `("H1", "H4", "D1", "W1")` in the v2 module.

### 2.4 Backward compatibility

A `SignalStrategyAdapter` wraps any v1 `Strategy` as a v2 strategy by synthesising a market
`OrderIntent` with the uniform ATR stop and a single 100% take-profit leg — reproducing
today's T6 behaviour exactly. **A test MUST assert that a v1 strategy run through the v2
engine produces r-multiples identical to the T6 path** (tolerance 1e-9) on a fixed fixture.
That test is the proof the new engine did not silently change execution semantics; it is
the single most important test in this build.

---

## 3. Part B — Position engine

New file: `src/layer0/strategies/position_engine.py`. Pure simulation: frames and orders in,
trades out. No I/O, no DB, no globals, deterministic.

### 3.1 Fill conventions — the accuracy contract

Bar data has no intrabar path. Every convention below resolves that ambiguity
**pessimistically**. They are numbered so a report can cite them.

- **F1 — Decision/execution separation.** An `OrderIntent` emitted at the close of bar *t*
  becomes eligible for fill from bar *t+1* onward. Never on bar *t*.
- **F2 — Market entry.** Fills at the open of bar *t+1*, plus adverse slippage.
- **F3 — Pending entry.** A `buy_stop` at level L fills when `high >= L` on some later bar,
  at `max(L, open)` — if the bar gapped through L, you get the open, which is worse. Mirror
  for `sell_stop` with `low <= L` and `min(L, open)`. Limits fill at L exactly (no
  price improvement modelled).
- **F4 — Expiry.** A pending order not filled within `expires_after_bars` is cancelled.
- **F5 — Stop before target, always.** If a single bar's range touches both the stop and a
  take-profit leg, **the stop is deemed hit first**. This is the existing engine's
  convention (`backtest_engine.py:318-338`) and is preserved. It is pessimistic and it is
  the largest single source of conservatism in the results.
- **F6 — Gap through stop.** If a bar opens beyond the stop, the fill is the **open**, not
  the stop level. Losses can exceed 1R. This must be visible in reports.
- **F7 — Multiple legs in one bar.** If one bar's range covers TP1 and TP2, both fill, in
  ascending distance from entry, each at its own level. A bar covering the stop *and* TP1
  fills the stop only (per F5).
- **F8 — Breakeven moves at bar close.** When the leg named by
  `StopRule.move_to_breakeven_on` fills on bar *k*, the stop moves at the **close of bar
  *k***, not intrabar. We cannot know the within-bar sequence, so the protection arrives
  late. Pessimistic and honest.
- **F9 — Trailing stops update at bar close** using that bar's completed ATR. Stops move
  only in the favourable direction; a trail never widens a stop.
- **F10 — Costs.** Spread 1.0 pip and slippage 0.5 pip on **entry only**, commission 0 —
  identical to the live cost model that produced `fact_trade_outcomes`. Do not change these
  values; import them from a single module-level constant block and cite it in reports.
- **F11 — End of data.** Open legs close at the final bar's close, reason `END_OF_DATA`,
  and are flagged in the report. Folds ending with many open positions are suspect.
- **F12 — Concurrency.** `max_concurrent_positions` defaults to **1 per (strategy, pair,
  granularity)**, matching T6. A strategy may raise it via metadata, but the report MUST
  state the value — comparing a 1-position result to a 5-position result is meaningless.

### 3.2 Per-bar order of operations

Fixed, and a test asserts it. Any other ordering produces optimistic results.

```
for each bar t:
    1. expire pending orders past their lifetime
    2. for each open position: check STOP (F5, F6)   ← before targets, always
    3. for each open position: check exit legs (F7), nearest first
    4. apply breakeven / trailing updates using bar t's CLOSE (F8, F9)
    5. attempt fills on pending orders (F3)
    6. admit new OrderIntents whose decision_bar == t-1 (F1), subject to F12
```

### 3.3 Output

`PositionEngine.run(...) -> BacktestResult` with a per-trade frame carrying, at minimum:
`entry_time, entry_price, direction, exit_time, exit_price, exit_reason, r_multiple,
legs_filled, max_adverse_excursion, max_favourable_excursion, bars_held, gapped`.

**`r_multiple` is the single number the gates consume**, defined as realised P&L divided by
the initial risk `|entry_price - stop.price|`, summed across legs weighted by fraction. It
MUST be computed in one place and reused, so that scale-out arithmetic cannot drift.

---

## 4. Part C — Multi-timeframe, and the causality rule

Do not write a new alignment engine. `src/layer0/core_engine/multi_timeframe.py` already
provides `MultiTimeframeEngine.align_timeframes()` with look-ahead prevention as a stated
design goal. **Wave 1's job is to verify that claim, then wire it — not to replace it.**

### The rule, stated once

> A context bar may inform a decision only after that context bar has **closed**.

Concretely: bars are stamped at their **open**. A D1 bar stamped `2026-08-05T21:00Z` covers
21:00 on the 5th through 21:00 on the 6th. It may first influence an H4 decision at
`2026-08-06T21:00Z` — **not** at any H4 bar in between, and emphatically not at
`2026-08-05T21:00Z`.

The mechanical form: `merge_asof(h4, d1, direction="backward", allow_exact_matches=False)`
after shifting the D1 frame's index forward by one full D1 interval. Get this wrong by one
bar and every D1-filtered strategy in the set is inflated. This is the FIX-S1-005 bug class,
which has already cost this project a full remediation cycle.

**Required test:** construct a synthetic D1 series whose trend flips on a known date; assert
no H4 signal reflects the flip before the D1 close that revealed it. Assert it at the
boundary bar specifically, not on average.

---

## 5. Part D — Simulating coarse strategies on H1 bars

Approved: D1 and H4 strategies are **decided** on their native frame and **resolved** on H1
bars.

- Signals and orders are generated from the native (D1/H4) frame only. The strategy never
  sees H1 data. Its logic is unchanged.
- The position engine resolves fills, stops, and legs against the **H1** frame within each
  native bar's span.

This is a large accuracy gain: a D1 bar with a 100-pip stop and a 600-pip TP3 tells you
nothing about sequence, whereas 24 H1 bars usually do. It is not perfect — H1 bars have
their own intrabar ambiguity — so F5 still applies at H1 resolution.

**Required deliverable:** every strategy is run **both ways** (native-bar resolution and H1
resolution) and the report carries both r-multiple series plus the delta. That delta *is* the
measurement of how much the bar-path assumption was worth. Publishing it is what makes the
~90% fidelity claim honest rather than asserted.

Cost: roughly 24× the bar count for D1 strategies. Accepted.

---

## 6. Part E — Causal swing points (required, and urgent)

`indicators.detect_swing_points()` (`src/layer0/data_access/indicators.py:452`) computes
`high.rolling(window=period*2+1, center=True).max()`. A centred window at bar *t* spans
`[t-period … t+period]`. **It is look-ahead.** It is the exact mechanism that contaminated
`Range_Stochastic_Divergence`, the only strategy in production
(`task/2026-August-week1/lookahead-audit/FINDINGS.md`).

**36 of the 51 source strategies reference swing highs, ZigZag, pivots, or fractals.**
Without a causal replacement, most of this initiative is born contaminated.

New module `src/layer0/strategies/causal_structure.py`:

```python
def confirmed_swing_points(high, low, period=5) -> tuple[pd.Series, pd.Series]:
    """Swing points stamped at their CONFIRMATION bar, not their occurrence bar.

    A swing high at bar k is confirmed only once `period` subsequent bars have all
    failed to exceed it — i.e. at bar k+period. The returned series marks k+period
    and carries the *level* that was set at k. At every bar t, the series reflects
    only information available at t.
    """

def zigzag_swings(high, low, depth=5, deviation_pips=0.0, backstep=3) -> pd.DataFrame:
    """Causal ZigZag: pivots appear only when confirmed. Never repaints."""

def last_n_confirmed_highs(high, low, n, period=5) -> pd.DataFrame:
    """Rolling access to the last n confirmed swing highs and their levels —
    what 'the second consecutive higher high' actually needs."""
```

The semantic difference is the whole point: a swing high **occurs** at bar *k* but is
**knowable** only at bar *k+period*. A strategy may act on it from *k+period* onward, and it
may use the *level* from bar *k*. That is legitimate and is what a live trader does. What is
illegitimate is knowing at bar *k* that bar *k* was a swing high.

Do **not** edit `indicators.detect_swing_points` — other code depends on it and the audit
records its behaviour. Add a module-level deprecation note pointing here, and add a test
asserting the new functions pass `assert_no_lookahead_v2` where the old one fails.

---

## 7. Part F — Data enablement

### W1 (trivial)

W1 is **already ingested** — `DEFAULT_GRANULARITIES = ["D1", "H4", "W1"]` in
`multi_timeframe_ingest.py`; 1,068 bars per pair back to 2005-12-30. Needed:

1. Add `"W1"` to `VALID_GRANULARITIES` (v2 module) and to
   `research_data._ALLOWED_GRANULARITIES`.
2. Refresh — W1's last bar is 2026-06-12, stale by ~8 weeks.
   `python -m src.system1.ingestion.multi_timeframe_ingest --granularity W1`
3. Investigate why the Saturday cron did not keep it current, and record the finding.

**Statistical warning, to be stated in every W1 report:** 36 months of training ≈ 156 W1
bars; a 6-month OOS window ≈ 26 bars. Trade counts will be single digits per fold. The 9
W1 strategies will return `low_confidence` and fail `OOS ≥ 60 months`. This is arithmetic,
not a bug, and the reports must say so rather than presenting a thin result as a verdict.

### Additional pairs

Demand extracted from the CSV's `target_pairs`, ranked by how many strategies name each
(32 rows additionally say "majors"/"any pair", which the 13 below cover):

| Pair | Named by | Status |
|---|--:|---|
| GBP_USD, EUR_USD, USD_JPY, AUD_USD, USD_CAD | 19/15/13/8/8 | **have** |
| GBP_JPY | 8 | add |
| EUR_JPY | 6 | add |
| NZD_USD | 4 | add |
| USD_CHF | 3 | add |
| EUR_GBP | 3 | add |
| EUR_AUD | 3 | add |
| AUD_NZD | 3 | add |
| EUR_CAD | 2 | add |

Procedure: insert `dim_asset` rows (`market_type='Forex'`, `is_active=true`), then
`python -m src.system1.ingestion.multi_timeframe_ingest --symbol <PAIR>` per pair. The
ingest is resumable (`ON CONFLICT ("timestamp", asset_id, granularity)`, resumes from
`MAX(timestamp)`), so interruption is safe. Expect a long backfill: ~130k H1 bars per pair
to 2006, against OANDA practice rate limits. Run overnight; verify with the coverage query
before declaring done.

**`XAU_USD` is named by 2 strategies and is deliberately excluded** — it is not Forex, and
pip value, margin, and `calculate_pips()` all assume FX conventions. Note it in the gap
document rather than half-supporting it.

**Scope note:** new pairs serve the research sandbox immediately. They do **not**
automatically flow into features/regime/attribution for the live path. That is a separate,
later decision and must not be made as a side effect of this build.

---

## 8. Part G — Verdict granularity

The T6 pilot pooled **56 folds across pairs × granularities into one cell**
(`results/research/rsi_mean_reversion/qualification_refused_*.json`). A strategy strong on
D1 EUR_USD and worthless on H1 USD_JPY receives one blended verdict, and both facts are lost.

v2 reports MUST carry, per strategy:

1. **Per-cell verdicts** — one gate evaluation per (pair × granularity), each with its own
   trade count and `low_confidence` flag.
2. **The pooled verdict** — retained for continuity with T6.
3. **The dispersion** — best and worst cell. A strategy that qualifies pooled but fails in
   9 of 13 cells is a concentration risk, which is already this system's finding C.

Promotion to `qualified` still requires the pooled gates to pass, imported from
`vetting/gates.py`. Per-cell results are reporting, not a second qualification path — there
must remain exactly one door to live.

---

## 9. Acceptance tests (Wave 1 is not done without these)

| # | Test | Asserts |
|---|---|---|
| 1 | `test_v1_equivalence` | A v1 strategy via `SignalStrategyAdapter` reproduces T6 r-multiples to 1e-9 |
| 2 | `test_t6_untouched` | The 15 existing T6 tests still pass, unmodified |
| 3 | `test_fill_order` | Per-bar operation order matches §3.2; a bar covering stop and TP1 yields the stop |
| 4 | `test_gap_through_stop` | Gapped bar fills at open, loss > 1R, `gapped=True` |
| 5 | `test_scale_out_arithmetic` | 3 legs at 1/3 each, hand-computed r-multiple matches |
| 6 | `test_breakeven_at_close` | Stop moves at the close of the triggering bar, not intrabar |
| 7 | `test_mtf_causality` | Synthetic D1 flip is invisible to H4 until the D1 close |
| 8 | `test_causal_swings` | `confirmed_swing_points` passes the truncation probe; `detect_swing_points` fails it |
| 9 | `test_no_threshold_literals` | No gate threshold appears in any new module |
| 10 | `test_no_write_path` | Source-level: no INSERT/UPDATE/DELETE in the v2 modules |
| 11 | `test_deterministic` | Same inputs → byte-identical trade frame across two runs |
| 12 | `test_stop_never_widens` | Trailing and breakeven only ever improve the stop |

Plus: `mypy` clean on all new modules; `black` formatted.

---

## 10. What this spec deliberately does not do

- **No parameter optimisation.** One declared parameter set per strategy. Sweeps invite
  overfitting and this system already has a concentration problem, not a tuning problem.
- **No position sizing.** System 1 never sizes. r-multiples only.
- **No regime conditioning.** The gates run on pooled OOS trades; regime cells are
  MODEL-004's job. Wiring the sandbox to regime attribution is the natural follow-on and is
  explicitly out of scope here.
- **No change to the live path.** Nothing in this build alters what the orchestrator
  publishes. Promotion of any of these 51 strategies to `qualified` is a separate, human
  decision made after the reports exist.
