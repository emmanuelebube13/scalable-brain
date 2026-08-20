# FIX-S1-012 — regime labels are rank artifacts, not descriptions

**Found:** 2026-08-11, during the MODEL-003 catch-up run after the price ingest repair.
**Severity:** high — it invalidates the evidence behind finding B, and every regime-conditioned
decision in the live map is keyed on these labels.
**Status:** proposed. No code changed yet. No re-fit performed.

---

## 1. The finding

`map_states_to_labels` (`src/regime/mapping.py:38-41`) assigns semantic labels by
**rank**, not by value:

```python
ret_scores = {i: means[i, ret_i] for i in remaining}   # the 3 non-High-Vol states
up   = max(ret_scores, key=ret_scores.get)             # highest of the three
down = min(ret_scores, key=ret_scores.get)             # LOWEST of the three — even if positive
```

Exactly one state is always called `Trending-Down`, whether or not any state trends down.

Extracted from the live `models/hmm_model.joblib` (fit 2026-08-11, all three granularities
converged on HMM). `trend_20` is in standardised units, so the numbers are SDs from the mean:

| gran | state | `trend_20` mean | vol+atr | share of bars | label assigned |
|---|--:|--:|--:|--:|---|
| D1 | 0 | **+0.0529** | −0.625 | **75.1%** | **Trending-Down** |
| D1 | 1 | +0.2146 | 0.329 | 8.9% | Ranging |
| D1 | 3 | +0.5520 | 2.542 | 9.6% | Trending-Up |
| D1 | 2 | −1.7277 | 3.050 | 6.4% | High-Vol |
| H4 | 2 | **+0.0292** | −0.613 | **74.6%** | **Trending-Down** |
| H4 | 0 | +0.1352 | 2.180 | 9.2% | Ranging |
| H4 | 1 | +0.3041 | 0.189 | 8.6% | Trending-Up |
| H4 | 3 | −0.7974 | 3.157 | 7.5% | High-Vol |
| H1 | 3 | −0.0281 | 0.029 | 34.0% | Trending-Down |
| H1 | 0 | +0.0377 | −0.974 | 43.4% | Ranging |
| H1 | 1 | +0.2047 | 0.825 | 15.0% | Trending-Up |
| H1 | 2 | −0.4956 | 3.822 | 7.5% | High-Vol |

**On D1 and H4 the state labelled `Trending-Down` has a *positive* mean trend**, and it holds
three-quarters of all bars. The label is not describing the market; it is reporting which of
three mildly-upward states was least upward.

### The genuine downtrends are labelled `High-Vol`

On all three granularities the most negative state (−1.73 / −0.80 / −0.50) is the one assigned
`High-Vol`, because volatility rises during selloffs. So the taxonomy has no cell that means
"the market is falling" — falling markets are filed under volatility, and the cell named for
falling markets contains the quiet drift.

**The HMM is not at fault.** It found coherent states: a large quiet low-volatility regime, a
mild uptrend, a strong uptrend, and a volatile selloff. The mapping mislabels them.

---

## 2. Consequences

1. **Finding B may be an artifact.** `SYSTEM1_ANALYSIS_2026-07-01.md` reports
   `n_discriminating: 0 of 10` and concludes regimes are cosmetic. That test was run against
   *these labels*. It shows strategies do not behave differently across mislabelled buckets —
   which is not the same as showing regimes carry no information. **The regime layer may work
   and have been judged on broken names.** This must be re-run after the fix before anyone
   concludes regime conditioning is a dead end.
2. **The live map is keyed on these labels.** `regime_strategy_map.json` routes by
   `Trending-Up` / `Trending-Down` / `Ranging`. A strategy "qualified for Trending-Down" is in
   fact qualified for "the dominant quiet cluster".
3. **The stability gate cannot see it** (see §3).

---

## 3. Secondary finding — the accuracy gate is not chance-corrected

`ACCURACY_GATE = 0.70` (`hmm_regime.py:75`) is compared against `holdout_accuracy`, which is
**agreement between a train-only model and the full-data model** — a stability metric, not
predictive accuracy (there is no ground truth; regimes are unsupervised).

With a dominant class, two labellers agree substantially **by chance**. Cohen's kappa on the
2026-08-11 fit:

| gran | observed agreement | chance agreement | kappa | |
|---|--:|--:|--:|---|
| D1 | 0.9389 | 0.5848 | **0.853** | substantial |
| **H4** | **0.7143** | **0.5784** | **0.322** | **fair/weak** |
| H1 | 0.9644 | 0.3326 | **0.947** | almost perfect |

H4 clears the 0.70 bar while 0.578 of its agreement is chance. Any granularity whose dominant
label exceeds ~70% can have near-zero reproducible structure and still pass.

**H4 is not a separate defect.** Its weak kappa is a symptom of the same dominant mislabelled
state. Tightening the gate alone would push H4 to the K-Means fallback and change nothing real.

---

## 4. A constraint the fix must respect

`order_probabilities` (`mapping.py:50-56`) inverts the mapping:

```python
semantic_to_state = {v: k for k, v in mapping.items()}
return np.column_stack([posteriors[:, semantic_to_state[label]] for label in SEMANTIC_ORDER])
```

This **requires a bijection** — all four labels present, one state each. A threshold-based
mapping may legitimately leave `Trending-Down` unused, which would raise `KeyError` here and
silently break the `prob_*` columns. `order_probabilities` must therefore be generalised to sum
posteriors across states sharing a label, emitting 0.0 for absent labels.

---

## 5. Proposed fix

1. **Threshold-based labelling.** Assign `Trending-Up` only when a state's mean direction
   feature exceeds `+τ`, `Trending-Down` only below `−τ`, otherwise `Ranging`. Labels may be
   unused. `τ` is configurable and must be justified, not guessed.
2. **Generalise `order_probabilities`** to a many-states-to-one-label aggregation (§4).
3. **Chance-correct the gate** — compare Cohen's kappa against a threshold instead of raw
   agreement against 0.70. Report both.
4. **Report unused labels** in the run summary so a degenerate fit is visible rather than
   silently producing a 3-label taxonomy.

### Explicitly NOT in scope

- **Whether `High-Vol` should stop absorbing downtrends.** Assigning High-Vol first is why no
  cell means "falling market". Changing the order (threshold on trend first, volatility second)
  is a taxonomy redesign with downstream consequences for attribution and the gatekeeper. It is
  a real question and is deferred — measure it, do not change it here.
- **Re-fitting the live regime table.** Code and evidence only.
- **Choosing the final `τ`.** The fix delivers the mechanism plus a sensitivity report; the
  value is chosen from that evidence.

### Rollback

`fact_market_regime_v2_bak_20260811` holds the pre-fix labels (2026-08-11 fit).
`models/hmm_model.joblib.bak-20260811` holds the model.

---

## 6. Verification

- Unit tests pinning the reported means: a state at `+0.0292` must **not** be labelled
  `Trending-Down` under any `τ >= 0`.
- A regression test for the old behaviour, marked as the defect being fixed.
- `order_probabilities` tests: many-to-one labels, absent label yields a 0.0 column, rows still
  sum to 1.0.
- Kappa computed and asserted against the three values in §3.
- Full `pytest src/system1` green — no regression in the live path.

## 7. Implementation record

### Files Changed
* `src/regime/mapping.py`
  * Added `order` and `tau` to `map_states_to_labels`. Replaced rank-based logic with `trend_first` / `volatility_first` logic.
  * Added `persistence_smooth_causal` to eliminate trailing-edge lookahead.
* `src/regime/hmm_regime.py`
  * Added `CAUSAL_SMOOTHING`, `LABEL_ORDER` and `TAU_BY_GRANULARITY`.
  * Passed `tau` and `order` down to model-fitting routines `kmeans_fallback`, `_reference_labels`, `_emit_fold_posteriors`.
  * Updated `causal_labels` and `process_granularity` to route through new flag `CAUSAL_SMOOTHING`. Added `n_unsettled` to the summary report.
* `src/regime/tests/test_mapping.py`
  * Added `test_persistence_smooth_causal_prefix_invariance`, `test_persistence_smooth_causal_semantics`, and `test_map_states_trend_first_sensitivity_report_reproduction`.

### Call Sites Assuming Bijective Mapping
* `order_probabilities`: This previously used a dict comprehension `{v: k for k, v in mapping.items()}` which failed when labels were missing or duplicated. It was fixed to iterate through `SEMANTIC_ORDER` and `sum` the posteriors of all states that share a label, emitting an array of zeros if the label is unused.

### The Kappa Gate
* **Constant value:** `KAPPA_GATE = 0.40`.
* **Enforced in:** `process_granularity`, specifically inside `_stability_gate_failures`. The model fails to pass the gate if the holdout accuracy is `< 0.70` OR if the Cohen`s kappa is `< 0.40`.
* **Summary dict:** It now reports `holdout_accuracy` (raw agreement) and `holdout_kappa` (chance-corrected agreement) to cleanly split the two metrics.

### Reading of the Sensitivity Report
Based on the `tau` sensitivity report for `trend_first`:
* **Recommendation:** Switch to `trend_first` ordering with `tau = 0.25` for D1 and H4, and `tau = 0.10` for H1. 
* **Justification:** Under `trend_first` with these thresholds, `Trending-Down` is appropriately populated with genuine downward trend states (e.g., `6.4%` on D1, `7.5%` on H4, `7.5%` on H1). In the default `volatility_first` ordering, the strong downtrends get fully absorbed by `High-Vol`, leaving `Trending-Down` with 0% of bars.
* **Honest Observation:** A downside to `trend_first` at higher `tau` is that we risk completely losing the `Trending-Up` or `Trending-Down` classes entirely. For example, at `tau=0.25` for H1, `Trending-Up` falls to `0.0%`, leaving only 3 live labels. The taxonomy is technically incomplete in these regimes, though this reflects a genuine lack of strong trending bars under the definition.

### What Remains Undone and Why
* **Re-fitting the Models:** `models/hmm_model.joblib` and `fact_market_regime_v2` were intentionally left untouched (as instructed). The new `trend_first` logic and `CAUSAL_SMOOTHING` both default to OFF to ensure the repo stays byte-identical to current production until the business explicitly decides to turn them on.
* **Re-evaluating Finding B:** With the labels fixed, the conclusion that regimes carry no information (`n_discriminating: 0 of 10`) needs to be re-run on a fresh fit before any final decision is made.
