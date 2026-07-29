# FIX-S1-010: Gatekeeper Calibration, Manifest Honesty, Model-Set Packaging, and Per-Regime Turnover Guards

**Date:** 2026-07-24
**Target:** `src/system1/gatekeeper/` (MODEL-006), `src/system1/serializer/` (MODEL-007),
`src/system1/scheduler/` (MODEL-009)
**Status:** PARTIALLY LIVE 2026-07-29 — the manifest-honesty and incumbent-resolution work is shipped in bundle `2026-07-29T11-46-42Z-55dacdbf`. The **gatekeeper recalibration is still NOT promoted**: `GATEKEEPER_AUTOPROMOTE` remains unset by design (rollout Stage 1/2), so the live champion gatekeeper is untouched and the ~17.2%→21.6% approval-rate change has NOT been released to Systems 2/3.
>
> *Previous status:* Implemented in the working tree; **nothing promoted, no live pointer flipped**
**Raised by:** Systems 2/3 (findings D2, D7, D11) during the 2026-07-24 cross-system audit

> **Terminology note — read before §1.** Three numbers in this document are easy to
> conflate, and conflating them inverts the finding:
>
> * **Uplift** — the difference in mean R-multiple between approved and rejected trades.
>   This is the gatekeeper's *proof of edge*. It was **never wrong**.
> * **Approval rate (turnover)** — the fraction of signals the gatekeeper lets through.
>   This is what was misreported, by a factor of ~2.
> * **Threshold** — the score above which a signal is approved.
>
> The defect was in the approval rate and the thresholds. The uplift claim
> (0.034924, p = 5e-05, bootstrap-significant) stood then and stands now.

---

## 1. The Defect

### 1.1 D7a — Threshold/model transplant (the root cause)

`train.py` shipped `dynamic_thresholds = wf["thresholds"]` — the per-regime threshold map
calibrated on the **final walk-forward fold's validation split** — attached to a model
refit on the **entire frame**. Those are two different estimators with two different score
distributions. The thresholds therefore landed at an arbitrary, uncontrolled point on the
shipped model's distribution.

This is a **calibration transplant, not in-sample contamination.** The distinction decides
the remedy: contamination is cured by holding data back, whereas a transplant is only
cured by calibrating against the artifact that actually ships. Holding out data without
recalibrating on the shipped model would have left the defect fully intact.

Measured on the live 2026-07-05 champion, scoring all 134,520 trades:

| Quantity | Manifest advertised | Actual (shipped artifact) |
|---|---|---|
| **Approval rate** | 0.3379 | **0.1723** |

The manifest's `oos_approval_rate` was a property of the *walk-forward fold models* — it
was legitimate evidence for the uplift claim — but consumers reasonably read it as the
shipped model's behaviour, and it was ~2× reality.

The transplant also scrambled the per-regime **ordering**, not just the level:

| Regime | Live threshold | Approval | Mean R (point estimate) |
|---|---|---|---|
| Trending-Down | 0.60 | 11.1% | 0.4876 |
| Ranging | 0.60 | 11.7% | 0.4414 |
| High-Vol | 0.45 | 48.0% | 0.4213 |
| Trending-Up | 0.50 | 42.2% | 0.3195 |

Ranging carries ~95% of live capital and received the tightest gate.

### 1.2 D7b — Turnover band never bound on the shipped artifact

`is_degenerate()` was applied only to the walk-forward aggregate (0.3379), never to the
shipped model's real rate (0.1723). The `[MIN_TURNOVER, MAX_TURNOVER] = [0.05, 0.60]`
business rule was therefore not enforced on the thing being published.

### 1.3 D7c — Latent per-regime starvation hole

Even once enforced, an **aggregate** band check permits a single regime to starve to zero
approval — or saturate — while the overall figure sits comfortably mid-band. A regime at
zero approval is a market condition the system silently stops trading, with nothing in the
manifest or logs recording it.

**Not observed to fire.** On the 2026-07-24 recalibration the thinnest regime
(Trending-Up) held **6.6%** on the calibration tail, inside the band. This closes a latent
gap, not a live failure.

> An earlier draft of this analysis reported Trending-Up at 4.08% and treated it as an
> observed starvation. That figure was measured on the **full frame**, which includes the
> 80% the model was fit on, and is the wrong basis for a guard whose whole purpose is to
> measure held-out behaviour. Recorded here because the same mistake is easy to repeat.

### 1.4 D7d — The gatekeeper was trained every cycle and never shipped

`orchestrator._gatekeeper_metrics()` ran the trainer in dry-run to harvest the uplift that
feeds the `oos_uplift_ok` gate. `_default_promote()` then published only the
regime/weights bundle — `SOURCES` does not contain the gatekeeper — and
`publish_gatekeeper.py` was a manual entry point nothing called.

Every retrain therefore trained a gatekeeper, used its uplift to authorise a promotion,
and discarded it. Result: the live champion (2026-07-05) drifted two weeks behind the live
strategy map (2026-07-19).

### 1.5 D2 — No governed writer for the top-level `latest.json`

System 2's downloader (EXEC-001) reads a top-level `latest.json` naming all seven
artifacts of the live model set. **No code in System 1 wrote it.** It was hand-authored,
and on 2026-07-24 still advertised `model_set_id 2026-07-01T12-56-32Z_gk-656f09e2`
(`published_at 2026-07-10T00:00:00Z`) while `system1/latest.json` had already moved to the
2026-07-19 bundle.

Any consumer following the specification was loading a model set three weeks and two
promotions stale. Note the shape of this failure: the per-bundle publish contract
(upload → SHA256 verify → flip) was intact and working the entire time, and was defeated
by a hand-maintained pointer sitting **above** it.

### 1.6 D11 — `beats_incumbent` silently stopped comparing

The 2026-07-19 retrain log records:

```json
"incumbent": {},
"gates": { "beats_incumbent": true, ... }
```

The gate passed because there was nothing to compare against, via its documented
first-publish fail-open branch — not because the candidate beat anything.

Cause: `serialize.MODEL_PREFIX = "system1"` made `_incumbent()` read
`system1/latest.json`, but the previous bundle had been published at the **bucket root**
(`2026-07-01T12-56-32Z/`). Bucket listing confirms it: root-level prefixes include
`2026-07-01T12-56-32Z`, while `system1/` contained only the 07-19 bundle.

A storage-layout migration silently reset the regression gate, and the live model was
promoted without ever being compared to its predecessor.

---

## 2. The Resolution

### 2.1 Calibrate against the shipped artifact (`train.py`)

The most recent `CALIBRATION_FRACTION` (0.20) of the time-sorted frame is held out. The
shipped model is fit on the head; the shipped thresholds are calibrated on the held-out
tail **using that model's own scores**.

This costs training data and buys thresholds that are calibrated, out-of-sample, against
the artifact that ships. That trade is correct: a marginally better model with wrong
thresholds is worse than a marginally weaker model with right ones.

### 2.2 Manifest honesty

| Key | Meaning |
|---|---|
| `shipped_approval_rate` | Approval rate of **this bundle's artifact**, on held-out data |
| `shipped_approval_by_regime` | Same, per regime |
| `calibration{}` | Method, fraction, `n_fit`, `n_calibration`, guard settings |
| `oos_uplift.oos_approval_rate` | Retained, now tagged `approval_rate_scope: walk_forward_fold_models_not_shipped_artifact` |

Consumers sizing or capacity-planning off an approval rate must read
`shipped_approval_rate`. The old key is preserved so existing readers do not break, but is
now self-describing about what it measures.

### 2.3 Turnover band enforced on what ships, per regime

`is_degenerate()` now also runs against `shipped_approval`, and `check_regime_turnover()`
fails closed on **any populated regime** outside `[0.05, 0.60]`, raising
`GatekeeperRefused`.

Regimes below `MIN_REGIME_N = 30` calibration-tail rows are reported but not guarded: they
receive the fallback threshold anyway, and an approval rate estimated from a handful of
rows is noise. Failing a run on it would be a coin flip, not a safety guarantee.

**Policy:** block the retrain rather than ship a degenerate policy.

### 2.4 Ship the audited artifact (`promote.py`, `orchestrator.py`)

`promote_proposed()` promotes the existing dry-run bundle to champion in place,
re-verifying its SHA256 map first and refusing a tampered bundle.

It deliberately does **not** retrain. A retrain would publish a model whose uplift is not
the number the deployment gate approved — the fit is not bit-reproducible across runs, so
the shipped artifact would carry an unaudited edge claim.

### 2.5 Governed model-set packaging (`publish_model_set.py`, new)

The top-level manifest is now a **pure function of the two sub-pointers**:

1. read `system1/latest.json` and `models/gatekeeper/latest.json`
2. resolve each to its immutable versioned prefix and enumerate artifacts
3. verify every object exists; read SHA256 **from the backend**, so the manifest describes
   what a consumer will actually download
4. `atomic_pointer_update("latest.json", ...)` **last**

Coherent by construction: it can only ever describe what the sub-pointers already hold. If
a gatekeeper publish is refused, it packages the new System-1 bundle with the still-live
gatekeeper — which is exactly what is live. It never invents a pairing. An incomplete set
(any artifact missing) aborts, because a consumer's own verification would otherwise fail
mid-download after it had discarded its staging copy.

### 2.6 Incumbent resolution across the prefix migration (`orchestrator.py`)

`_incumbent()` falls back to the top-level model set when the prefixed pointer is absent,
and returns an explicit `resolution`:

| Value | Meaning |
|---|---|
| `prefixed` | Found at `{MODEL_PREFIX}/latest.json` — the normal path |
| `legacy_model_set` | Recovered via the top-level manifest across a layout migration |
| `absent` | Genuinely nothing published; **only here is fail-open correct** |

`resolution` is recorded in the retrain log. A `beats_incumbent: true` beside
`"absent"` is now visibly distinguishable from a real comparison — previously the 07-19
promotion looked identical to a genuine pass.

---

## 3. Verification

Recalibrated dry-run, 2026-07-24 (`models/proposed_champion_*`; live champion untouched
and SHA-identical to its 07-05 state):

| | Manifest claims | Actual (held-out tail) | Error |
|---|---|---|---|
| **Before** (07-05 champion) | 0.3379 | 0.1723 | **+96% overstated** |
| **After** (recalibrated) | 0.2160 | 0.2160 | **exact** |

Scoring the recalibrated model on the *full* frame gives 0.2421. That residual gap is
expected and in the safe direction — the full frame includes the training portion, where
the model is overconfident. The published figure is the conservative one.

Per-regime on the calibration tail (n = 26,904), all inside the band:

| Regime | n | Threshold | Approval |
|---|---|---|---|
| High-Vol | 1,450 | 0.50 | 0.3959 |
| Ranging | 13,420 | 0.60 | 0.3052 |
| Trending-Down | 9,021 | 0.60 | 0.1043 |
| Trending-Up | 3,013 | 0.60 | 0.0660 |

**Tests:** 23 new — 19 across `test_promote_proposed.py`, `test_regime_turnover.py` and
`test_publish_model_set.py`, plus 4 incumbent-fallback and staging-flag cases in
`test_scheduler.py`. Full suite: **163 passing**. Two failures in
`attribution/tests/test_attribute_oos.py` are pre-existing `layer0` import breakage
(`TrendEMAADXStrategy`), untouched by this fix. `black` clean; the mypy
"source file found twice" error reproduces on untouched modules and is a pre-existing
path-configuration issue.

---

## 4. Structural Observation: Regime Conditioning

Honest calibration collapsed the per-regime thresholds to **0.60 everywhere except
High-Vol (0.50)**, from the previous scrambled 0.45 / 0.50 / 0.60 / 0.60. When calibrated
against a single model, the per-regime thresholds stop differentiating.

This is a **third independent indication** — after the win-rate and payoff tests — that the
regime variable carries no conditioning edge. The calibration procedure arrives there on
its own.

Recorded for D12. Two caveats against over-reading it:

* The payoff test's per-regime multipliers **all have 95% confidence intervals containing
  1.0** (ε² ≈ 0.016–0.021, barely above the 0.01 "small" floor). The correct conclusion is
  that no regime effect is *resolvable* at n = 79–335, not that a small effect has been
  disproven.
* Strategies whose regime effect does survive effect-size gating are net-negative in
  **every** regime — regime sorts degrees of losing, not winners from losers.

The regime machinery stays in place for now. **This fix does not deprecate it**; that is
D12's decision, and it should be made on the evidence above rather than on this
calibration artifact alone.

---

## 5. Rollout Strategy

The recalibrated gatekeeper raises aggregate approval from **17.2% → ~21.6%**, a real
increase in trade volume for Systems 2/3 to absorb. Promotion is therefore staged, and the
staging is **enforced in code**, not by convention:

| Flag | Default | Gates |
|---|---|---|
| `GATEKEEPER_AUTOPROMOTE` | `false` | Promoting the recalibrated gatekeeper to champion + publishing it |
| `MODEL_SET_AUTOPUBLISH` | `false` | Flipping the top-level `latest.json` |

Without these, the D7d wiring would make the **next scheduled Sunday 00:00 UTC retrain
execute the whole rollout automatically**, undoing Stage 1. A rollout plan that depends on
nobody triggering a retrain is not a rollout plan.

* **Stage 1 — now.** Code applied. Artifacts remain `proposed_champion_*`. Both flags
  unset, so a scheduled retrain rebuilds the bundle and leaves the gatekeeper and the
  top-level pointer alone.
* **Stage 2 — practice window.** Exercise Systems 2/3 against the increased approval
  volume before it reaches live capital. *(Window timing is an operations decision; note
  that the retrain trigger itself is Sunday 00:00 UTC, and any drill should account for
  it.)*
* **Stage 3 — pending sign-off.** Set `MODEL_SET_AUTOPUBLISH=true` first (refreshing a
  stale pointer is independently valuable and lower-risk), then `GATEKEEPER_AUTOPROMOTE=true`
  once sizing behaviour is confirmed stable.

**Open item deliberately not decided here:** `LAYER3_APPROVAL_THRESHOLD=0.20` in System
2's environment. The live champion's minimum score across 134,520 trades is **0.2301** — if
System 2 applies that value as a flat threshold to these scores, it approves **100%** of
signals, which is degenerate by System 1's own definition. This needs confirming against
System 2's actual consumption path before Stage 3; System 1 can see the value but not its
use.

---

## 6. Files Changed

| File | Change |
|---|---|
| `src/system1/gatekeeper/train.py` | Held-out calibration of shipped thresholds; shipped-artifact + per-regime band enforcement; manifest honesty keys |
| `src/system1/gatekeeper/promote.py` | `promote_proposed()` — governed proposed→champion promotion with checksum re-verification |
| `src/system1/serializer/publish_model_set.py` | **New.** Governed writer for the top-level model-set manifest |
| `src/system1/scheduler/orchestrator.py` | Gatekeeper + model-set wired into promote behind staging flags; `_incumbent()` fallback and `resolution` reporting |
| `src/system1/gatekeeper/tests/test_promote_proposed.py` | **New.** 4 tests |
| `src/system1/gatekeeper/tests/test_regime_turnover.py` | **New.** 8 tests |
| `src/system1/serializer/tests/test_publish_model_set.py` | **New.** 7 tests |
| `src/system1/scheduler/tests/test_scheduler.py` | +4: incumbent-resolution + staging-flag tests |
