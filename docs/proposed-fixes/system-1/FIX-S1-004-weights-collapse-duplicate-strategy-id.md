# FIX-S1-004 — Per-regime weights collapse when one strategy qualifies in multiple granularities (Ranging weight = 5e-8, not 1.0)

**Severity:** P0 (ships a corrupt position-sizing artifact to Computer 2; violates the weights contract's sum-to-1 intent)
**Status:** VERIFIED (log-only) — corrected weights in `proposed_strategy_weights.json`; live artifact untouched, pending promotion sign-off
**Author:** Claude (System-1 audit)
**Date raised:** 2026-06-26

> **Implementation note (2026-06-29):** Fixed on branch `fix/s1-004-weights-collapse`.
> `gates.normalized_weights` now keys by the variant identity (`name@granularity`, via
> `_variant_key`) instead of `str(strategy_id)`; duplicate-strategy policy is **keep-both**
> (each granularity variant keeps its own weight, summing to 1.0 across variants) and is
> documented in the docstring. `vet.build` gained a hard post-condition
> (`_assert_weights_normalized` → raises `WeightsNotNormalized`) that fails the run if any
> non-empty regime's weights deviate from 1.0 by ≥1e-6. Tests: 13/13 vetting, 69/69 System-1;
> black + mypy clean (mypy residue is pre-existing missing-stub noise only). A true log-only
> MODEL-005 re-run (run `5bfa38bc…`, 80 attribution cells) emitted
> `results/reports/proposed_strategy_weights.json`: **Ranging corrected from sum 5e-08 → 1.0**
> (`{…@H1: 0.99999995, …@H4: 5e-08}`); Trending-Up/Down unchanged at 1.0; High-Vol still empty.
> Contract unchanged (permissive `additionalProperties`; variant keys validate). Reviewed
> (`/code-review high`, no findings) and runtime-verified (`/verify`: fresh CLI re-run sums to
> 1.0, live artifact still `5e-08`, guard raises on the shipped-bug map). The live
> `results/state/strategy_weights.json` is untouched — promotion awaits sign-off. Computer-2
> note: sizing must key by variant (`name@granularity`), not `strategy_id`.
**Scope:** `src/system1/vetting/gates.py` (`normalized_weights`), `src/system1/vetting/vet.py` (`build`),
`contracts/weights-contract.json`, MODEL-005 → MODEL-007 handoff (`results/state/strategy_weights.json`).
**Affected pipeline:** MODEL-005 (vetting/weights) → MODEL-007 (serialize/publish) → Computer 2 (position sizing).
**Risk to live trading:** **Direct.** The shipped `strategy_weights.json` gives the only qualified strategy a
weight of `5e-08` in the **Ranging** regime — the single most populous regime — so any consumer that scales
exposure by this weight allocates ≈ 0 to it there.

---

## 1. Executive summary

`normalized_weights` builds the per-regime weight map keyed by `str(strategy_id)`. The regime→strategy map,
however, lists strategies as **(strategy_id × granularity) variants** — the same `strategy_id` can legitimately
qualify twice in one regime (e.g. `Range_Stochastic_Divergence@H1` **and** `@H4`). When that happens, the dict
comprehension **collides on the duplicate key and keeps only the last (lowest-ranked) variant's weight**,
silently dropping the dominant variant. The result is a regime whose weights **do not sum to 1.0** — in the
currently-shipped artifact, `Ranging` resolves to `{"10": 5e-08}` instead of `{"10": 1.0}`. The JSON-schema
contract only bounds each weight to `[0,1]` and cannot express the sum-to-1 invariant, so the broken artifact
passes validation and is published.

---

## 2. Evidence

**A. The shipped artifact is already wrong.** `results/state/strategy_weights.json` (run `5bfa38bc…`):

```
Trending-Up    {'10': 1.0}
Trending-Down  {'10': 1.0}
Ranging        {'10': 5e-08}      <-- sums to 5e-08, not 1.0
```

The matching `regime_strategy_map.json` lists **two** entries for Ranging — both strategy 10:

```
Ranging -> [(10, 'Range_Stochastic_Divergence@H1', rank 1),
            (10, 'Range_Stochastic_Divergence@H4', rank 2)]
```

So the map says "two qualifying variants in Ranging," but the weights collapse them into a single
`strategy_id` key.

**B. Root mechanism reproduced** from `gates.py:59` `normalized_weights`:

```python
return {str(c["strategy_id"]): w / total for c, w in zip(ranked_cells, shifted)}
```

Driving it with the two Ranging cells (recomputed from `fact_strategy_regime_attribution`):

```
ranked cells: [(10, 'H1', composite 22.65, rank 1), (10, 'H4', composite 2.72, rank 2)]
normalized_weights -> {'10': 5.017e-08}   sum = 5.017e-08
```

`rank_cells` sorts by composite desc, so `ranked_cells[0]` is the strong H1 variant (weight ≈ 1.0) and
`ranked_cells[1]` is the weak H4 variant (`shifted = 1e-6`, weight ≈ 5e-8). The comprehension writes key
`"10"` for H1 first, then **overwrites** it with the H4 value — the ≈1.0 weight is destroyed and the residual
floor weight survives.

**C. The contract cannot catch it.** `contracts/weights-contract.json` only asserts
`additionalProperties: {type: number, minimum: 0, maximum: 1}` per regime — there is no sum constraint
(jsonschema cannot express "values sum to 1"), so `vet._validate(out["weights"], "weights-contract.json")`
passes a degenerate artifact. `gates.normalized_weights`'s own docstring claims weights "sum to 1.0."

---

## 3. Root cause

A **key-identity mismatch between producer and consumer of the variant concept.** Everywhere else in
MODEL-005 a strategy is identified by **(strategy_id, granularity)** — `vet._load_cells` builds
`variant = f"{strategy_name}@{granularity}"`, and `regime_strategy_map.json` entries carry that `variant`.
But `normalized_weights` reduces identity to `strategy_id` alone. When the same `strategy_id` qualifies at more
than one granularity in a regime, the weight dict loses entries and the per-regime weights stop summing to 1.

This is latent for any regime with one strategy_id, and only surfaced now because Ranging qualified the same
strategy at two granularities — which is exactly the design's intent (rank multiple qualifiers per regime).

---

## 4. Proposed solution

1. **Key weights by the same variant identity the map uses** (the `variant` string, or an explicit
   `(strategy_id, granularity)` tuple serialized to a stable string), so two granularity variants of one
   strategy keep distinct weights that sum to 1. Update both `gates.normalized_weights` and the JSON shape
   in `vet.build` (and the contract's `patternProperties` if the key format is constrained).
2. **Add a hard post-condition** in `vet.build`: for every non-empty regime, assert
   `abs(sum(weights[regime].values()) - 1.0) < 1e-6`, and **fail the run** otherwise — so a collapsed/degenerate
   weight map can never be published again (mirrors the metric sanity-bound guard FIX-S1-001 added).
3. **Decide the duplicate-strategy policy explicitly:** either (a) keep both granularity variants with
   summed-to-1 weights, or (b) collapse to one variant per strategy_id *by design* (keep the best-ranked and
   renormalize) — but make it a deliberate, documented reduction, not a silent dict overwrite.
4. If Computer 2 keys sizing by `strategy_id` (not variant), reconcile the contract on both sides so the key
   space matches; otherwise the consumer will look up `"10"` and get the wrong (or floor) weight.

---

## 5. Validation plan

- **Unit:** `normalized_weights` over two cells with the same `strategy_id` returns two keys whose values sum
  to 1.0 (regression test for this exact case); single-cell regime returns `{key: 1.0}`.
- **Property:** for any regime list, `sum(normalized_weights(...).values()) == 1.0` (±1e-9).
- **Artifact gate:** re-run MODEL-005 log-only and assert every non-empty regime in
  `proposed_strategy_weights.json` sums to 1.0; diff against the current broken `strategy_weights.json`.
- **Cross-check:** confirm Computer 2's sizing consumer reads the corrected key shape.

---

## 6. Rollout, risk, non-goals

- **Rollout:** pure function fix + a post-condition assert + a contract tweak; log-only re-run, then re-promote
  the corrected weights with MODEL-007. No DB migration.
- **Risk:** none while log-only; the current (broken) artifact stays authoritative until the corrected one is
  reviewed. Note the live risk is *present today* (Ranging ≈ 0 weight), so this should be sequenced early.
- **Non-goal:** changing the weighting formula (composite-proportional) — only fix the key collision and add
  the sum-to-1 guard.

---

## 7. One-paragraph summary for a fast reviewer

Per-regime strategy weights are keyed by `strategy_id`, but the map ranks **(strategy_id, granularity)
variants**, so when one strategy qualifies at two granularities in a regime the weight dict overwrites itself
and keeps only the lower-ranked variant's floor weight. The shipped `strategy_weights.json` therefore gives
Ranging — the most populous regime — a total weight of `5e-08` instead of `1.0`, and the JSON-schema contract
(which only bounds each weight to [0,1]) can't catch it. Fix: key weights by the variant identity the map
already uses, add a hard "weights sum to 1.0 per regime or fail the run" post-condition, and re-publish.
Concrete, certain, and live-affecting — fix early.
