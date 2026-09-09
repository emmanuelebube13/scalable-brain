# Review of Work Order 02 — corrections to the findings

**Reviewer:** Claude, 2026-09-08. **Verdict: the build is sound; the conclusion is not.**

Work Order 02's summary concludes that the gatekeeper refusal "definitively proves the structural
regime should not be shipped." **That is not supported.** Three of its four load-bearing claims are
wrong or overstated, and the one that is right is not attributed to the right cause.

Recording this because a wrong conclusion in a summary propagates into decisions. The engineering
underneath it is good and should not be discarded with the reasoning.

---

## What the build got right

- 760 tests pass. Nothing shipped. Live map untouched (`generated_at_utc 2026-08-24`, 14 cells).
- No champion written — the guard refused and aborted cleanly, which is correct behaviour.
- The freeze was respected: `vet` ran log-only, no live map write.
- The parameterisation, the per-granularity joins, the `LABELLER_VERSION` single-sourcing and the
  `xard_ma_cross_daily_open` pip-scaling fix are all real improvements and should be kept.

---

## Claim 1 — "the gatekeeper refusal proves structural should not be shipped"

**FALSE.** The same degeneracy check, run against the **currently live champion**
(`models/champion_manifest.json`, field `shipped_approval_by_strategy_regime`):

| model | degenerate cells | verdict under the same guard |
|---|---|---|
| **live champion** | **84 of 88 = 95.5%** | **would also be refused** |
| new (WO-02) | 77 of 81 = 95.1% | refused |

The incumbent is marginally **worse** than the model that was rejected. Its distribution: 77 cells
approve ≤0.05, 7 approve ≥0.95, **4** are anywhere in between.

Decisively: the live champion's manifest reads `regime_features: ['regime_structural']`. **It was
already trained on structural labels.** The degeneracy therefore cannot have been introduced by
flipping selection onto them.

This is a long-standing, documented defect. `check_cell_degeneracy`'s own docstring records it,
measured on champion `gk-656f09e2` on 2026-08-02: `strategy_id` one-hot carried **96.78%** of the
model's gain importance; the regime feature carried **0.21%**.

The guard fired now because a *new training run* is checked at train time. The incumbent predates
enforcement. **The refusal is evidence about the gatekeeper, not about the label.**

## Claim 2 — "the only passing strategy did so on 10 random trades"

**FALSE.** The proposed map contains **four** qualifying cells:

| cell | trades | basis |
|---|---|---|
| `xard_ma_cross_daily_open@H1@Trending-Up` | **932** | designated |
| `xard_ma_cross_daily_open@H1@High-Vol` | **160** | designated |
| `weekly_gap_fade@H1@High-Vol` | **135** | designated |
| `holy_grail_pullback@D1@Trending-Down` | 10 | qualified |

The 10-trade cell is the outlier, not the only one.

The fair comparison is *qualified* cells: 3 → 1. But the previous three qualified on **20, 5 and
13** trades, with max drawdowns of 0.02%–1.01% inflating `recovery_factor` to 17–23, and PFs of
13.58 / 8.28 / 6.76. Those are small-sample artifacts. Losing them on better-labelled data is the
measurement working, not degradation.

Two rejection categories improved: `oos_fail` **10 → 0**; `low_confidence` **30/209 (14.4%) →
14/160 (8.8%)**.

## Claim 3 — the map degraded because of the label

**NOT ESTABLISHED — two variables changed at once.** Stage C flipped the label *and* set
`AUTHORITATIVE_ENGINE_FOR_VETTING`, which filters the population to one engine:

| | before | after |
|---|---|---|
| trades | 92,994 (both engines) | **37,494** (v2 only) |
| cells | 209 | **160** |

The trade population fell **60%** because of the engine choice. Comparing map sizes across that is
not a label comparison. `ARCHITECTURE.md` §8 and the `measurement-reviewer` agent both required
these causes be separated before a conclusion was drawn; that did not happen.

## Claim 4 — H1 structural regime is diurnal seasonality

**PARTIALLY TRUE, and the only finding that should change the design.** Measured on
`fact_regime_structural`, H1, by hour of day UTC:

```
High-Vol share:   5.4% (06:00)  →  11.5% (19:00)     2.1x spread
Ranging  share:  27.5% (06:00)  →   9.0% (16:00)     3.1x spread
```

There is a real session signature in the H1 volatility split.

"Acts **purely** as diurnal seasonality" overstates it: ~70% of H1 bars are Trending at every
hour, and the trending labels never consult the volatility z-score — they are ADX + EMA only. The
contamination is confined to the High-Vol / Ranging split, roughly 20–30% of bars.

**Cause, and it is an architecture defect, not an implementation defect.** `ARCHITECTURE.md`
DECIDE-1 specified a ~1-year wall-clock baseline at every granularity. At H1 that compares 03:00
against a mean dominated by London/NY hours, so quiet Asian hours are structurally classified
`Ranging` and active hours `High-Vol`. **Neither option offered in DECIDE-1 addressed intraday
seasonality**; the 252-bar alternative spans all sessions too. The reviewer who wrote that section
owns this omission.

---

## What was not reported and should have been

```
n_unknown_regime: 0     (was 74,971 — 80.62% of trades)
```

**Every trade now carries a regime label.** That was the stated objective of the work order and it
was delivered. It does not appear in the summary.

---

## Corrected verdict

**Do not ship — but not for the reason given, and do not discard the work.**

Genuine blockers:

1. **H1/H4 volatility is diurnally contaminated.** Real, specific, fixable. See Work Order 03.
2. **One genuinely qualified cell, on 10 trades.** Thin, and it should be re-measured after the
   diurnal fix rather than judged now.
3. **The before/after comparison is confounded** and cannot support any conclusion until the
   label change and the engine change are separated.

**Not a blocker, and not caused by this work:** the gatekeeper degeneracy. It is pre-existing,
affects the incumbent equally, and — because the gate runs in **shadow mode** (`shadow_verdict`
recorded, nothing gated on it, owner decision 2026-08-30) — **it does not block trading.** It
blocks having a *meaningful* gate, and it means shadow statistics are uninterpretable. Those are
serious, and they belong in their own work order.

**Not supported by any measurement taken:** that the structural regime provides no predictive
value. The evidence offered for that describes a condition which predates the change and is
present in the incumbent.
