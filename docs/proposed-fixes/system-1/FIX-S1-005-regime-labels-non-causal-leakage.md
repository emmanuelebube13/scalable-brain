# FIX-S1-005 — Regime labels are non-causal (in-sample HMM fit + forward-backward smoothing), so the "point-in-time" regime join leaks the future into attribution and the gatekeeper's OOS test

**Severity:** P1 (look-ahead leakage; corrupts MODEL-004 attribution and the validity of MODEL-006's OOS uplift — the gatekeeper's core "does it add edge?" proof. Arguably P0.)
**Status:** Proposed
**Author:** Claude (System-1 audit)
**Date raised:** 2026-06-26
**Scope:** `src/system1/regime/hmm_regime.py` (fit + label emission), `src/system1/attribution/attribute.py`
(`tag_regime_at_entry`), `src/system1/gatekeeper/train.py` (`build_frame`, walk-forward OOS uplift).
**Affected pipeline:** MODEL-003 (regime) → MODEL-004 (attribution) and MODEL-006 (gatekeeper).
**Risk to live trading:** Indirect but material — a gatekeeper whose OOS edge is partly an artifact of leakage
can be promoted and then filter live signals with less (or no) real edge.

---

## 1. Executive summary

The regime label written to `fact_market_regime_v2.regime_smoothed` (and the four `prob_*` columns) is
produced by a single Gaussian HMM **fit on the entire price history at once**, then decoded with
`predict` / `predict_proba`, which use **forward-backward smoothing over the whole sequence**. Both the model
parameters *and* the per-bar posteriors at time `t` therefore depend on bars **after** `t`. Downstream,
`attribution.tag_regime_at_entry` and `gatekeeper.build_frame` join each trade to the regime "at entry" with a
`merge_asof(direction="backward")` and call this a **point-in-time** join. The join correctly forbids using a
regime *bar* later than entry — but the *value* sitting on that bar already encodes the future, so the
"point-in-time" guarantee is cosmetic. The gatekeeper then feeds these leaked regime features into a
**walk-forward OOS uplift test** that is supposed to prove the model adds edge on unseen data; the test is
contaminated, so its headline number (`oos_uplift = 0.0319 R, p = 0.0001`) overstates the real edge.

---

## 2. Evidence

**A. The production model is fit on all data and decoded with smoothing** (`hmm_regime.py`):

```python
Xs = scaler.fit_transform(df[FEATURE_NAMES]...)   # fit on FULL history (line 264)
hmm = fit_hmm(Xs, lengths)                          # fit on FULL history (line 278)
raw_state = hmm.predict(Xs, lengths)                # Viterbi over whole sequence
probs_state = hmm.predict_proba(Xs, lengths)        # forward-backward posteriors (line 288)
```

`predict_proba` returns `P(state_t | x_1..x_T)` — the smoothed posterior over the **entire** sequence — and
`predict` (Viterbi) is a global most-likely-path decode. `regime_raw = argmax(prob_*)` and the
3-bar-smoothed `regime_smoothed` are derived from these, then upserted to `fact_market_regime_v2` and consumed
as the point-in-time regime.

**B. Demonstration that the posterior at a past bar moves when only *future* bars change** (the definition of
look-ahead). Fitting a 2-state Gaussian HMM, then changing only bars `t ≥ 81` and re-decoding:

```
Max posterior change at a bar t < 80 caused purely by FUTURE bars: 0.0225 (at t=79)
count of bars t<80 whose posterior moved >0.01 due to future bars : 3
```

The smoothed posterior at a bar is provably a function of later bars. (The dominant leak is even simpler: the
HMM means/covariances/transitions used to label *every* bar were estimated from the whole history, including
data far in the future of any given trade.)

**C. The downstream joins call this "point-in-time."**
- `attribution.attribute.tag_regime_at_entry` (docstring: *"Point-in-time regime tag per trade"*) merges on
  `regime bar <= entry_time`.
- `gatekeeper.train.build_frame` (docstring: *"joined point-in-time (regime bar <= entry)"*) does the same and
  uses `prob_trending_up/down/ranging/high_vol` + `regime_smoothed` as model features
  (`champion_manifest.json` `regime_features`).

Both restrict the *bar* but not the *information content* of the label.

**D. The gatekeeper's OOS validity claim rests on these features.** `gatekeeper.train._walk_forward` does an
expanding-window split and reports `oos_uplift = 0.0319 R`, `p = 0.0001`, `significant = True` over
112,100 OOS trades (`champion_manifest.json`). 5 of the 12 model features and all per-regime thresholds derive
from the leaked regime labels, so the "out-of-sample" trades are scored with features that saw beyond the OOS
window. The model is "regime-aware" by design, so this is not a peripheral feature — it is the headline.

**E. The code already half-knows.** `hmm_regime` builds a *train-only* reference model
(`_reference_labels` / `aligned_accuracy`, `ACCURACY_GATE = 0.70`) to check holdout **stability** — but the
labels actually **written to the DB and consumed downstream are from the full-history fit**, not the
walk-forward one. The stability gate guards the artifact's robustness; it does not make the consumed labels
causal.

---

## 3. Root cause

Regime labeling is treated as an *offline descriptive* task (best global fit of states to the whole series),
but the labels are then consumed as if they were an *online causal* signal available at each trade's entry.
HMM smoothing (`predict_proba`) and Viterbi (`predict`), plus the single full-history fit, all use future
information by construction. There is no causal/filtered inference path (`P(state_t | x_1..x_t)` only) and no
walk-forward re-fit feeding the labels that attribution/gatekeeper consume.

---

## 4. Proposed solution (high level — needs design)

1. **Emit causal regime labels for training/attribution.** Two options, increasing rigor:
   - **Filtered (online) inference:** label bar `t` with the **forward-only** filtered posterior
     `P(state_t | x_1..x_t)` (hmmlearn exposes `_do_forward_pass`/score machinery; or use the forward
     variable), never the smoothed `predict_proba`. Drop Viterbi for the consumed label.
   - **Walk-forward re-fit:** fit the HMM on an expanding in-sample window and label only the next unseen
     window, rolling forward — so a bar's label never used data beyond it (mirrors FIX-S1-002's walk-forward
     remedy and reuses the existing `_train_sequences` scaffolding).
2. **Persist both** a causal label (for ML/attribution consumption) and, if useful, the smoothed label (for
   *post-hoc* reporting only), clearly distinguished in the schema so no consumer can accidentally train on the
   smoothed one.
3. **Re-run MODEL-004 and MODEL-006 on the causal labels** and re-measure: expect the attribution per-regime
   metrics to shift and the gatekeeper's OOS uplift to **shrink** toward its true value — that shrinkage is the
   leakage being removed.
4. **Add a leakage regression test:** assert that changing bars strictly after `t` does not change the emitted
   label/posterior at `t`.

---

## 5. Validation plan

- **Unit/property:** emitted causal posterior at `t` is invariant to any mutation of bars `> t` (the test in
  §2B, inverted into an assertion).
- **Re-run diff:** MODEL-006 OOS uplift on causal vs smoothed labels — quantify the inflation; if uplift
  collapses to ~0 or insignificant, the current champion's edge was substantially leakage.
- **Attribution diff:** compare per-regime metric distributions (smoothed vs causal) to size the impact on the
  regime→strategy map.

---

## 6. Rollout, risk, non-goals

- **Sequencing:** do this alongside / after FIX-S1-002 (both are leakage/OOS-honesty fixes and share the
  walk-forward machinery). Changes how labels are produced, so re-run regime → attribution → gatekeeper.
- **Risk:** none to live trading during the work (incumbent bundle stays authoritative). The cost is honesty:
  the new numbers will look worse, which is the point.
- **Non-goal:** changing the regime *feature set* or the number of states; only the causality of the emitted
  label. (Whether regimes discriminate at all is FIX-S1-003.)

---

## 7. One-paragraph summary for a fast reviewer

`fact_market_regime_v2.regime_smoothed` and its `prob_*` columns come from one HMM fit on the *whole* price
history and decoded with forward-backward smoothing / Viterbi, so a bar's regime label depends on later bars
(demonstrated: changing only future bars shifts a past bar's posterior). Attribution and the ML gatekeeper join
trades to this label and call it "point-in-time," but the join only bounds the bar time, not the future
information baked into the label — so the gatekeeper's walk-forward "OOS uplift" (0.0319 R, p=0.0001) is
contaminated and overstates real edge. Fix: emit a **causal** regime label (forward-only filtered posterior, or
walk-forward re-fit) for everything ML/attribution consumes, keep the smoothed label for reporting only, add a
"future bars can't change a past label" regression test, and re-measure — the gatekeeper's uplift should shrink
toward its honest value.
