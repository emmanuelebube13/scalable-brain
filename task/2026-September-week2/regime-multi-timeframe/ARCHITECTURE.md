# Structural regime — multi-granularity architecture

**Status:** approved, 2026-09-07. **All three owner decisions are answered — see §9.**
**Scope:** make the structural label exist at every granularity a strategy trades on, and make
selection run on it. **Retiring the HMM is explicitly NOT in this scope** — see §7.

---

## 1. The defect, stated plainly

`src/regime/build_structural.py` hardcodes `GRANULARITY = "D1"`. It is the only granularity the
canonical labeller can produce. Every consumer that needs a regime at H1 or H4 reaches backward
and borrows the daily label.

Price data exists at six granularities. The labellers cover them unevenly:

| source | granularities labelled | rows |
|---|---|---|
| `fact_market_prices` | M15, M30, H1, H4, D1, W1 | 4.75M |
| `fact_market_regime_v2` (HMM) | **D1, H4, H1** | 202,411 |
| `fact_regime_structural` | **D1 only** | 29,698 |

So the proposed flip to structural is also, silently, a reduction from three labelled
granularities to one. That is not an acceptable side effect of a change made for other reasons.

## 2. Evidence that the borrowed label is wrong, not merely coarse

Measured 2026-09-07, EUR_USD and USD_JPY, full history. "Own" = the structural rule computed on
that granularity's own bars. "D1" = the daily label currently borrowed via backward join.

| granularity | agreement with the borrowed D1 label |
|---|---|
| H4 | **40.7%** (EUR_USD), 41.1% (USD_JPY) |
| H1 | **32.3%** (EUR_USD), 33.0% (USD_JPY) |

An H1 trade is currently tagged with a regime that disagrees with its own timeframe **two thirds
of the time**.

The conditional distributions say something sharper than the headline. At H4 the daily label
still carries information — `D1 Trending-Down → H4 Trending-Down` at 51.5% against a ~35% base
rate, and the diagonal is elevated throughout. At H1 that structure collapses:

```
EUR_USD, H1 label distribution GIVEN the D1 label
                  High-Vol  Ranging  Trend-Dn  Trend-Up
D1 High-Vol            6.9     17.8      32.8      42.5
D1 Ranging             7.0     18.4      36.2      38.5
D1 Trending-Down       8.2     18.1      41.6      32.1
D1 Trending-Up         8.4     18.7      34.8      38.2
```

The rows are nearly identical. `D1 High-Vol` and `D1 Ranging` produce almost the same H1
distribution, and `D1 High-Vol` yields `H1 Trending-Up` (42.5%) *more often* than `D1 Trending-Up`
does (38.2%). **At H1 the borrowed daily label is close to non-informative about the state of the
market on the timeframe the trade is actually taken on.**

Also measured: the label's mean age when borrowed is **11.5h at H1** (max 23h) and **11.4h at H4**.
Within a calendar day an H1 trade sees **1.011 distinct regimes** — every hourly signal in a day
shares one regime value, so the feature is a daily constant at the timeframe it is used on.

## 3. The rule is mechanically sound at every granularity

Same rule, same constants, applied per granularity (EUR_USD, full history):

| gran | bars | flicker | High-Vol | Ranging | Trending (both) |
|---|---|---|---|---|---|
| D1 | 5,951 | 0.091 | 9.9% | 18.5% | 67.4% |
| H4 | 33,290 | 0.090 | 8.2% | 15.1% | 76.0% |
| H1 | 131,044 | 0.083 | 7.8% | 18.2% | 73.9% |
| M30 | 260,669 | 0.084 | 8.3% | 20.7% | 70.9% |

It does not degenerate — no exploding flicker, no collapsed distribution. Extending it is a
tractable change, not a research project.

## 4. The real modelling problem: every window constant is calibrated for D1

This is the part that must be decided, not defaulted.

```python
ADX_TREND_THRESHOLD = 25.0     # ADX period 14
VOL_ZSCORE_WINDOW   = 252      # trailing z-score of ATR%
EMA spans            = 50, 200
```

`252` means **one trading year** at D1. Applied unchanged it means ~42 days at H4, ~10.5 days at
H1, ~5 days at M30. So "High-Vol" would mean "volatile versus the last year" at D1 and "volatile
versus the last week" at M30 — four different concepts sharing one name, shipped in one enum to
three systems.

**[DECIDE-1 — ANSWERED: Option B, constant wall-clock. Owner, 2026-09-07.]**

- **Option A — constant bars (252 everywhere).** Cheapest. The label is relative to the recent
  context *of the timeframe you trade*, which is arguably what an intraday strategy wants. But the
  label's meaning varies by granularity and cannot be compared across them.
- **Option B — constant wall-clock (recommended).** Scale to ~1 year at every granularity:
  D1 252, H4 1,512, H1 6,048. "High-Vol" then means the same thing everywhere, cells remain
  comparable across granularities, and the map's regime keys stay coherent. Costs a longer warm-up
  at H1 (6,048 bars ≈ 1 year — affordable, data starts 2006).

**Recommendation: Option B**, because the regime name is about to become a cross-system contract
value. A label whose meaning depends on the granularity it was computed at cannot be safely put in
`regime-status-contract.json`.

**[DECIDE-2 — ANSWERED: no, they do not scale. Owner, 2026-09-07.]**

ADX(14) and the 50/200 EMAs stay as they are at every granularity. They are conventional at any
timeframe and they are *shape* parameters — they describe the character of price action in front
of them and need no reference period. Only the volatility z-score is explicitly a "versus recent
history" measure, and only it needs a wall-clock anchor.

**This asymmetry must be written into the code as a deliberate choice with this reason.** One
constant scaling while two do not looks exactly like an oversight, and the next person to read it
will "fix" it.

## 5. Target architecture

### 5.1 One labeller, parameterised

`GRANULARITY = "D1"` becomes a parameter. The table is **already** keyed
`(asset_id, granularity, bar_time_utc)`, so this is purely additive — no schema change, no
migration, existing D1 rows untouched.

```
build_structural.py --granularity D1|H4|H1 [--all]
```

Labelled set = exactly the granularities strategies trade on: **D1, H4, H1**.
`fact_trade_outcomes` contains no M30/M15/W1 trades, so labelling them is speculative work and is
out of scope. The parameter makes adding them later a config change.

### 5.2 Every consumer joins on granularity

The load-bearing change. Today consumers join on `(asset_id, bar_time)` and take whatever
granularity exists. They must join on `(asset_id, granularity, bar_time)` and use **the signal's
own granularity**:

| consumer | today | after |
|---|---|---|
| `attribution/attribute.py` | backward join to D1, 72h tolerance | join on the trade's own granularity |
| `gatekeeper/features.py` | `build_structural_labels(d1_frame)` | read the table at the decision granularity |
| `regime/live.py` | newest D1 row per instrument | newest row per (instrument, granularity) |
| `analytics/publish_*` | D1 | per-granularity |

`REGIME_TAG_TOLERANCE_HOURS` must be re-derived: with own-granularity labels the tolerance
becomes ~1–2 bars, not 72 hours. A 72h tolerance on an H1 label would silently reintroduce the
staleness this change exists to remove.

### 5.3 Nothing hardcoded — single source of truth

Three constants currently disagree and must collapse to one derivation:

| location | today | after |
|---|---|---|
| `attribute._REGIME_MODEL_VERSION_BY_LABEL["regime_structural"]` | `"structural-v1.0.0"` **(wrong)** | derived from `structural.LABELLER_VERSION` |
| `gatekeeper/train.REGIME_MODEL_VERSION` | `"hmm-v1.0.0"` **(wrong — it trains on structural)** | derived |
| `serializer/serialize.REGIME_MODEL_VERSION` | `"hmm-v1.0.0"` | derived |

`structural.LABELLER_VERSION` is the single source. It is currently `structural-v1.1.0` and must
be bumped to **`structural-v2.0.0`** by this change: a label whose window definition changed is
not the same label, and every artifact carrying the old version must be re-derived, not reused.

**MUST NOT be collapsed:** `attribute.SELECTION_SOURCE_LABEL` and
`map_contract.ROUTING_SOURCE_LABEL`. They look duplicated. They are declared independently *on
purpose* so the admissibility check can compare them — merging them makes the check vacuous and
re-authorises the 2026-08-24 defect. This is the one place where "nothing hardcoded" must not be
applied.

### 5.4 Freshness contracts per granularity

`risk_off.CONTRACTS` currently carries one `fact_regime_structural` entry with
`max_staleness_hours=30, bar_hours=24`. With three granularities the contract must be per
granularity, and `bar_hours` must match the granularity (H1→1, H4→4, D1→24).

**Known, unresolved, and NOT to be fixed here** (see `audit/reports/work_order_01.md` §Part 1):
the D1 contract is structurally unsatisfiable every Sunday 21:00Z → Monday 21:00Z, because the
newest complete D1 bar is Friday's and the weekend pin lifts at market open. An H1 contract will
not have this problem. **Do not "fix" the D1 window as a side effect of this work** — it is a
separate owner decision about `_reference_time`.

## 6. What must be rebuilt, in order

The label is upstream of everything. Changing it invalidates every derived artifact:

```
1. build_structural --all              → fact_regime_structural (D1 + H4 + H1)
2. attribute.run(engine_version=…)     → fact_strategy_regime_attribution   [BLOCKED: DECIDE-3]
3. vet --live                          → regime_strategy_map + weights      [BLOCKED: map freeze]
4. gatekeeper retrain                  → new champion (its regime feature changed meaning)
5. publish model set                   → System 2 downloads it
```

**[DECIDE-3 — ANSWERED: `position_engine_v2`. Owner, 2026-09-07.]**

`attribute.AUTHORITATIVE_ENGINE_FOR_VETTING` is still `None` in code and step 2 raises until it is
set. **Setting it is part of Stage C**, not a prerequisite done in advance.

Rationale to record alongside the constant, per `engine_validation_2` §B2: the two engines'
`r_multiple` is not the same quantity and no strategy runs under both, so there is no data-driven
tie-break — this is a judgement. v2 carries 48 of 67 strategies, all three granularities, and 170
of the 209 cells. Its two known defects (the USD_JPY pip-scaling bug O-28, and the stop-first exit
rule O-29) both make it measure **worse** than it is, so choosing it does not flatter it.

**Consequence to be aware of when it is set:** the orchestrator's promotion path stops raising.
The retrain cron polls hourly and currently no-ops (`no_trigger_or_cooldown`), and `vet --live` is
still refused by the map freeze, so nothing runs away — but the guard that has been stopping the
pipeline at step 2 is gone from that moment. Do not set it earlier in the sequence than Stage C.

Step 4 is not optional. The gatekeeper's `regime_structural` feature changes meaning when the
window definition changes and when H1/H4 signals stop borrowing a daily label. **A champion
trained on the old feature scoring the new one is train/serve skew** — the exact defect class
FIX-S1-016 was.

## 7. Explicitly out of scope

- **Retiring the HMM.** Logged for a later work order. It still gates promotion
  (`regime_accuracy_ok`, `beats_incumbent`) and still ships as a required artifact
  (`S1_ARTIFACTS`). Removing it breaks two promotion gates in opposite directions — one fails
  closed, one silently passes — and is a cross-system contract change. Not now.
- **Adding a Low-Vol regime / renaming the labels.** Owner deferred, 2026-09-07.
- **Changing any guard threshold**, including the 54h D1 staleness window.
- **M30/M15/W1 labelling.** Parameterised for later; not built.

## 8. Honest risk statement

**This change is a correctness fix, not a performance fix. Do not expect it to make money.**

The R3 regime-aware trial measured 129 comparisons across three label sources and found **27
better on point estimate and zero with a confidence interval clear of zero** — with per-granularity
HMM labels available. That is evidence of no effect from regime conditioning, and it was measured
on labels that already had the resolution this work order adds.

What this change buys is coherence: a strategy is selected under the same conditions it is traded
under, at the timeframe it trades on. That is worth having on its own terms. It is not a reason to
expect the map to improve.

**The rebuilt map may contain fewer cells than today, or none.** Every cell metric is recomputed
on labels that disagree with the old ones 59–67% of the time. Cells currently qualifying on 5 and
13 trades will be re-measured. An empty map is a legitimate outcome and must be reported as a
finding, not worked around.

---

## 9. Owner decisions — answered 2026-09-07

| # | Decision | Answer |
|---|---|---|
| **DECIDE-1** | Do volatility windows scale with granularity? | **Yes — Option B, constant wall-clock.** ~1 year at every granularity: D1 252, H4 1,512, H1 6,048 bars. |
| **DECIDE-2** | Do ADX(14) and the 50/200 EMAs also scale? | **No.** They stay unchanged at every granularity. The asymmetry is deliberate and must be documented in code. |
| **DECIDE-3** | `AUTHORITATIVE_ENGINE_FOR_VETTING` | **`position_engine_v2`.** Set during Stage C, with the §6 rationale recorded beside the constant. |

Consequences that follow from these and are now settled, not open:

- `structural.LABELLER_VERSION` → **`structural-v2.0.0`**. DECIDE-1 changes the window definition,
  so every existing D1 row is stale evidence and must be re-derived, not preserved.
- The H1 warm-up becomes 6,048 bars (~1 year). Data starts 2006, so coverage is unaffected in
  practice — but the warm-up mask must be sized **in bars of that granularity**, and the
  `UNKNOWN` share per granularity must be reported.
- Labels remain comparable across granularities, so a cell's regime key means the same thing at
  D1, H4 and H1. This is what makes the map's regime keys coherent and is the reason B was chosen.
