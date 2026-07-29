# T3 — Promote the Verified Work · Technical Report

**Date:** 2026-07-29 · **Status:** COMPLETE — owner signed off, bundle `2026-07-29T11-46-42Z-55dacdbf` promoted · **Commits:** `177e373`, `977375f`

The sign-off decision itself lives in `T3-signoff-evidence.md` in this folder.

---

## 1. Ratchet analysis (step 1) — with file:line evidence

### The premise was wrong

T3 states the gate was "re-armed at a `0.965` factor that ratchets".

```
$ grep -rn '0\.965' src/ --include=*.py
(no matches)
```

`0.965` appears **only** in the task prompts (`task/2026-07-28.md:13`,
`T3-promote-verified-work.md:8,13,25,26`). It is the `regime_accuracy` of the live
2026-07-26 bundle — visible in `results/state/retrain_log_20260726T0028010*.json` and in the
bundle's own `model_metadata.json` on GCS — misread as a threshold constant.

### The real mechanism

`src/system1/scheduler/orchestrator.py:226` (pre-fix):

```python
inc_acc = (incumbent.get("metrics") or {}).get("regime_accuracy")
gates["beats_incumbent"] = inc_acc is None or (acc is not None and acc >= inc_acc)
```

A bare `>=` with **no tolerance band at all**. The baseline is supplied by
`_incumbent()` (`orchestrator.py:79`), which reads
`{MODEL_PREFIX}/latest.json` → `{MODEL_PREFIX}/<version>/model_metadata.json` and returns
`metrics["regime_accuracy"]`. That metadata is written at promotion time by
`serialize.publish` (`src/system1/serializer/serialize.py:129`) from the **challenger's own**
metrics.

**Therefore the baseline compounds.** Promotion requires `acc >= inc_acc`, and each promotion
overwrites the baseline with the promoted challenger's accuracy ⇒ the sequence of live
accuracies is monotonically non-decreasing. It is a high-water mark over a *noisy* estimate,
which converges on the maximum of the noise distribution and then blocks every subsequent
challenger — including strict improvements that happen to sample lower. Observed climb:
**0.717 (07-01) → 0.8603 (07-19) → 0.965 (07-26)**.

**Confirmed: the ratchet hypothesis is correct. The stated mechanism is not.**

### The larger finding: the gate had never bound

Every real retrain shows `inc_acc = None`:

| Log | `regime_accuracy` | `incumbent_resolution` | `beats_incumbent` |
|---|---:|---|---|
| `retrain_log_20260701T1256354*.json` | 0.717 | (field absent) | fail-open |
| `retrain_log_20260719T0028418*.json` | 0.8603 | (field absent) | fail-open |
| `retrain_log_20260726T0028010*.json` | 0.965 | `absent` | fail-open |

Root cause is **not** in the gate. `src/common/storage/__init__.py:build_storage()` read
`os.environ.get("STORAGE_PROVIDER", "local")`, and `scheduler.orchestrator` loads `.env`
nowhere. Verified directly:

```
$ python -c "import os; from src.system1.scheduler import orchestrator; \
             print(os.environ.get('STORAGE_PROVIDER')); \
             from src.common.storage import build_storage; print(type(build_storage()).__name__)"
None
LocalFSBackend
```

So `_incumbent()` was reading the **local `model-artifacts/` tree** — which has no
`system1/` prefix — instead of GCS, on every real retrain. It found nothing, logged
`NO INCUMBENT FOUND`, and fell through to the documented fail-open branch.

Against live GCS with `.env` loaded, the same lookup succeeds:

```
system1/latest.json  -> 2026-07-26T00-27-51Z-b48f48d3
metrics: {"regime_accuracy": 0.965, "oos_uplift": 0.03891295487393264,
          "oos_uplift_significant": true, "n_qualified_strategies": 4}
```

This is precisely the producer/consumer divergence FIX-S1-007's docstring describes,
resurfacing through a different mechanism: FIX-S1-007 routed the *consumer* through the
storage abstraction, but nothing ensured the abstraction was configured.

---

## 2. The fixes (step 2)

### FIX-S1-011 — anti-ratchet tolerance · commit `177e373`

`orchestrator.py`:

```python
BEATS_INCUMBENT_TOLERANCE = 0.965
...
if inc_acc is None:      gates["beats_incumbent"] = True
elif acc is None:        gates["beats_incumbent"] = False        # fail closed
else:                    gates["beats_incumbent"] = acc >= inc_acc * BEATS_INCUMBENT_TOLERANCE
gates["beats_incumbent_detail"] = {...}                          # evidence for the log
```

The bar now tracks the **currently live** incumbent within a band rather than a historical
maximum, so it can fall as well as rise and cannot compound. Downward drift is bounded by the
absolute `REGIME_ACCURACY_FLOOR = 0.70`, which still binds independently.

`passed` is now computed over boolean gates only — a truthy `*_detail` dict must never be
able to count as a passing gate:

```python
passed = all(v for k, v in gates.items() if isinstance(v, bool))
```

**Tests** — `src/system1/scheduler/tests/test_beats_incumbent_ratchet.py`, 10 cases including
the three T3 asks for:
- `test_strictly_better_challenger_promotes`
- `test_marginally_worse_challenger_does_not_flap`
- `test_three_successive_promotions_do_not_raise_the_bar`

plus `test_the_bar_can_fall_not_only_rise` (the defining anti-ratchet invariant),
`test_real_regression_is_still_blocked`,
`test_downward_drift_is_bounded_by_the_absolute_floor`,
`test_missing_incumbent_fails_open_but_absolute_gates_still_bind`,
`test_missing_candidate_accuracy_fails_closed`, and two asserting the detail block is
evidence rather than a gate.

### FIX-S1-012 — backend configuration · commit `977375f`

`src/common/storage/__init__.py` now calls `_ensure_env_loaded()` before reading
`STORAGE_PROVIDER`. `load_dotenv` does not override variables already in the environment, so
explicit test/CI overrides still win (asserted by test).

**Tests** — `src/common/storage/tests/test_backend_selection.py`, 4 cases, each in a
subprocess with `STORAGE_PROVIDER` scrubbed so the cold-start path is genuinely exercised:
- `test_backend_honours_dotenv_without_any_prior_import`
- `test_explicit_environment_still_overrides_dotenv`
- `test_orchestrator_import_path_resolves_the_real_backend`
- `test_incumbent_resolves_a_live_bundle_not_absent` — asserts `_incumbent()` returns
  `prefixed`/`legacy_model_set`, never `absent`, because `absent` means the gate is inert.

**Full suite: 256 passed.**

---

## 3. Gated evaluation (step 3, adapted)

T3 step 3 says `orchestrator --force`. That promotes when the gates pass, and there is no
dry-run flag — it would have flipped the live pointer without the sign-off RUN-ALL requires.

**What was done:** the forced run was started, then killed mid-HMM before reaching the publish
stage. Verified afterwards: `retrain_state.json` unchanged
(`2026-07-26T00-27-51Z-b48f48d3`), no promotion/publish lines in the log, stale
`results/state/retrain.lock` removed, `fact_market_regime_v2` row counts intact
(D1 29,408 · H1 650,815 · H4 165,118).

It was replaced by an equivalent non-promoting evaluation calling the same
`_default_pipeline()`, the same `_incumbent()` and the same `deployment_gates()` — output in
`results/state/t3_evidence_20260729.json`.

> `_default_pipeline()` calls `vet.run(live=True)`, which rewrites
> `results/state/regime_strategy_map.json` and `strategy_weights.json`. Those are **staging
> artifacts on this machine**, not the live model — Systems 2 and 3 read the GCS bundle,
> which was not touched. The rewrite is visible as a tracked git diff.

### Results — all four gates PASS

| Gate | Candidate | Threshold | Verdict |
|---|---:|---:|---|
| `regime_accuracy_ok` | 0.965 | ≥ 0.70 | PASS |
| `non_empty_map` | 4 | ≥ 1 | PASS |
| `oos_uplift_ok` | 0.0376735 (significant) | ≥ 0.0 and significant | PASS |
| `beats_incumbent` | 0.965 | ≥ 0.931225 | PASS |

`would_promote: true`, `promotion_attempted: false`. **Incumbent resolution: `prefixed`** —
the first successful incumbent resolution in the project's history.

### Candidate vs incumbent

| | Live 2026-07-26 | Candidate | Δ |
|---|---:|---:|---:|
| `regime_accuracy` | 0.965 | 0.965 | 0.000 |
| `oos_uplift` | 0.0389130 | 0.0376735 | −0.0012395 |
| `oos_uplift_significant` | true | true | — |
| qualified entries | 4 | 4 | 0 |

### Map diff — structurally identical

Same 4 entries across 3 strategy×regime cells, all `Range_Stochastic_Divergence`:
Trending-Up @H1, Trending-Down @H1, Ranging @H1+H4. Nothing gained, nothing dropped.
High-Vol remains empty (starvation). See `map_diff_heatmap.png`.

Per-cell metric deltas (live → candidate) split both ways:

| Cell | PF Δ | Sharpe Δ | trades Δ |
|---|---:|---:|---:|
| Ranging @H1 | +0.1386 | +0.1661 | −3 |
| Ranging @H4 | −0.2703 | −0.2056 | 0 |
| Trending-Down @H1 | −0.2626 | −0.1413 | +6 |
| Trending-Up @H1 | +0.0763 | +0.0622 | −1 |

Weights are unchanged in structure (Ranging 0.95/0.05 H1/H4; 1.0 elsewhere).

---

## 4. Promotion (step 5) — executed after owner sign-off

The owner reviewed the evidence package and answered **"Promote now"**. Promotion ran through
`orchestrator --force` — the single governed path (FIX-S1-009). No other route was used.

| | Value |
|---|---|
| Promoted bundle | `2026-07-29T11-46-42Z-55dacdbf` |
| Superseded | `2026-07-26T00-27-51Z-b48f48d3` |
| `incumbent_resolution` | `prefixed` — **the first real `beats_incumbent` comparison in the project's history** |
| Gates | all four PASS; `beats_incumbent` 0.965 ≥ 0.931225 |
| Analytics bundle | refreshed → `2026-07-29T11-46-49Z-f3014649` |
| Gatekeeper champion | **untouched** (`GATEKEEPER_AUTOPROMOTE` unset, by instruction) |
| Retrain log | `results/state/retrain_log_20260729T114651736689Z.json` |

### Pointer verification (read back from GCS through the storage abstraction)

```
system1/latest.json   -> 2026-07-29T11-46-42Z-55dacdbf   promoted_at 2026-07-29T11:46:44Z
metadata sha256 matches the pointer's metadata_sha256:  True
artifacts: checksums.sha256, hmm_model.joblib, model_metadata.json,
           regime_strategy_map.json, strategy_weights.json
```

### Two gaps this promotion exposed

**(a) `previous.json` was NOT archived — because the feature does not exist.**
T3's acceptance criterion asks to verify it. `system1/previous.json` is missing, and was
missing *before* this promotion too. `grep -rn 'previous.json' src/` returns nothing:
**CLAUDE.md documents an archiving step that no code implements.** Rollback today means
manually rewriting `system1/latest.json` back to `2026-07-26T00-27-51Z-b48f48d3`, which
remains intact under its immutable prefix.

**(b) The two live pointers now disagree.** The orchestrator logged
`top-level model set NOT refreshed (MODEL_SET_AUTOPUBLISH not set)`:

| Pointer | Bundle |
|---|---|
| `system1/latest.json` | `2026-07-29T11-46-42Z-55dacdbf` ← new |
| `latest.json` (model set: bundle + gatekeeper) | `2026-07-26T00-27-51Z-b48f48d3` ← old |

If Systems 2/3 consume the model set, **the promotion has not reached them**. Publishing it
(`python -m src.system1.serializer.publish_model_set`) is a separate staged-rollout step with
its own env guard; it was deliberately not run, since arming it is a rollout decision rather
than a consequence of this sign-off.

**(c) OOS uplift regressed and no gate saw it.** The promoted bundle records
`oos_uplift = 0.03649` against the superseded bundle's `0.03891` — ~6% lower. The gatekeeper's
uplift estimate is stochastic (the pre-run evaluation measured 0.03767 on the same data), and
`beats_incumbent` compares only `regime_accuracy`. A bundle-level uplift regression check is
missing.

### Fix-doc statuses updated

`FIX-S1-001/002/004/005/006` → **PROMOTED & LIVE 2026-07-29**, naming the bundle, with their
previous status preserved inline. `FIX-S1-009` was already IMPLEMENTED. `FIX-S1-010` →
**PARTIALLY LIVE**: manifest-honesty and incumbent-resolution shipped, but the gatekeeper
recalibration is explicitly *not* released (the 17.2%→21.6% approval change is still gated).
New doc: `FIX-S1-011-beats-incumbent-ratchet-and-inert-gate.md`.

**Step 6 (AUTOPROMOTE)** — recommendation written in the evidence package; switch left OFF, as
instructed. No code touches it.

---

## 5. Recommendation made, and the decision taken

The evidence package recommended **against** promoting today, on the grounds that the
candidate was not an improvement. The owner reviewed that and chose to promote. Both the
recommendation and the decision are preserved in `T3-signoff-evidence.md` (§7 and §8).

The material gain from promoting: the live bundle is now the first one built on
non-stale trade data (post-T1). The material cost: a ~6% lower recorded OOS uplift, and a
pointer inconsistency that needs resolving (§4b).

---

## 6. Commits

| SHA | Subject |
|---|---|
| `177e373` | FIX-S1-011: stop beats_incumbent from ratcheting to a high-water mark |
| `977375f` | FIX-S1-012: build_storage() must load .env, not silently fall back to local |

No co-author trailer. Nothing pushed.

## 7. Follow-ups this task surfaced

1. **`orchestrator` has no dry-run.** `--force` is all-or-nothing and always promotes on a
   pass. A `--evaluate-only` flag would remove the need for the workaround used here and is
   worth adding before anyone else follows T3's step 3 literally.
2. **`beats_incumbent` compares only `regime_accuracy`.** The candidate's OOS uplift is
   *worse* than the incumbent's and no orchestrator gate noticed. The gatekeeper publish path
   does compare uplift, but that is a separate artifact with its own pointer. A bundle-level
   uplift regression check is missing.
3. **`regime_accuracy` of 0.965 deserves scrutiny.** It climbed 0.717 → 0.8603 → 0.965 across
   three retrains on largely unchanged data. Either the regime model genuinely improved that
   fast, or the accuracy measure is drifting toward something self-fulfilling. Worth a look
   before it is used as a promotion criterion in anger.
4. Several HMM folds log `Model is not converging` — tolerated by the fallback design, but
   the frequency should be quantified.
