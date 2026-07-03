# System-1 Five-Fix Independent Verification Report

**Date:** 2026-07-01
**Branch:** `fix/s1-integration` (tip `8e0d094`)
**Verifier:** independent verification agent (read-only; no source/artifact modified except this report)
**Scope:** FIX-S1-002, -003, -004, -005, -006 — logical + contextual verification, full-suite + targeted tests, log-only invariant.

---

## (a) Executive verdict table

| Fix | Logical | Contextual | Key evidence |
|-----|---------|------------|--------------|
| **S1-004** weights collapse | **PASS** | **PASS** | `normalized_weights` keys by `_variant_key` (`name@granularity`); `vet._assert_weights_normalized` raises `WeightsNotNormalized` if any non-empty regime ≠ 1.0 ±1e-6; runs on the *rounded* written values. Proposed artifact: Ranging = `{@H1:0.99999991, @H4:9e-8}` sum 1.0; **live artifact still `{"10":5e-08}`**. 14/14 vetting tests incl. guard-raises + keep-both. |
| **S1-002** true OOS | **PASS** | **PASS** | `oos_months = oos_month_span(union of OOS folds the cell traded)`; metrics on `is_oos` subset only; empty OOS ⇒ trade_count 0 ⇒ gate fails (safe). `assign_oos`/`generate_folds`/`oos_month_span` calendar math re-derived correct. Overfit-fails-OOS + low-oos + zero-oos + schema-aware fallback tests green (25/25). |
| **S1-005** causal labels | **PASS** | **PASS** | `filtered_posteriors` = forward-only `_hmmc.forward_log`, row-normalized, no backward/Viterbi. Leakage regression (future mutation can't move label ≤t, atol 1e-12) + guard-can-fire counter-test (smoothed DOES leak) + walk-forward causal test all green. AST test proves neither attribution nor gatekeeper SELECT bare smoothed columns; both use `regime_causal`/`prob_causal_*`. 18/18. |
| **S1-003** discrimination | **PASS** | **PASS** | Log-only re-run reproduced report **exactly**: entry-only 0/10 (max 0.0752, med 0.0305), dominant-over-life 0/10 (max 0.0968, med 0.02765) on `regime_causal`. `discriminates` = chi2 p<0.05 AND spread≥0.10. Synthetic-discrimination test flags True; post-hoc only (no production attribution change). 10/10. |
| **S1-006** deployment gates | **PASS** | **PASS** | `oos_uplift_ok` requires `uplift>=MIN_UPLIFT(0.0) AND significant`; `None`⇒fail-closed unless `allow_missing_uplift`. `serialize.publish(metrics=)` persists `regime_accuracy`; `_incumbent` reads it; `beats_incumbent` fires. Gatekeeper `run()` returns flat `oos_uplift`/`significant`. 21/21 (7 gate-reject + serializer round-trip). |

**Overall: all five fixes verified. No failed checks. Two accurately-documented caveats remain (below).**

---

## (b) Per-fix findings

### FIX-S1-004 — per-regime weights collapse
- **Logical.** `gates.normalized_weights` (line 83–106) returns `{_variant_key(c): w/total ...}`. `_variant_key` prefers the cell's `variant` field (`name@granularity`), falling back to `f"{strategy_id}@{granularity}"` — never bare `strategy_id`. `vet.build` computes `weights_out[regime] = {k: round(v,8) ...}` then calls `_assert_weights_normalized` **on the rounded values that are actually written** (not the pre-round floats), raising `WeightsNotNormalized` when `abs(sum-1.0) >= 1e-6` for any non-empty regime. This is the correct guard location and it can fire.
- **Contextual.** Empirically compared the two artifacts:
  - Live `results/state/strategy_weights.json` (protected): `Ranging = {"10": 5e-08}` — **UNTOUCHED, still the shipped bug.**
  - Proposed `results/reports/proposed_strategy_weights.json`: `Ranging = {"Range_Stochastic_Divergence@H1": 0.99999991, "@H4": 9e-08}` → sums to 1.0, keyed by variant.
- **Tests.** `test_weights_keep_both_variants_same_strategy_id`, `test_weights_sum_to_one_property`, `test_assert_weights_normalized_raises_on_broken`, `test_build_post_condition_raises_on_collapsed_weights` (all present, green). Guard-can-fire proven via `pytest.raises(WeightsNotNormalized)`.
- **Note (minor, not a defect):** the proposed numbers drifted from the fix-doc header (`0.99999995 / 5e-08` → `0.99999991 / 9e-08`) — a downstream re-run (causal-label/attribution change) slightly moved composite scores. Sum-to-1 holds either way; substance unchanged. Also: proposed keys are variant strings while the *live* file keys by `strategy_id` — Computer-2 sizing must key by variant (already flagged in the doc).

### FIX-S1-002 — true out-of-sample
- **Logical.** `walk_forward.generate_folds`: first OOS window at `cutoff = series_start + min_train(36mo)`, stepping `step(6mo)`, `oos_window(6mo)`, `oos_end` clamped to `series_end`, anchored train. `assign_oos`: `is_oos ⇔ entry >= folds[0].oos_start`; `fold_id = searchsorted(oos_starts, et, 'right')` (1-based); NaT ⇒ not-OOS. `oos_month_span`: merges adjacent/overlapping OOS windows (contiguous tiling collapses to one span) and divides whole-day length by 30.44. Re-derived by hand on the contiguous-tiling case — correct. `attribute._oos_cell_metrics` computes every gate metric on the OOS subset and `oos_months` from `oos_month_span(folds the cell's OOS trades hit)`; an empty OOS subset yields trade_count 0 / oos_months 0 ⇒ cannot clear gates (safe direction). Gate in `gates.evaluate_gates` unchanged (60mo) but now reads a real OOS value.
- **Contextual.** `_load_trades` is schema-aware: uses `is_oos`/`fold_id` only when **both** columns exist, else logs a warning and treats all trades as in-sample (every cell fails OOS — fail-safe). `in_sample_span_months` retained reporting-only under an honest name. `validation_design` lineage written into the map (contract loosened additively — `contracts/regime-map-contract.json` +14 lines).
- **Tests.** `test_overfit_strategy_passes_in_sample_but_fails_oos_gates` (mandatory "gate can fire"), `test_oos_gate_fires_on_low_oos_months`, `test_zero_oos_trades_cell_fails_gates`, `test_load_trades_schema_aware_fallback/_present`, clamp + hard-abort branch tests. 25/25 (walk_forward + attribute_oos).
- I did **not** re-run `attribute.run()` (it DELETE/INSERTs into `fact_strategy_regime_attribution` — a DB write, out of read-only scope). The `oos_fail 0→8` / `11/80` figures are taken from the committed run report; the gate-can-fire logic is proven independently by the unit tests.

### FIX-S1-005 — causal regime labels
- **Logical.** `mapping.filtered_posteriors` wraps `hmmlearn._hmmc.forward_log` (forward lattice `log P(x_1..x_t, state_t)`), stable per-row log-normalize, exponentiate — **no backward pass, no Viterbi**. Causal by construction. `regime/tests/test_causal_labels.py`:
  - `test_filtered_label_invariant_to_future_bars`: violently mutate bars `>t0`, filtered posterior at `≤t0` unchanged (`np.allclose atol 1e-12`, argmax equal). **PASS.**
  - `test_smoothed_predict_proba_leaks_so_guard_can_fire`: same mutation moves a **past** bar's `predict_proba` > 1e-6 — proves the leakage test is non-vacuous. **PASS.**
  - `test_walk_forward_labels_invariant_to_future_mutation` + `test_warmup_bars_are_unknown` (36-mo warmup ⇒ NULL). **PASS.**
- **Contextual.** `attribute._load_regimes` and `gatekeeper.build_frame` SELECT `regime_causal` / `prob_causal_*` with `regime_causal IS NOT NULL`. `gatekeeper` feature lists: `CATEGORICAL` includes `regime_causal`; `NUMERIC`/`REGIME_FEATURES` use `prob_causal_*`; per-regime threshold calibration groups by `regime_causal`. `test_no_smoothed_leak.py` AST-parses each consumer's regime SQL literals and asserts none contain any smoothed token and all contain `regime_causal` — a real regression guard. **PASS.**
- **Caveat (documented, still true):** the gatekeeper's `_walk_forward` uses `np.array_split(frame, N_FOLDS+1)` (line 189) — a **count-based** split, not time-based. So `oos_uplift = 0.0405` uses causal *labels* but a count-based OOS split; the doc's "do not over-read as a fully-clean OOS estimate" caveat is accurate.

### FIX-S1-003 — regimes don't discriminate
- **Logical.** Re-ran `python -m src.system1.attribution.discrimination --no-report` (log-only; wrote nothing). Output **exactly matched** the committed `regime_discrimination_20260630T225156Z.json`:
  - entry-only: `n_discriminating 0/10`, max_spread 0.0752, median 0.0305
  - dominant-over-life: `0/10`, max_spread 0.0968, median 0.02765
  - strat 10 anti-specialization confirmed (wins least Trending-Up 0.6694, most Trending-Down 0.7662).
  `discriminates = (p is not None and p<0.05 and spread>=0.10)` — significance AND materiality, as claimed.
- **Contextual.** Module is post-hoc: `run()` reads via `ATTR.tag_regime_at_entry` + its own over-life tagger, writes only a `results/reports/*.json`; production attribution untouched. Over-life tag documented as non-tradeable (look-ahead if used to gate). §7 conclusion + register row match the numbers.
- **Tests.** `test_detects_strong_discrimination` (measurement can flag True), `test_reports_no_discrimination_when_flat`, `test_significant_but_immaterial_does_not_count`, `test_single_regime_pvalue_none`, tagging tests. 10/10.

### FIX-S1-006 — deployment gates never reject
- **Logical.** `deployment_gates` (orchestrator line 93): `oos_uplift_ok` — `uplift is None ⇒ bool(allow_missing_uplift)` (fail-closed by default); else `uplift >= MIN_UPLIFT(0.0) and bool(significant)`. `beats_incumbent` — `inc_acc is None or (acc>=inc_acc)` (first-comparison fail-open, absolute gates still bind). `_gatekeeper_metrics` runs `train.run(dry_run=True)` (writes `models/proposed_champion_*`, never live) and surfaces `oos_uplift`/`significant`; failure ⇒ `{}` ⇒ `oos_uplift=None` ⇒ fail-closed.
- **Contextual — producer/consumer reconciliation.** `serialize.publish(metrics=)` merges non-None metrics into `model_metadata.json.metrics` incl. `regime_accuracy`; `_incumbent` reads exactly `metrics["regime_accuracy"]`; `_default_promote` forwards `candidate["regime_accuracy"]`. Key `regime_accuracy` identical on both sides. Gatekeeper `run()` returns flat `oos_uplift`/`significant` (lines 342/344), matching `_gatekeeper_metrics`'s `res.get(...)` — so the gate can also PASS (no inverted inertia).
- **Tests.** `test_oos_uplift_gate_rejects_missing_uplift/_insignificant/_below_min`, `test_oos_uplift_missing_allowed_with_override`, `test_beats_incumbent_rejects_worse_candidate`, integration `test_incumbent_regime_accuracy_round_trips_and_blocks_worse` (⇒ `skipped_gates_failed`), `test_publish_persists_regime_accuracy/_drops_none_metrics`. 21/21.

---

## (c) Test-suite results

| Suite | Result |
|-------|--------|
| Full `pytest src/system1/ -q` | **124 passed** in ~7.7s (matches expected 124) |
| S1-004 vetting `test_gates.py` | 14 passed |
| S1-002 `test_walk_forward.py` + `test_attribute_oos.py` | 25 passed |
| S1-005 `test_causal_labels.py` + `test_no_smoothed_leak.py` + `test_mapping.py` | 18 passed |
| S1-003 `test_discrimination.py` | 10 passed |
| S1-006 `test_scheduler.py` + `test_serialize.py` | 21 passed |

---

## (d) Discrepancies between claims and reality

I looked hard for anything that does not hold up. Nothing material was found. The minor/nominal items:

1. **Vetting test count 13→14.** Fix-doc header says "13/13 vetting"; current is 14/14. Additive (one more test), not a regression. Not a concern.
2. **Proposed-weights numeric drift.** Fix-doc header quotes Ranging `@H1:0.99999995 / @H4:5e-08`; the current proposed artifact is `0.99999991 / 9e-08`. Cause: a later causal-label/attribution re-run shifted composite scores slightly. **Both sum to 1.0**; the corrective claim (Ranging 5e-08 → 1.0, keyed by variant) still holds. Cosmetic.
3. **The `git diff` log-only test is necessary but weak** (see (e)) — the strong evidence is that I *read the live file* and it still contains the bug. This is a methodological caveat, not a fix defect.

No inflated claims detected. The most surprising documented result (S1-005: OOS uplift did **not** shrink, 0.0319→0.0405) is reported faithfully in the doc as a hypothesis-refuting outcome, with the correct caveat that the gatekeeper split is still count-based — I confirmed that caveat in code.

---

## (e) Log-only invariant check

- **`git diff --stat fix/s1-baseline..HEAD`** touches only: `contracts/`, `docs/`, `results/reports/regime_discrimination_*.json`, `src/system1/**`, and one new producer `src/layer0/persist_trade_outcomes.py`. **No** `models/champion_*` and **no** `results/state/*.json` live artifact. PASS.
- **Stronger empirical check:** the protected live artifacts (`results/state/strategy_weights.json`, `results/state/regime_strategy_map.json`, `models/champion_*`) are **git-untracked / ignored** — so a `git diff` can *never* show them regardless of what happens. I therefore verified them directly: live `strategy_weights.json` still holds the buggy `Ranging = {"10": 5e-08}`, and no `models/champion_*` is modified in the working tree. The real log-only protection is structural: `vet.run(live=False)` writes `results/reports/proposed_*`, `gatekeeper.run(dry_run=True)` writes `models/proposed_champion_*`, and the discrimination module writes only a report. **Invariant holds, confirmed empirically, not just via git.**
- My own actions were read-only: the discrimination re-run used `--no-report` (wrote nothing); I did not run any `--live`/`--promote`/`attribute.run` DB-writing path.

---

## (f) Residual risks / follow-ups

- **Gatekeeper `_walk_forward` is count-based, not time-based** (`np.array_split`, N_FOLDS=5). The causal-label OOS uplift (0.0405) is not yet a fully-clean time-ordered OOS estimate. Accurately documented; out of scope for this batch — recommend a dedicated fix.
- **`src/common` is untracked** (0 files in `git ls-files src/common`). Every System-1 module imports `src.common.db` / `src.common.storage`; these are not under version control on this branch, so the diff and any reviewer's checkout depend on locally-present, unversioned code. Accurately noted as a known caveat; should be brought under version control before promotion.
- **`src/layer0/persist_trade_outcomes.py`** is a new 373-line producer added in this branch (populates `fact_trade_outcomes.is_oos`/`fold_id`). It is source, not a live artifact — no invariant breach — but it lives outside `src/system1` and was not called out in the per-fix scope lists; worth a line in the register for provenance.
- **Promotion still pending sign-off** for all five (correct posture). When promoting S1-004's corrected weights, Computer-2 sizing must key by `name@granularity` variant, not `strategy_id` — the live and proposed key spaces differ.
- **DB-side figures (oos_fail 0→8, attribution distributions) were not independently re-derived** here to preserve read-only DB state; they rest on the committed run reports plus the unit-level gate-can-fire proofs.

---

*Verification complete. All five fixes pass logical and contextual checks; 124/124 tests green; log-only invariant confirmed empirically.*
