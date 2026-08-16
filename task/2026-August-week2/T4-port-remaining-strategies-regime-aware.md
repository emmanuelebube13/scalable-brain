# T4 — Port the remaining 8 strategies into the regime-aware framework

**Engineer:** Gemini Pro
**Reviewer:** Claude (will verify each equivalence test before any result is believed)
**Repo:** `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`
**Venv:** `source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate`
**Estimated time:** 3–4 hours. **Risk:** low — read-only, self-contained, nothing in production changes.

---

## Read these three documents first. Do not skip them.

| document | why |
|---|---|
| `docs/design/REGIME_LABELS_EXPLAINED.md` | **what the HMM label and the D1 trend label actually are**, how they differ, and which column is safe to read. Confusing them has already produced one false result. |
| `docs/design/STRATEGY_EXPERIMENT_STANDARD.md` | the eight rules any result must satisfy. Your output will be judged against them. |
| `task/2026-August-week2/deliverables/T3-regime-aware/README.md` | what the first port found, and the confound it exposed. |

### The 30-second version of the labels

- **HMM label** — 4 states (`Trending-Up`, `Trending-Down`, `Ranging`, `High-Vol`) from a fitted
  Hidden Markov Model, stored in `fact_market_regime_v2.regime_causal`. **Only ever read
  `regime_causal`.** The sibling column `regime_smoothed` is fitted forward *and* backward over
  full history, so it leaks the future into past labels. Known weakness: the HMM label is 92–98%
  `Ranging` for EUR_USD, GBP_USD, AUD_USD and USD_CAD, so conditioning on it tends to collapse
  into "is this USD_JPY".
- **D1 trend label** — a fixed rule, not a model: daily `EMA(50) > EMA(200)` → `Trending-Up`,
  below → `Trending-Down`, warm-up → `UNKNOWN`, shifted one bar for causality. Built by
  `src/regime_aware/context.py::build_trend_labels`. Varies healthily on all five pairs.

Both already work. **You do not need to modify either.** You consume them.

---

## What you are doing

`Trend_Donchian_VCP` has been ported to the regime-aware framework. Port the other **8**, so
every strategy can be measured three ways — blind, HMM-aware, trend-aware — against the current
system.

You are not inventing strategies, not tuning parameters to improve results, and not touching
production. You are porting existing logic faithfully and proving the port is faithful.

---

## Hard constraint: one folder

**Every strategy port lives in `src/regime_aware/strategies/`, one file per strategy.**

Nothing about this work may appear anywhere else. No new top-level folders, no files under
`src/layer0/` or `src/system1/`, no edits to production strategies. If you feel you need to
change something outside `src/regime_aware/`, stop and report instead — that is a design problem,
not a coding one.

```
src/regime_aware/
├── context.py                  DO NOT EDIT (labels)
├── contract.py                 edit ONLY to add ParamBlock fields (see below)
├── runner.py                   edit to register the new strategies
├── strategies/
│   ├── donchian_vcp.py         the template — read it end to end first
│   ├── donchian_h1.py          ← you write these 8
│   ├── donchian_h4.py
│   ├── ema_adx_h1.py
│   ├── ema_adx_h4.py
│   ├── ema_adx_multitf.py
│   ├── bollinger_h1.py
│   ├── bollinger_h4.py
│   └── bollinger_aggressive.py
└── tests/                      one equivalence test per strategy
```

---

## The 8 strategies

All live in `src/layer0/strategies/strategieStaged/`. Column `gran` is the strategy's declared
`primary_granularity` — the frame it trades, and the only one it should be run on.

| # | production class | name | gran | key parameters |
|---|---|---|---|---|
| 1 | `TrendDonchian_H1_Only` | `Trend_Donchian_H1` | H1 | channel 10, ADX 14 / 25, SL 1.5×ATR, TP 3.0×ATR |
| 2 | `TrendDonchian_H4_Only` | `Trend_Donchian_H4` | H4 | channel 20, ADX 14 / 25, SL 1.5, TP 3.0 |
| 3 | `TrendEMAADX_H1_Only` | `Trend_EMA_ADX_H1` | H1 | fast 10 / slow 20, ADX 14 / 25, SL 1.5, TP 2.5 |
| 4 | `TrendEMAADX_H4_Only` | `Trend_EMA_ADX_H4` | H4 | fast 20 / slow 50, ADX 14 / 25, SL 1.5, TP 2.5 |
| 5 | `TrendEMAADX_MultiTF` | `Trend_EMA_ADX_MultiTF` | H4 | identical to #4 — see the note below |
| 6 | `RangeBollinger_H1_Only` | `Range_Bollinger_H1` | H1 | bb 20 / 2.0σ, RSI 14, require_rsi |
| 7 | `RangeBollinger_H4_Only` | `Range_Bollinger_H4` | H4 | bb 20 / 2.0σ, RSI 14, require_rsi |
| 8 | `RangeBollinger_Aggressive` | `Range_Bollinger_Aggressive` | H4 | bb 20 / **1.5σ**, `require_rsi=False`, SL 1.0, TP 1.0 |

**Do not port `Range_Stochastic_Divergence` (id 10).** It is `INTEGRITY_DISQUALIFIED` for
look-ahead; its numbers are fiction.

**About #5.** `Trend_EMA_ADX_MultiTF` currently produces byte-identical output to #4 — same
parameters, and the flag that is meant to distinguish it (`use_multi_timeframe`) is never read by
the legacy engine. Port it anyway and **expect its blind arm to match #4 exactly**. That is a
useful check, not a bug. Note it in your report rather than trying to "fix" it.

---

## Extending `ParamBlock`

The current `ParamBlock` in `contract.py` carries Donchian fields (`channel_period`,
`squeeze_lookback`). The other families need their own knobs.

**Approach: add fields to the single frozen dataclass with defaults.** Do not build a class
hierarchy for this — one contract, one validator, one test surface is worth more than avoiding a
few unused fields. A strategy ignores the fields it does not use.

Add: `fast_ema: int = 20`, `slow_ema: int = 50`, `bb_period: int = 20`, `bb_std: float = 2.0`,
`rsi_period: int = 14`, `rsi_oversold: float = 30.0`, `rsi_overbought: float = 70.0`,
`require_rsi: bool = True`.

**Every existing test must still pass after this change**, unchanged. If adding a defaulted field
breaks an equivalence test, the default is wrong.

---

## Per strategy — the procedure

Follow `donchian_vcp.py` exactly. For each strategy:

### Step 1 — `BASELINE`

A `ParamBlock` reproducing the production strategy's settings precisely. Read the production
class constructor; do not guess. Include a test asserting `BASELINE` matches the live production
object field by field (`test_baseline_matches_production_config` in the template).

### Step 2 — subclass the production strategy

Subclass the real class so config, warm-up and exit handling are inherited rather than
reimplemented. Override only:

- `calculate_indicators` — compute indicators for **every distinct parameter value** any block
  requests, over the **full continuous frame**. Never compute an indicator inside a regime
  segment: a channel or EMA that restarts at a regime boundary invents signals that never
  occurred. See the `contract.py` docstring.
- `generate_signals` — one vectorised pass per regime, masked to that regime's bars, honouring
  `enabled`, `allowed_directions` and the block's own parameters.
- `calculate_stop_loss` / `calculate_take_profit` — use `resolve_at(self.params, df)`. The engine
  passes a window ending at the entry bar, so reading its last row is causal.

> **The trap that will break your equivalence test.** Every family rescales its periods by
> granularity inside `calculate_indicators`, and **each family does it differently**. Donchian
> uses a plain `period // 2` on H1. Bollinger uses a floored form — `max(10, bb_period // 2)` for
> the band and `max(7, rsi_period // 2)` for RSI. EMA has its own. Read the production
> `calculate_indicators` for the family you are porting and reproduce its scaling exactly; do not
> copy `_scaled_period` from `donchian_vcp.py` and assume it generalises. This is the single most
> likely cause of an equivalence failure, and it will look like a subtle "close but not identical"
> mismatch rather than an obvious break.

### Step 3 — the equivalence test (**mandatory, and the whole point**)

With `RegimeParams.uniform(BASELINE)`, the port must reproduce the production strategy **trade
for trade**: entry time, direction, entry price, stop, take profit, exit reason, r-multiple.

If this fails, **stop on that strategy and report it**. Do not proceed to results — an A/B built
on a port that changes trades measures the port, not the regime. Also assert the fixture actually
produced trades; a test that passes on an empty trade list proves nothing.

### Step 4 — the two regime-aware parameter sets

`REGIME_AWARE` (for HMM labels) and `TREND_AWARE` (for D1 trend).

**Choose the values a priori, from the strategy's economics, and write the reasoning in the module
docstring before you run anything.** Do not tune them after seeing results. If a result makes you
want different values, that is a new named variant — add it, do not edit the original.

Guidance, from the strategy families rather than from the data:

- **Breakout strategies (Donchian)** — the classic failure is the false break in a range. Sitting
  out `Ranging` and widening the stop in `High-Vol` is defensible.
- **Mean-reversion strategies (Bollinger)** — the opposite. These are *supposed* to work in a
  range and to be run over by trends. Do not blindly copy the Donchian blocks; a defensible
  a-priori set may sit out the trending regimes instead.
- **Under the D1-trend context**, `Ranging` and `High-Vol` never occur. Express the trade-with-
  the-trend rule with `allowed_directions=(1,)` in `Trending-Up` and `(-1,)` in `Trending-Down`.
- **`UNKNOWN` should almost always be `enabled=False`.** No label, no opinion.

### Step 5 — register in the runner

Extend `runner.py` so it sweeps all 9 strategies and emits one comparison per strategy. Keep the
existing output sections (context coverage, overall, by regime, by pair), the bootstrap CIs and
the permutation test. Reuse the gates and folds already imported from `src/system1/` — do not
re-declare thresholds.

---

## Rules that are not negotiable

- **Read `regime_causal` only.** Never `regime_smoothed`. `context.py` already refuses it; do not
  work around that guard.
- **Read-only.** The connection opens with `SET default_transaction_read_only = on`. No writes to
  any table, ever. `test_package_source_contains_no_write_statements` enforces it.
- **Each strategy runs on its declared `primary_granularity` only.** Running a strategy on a frame
  it never declared is the duplication defect that was fixed on 2026-08-15.
- **No parameter tuning to improve results.** Ever. See rule 2 of the standard.
- **No edits outside `src/regime_aware/`.**
- **No commits, no pushes.** This is reviewed before it lands.
- **No `Co-Authored-By:` trailer** anywhere.

---

## Done when

- 8 new files in `src/regime_aware/strategies/`, one per strategy.
- An equivalence test per strategy, all passing, each proving a non-empty trade list.
- `python -m pytest src/regime_aware/tests/ -q` — all green.
- `python -m pytest src/system1 src/layer0 src/regime_aware -q` — **612 or more passing, zero failing.**
- `python -m src.regime_aware.runner --lookback-years 10` runs to completion, exit 0, and writes
  its report to `results/regime_aware/`.
- `fact_trade_outcomes` still has **55,756** rows and `fact_strategy_regime_attribution` **1,360**.

---

## Report back with

1. The equivalence-test result for each of the 8, stated individually. If any failed, say so
   plainly and stop there for that strategy — a failed equivalence test is the single most
   important thing you could tell the reviewer.
2. Your a-priori parameter blocks per strategy **and the reasoning**, in the same form as the
   `donchian_vcp.py` docstring.
3. The comparison table per strategy: blind vs HMM-aware vs trend-aware, with n, PF, PF 95% CI,
   Sharpe, max drawdown — pooled and **per pair**.
4. The permutation test per strategy for both regime-aware arms against blind.
5. For each strategy: does any arm beat blind with a PF confidence interval that **excludes 1.0**?
   Name them, or state plainly that none do.
6. Whether `Trend_EMA_ADX_MultiTF`'s blind arm matched `Trend_EMA_ADX_H4` exactly.
7. Anything you noticed and deliberately did not touch.

**Expected outcome, stated in advance so you are not tempted to produce a better one:** most or
all arms will fail the gates, and most confidence intervals will straddle 1.0. That is a
legitimate and useful result. A clean negative is worth far more here than a positive that does
not survive review.
