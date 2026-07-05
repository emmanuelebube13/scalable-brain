# FIX-XC-001 — Regime label leaks future data into every downstream join (HMM forward-backward posterior)

**Severity:** P0 (look-ahead leakage corrupts Layer-3 training + creates train/serve skew at live inference)
**Status:** Proposed
**Author:** Claude (cross-cutting auditor)
**Date raised:** 2026-06-26
**System:** Cross-cutting (Layer-1/System-1 regime producer → `fact_market_regime_v2` → Layer-3 training, Layer-4 live)
**Risk to live trading:** High — the ML gatekeeper is trained on a feature it cannot honestly reproduce live; the live regime tag for the current bar is not the one training saw.

---

## 1. Executive summary

`fact_market_regime_v2.regime_label` — the regime tag every downstream layer joins on — is produced by a
4-state Gaussian HMM (`src/system1/regime/hmm_regime.py`) whose per-bar label is the **argmax of
`GaussianHMM.predict_proba(...)`**, i.e. the **forward–backward smoothed posterior
`P(state_t | x_1 … x_T)`**. That posterior's backward pass uses **all observations of the whole
instrument history, including bars after `t`**. The model is fit once on the *entire* series (no
walk-forward), so the label at time `t` is a function of data from `> t`.

That label is then (a) one-hot encoded as a **training feature** in the Layer-3 ML gatekeeper, and
(b) read as a live **inference feature / gate input** in Layer-4. This is textbook look-ahead leakage:
the gatekeeper learns on a regime tag that "knows the future," inflating apparent edge in
backtest/validation, and at live time the current bar's smoothed posterior is unavailable/unstable, so
the served regime differs from the trained one (train/serve skew). The downstream point-in-time join is
*correct on the key* (`<= s.timestamp`) but the **value it pulls is non-causal**, so the join cannot
save it.

---

## 2. Evidence

### 2.1 The written label is the non-causal posterior argmax

`src/system1/regime/hmm_regime.py`:

```
278  hmm = fit_hmm(Xs, lengths)            # fit on the FULL series (all bars, all instruments)
279  raw_state = hmm.predict(Xs, lengths)  # Viterbi = global MAP decode over the whole sequence
...
288  probs_state = hmm.predict_proba(Xs, lengths)   # forward-backward posterior P(state_t | x_1..x_T)
```

`assemble_regime_rows` builds `regime_raw` from that posterior, then `regime_smoothed` from `regime_raw`:

```
133  ordered_probs = M.order_probabilities(probs_state, mapping)
137  raw_idx = np.argmax(ordered_probs, axis=1)        # regime_raw = argmax of the SMOOTHED posterior
140  df["regime_raw"] = raw_labels
149  sm = M.persistence_smooth(raw_seq, min_bars=3)    # causal debounce of a non-causal input
153  df["regime_smoothed"] = smoothed_all
```

`write_rows` writes `regime_smoothed` into **both** `regime_label` and `regime_smoothed`
(`hmm_regime.py:188-203`, the 4th positional value `r.regime_smoothed` is `regime_label`). The DB confirms
`regime_label == regime_smoothed` for **841,596 / 841,596 rows (100%)**:

```
label==smoothed: 841596/841596 ;  raw==smoothed: 840362/841596
```

`persistence_smooth` is itself causal (`mapping.py:47-51`), but it is fed `regime_raw`, which is the
forward-backward posterior argmax — so the causal debounce launders a non-causal label. `load_features`
pulls the **entire** price history for a granularity (`hmm_regime.py:62-69`) and the fit/predict run over
all of it; the only "holdout" (`_train_mask`, `_reference_labels`) is used **solely as a stability
*check*** (`process_granularity:282-286`) — it never produces the written labels. There is **no
walk-forward / expanding-window relabelling**, so every written bar sees the full future.

### 2.2 The leaked label is consumed as a model feature

**Layer 3 training** — `src/layer3_ml/training/train_ml_gatekeeper.py`:
```
356  'fmr.Regime_Label AS "Regime_Label"',          # joined at fmr.timestamp = fs.timestamp
611  if "Regime_Label" in df.columns:
613      regime_dummies = pd.get_dummies(df["Regime_Label"], prefix="Regime")   # one-hot → model features
```
The join is exact-timestamp (`build_query_with_contract:302` `fmr."timestamp" = fs."timestamp"`), so the
training row at signal-time `t` is tagged with a future-aware regime.

**Layer 4 live** — `src/layer4_executor/live_pipeline.py`:
```
528  'r.Regime_Label AS "Regime_Label"',
590  SELECT MAX("timestamp") FROM {REGIME_TABLE} ... AND "timestamp" <= s."timestamp"   # PIT join key OK
```
The join *key* is correctly point-in-time (`<=`), which makes the leak insidious: the engineer did the
right thing at the join, but the **value** stored at that timestamp was computed with future data, so the
served feature still leaks (and, for the most-recent bar, is not even stably reproducible without future
bars → train/serve skew).

### 2.3 Why this matters numerically

The HMM is explicitly upweighted on a persistent trend feature (`FEATURE_WEIGHTS["trend_20"]=3.0`,
`hmm_regime.py:49`) precisely to make `Trending-Up/Down` separable. The smoothed posterior therefore
"sees" whether a trend *continued* after `t` — exactly the kind of future information a gatekeeper would
love and must never have. Any validation/Sharpe/expectancy computed with this feature is optimistic by an
unknown, untrustworthy margin.

---

## 3. Root cause

Unsupervised regime *description* (smoothing the whole series for a clean historical narrative) was reused
as a *point-in-time feature* without re-deriving it causally. `predict_proba` (forward-backward) and
`predict` (Viterbi global decode) are both **non-causal by construction**; only `filter`-style
(forward-only) posteriors or an online/walk-forward decode are point-in-time safe. The producer optimised
for low flicker (a smooth picture) at the cost of causality, and no contract test asserts that a regime
tag at `t` is independent of bars `> t`.

---

## 4. Proposed fix

1. **Produce a causal regime label for the feature contract.** Replace the written `regime_label` with a
   forward-only quantity. Options, simplest first:
   - **Forward filtering:** decode with the forward pass only (`P(state_t | x_1..x_t)`) instead of
     `predict_proba`. hmmlearn exposes `score_samples`/`_do_forward_pass`; or run an online
     filter. Keep `regime_smoothed`/`predict_proba` columns for *analytics only*, clearly labelled
     "non-causal — do not use as a feature."
   - **Walk-forward relabelling:** fit on `[0, t)` and label `t` on an expanding/rolling schedule. More
     faithful, more expensive — acceptable as a periodic batch.
2. **Make `regime_label` the causal column** and repoint Layer-3/Layer-4 reads at it. Add a column comment
   / manifest flag distinguishing `regime_label` (causal, feature-safe) from `regime_smoothed`
   (non-causal, analytics-only).
3. **Add a leakage contract test** (cross-cutting): for a held-out tail of history, recompute the regime
   label with and without the future tail present and assert the in-window labels are identical
   (a causal producer is invariant to appended future bars). Fail CI / fail the run otherwise.
4. **Re-train and re-validate Layer 3** on the corrected feature; expect validation metrics to *drop* —
   that drop is the leakage being removed, not a regression.

No schema change is required (reuse columns; only the *value semantics* of `regime_label` change).

---

## 5. Validation plan

- **Leakage invariance test** (the decisive check): `label_causal(history[:k]) == label_causal(history)[:k]`
  for several `k`. The current producer fails this (posterior changes when future bars are added); the fix
  must pass it.
- **Before/after feature-importance + metric diff:** retrain Layer-3 log-only; tabulate AUC/expectancy
  with the leaked vs causal regime feature. A large gap confirms the leak's magnitude.
- **Flicker budget:** confirm the causal label's flicker rate is still acceptable (it will be higher than
  the smoothed one — that is honest).

---

## 6. Rollout / risk

- **Rollout:** producer change is additive (new causal column or recomputed `regime_label`); run it
  log-only, diff distributions, then repoint consumers behind a flag. No live trades until Layer-3 is
  retrained on the causal feature.
- **Risk if not fixed:** every Layer-3 promotion decision and every Layer-4 gate that uses the regime
  one-hot is built on a future-aware feature; live performance will under-deliver versus backtest by the
  size of the leak, and the gatekeeper may approve trades it would reject without the peek.
- **Reversibility:** analytics columns retained; consumers flag-gated. Fully revertible.

---

## 7. One-paragraph summary

The regime tag every layer joins on (`fact_market_regime_v2.regime_label`) is the argmax of an HMM
**forward–backward posterior fit on the entire price history**, so the label at bar `t` is computed using
bars after `t`. It is then one-hot encoded as a Layer-3 training feature (`train_ml_gatekeeper.py:611-613`)
and read live in Layer-4 (`live_pipeline.py:528`). The DB shows `regime_label == regime_smoothed` for 100%
of 841,596 rows, and the producer (`hmm_regime.py:278-288`) uses `predict`/`predict_proba` with no
walk-forward. The downstream `<= timestamp` join is correct on the key but pulls a non-causal value, so it
cannot prevent the leak. Fix: produce a forward-only (causal) regime label, repoint consumers at it, add a
"future-invariance" contract test, and retrain Layer-3 — expecting validation metrics to fall as the
leakage is removed.
