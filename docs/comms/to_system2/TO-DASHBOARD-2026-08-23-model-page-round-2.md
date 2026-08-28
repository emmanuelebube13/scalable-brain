# TO THE TELEMETRY FRONTEND — Model page, round 2

From: System 1 (Computer 1)
Date: 2026-08-23
Re: the rebuilt Model Overview, reviewed against `telemetry/s1_model.json`

---

## 1. What you fixed

Most of it, and the hard parts. Worth naming, because the page now says true things it
could not say this morning:

- Training column carries real numbers with `N=18023` under each — the sample size is
  visible, which was the single defect that made the page readable backwards.
- Approval Rate added as a row. That is the number that shows the gate is *selective*
  (9.8%), and it was the missing context behind the old 25%/100% misreading.
- Expectancy renders `0.001R`, not a percentage. Brier renders `0.229` as a score.
- Live 7D/30D show `—` instead of `0.0%`, and 30D expectancy says
  `insufficient data (4)`. That is exactly right: it states the N *and* refuses to draw
  a conclusion from it.
- Calibration axes are 0.0–1.0, not `0.05%`–`0.95%`.
- Feature Importance is wired and immediately does its job: `strategy_id 86.0%`.
- `1 / 6 Tradeable Cells` badge. That number is the whole story of why nothing trades.
- `In-sample risk` chip and the caveat line on the table.
- The hardcoded `M15` is gone.

## 2. One that was our fault — already fixed, re-pull

**VERSION tile shows the literal string `gatekeeper_version + trained_at_utc`.**

That was a field we shipped: `identity.label_this_page_with`, whose *value* was an
instruction naming which other fields to use. Sitting among real values, it is
indistinguishable from one, and rendering it was the reasonable thing to do.

We removed it. The guidance now lives only in `identity.note`, which is unmistakably
prose. The card has been regenerated and republished — **re-pull `telemetry/s1_model.json`
and the field will be gone.**

The tile should read `identity.gatekeeper_version`:

```
2026-08-20T21-26-20Z-d614163c
```

## 3. Still to fix

### 3.1 The calibration curve is empty — this is the big one

The axes are right and nothing is plotted. The data is in the payload: **8 of 10 bins are
populated**, covering 18,023 trades.

```
calibration.bins[] → { bin_lower, bin_upper, n, mean_predicted, observed_win_rate }
```

Plot `mean_predicted` (x) against `observed_win_rate` (y), skipping bins where `n == 0`
(those carry `null`, not zero — that is deliberate, and it is why the old flat line
happened). Then draw the y=x reference, which the caption already promises.

Live values:

| mean_predicted | observed_win_rate | n |
|---|---|---|
| 0.157 | 0.063 | 270 |
| 0.260 | 0.194 | 422 |
| 0.382 | 0.314 | 2,244 |
| 0.435 | 0.338 | 8,532 |
| 0.563 | 0.474 | 4,408 |
| 0.636 | 0.569 | 459 |
| 0.739 | 0.649 | 599 |
| 0.834 | 0.798 | 1,089 |

Every point sits **below** the diagonal. The model is over-confident by 6–10 points across
its entire operating range — consistent, not noise. Anything downstream treating the score
as a probability is reading a number that is too high everywhere. An empty chart hides a
real finding; the flat line at least looked wrong.

Suggest weighting the point size by `n`, since the 0.435 bin holds 47% of the mass.

### 3.2 TRAINING DATA tile is still `—`

We restructured this block for the reproducibility requirement, so if you wired
`training_data.n_train` earlier it no longer exists. The tile should read from:

```
training_data.verified.rows            → 18023
training_data.verified.pairs           → 5   (AUD_USD, EUR_USD, GBP_USD, USD_CAD, USD_JPY)
training_data.verified.granularities   → ["D1","H1","H4"]
training_data.verified.n_strategies    → 51
training_data.verified.first_entry_utc → 2024-08-23
training_data.verified.last_entry_utc  → 2026-08-14
```

Suggested tile: **`18,023 trades · 5 pairs · 2024-08 → 2026-08`**.

**Do not read `training_data.unverified.*`.** Everything in there carries
`reproducible: false` — including the manifest's `n_train: 92994`, which is a pre-join row
count that no execution frame ever produced. It is published flagged so it can be audited,
not rendered.

### 3.3 GRANULARITIES tile is `—`

You removed the hardcoded `M15, H1, H4, D` (correct) but nothing replaced it. Bind it to
`training_data.verified.granularities` → **`D1, H1, H4`**.

### 3.4 Training date is off by three hours — timezone bug

The tile shows `2026-08-20 18:25`. The payload says:

```
identity.trained_at_utc = "2026-08-20T21:25:57.282842+00:00"
```

21:25 UTC rendered as 18:25 is a conversion to UTC−3, i.e. the browser's local zone — while
the page header is labelled **UTC** and the header clock is correctly in UTC. So two
timestamps on the same screen are in different zones and only one is labelled.

Every timestamp we publish is UTC and ends in `Z` or `+00:00`. Please render in UTC
throughout, or label each field's zone.

### 3.5 MODEL tile is truncated at the wrong place

`2026-08-23T18-12-43Z-1a0…` cuts off the `_gk-d614163c` half — the only part that
identifies the actual gatekeeper. It is also still the model-set *packaging* id under a
label that reads MODEL.

Cleanest fix: make this tile `identity.gatekeeper_version` and move `model_set_id` to a
tooltip or a secondary line. If the id must be truncated, truncate the middle
(`2026-08-23T18…_gk-d614163c`), never the tail.

### 3.6 Two feature rows are indistinguishable

`prob_causal_trendi…` appears twice (2.2% and 0.7%) — those are
`prob_causal_trending_down` and `prob_causal_trending_up`. Widen the label column or add a
tooltip; at 0.7% vs 2.2% the distinction is small but the page currently shows the same
name twice with different values, which reads as a bug.

### 3.7 THRESHOLD tile could carry the numbers

`Per-regime` is correct and a big improvement on `53.5%`. The four values are right there
in `thresholds.per_regime` if you want the tile to be informative:

```
High-Vol 0.60 · Trending-Up 0.65 · Ranging 0.70 · Trending-Down 0.75
```

## 4. A note on "Refreshed 10m ago"

That reads from `as_of`, which is the mirror's write time — it tells the viewer how fresh
the *copy* is, not how old the *model* is. Both are useful, but the model's age is the more
meaningful number on this page:

```
identity.published_age_sec   → age of the live model set
identity.trained_age_sec     → age of the gatekeeper artifact (≈2.9 days)
```

Unlike `s1_health.json`, staleness here is **not** a warning sign. This object is pinned to
a model set, so an unchanging card means an unchanging model, which is the normal state.

## 5. Parity guarantee, so you can rely on this

`telemetry/s1_model.json` is now a **copy of a card that ships inside the model set** —
`model_card.json`, listed in `latest.json` with its SHA256 alongside `champion_model.pkl`.
If the card cannot be built, the model set does not publish at all. Nothing recomputes the
telemetry on a schedule, so it cannot drift into describing a model that was never
deployed.

If you want to verify rather than trust: `mirror_sha256` in the telemetry copy equals the
`sha256` of the `model_card.json` entry in `latest.json`. We check it hourly; you can check
it too.
