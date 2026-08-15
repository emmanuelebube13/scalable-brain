# FIX-S1-013 — look-ahead audit of all ten qualified strategies

**Date:** 2026-08-02 · **Instrument set:** EUR_USD + GBP_USD, 20,000 bars per granularity
**Verdict: 1 of 10 strategies is contaminated — and it is the only one in production.**

---

## 1. Result

| # | Strategy | Verdict |
|--:|---|---|
| 1 | Trend_EMA_ADX_H1 | ✅ clean |
| 2 | Trend_EMA_ADX_H4 | ✅ clean |
| 3 | Trend_EMA_ADX_MultiTF | ✅ clean |
| 4 | Trend_Donchian_H1 | ✅ clean |
| 5 | Trend_Donchian_H4 | ✅ clean |
| 6 | Trend_Donchian_VCP | ✅ clean |
| 7 | Range_Bollinger_H1 | ✅ clean |
| 8 | Range_Bollinger_H4 | ✅ clean |
| 9 | Range_Bollinger_Aggressive | ✅ clean |
| **10** | **Range_Stochastic_Divergence** | 🚨 **LOOK-AHEAD — emits NO signals in real time** |

Three independent lines of evidence agree:

1. **Empirical, EUR_USD** — 20 firing bars probed per strategy: 9 clean, strategy 10 differs on 20/20.
2. **Empirical, GBP_USD** — 40 firing bars probed per strategy: all 9 clean.
3. **Static scan** — look-ahead patterns (`center=True`, `shift(-`, `detect_swing_points`) appear
   **4×** in `range_stochastic.py` and **0×** in `trend_ema_adx.py`, `trend_donchian.py`,
   `range_bollinger.py` (the files behind strategies 1–9).

### Method note (this matters)

Probes must target bars where the strategy **actually fires**. These strategies are rare — strategy
10 fires 352 times in 130,299 EUR_USD H1 bars. An initial probe over a quiet 55-bar window returned
zero disagreements and nearly produced a false "clean" verdict. A quiet window agrees trivially and
is not evidence of absence.

### Mechanism (strategy 10)

`_detect_bullish_divergence` / `_detect_bearish_divergence`
(`range_stochastic.py:245,248,281,284`) locate swing points with
`rolling(window=10, center=True)`. A centred 10-bar window at bar *t* spans `[t-4 .. t+5]` — the
entry condition depends on five bars that have not happened yet. Computed honestly, **every signal
becomes 0**.

`src/layer0/strategies/contract.py::assert_no_lookahead` already names
"a full-series `rolling(center=True)`" as a rejection case. It was written for the T6 research
sandbox; the legacy staged strategies that produced `fact_trade_outcomes` were never run through it.

---

## 2. 🚨 The consequence — the qualified set is empty without the cheat

`results/state/regime_strategy_map.json`, the live map, qualifies **strategy 10 and nothing else**:

| Regime | Qualified |
|---|---|
| Trending-Up | `Range_Stochastic_Divergence@H1` |
| Trending-Down | `Range_Stochastic_Divergence@H1` |
| Ranging | `Range_Stochastic_Divergence@H1` |
| High-Vol | *(empty)* |

**The one strategy that reached production is the one that cheats.** Vetting did not select it
despite the look-ahead — it selected it **because** of it. Peeking five bars ahead at swing points
is equivalent to choosing entries with hindsight, and it lifted the metrics clear of every gate.

### How far short the honest strategies fall

Best value achieved across all cells, latest qualification run:

| | best PF | best Sharpe | best Recovery | best Win |
|---|--:|--:|--:|--:|
| **Gate required** | **≥1.50** | **≥0.80** | **≥3.00** | **≥0.40** |
| strategy 10 (look-ahead) | 3.08 | 10.00 | 80.02 | 1.00 |
| **strategies 1–9 (honest)** | **1.27** | **0.60** | **2.84** | 0.56 |

**No honest cell passes more than 3 of the 6 gates.** The best are not marginally short — PF 1.21–1.27
against a 1.5 bar, Sharpe 0.60 against 0.80, recovery 2.84 against 3.00.

> **Bottom line: with the look-ahead removed, System 1 has no qualified strategy, and nothing close
> to qualifying.** The project's founding rule — *"no strategy touches live capital until it proves
> a mathematical edge"* — has not been satisfied by any honest strategy in the library.

---

## 3. What is now known to be unsound

Everything derived from strategy 10's metrics:

- `regime_strategy_map.json` and `strategy_weights.json` (all live weight is strategy 10)
- `oos-r-multiples-strat10-td-h1.json` — sent to Computer 2 on 2026-08-01; **already retracted**
- the 75.6% win rate / PF 3.24 / +0.47R benchmark quoted throughout the Computer-2 exchange
- MODEL-004 attribution rows for strategy 10
- the gatekeeper's training label distribution for strategy 10 (its "wins" were hindsight wins)

Not affected: the regime model, the feature store, the ingest path, and strategies 1–9's own
(honest, failing) numbers.

---

## 4. Not in the qualified ten, but broken the same way

`SupportResistance*` uses `detect_swing_points` (`indicators.py:465-469`), the same centred-window
pattern. It is **not** among the ten qualified strategies, so nothing in production depends on it —
but it must not be promoted before the same fix. `VCPBreakout` scanned clean.

---

## 5. Recommended sequence

1. **Fix or retire strategy 10.** A causal divergence detector must confirm a swing only after the
   right-hand bars exist — which means the signal arrives *later* and the edge may not survive.
   Retiring it is a legitimate outcome.
2. **Wire `assert_no_lookahead` into qualification** so no strategy can ever qualify without
   passing it. This is the guard that should have existed.
3. **Re-run qualification** on the honest library, expecting an empty or near-empty qualified set.
4. **Accept that as the true starting position** — the strategy library needs genuinely new
   research, not a re-tune. Rebuilding MODEL-006 or wiring Pub/Sub before this would be building
   on nothing.

Nothing is trading; Computer 2's breaker is shut and the retrain cron is disabled. There is no time
pressure on any of it.

---

*Reproduce: `PYTHONPATH=. python task/2026-August-week1/lookahead-audit/audit_all_strategies.py`*
