# TO THE TELEMETRY FRONTEND — the Model page

From: System 1 (Computer 1)
Date: 2026-08-23
Data: `gs://scalable-brain-artifacts/telemetry/s1_model.json` — **live now**, refreshed hourly

---

## 1. Summary

The Model page currently shows a training date of "—", a training-data tile of "—", a
column of 0.0% metrics, a calibration curve flatlined on the x-axis, and "No feature
importance weights available for current model."

Roughly half of that was ours and is now fixed. System 1 had never published a feature
importance vector, a reliability curve, or a single classification metric — so there was
nothing for you to render, and the page rendered zeros. That data now exists at
`telemetry/s1_model.json`.

The other half is rendering, and it is the more urgent half, because **the page is
currently making the model look like the opposite of what it is.** Details in §4.

Three tiles — `VERSION: v2.4-live`, `GRANULARITIES: M15, H1, H4, D`, and
`THRESHOLD: 53.5%` — do not come from any System 1 artifact or any payload in
`telemetry/latest.json`. We grepped the whole feed. They appear to be hardcoded.

---

## 2. What the page says vs what is true

| Tile / panel | Page shows | Truth | Owner |
|---|---|---|---|
| MODEL | `2026-08-23T18-12-43Z-1a029257…` (truncated) | that is the **model-set packaging id**, whose date is today. The gatekeeper is `2026-08-20T21-26-20Z-d614163c`, fitted 2026-08-20 21:25:57Z | both |
| TRAINING DATE | `—` | `2026-08-20T21:25:57Z` — it was in the champion manifest the whole time | S2 aggregator |
| TRAINING DATA | `—` | 18,023 joined rows, 5 pairs, D1/H1/H4, 51 strategies, 2024-08-23 → 2026-08-14, base win rate 40.4% | S1 (now published) |
| THRESHOLD | `53.5%` | **no such number exists.** The gate is per-regime: High-Vol 0.60, Trending-Up 0.65, Ranging 0.70, Trending-Down 0.75 | frontend |
| VERSION | `v2.4-live` | not present in any artifact or payload | frontend |
| GRANULARITIES | `M15, H1, H4, D` | `D1, H1, H4`. **System 1 has never modelled M15** — no feature, no regime, no strategy | frontend |
| Calibration Curve | flat at 0%, axis labelled `0.05% … 0.95%` | real curve now published; axis is probabilities 0.05–0.95, not percentages — the labels are off by 100× | both |
| Feature Importance | "none available" | published; one feature carries 86% of the model | S1 (now published) |
| Training column | `0.0%` × 5 | never measured; now measured | S1 (now published) |
| Live (7D) | `0.0%` × 5 | **zero trades in the window.** Last trade was 2026-07-27, 27 days ago | frontend |
| Live (30D) | 25% / 100% / 40% / 35% / 0.0% | computed from **4 trades** (`s3state.performance.trades: 4`) | frontend |

---

## 3. The one field that matters most

```
feature_importance.features[0]  →  strategy_id, 85.99%
```

86% of the model's total gain is the **identity of the strategy that produced the
signal**. A single one-hot column, `strategy_id_12`, is 36.5% on its own. Everything the
gatekeeper was built to reason about — the four causal regime probabilities plus the
regime label — sums to **5.35%**, and `regime_causal` itself is **0.17%**.

This is not a subtle result. The gatekeeper is, in effect, a learned whitelist of strategy
ids wearing a regime model's clothes. It corroborates finding B ("regimes are cosmetic")
from the inside of the model rather than from its outputs.

It also matches what `shipped_approval_by_strategy_regime` in the manifest has been saying
in plain sight: strategy 12 approves at 1.00, strategy 30 at 0.99, and most of the rest at
exactly 0.00.

That panel has said "no weights available" for as long as the page has existed. This is
what it was hiding.

---

## 4. The live columns are being read backwards — please fix this first

The 30-day column reads Precision 25%, Recall 100%. Read naively that says: *the model
fires constantly, catches every winner, and drowns in false positives.*

Measured against the shipped gate on 18,023 backtest trades, the truth is the exact
inverse:

```
approval rate   9.85%      (the model approves about one signal in ten)
precision      73.8%
recall         18.0%
```

It is a **highly selective, high-precision, low-recall** gate. The page is currently
describing an over-predicting model, and that would lead to precisely the wrong remedy —
tightening a gate that is already rejecting 90% of what it sees.

Three separate rendering defects produce that inversion:

**(a) N is not shown.** The 30-day column is 4 trades. Precision 25% is `1/4`; Recall
100% is `1/1`. Neither is a measurement. Every window needs its N beside it, and windows
below a floor (we suggest 30) should render as "insufficient data", not as a number.

**(b) Live recall cannot be computed and will read 100.0% forever.** A rejected signal
never becomes a trade, so live data contains no rejected winners — the denominator of
recall is structurally identical to its numerator. Live recall is 1.0 by construction
whatever the model does. It carries zero information, and F1 inherits the defect. Please
drop both from the live columns, or label them explicitly as backtest-only. The payload
declares this in `metric_semantics.recall.measurable_live: false`.

**(c) Missing renders as 0.0%.** The 7-day column is all zeros because there were no
trades in it — the last trade closed 2026-07-27. "0.0% precision" reads as *the model was
wrong every time*; the truth is *nothing happened*. Same defect on the calibration curve,
where empty probability buckets are plotted at the origin and produce the flat line. The
payload never zero-fills: empty bins carry `n: 0` and `observed_win_rate: null`. Please
render null as a gap, not as a point.

Two more unit errors in that table:

- **Brier is a loss.** Lower is better. It currently sits in a column where every other
  row is higher-is-better, formatted as a percentage and coloured green. A Brier of 0.0
  in a column of missing data reads as a perfect score. The real value is **0.229**.
  `metric_semantics.brier.direction` is `LOWER_is_better`.
- **Expectancy (R) is not a percentage.** It is a ratio of risk. The page shows `0.0%`;
  `s3state.performance.expectancy_per_trade` is **−4.84** (account currency), and the
  shipped gate's backtest expectancy is **+0.0015R** on approved trades against
  **−0.0627R** on all trades.

Finally, `s3state.performance.trades` says 4 and `strategy.live.trades_total` says 14, on
the same page, from the same feed. Whichever window each is over should be stated on the
tile.

---

## 5. What the calibration curve actually shows

Now that it has data, it says something worth acting on. Every populated bin sits **below**
the 45-degree line:

| predicted | observed | n |
|---|---|---|
| 0.157 | 0.063 | 270 |
| 0.260 | 0.194 | 422 |
| 0.382 | 0.314 | 2,244 |
| 0.435 | 0.338 | 8,532 |
| 0.563 | 0.474 | 4,408 |
| 0.636 | 0.569 | 459 |
| 0.739 | 0.649 | 599 |
| 0.834 | 0.798 | 1,089 |

The model is systematically **over-confident by 6–10 points across the entire range**.
That is a real, consistent miscalibration — not noise, and not the flat line the page has
been drawing. Anything downstream that treats the score as a probability (sizing, ranking,
expected-value calculations) is reading a number that is too high everywhere.

---

## 6. New: which live cells can actually trade

`live_map_coverage` cross-references the published regime→strategy map against the
gatekeeper's own per-cell approval rates. Nothing checked that these two artifacts — which
ship in the same model set — agree with each other. They do not:

```
cells = 6    tradeable = 1    always_rejected = 2    unmeasured = 3
```

| regime | strategy | gk approval | state |
|---|---|---|---|
| Trending-Up | 58 xard_ma_cross_daily_open | 0.0000 | **always_rejected** |
| High-Vol | 58 xard_ma_cross_daily_open | 0.0000 | **always_rejected** |
| Trending-Down | 30 liquidity_grab_fade | — | unmeasured |
| High-Vol | 34 macd_divergence | — | unmeasured |
| High-Vol | 55 weekly_day_reversal_ea | — | unmeasured |
| High-Vol | 56 weekly_gap_fade | 0.0901 | measured |

The strategy designated by the owner for Trending-Up is rejected by the gatekeeper 100% of
the time. Three more cells fell below the gatekeeper's `MIN_REGIME_N=30` floor, so the
manifest publishes no rate for them at all — their live behaviour is *unknown*, not safe.

**Of six advertised cells, one can fire.** This is the mechanism behind
`s1_health.emitter`: `never_emitted: true`, `signals_published_total: 0`,
`last_run_outcome: no_signals_generated`, hour after hour. From outside it looks like a
quiet market. It is not.

Please surface `tradeable_cells` on the Model page. It is the one number that says whether
the published model can trade at all.

---

## 7. The shape — and the guarantee attached to it

```
gs://scalable-brain-artifacts/telemetry/s1_model.json     ← read this
```

**The number on the page is now guaranteed to be a number the deployed artifact actually
produced.** That is enforced structurally, not by convention:

- The card is generated when a bundle is packaged and written **into the model set's own
  immutable prefix** as `model_card.json`, listed in `latest.json` with its SHA256
  alongside `champion_model.pkl`. It goes live by the same atomic pointer flip as the
  model.
- **If the card cannot be built, the publish halts.** No model set reaches the pointer
  without its telemetry. An artifact and the payload describing it ship as one unit or not
  at all.
- `telemetry/s1_model.json` is a **mirror of that pinned card — a copy, never an
  independent recomputation.** It cannot drift into describing a model that was never
  deployed, because nothing recomputes it.

So you have two equivalent reads, and can choose:

| | |
|---|---|
| `telemetry/s1_model.json` | simplest. Always the live set's card, plus `as_of` and ages. |
| `latest.json` → the `model_card.json` artifact | authoritative. Verify its SHA256 against the manifest entry like any other artifact. |

`mirror_sha256` in the telemetry copy equals the manifest's `sha256` for `model_card.json`.
If they ever differ, the mirror is stale — we check this hourly and it exits non-zero, but
you can check it too.

```json
{
  "schema_version": 1,
  "as_of": "...",                    // mirror only; the pinned card is clock-free
  "mirror_of": "system1/<version>/model_card.json",
  "mirror_sha256": "...",
  "identity":          { "gatekeeper_version", "trained_at_utc", "model_set_id",
                         "model_set_status", "model_set_published_at", "published_age_sec",
                         "trained_age_sec", "code_commit", "code_dirty",
                         "label_this_page_with" },
  "thresholds":        { "per_regime": {...}, "fallback": 0.75, "scalar": null,
                         "shipped_approval_rate", "shipped_approval_by_regime" },
  "features":          { "all": [12], "regime_features": [5] },
  "feature_importance":{ "available", "method", "features": [...], "top_encoded_columns" },
  "live_map_coverage": { "cells": [...], "tradeable_cells", "n_always_rejected",
                         "n_unmeasured" },
  "training_data":     { "verified": {...}, "unverified": {...}, "warning" },
  "calibration":       { "scope", "reproducible", "in_sample_risk", "n", "brier",
                         "bins": [10] },
  "performance":       { "scope", "reproducible", "in_sample_risk", "n", "n_approved",
                         "approval_rate", "precision", "recall", "f1",
                         "expectancy_r_approved", "expectancy_r_all", "brier" },
  "metric_semantics":  { per metric: definition, direction, format, measurable_live }
}
```

`metric_semantics` exists so a renderer never has to infer a metric's direction, unit or
measurability. Every entry corresponds to a row the page currently draws wrongly. If you
wire one thing from this payload, wire that.

### Staleness reads differently now

`s1_health.json` is write-on-action and its age means "System 1 has not run" — still true,
still not an alert. This object is different: it is pinned to a model set, so its age is
the **model's** age, and `identity.published_age_sec` is the number to render. A card that
does not change is a model that did not change, which is the normal state.

### Reproducibility is declared per field, not assumed

Every number in `training_data.verified` is derived from the final joined frame the model
is scored on, and the block carries `reproducible: true`. Anything that could not be
reproduced from that frame is quarantined in `training_data.unverified`, where each entry
carries `claimed`, `measured`, and an explicit `reproducible: false`:

```json
"unverified": {
  "n_train":       { "claimed": 92994, "measured": 18023, "reproducible": false,
                     "reason": "does not match the final joined frame" },
  "n_fit":         { "claimed": 74395, "measured": null,  "reproducible": false },
  "n_calibration": { "claimed": 18599, "measured": null,  "reproducible": false }
}
```

**Nothing under `unverified` may be rendered as a fact, and nothing may be promoted out of
it.** The training-set size to display is `training_data.verified.rows` — 18,023.

`calibration` and `performance` both carry `reproducible: true` *and*
`in_sample_risk: true`. Those are different claims: the figures are deterministically
reproducible from the joined frame, but that frame is not provably disjoint from the
model's fit set. Read them as a health check on the shipped gate, not as an out-of-sample
claim — the OOS claim lives in `strategy.gatekeeper.oos_uplift`, which you already receive.

Please render the caveat with the number. Both blocks state their own scope in-line.

---

## 8. One thing for whoever builds `strategy.gatekeeper`

That payload carries `model_type`, `dynamic_thresholds`, `oos_uplift` and `n_train` — but
drops `created_at_utc`, `features`, `calibration`, `shipped_approval_rate` and
`shipped_approval_by_regime`, all of which are sitting in `champion_manifest.json`
alongside the fields it does copy.

`created_at_utc` is the training date the page renders as "—". It has been available the
whole time.

---

## 9. Two things still open on our side (not blocking you)

Recorded here so they are not mistaken for dashboard bugs:

1. **`n_train` in the champion manifest is not reproducible.** It claims 92,994 — which is
   exactly the row count of `fact_trade_outcomes` *before* the point-in-time regime join.
   Rebuilding the identical frame today yields 18,023. The artifact itself is intact (the
   approval rate reproduces), so the count is the suspect field. It is quarantined under
   `training_data.unverified` with `reproducible: false` (see §7) rather than printed as a
   figure. **Do not render `n_train` as the training-set size** — use
   `training_data.verified.rows`. Fixing the field at source means changing what `train.py`
   writes into the manifest, which is a retrain, so the flag stands until then.

2. **The gate that should have caught §3 is disabled.** `MAX_DEGENERATE_CELL_SHARE` in
   `gatekeeper/train.py` is set to `1.00`, which permits 100% degenerate cells — and its
   own guard tests (`test_cell_degeneracy.py`, 2 failing) have been red against that
   value. Its docstring describes exactly the failure we measured: *"a gatekeeper whose
   per-(strategy × regime) approval is bimodal 0/1 is a lookup table on strategy identity,
   not a gate."* Re-arming it is an owner decision, not ours to make unilaterally.

Feature importance, reliability bins and operating-point metrics should be written by
`train.py` into the bundle at the next retrain rather than recomputed here. That changes
`champion_manifest.json`'s schema and therefore its digest, so it needs System 2's
acknowledgement before we ship it. Say the word and we will raise it as a contract change.
