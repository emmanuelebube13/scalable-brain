# Note to Systems 2 and 3 — regime per strategy per timeframe

**From:** Computer 1 / System 1
**Status:** DRAFT — not sent. Owner sends.
**Re:** a new artifact you can render, and prior art you should not trust

---

## 0. The short version

1. System 1 is publishing a **new** artifact: current regime per strategy, per timeframe,
   per pair — including whether each strategy is currently gated **off**.
2. It is a **separate pointer**. The model-set pointer and the analytics pointer are
   unchanged by this work. Nothing about your existing consumption changes.
3. **The view is yours to build.** Telemetry is your surface. §3 is what we suggest you
   render; it is a proposal, not a spec you owe us.
4. **You are not blocked on us**, and we are not blocked on you.
5. This supports a **trial**, not a promotion. Nothing here is live-tradeable and no
   strategy is being promoted. See §4.

---

## 1. What the artifact carries

Published under its own prefix with its own `latest.json`, following the same contract as
everything else we publish: immutable versioned prefixes, SHA256 verify **before** the
atomic pointer flip, superseded pointer archived.

Per (strategy × granularity × pair):

| Field | Meaning |
|---|---|
| `strategy_key` | string id, e.g. `kiss_h4` |
| `family` | `trend_following` / `mean_reversion` / `breakout` / `unclassified` |
| `granularity` | H1 / H4 / D1 |
| `pair` | instrument |
| `regime_current` | label at the most recent closed bar |
| `regime_source` | `d1_trend` or `hmm_causal` — never absent |
| `as_of_bar_utc` | timestamp of the **bar**, not of publication |
| `is_trading` | whether this strategy's mask enables this regime |
| `mask` | the frozen per-regime enable map |
| `bars_in_regime` | how long the current label has held |

Document level: `status`, `qualification_run_id`, `generated_at_utc`, `schema_version`, `payload_sha256`, `cadence`.

**Two fields we ask you to treat as distinct**, because collapsing them makes a dead feed
look healthy: `as_of_bar_utc` tells you when the market last printed a bar;
`generated_at_utc` tells you when we last published. An old `as_of_bar_utc` over a weekend
is correct. An old `generated_at_utc` is us being broken.

Machine-readable contract ships alongside: `contracts/regime-status-contract.json`.

---

## 2. `regime_source` is not decoration — please surface it

There are two different things in our repo called "the regime" and they are not
interchangeable. The trial routes on the **D1 trend label** (a fixed EMA(50)/EMA(200) rule,
nothing fitted). The **HMM label** is also published for comparison.

We are asking you to display which one produced a given label, because we have measured the
HMM label's coverage and it is severely uneven:

```
H4  AUD_USD  n= 28185 | Up  0.0%  Dn  4.0%  Rng 90.5%  HV  5.5%
H4  EUR_USD  n= 28222 | Up  0.0%  Dn  1.7%  Rng 93.5%  HV  4.9%
H4  GBP_USD  n= 28164 | Up  0.0%  Dn  3.5%  Rng 91.1%  HV  5.4%
H4  USD_CAD  n= 28172 | Up  0.0%  Dn  1.3%  Rng 95.0%  HV  3.8%
H4  USD_JPY  n= 28187 | Up 23.9%  Dn 14.0%  Rng 10.9%  HV 51.2%
```

Every Trending-Up H4 bar in our database belongs to USD_JPY. A dashboard that shows an HMM
label without saying it is the HMM label will read as "the market regime" and mislead.

---

## 3. What we suggest you render

A grid: **strategy × timeframe**, cell coloured by current regime, with an explicit visual
state for *gated off* — a strategy sitting out is the most operationally interesting thing
in the trial and it must not look like "no data".

Suggested affordances, in rough priority:

1. **Gated-off is a first-class state**, visually distinct from both "trading" and "unknown"
2. `regime_source` visible per cell or as a global toggle
3. `bars_in_regime`, so a label that just flipped is distinguishable from a settled one
4. Both timestamps surfaced, with staleness driven by `generated_at_utc`
5. Filter by family
6. `UNKNOWN` rendered as "no opinion / not trading", never as a neutral blank

---

## 4. Prior art — do not port it

`archieved/layer5/frontend/src/components/views/Regimes.tsx` exists and is the closest thing
to this that we have built before. **We reviewed it and recommend against porting it.**
Three reasons, all verified in the source:

- It renders regime **per asset**, with no strategy dimension. `Strategies.tsx` contains no
  regime references at all.
- It has **no timeframe dimension** — its backing query collapses H1 and H4 via
  `MAX(Timestamp) per Asset_ID`.
- Its price/regime overlay is **hardcoded placeholder data**, banded by row index:
  `regime: i < 10 ? 'Trending_HighVol' : i < 20 ? 'Ranging_LowVol' : 'Trending_LowVol'`.
  It was never connected to a real label.

It also uses a different four-label vocabulary (`Trending_HighVol`, `Trending_LowVol`,
`Ranging_HighVol`, `Ranging_LowVol`) which does not match what we publish
(`Trending-Up`, `Trending-Down`, `Ranging`, `High-Vol`, `UNKNOWN`).

Useful as a layout reference. Not useful as a data path.

---

## 5. What this is not

**This is a trial, and a short one.** Its first-week goal is operational — does the
apparatus work end to end — not statistical. A week of D1/H4 bars cannot establish whether
regime-gating improves outcomes, and we will not claim it has.

**No strategy is being promoted.** The route from our research sandbox to a published model
set does not exist; it is scoped as nine gaps in our
`CONTRACT_V2_AND_POSITION_ENGINE.md` §11.3, two of which need agreement with you (the map
schema growing direction and exit fields, and Pub/Sub provisioning). This artifact does not
change that and is not a step around it.

**If the model-set pointer ever changes without a note from us, treat it as an incident.**
Unchanged from our 2026-08-15 notice.

---

## 6. What we need from you

Nothing blocking. Two things when convenient:

1. Tell us if the field set in §1 is missing anything your view would need — cheaper to add
   before you build than after.
2. Tell us your preferred refresh cadence so we can set ours to match, rather than you
   polling an artifact that updates on a different clock.
