# FIX-S1-006 — Retrain deployment gates `oos_uplift_ok` and `beats_incumbent` are structurally inert (never reject)

**Severity:** P1 (the two gates that are supposed to stop a worse/edge-less model from being promoted can never fire — overstates promotion safety)
**Status:** VERIFIED (log-only) — both inert gates can now reject; gate-can-fire tests prove it (red before, green after, independently re-run: full system1 suite 114 passed, 7/7 gate-reject tests green); `/code-review high` found no correctness bugs; gatekeeper key reconciliation (`run()` -> `oos_uplift`/`significant`) confirmed so the gate can also PASS; live champion/map untouched, no promotion path called, pending sign-off
**Author:** Claude (System-1 audit)
**Date raised:** 2026-06-26
**Scope:** `src/system1/scheduler/orchestrator.py` (`deployment_gates`, `_default_pipeline`, `_incumbent`),
`src/system1/serializer/serialize.py` (`metrics` written to `model_metadata.json`).
**Affected pipeline:** MODEL-009 (retrain orchestrator) → MODEL-007 (publish) → Computer 2.
**Risk to live trading:** A retrain that does not beat the incumbent, or whose gatekeeper shows zero/negative
OOS uplift, is still promoted as long as the regime-accuracy floor and a non-empty map hold.

> **Implementation note (2026-06-30):** Implemented on branch `fix/s1-006-deployment-gates` (stacked on
> FIX-S1-005). **Both inert gates now bind.**
>
> **`oos_uplift_ok` — armed + fail-closed.** Removed the `None ⇒ True` branch. The gate now requires
> `oos_uplift >= MIN_UPLIFT and significant` (new named constant `MIN_UPLIFT = 0.0` — keeps the historical
> non-negative-uplift threshold but *additionally* demands bootstrap significance, so a positive-but-noisy
> uplift no longer passes). `_default_pipeline` threads MODEL-006 in via a new `_gatekeeper_metrics()` helper
> that runs the gatekeeper **log-only (`dry_run=True`, writes `models/proposed_champion_*`, never the live
> champion — global rule #1)** and surfaces `oos_uplift` + `significant`. **Chosen policy for a genuinely
> missing gatekeeper result: FAIL CLOSED** — `oos_uplift is None` blocks promotion unless the operator
> passes the explicit `--allow-missing-uplift` override (new CLI flag + `run(allow_missing_uplift=...)` param).
> No silent `None ⇒ pass`.
>
> **`beats_incumbent` — producer/consumer contract reconciled on `regime_accuracy`.** `serialize.publish`
> gained an optional `metrics` arg that persists gate-relevant candidate metrics (`regime_accuracy`, plus the
> OOS uplift) into `model_metadata.json`'s `metrics` block alongside the always-present
> `n_qualified_strategies` (None-valued metrics are dropped). `_default_promote(candidate)` forwards the
> candidate's `regime_accuracy` so the next run's `_incumbent()` reads it back and the comparison is no longer
> vacuous. The metric key (`regime_accuracy`) is identical on both producer (serializer) and consumer
> (orchestrator) sides.
>
> **First-ever comparison (no incumbent metric yet): `beats_incumbent` FAILS OPEN.** There is nothing to
> beat, so a bootstrap candidate that clears the *absolute* floors (accuracy, non-empty map, and a
> significant OOS uplift) is allowed to become the first incumbent. The absolute gates — including the
> fail-closed `oos_uplift_ok` — still bind, so the first model must still demonstrate edge; only the
> head-to-head comparison is waived. Documented in the `deployment_gates` docstring.
>
> **Gate-can-fire tests (red before, green after — verified by stashing the source change):**
> `test_oos_uplift_gate_rejects_missing_uplift` / `_insignificant_uplift` / `_below_min_uplift`,
> `test_beats_incumbent_rejects_worse_candidate`, and the integration test
> `test_incumbent_regime_accuracy_round_trips_and_blocks_worse` (publishes a bundle, asserts
> `model_metadata.json.metrics.regime_accuracy` round-trips through `_incumbent()`, then runs the orchestrator
> with a deliberately-worse candidate → `outcome == "skipped_gates_failed"`). Serializer side:
> `test_publish_persists_regime_accuracy` / `_drops_none_metrics`. Whole System-1 suite green:
> 105 → **114 passed**. `black` + `mypy` clean on the changed logic (one pre-existing
> `_register_mlflow -> str` annotation nit in `serialize.py` is untouched/out of scope).

---

## 1. Executive summary

`deployment_gates` advertises four guards: regime-accuracy floor, non-empty map, **OOS-uplift ≥ 0**, and
**beats-incumbent**. Two of the four are wired so they can **never reject**:

- `oos_uplift_ok` is `True if uplift is None else uplift >= 0`, and `_default_pipeline` **always sets
  `oos_uplift = None`** (MODEL-006 is run separately and never threaded in). So the OOS-uplift gate is
  unconditionally `True`.
- `beats_incumbent` compares the candidate's `regime_accuracy` to the incumbent's
  `metrics["regime_accuracy"]`, but the serializer **never writes `regime_accuracy`** into a bundle's
  `model_metadata.json` (it writes only `n_qualified_strategies`). So `inc_acc` is always `None`, and the gate
  is unconditionally `True`.

The promotion decision therefore collapses to "regime accuracy ≥ 0.70 **and** the map is non-empty" — the two
guards meant to ensure the new model is *better than what's live* and that the *gatekeeper adds edge* are
decorative. This is the same failure class as FIX-S1-002: a gate that can never reject is not measuring what it
claims.

---

## 2. Evidence

`orchestrator.py:83` `deployment_gates`:

```python
uplift = candidate.get("oos_uplift")
gates["oos_uplift_ok"] = True if uplift is None else (uplift >= 0)          # None -> True
inc_acc = (incumbent.get("metrics") or {}).get("regime_accuracy")
gates["beats_incumbent"] = inc_acc is None or (acc is not None and acc >= inc_acc)  # None -> True
passed = all(gates.values())
```

`orchestrator.py:99` `_default_pipeline` (the function MODEL-009 actually runs):

```python
return {
    "regime_accuracy": min(accs) if accs else None,
    "n_qualified_strategies": vet["n_qualifying"],
    "oos_uplift": None,                      # MODEL-006 blocked on fact_signals  -> oos_uplift_ok always True
}
```

`serialize.py:118` — the only metrics ever persisted to a bundle:

```python
"metrics": {"n_qualified_strategies": ctx["n_qualified"]},   # no regime_accuracy
```

`orchestrator.py:70` `_incumbent` reads exactly that `metrics` block:

```python
metrics = json.load(fh).get("metrics", {})        # -> {"n_qualified_strategies": ...}
return {"bundle_version": ..., "metrics": metrics} # metrics["regime_accuracy"] is absent -> None
```

So on every real run: `candidate["oos_uplift"] is None` → `oos_uplift_ok = True`; and
`incumbent metrics has no regime_accuracy` → `inc_acc is None` → `beats_incumbent = True`. Neither gate can
contribute a `False` to `all(gates.values())`. Only `regime_accuracy_ok` and `non_empty_map` can ever block a
promotion.

---

## 3. Root cause

Two contract gaps left the gates dangling:

1. **MODEL-006 (gatekeeper OOS uplift) is not threaded into the orchestrator.** The retrain pipeline runs
   regime → attribution → vetting → publish, but not the gatekeeper, and hard-codes `oos_uplift = None`. The
   `None ⇒ pass` convenience branch (added so the pipeline could run while MODEL-006 was "blocked on
   fact_signals") turned a real gate into a no-op and was never re-armed.
2. **The serializer doesn't persist the comparison metric.** `beats_incumbent` compares on `regime_accuracy`,
   but bundles only store `n_qualified_strategies`. The incumbent's comparable metric is never available, so
   the comparison is always vacuous. Producer (serializer) and consumer (orchestrator) disagree on which
   metric identifies "better."

---

## 4. Proposed solution

1. **Thread MODEL-006 into the candidate metrics** (or explicitly mark the gate `unavailable` and **fail
   closed**, not open): when the gatekeeper is trained, surface its `oos_uplift` + `significant` into
   `_default_pipeline`'s return, and make `oos_uplift_ok` require `uplift >= MIN_UPLIFT and significant`. While
   MODEL-006 is genuinely unavailable, `oos_uplift_ok` should be `False` (block promotion) or require an
   explicit `--allow-missing-uplift` override — never a silent pass.
2. **Persist the comparison metric in the bundle.** Have `serialize.publish` write
   `metrics["regime_accuracy"]` (and any other gate-relevant metric) into `model_metadata.json` so
   `_incumbent` can actually read it and `beats_incumbent` can fire. Reconcile the metric key on both sides.
3. **Add a self-test that the gate can reject:** a unit test feeding a candidate that is worse than the
   incumbent (and one with negative uplift) must return `passed = False` — a regression guard that these gates
   are live, mirroring FIX-S1-002's "a gate must be able to fire" principle.

---

## 5. Validation plan

- **Unit:** `deployment_gates` returns `False` when (a) `candidate.oos_uplift < MIN_UPLIFT` / not significant,
  and (b) `candidate.regime_accuracy < incumbent.regime_accuracy`. Currently both pass — the test should fail
  before the fix and pass after.
- **Integration:** publish a bundle, confirm `model_metadata.json.metrics.regime_accuracy` is present and that
  `_incumbent()` reads it back; run the orchestrator with a deliberately-worse candidate and confirm
  `outcome == "skipped_gates_failed"`.

---

## 6. Rollout, risk, non-goals

- **Rollout:** additive — one new metric in the serializer manifest + tighter gate logic + threading the
  gatekeeper result. No DB migration. Backward-compatible (older bundles simply have no `regime_accuracy`, so
  decide a documented fail-open vs fail-closed default for the *first* comparison).
- **Risk:** tightening these gates may **block** promotions that previously sailed through — that is the
  intended behavior; surface the blocked reason clearly in `retrain_log_*.json`.
- **Non-goal:** redesigning the trigger logic (`triggers.py`) or the regime-accuracy floor value.

---

## 7. One-paragraph summary for a fast reviewer

The retrain orchestrator's promotion guard lists four gates, but two of them can never say "no":
`oos_uplift_ok` is `True` whenever uplift is `None`, and the pipeline always passes `oos_uplift = None`; and
`beats_incumbent` compares on `regime_accuracy`, which the serializer never writes into a bundle, so the
incumbent value is always `None` and the comparison is vacuous. Promotion therefore reduces to "regime accuracy
≥ 0.70 and non-empty map," with the "adds edge" and "better than live" guards inert. Fix: thread the
gatekeeper's OOS uplift into the candidate (and fail closed when it's missing), persist `regime_accuracy` in
the bundle metadata so `beats_incumbent` can actually compare, and add a unit test proving each gate can
reject.
