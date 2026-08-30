# FIX-S1-018 — the gatekeeper applies no threshold at inference, so the live gate is inert

**Status:** OPEN (found 2026-08-30) · **Severity:** high · **Author:** Claude (Opus 5), at owner request

---

## Summary

System 1 ships a "regime-aware ML gatekeeper" and Systems 2/3 have been asking for its
runtime approval rate. There is no approval rate to report, because **nothing in the live
path ever compares a score to a threshold.** Every signal the scorer can score is published
regardless of its score. The champion's calibrated per-regime cutoffs are computed at
training time, written into the manifest, shipped in the bundle — and never read again.

This was found while building the Gate-1 signal ledger, which was commissioned to *measure*
the approval rate. The ledger is implemented and now records the evidence below on every
signal; it does not fix this.

## Evidence

**1. The scorer returns no threshold and never loads the manifest.**

`src/gatekeeper/score.py:106-111` — the only success path:

```python
X = self.preprocessor.transform(df)
prob = self.model.predict_proba(X)[0, 1]
return {"status": "scored", "score": float(prob)}
```

`Scorer.__init__` assigns `self.manifest_path` (`score.py:16`) and `_load()`
(`score.py:19-42`) opens only `champion_model.pkl` and `champion_preprocessor.pkl`. There
is no `self.manifest`. Grep confirms no runtime reader of `champion_manifest.json` in the
live path — only `train.py`, `model_card.py`, `analytics/extract.py`, and the serializer.

**2. The consumer hardcodes a placeholder.** `src/signals/run.py`, before this change set:

```python
if score_res["status"] == "scored":
    sig["model_score"] = score_res["score"]
    # What is threshold applied? The global one or strategy specific?
    # Let's say 0.5 default.
    sig["threshold_applied"] = 0.5
```

That value is then stamped onto the wire as `threshold_applied` (`producer.py:119-120`) — a
provenance claim that a threshold was applied when none was.

**3. The real thresholds exist and 0.5 is below every one of them.**
`models/champion_manifest.json` → `dynamic_thresholds`:

```json
{"High-Vol": 0.7999999999999999, "Ranging": 0.75,
 "Trending-Down": 0.6, "Trending-Up": 0.75, "fallback": 0.75}
```

Calibrated in `train.py:293-307` on `regime_structural`, applied in training only
(`train.py:310-318`). So the shipped placeholder would pass everything the calibration says
to reject.

**4. The join is one lookup away and is not made.** The regime key the thresholds are
indexed by is already on the signal dict at the decision point — `sig["regime"]`
(`build.py:448`) and `sig["regime_structural"]` (`build.py:470-471`).

**5. Confirmed from the ledger.** First rows written after this change set:

```
signal            gate1_outcome            threshold_applied  threshold_calibrated
f6f8e1d1-58d2-…   scored                   0.5                0.75
id-unscored       unscored                 None               0.75
id-dropped        dropped_corrupt_feature  None               0.7999999999999999
```

## Why it matters

- **The reported approval rate is undefined, not zero.** An approval rate is
  `scored / (scored + refused)`, and a below-threshold refusal does not exist. The only
  drop in the live path is `NAN_FEATURE:*` — corrupt data, not a verdict. Anything
  computing a rate from the drop count is measuring the data-quality failure rate and
  calling it a model gate.
- **`threshold_applied` on the wire is false.** System 3 receives 0.5 and may reasonably
  read it as the cutoff this decision passed.
- **~~It compounds with a second defect.~~ RETRACTED 2026-08-30 — this was wrong.** The
  original text claimed the gatekeeper scores nothing live because `MISSING_FEATURE` is
  universal, citing `run.py:224-233`. **That comment was stale**: it described the previous
  champion (`gk-656f09e2`), which used `prob_causal_*` / `regime_causal`. The champion live
  since 2026-08-24 needs only `atr_value`, `adx_value`, `regime_structural`, `strategy_id`
  and three features derived from them — and `build.py` already assembles all of them via
  `build_inference_features`. **The live feature vector needs no repair.** See §Measurement.
  The comment has been corrected in code. This is a lesson about trusting a comment over a
  measurement, and it had already propagated into a message sent to Systems 2/3.

## Measurement (2026-08-30) — what applying the threshold would actually do

Scoring works. Every live-map strategy is known to the preprocessor, and every
(pair × granularity) combination produced a score:

```
SCORED 15 / 15   (5 pairs x H1/H4/D1, strategy 58, live data 2026-08-30)
EUR_USD H1 Trending-Down score=0.4380 thr=0.6000 -> REFUSE
GBP_USD H1 Trending-Up   score=0.4409 thr=0.7500 -> REFUSE
...
```

The live scores cluster **0.42–0.46**; the calibrated cutoffs are **0.60–0.80**. Per
strategy, on EUR_USD H1 across all four regimes:

| Strategy | Best score | Passes its calibrated cutoff? |
|---|---|---|
| 30 `liquidity_grab_fade` (qualified) | 0.7568 | **Yes** — in Trending-Up/Down/Ranging |
| 34 `macd_divergence` (qualified) | 0.6812 | Only in Trending-Down, where it is **not routed**; refused in High-Vol, where it is |
| 17, 36, 43, 55, 56, 58 | 0.2174–0.5731 | **No** — refused in every regime |

**4 of 32 (strategy × regime) cells clear the bar. Of the 15 cells actually in the live
map, 1 would pass** — strategy 30 in Trending-Down.

This is not a surprise and not a bug: the champion's own `shipped_approval_rate` is
**0.079**, so it was calibrated to approve ~8% of what it sees. **Applying the threshold
correctly therefore cuts live signal flow by roughly 93%.**

That makes the remediation an owner decision, not a code change. The gate is currently
inert; switching it on is a large, deliberate reduction in trading activity, and it must be
chosen rather than shipped as a bug fix.

## What was NOT done

Nothing in this document is fixed. The ledger records the gap; it does not close it.
Deliberately out of scope of the ledger change set, because applying the real thresholds
changes what reaches the wire and must be its own change with its own adversarial pass.

## Proposed remediation, in order

**Step 0 is a decision, not code.** Switching the gate on removes ~93% of live signals and
leaves essentially one cell trading (strategy 30 in Trending-Down). That may well be
correct — it is what the calibration says — but it is a trading-activity decision and needs
the owner, and a notice to Systems 2/3 before their fill rate collapses without explanation.

Then, in order:

1. Have `Scorer` load its own manifest and return `{score, threshold, regime_key}`, so the
   threshold travels with the score instead of being guessed by the caller. This is the
   actual defect and it is small.
2. Add a genuine below-threshold refusal outcome, and extend the ledger's `gate1_outcome`
   vocabulary to match. **Only then is a runtime approval rate computable** — and at that
   point it becomes computable immediately, because scoring already works.
3. Run it in **shadow mode first**: keep publishing as today, but record in the ledger what
   the gate *would* have decided. One week of `threshold_calibrated` vs `model_score` rows
   gives a measured refusal rate on real traffic before anything is switched. The ledger
   already carries both fields, so this needs no new plumbing.
4. Reconcile the unpublished-champion drift (O-17) **before** switching the gate on. The
   thresholds being applied would come from a manifest describing a model Systems 2/3 have
   never seen.
5. Until step 1 ships, `s1_health.json` carries `gate1.approval_rate_computable: false`
   with `approval_rate_blocked_by` naming this document, so no consumer derives a rate from
   an inert gate.

## Related

- **FIX-S1-010** — the same class of defect one layer up: `oos_approval_rate` was a
  property of walk-forward fold models being read as the shipped artifact's behaviour.
  That fix introduced `shipped_approval_rate` and `approval_rate_scope`.
- **FIX-S1-016** — the status-conflation defect this one rhymes with: a field meaning one
  thing read as though it meant another, with no error anywhere.
- **Live scorer runs an unpublished champion** (separate, open): `Scorer` loads a
  directory rather than a pointer, so `models/champion_model.pkl`
  (`23b6d4ca…`) is not the published artifact (`8845b442…`, version
  `2026-08-20T21-26-20Z-d614163c`) whose id the wire stamps as `bundle_id`. The ledger now
  records `gatekeeper_model_sha256` beside `bundle_id` so the divergence is visible per
  signal.
