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
- **It compounds with a second defect.** Even if the threshold were wired, the gatekeeper
  currently scores nothing live: `MISSING_FEATURE` applies to every signal because the
  champion trains on `fact_market_regime_v2` columns written retrospectively inside
  completed walk-forward folds, and a live bar has no row there (`run.py:224-233`). Wiring
  the threshold without fixing the feature vector changes nothing observable.

## What was NOT done

Nothing in this document is fixed. The ledger records the gap; it does not close it.
Deliberately out of scope of the ledger change set, because applying the real thresholds
changes what reaches the wire and must be its own change with its own adversarial pass.

## Proposed remediation, in order

1. **Do not start by wiring the threshold.** With `MISSING_FEATURE` universal, it is a
   no-op that looks like a fix. Fix the live feature vector first, or accept that the
   gatekeeper is out of the loop and say so to Systems 2/3 explicitly.
2. Have `Scorer` load its own manifest and return `{score, threshold, regime_key}` so the
   threshold travels with the score instead of being guessed by the caller.
3. Add a fourth outcome — a genuine below-threshold refusal — and extend the ledger's
   `gate1_outcome` vocabulary to match. Only then is a runtime approval rate computable.
4. Until then, `s1_health.json` carries
   `gate1.approval_rate_computable: false` with `approval_rate_blocked_by` naming this
   document, so no consumer derives a rate from an inert gate.

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
