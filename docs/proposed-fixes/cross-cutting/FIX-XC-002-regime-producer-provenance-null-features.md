# FIX-XC-002 — Regime table written by an undocumented producer; Layer-3 reads 5 regime features that are 100% NULL

**Severity:** P1 (degenerate/dead features fed to the ML gatekeeper + provenance/contract drift; two writers race on one table)
**Status:** Proposed
**Author:** Claude (cross-cutting auditor)
**Date raised:** 2026-06-26
**System:** Cross-cutting (`fact_market_regime_v2` producer contract → Layer-3 features, docs)

---

## 1. Executive summary

The repo documents `src/layer1_regime/Fact_market_regime_v2.py` (a **K-Means** engine) as the "preferred"
Layer-1 producer of `fact_market_regime_v2` (CLAUDE.md, `ERD_ACTIVE_SCHEMA_2026.md`). The live table is in
fact populated **entirely by a different, undocumented HMM producer** (`src/system1/regime/hmm_regime.py`,
`regime_model = 'HMM'`, `model_version = 'hmm-v1.0.0'`). The two writers emit **disjoint column sets** to
the same table and conflict target. As a direct consequence, **five regime feature columns that Layer-3
training explicitly reads are 100% NULL**, so the ML gatekeeper is fed dead/constant features, and a
re-run of the *documented* producer would overwrite live data with a different schema footprint.

---

## 2. Evidence

### 2.1 The documented producer is not the actual producer

Live column population in `fact_market_regime_v2` (841,596 rows):

```
regime_model:           HMM         (841,596 / 100%)
model_version:          hmm-v1.0.0  (841,596 / 100%)
regime_raw:             100% non-null
regime_smoothed:        100% non-null
prob_trending_up/...:   100% non-null      <- written only by hmm_regime.py
session_volume_z:       0 non-null (0%)    <- written ONLY by the documented KMeans script
```

`src/layer1_regime/Fact_market_regime_v2.py` writes `session_volume_z` (its `col_map`, lines 516-529) and
does **not** write `regime_raw/regime_smoothed/prob_*`. The live table is the exact inverse: `prob_*`
fully populated, `session_volume_z` fully NULL. Therefore the documented KMeans script **did not write a
single live row** — `src/system1/regime/hmm_regime.py` did (its `UPSERT_SQL`, lines 164-183, writes
exactly `regime_raw, regime_smoothed, prob_*, regime_model`). CLAUDE.md ("K-Means clustering … preferred
… `Fact_market_regime_v2.py`") and `ERD_ACTIVE_SCHEMA_2026.md` describe the wrong engine.

### 2.2 Layer-3 reads regime feature columns that are entirely NULL

`src/layer3_ml/training/train_ml_gatekeeper.py` adds these regime features when the column exists
(`_maybe_add`, lines 395-411). They **exist** (so `_maybe_add` includes them) but are **100% NULL** in the
live table:

```
h4_trend_direction:    non-null 0 (0.0%)
d1_trend_direction:    non-null 0 (0.0%)
trend_alignment_score: non-null 0 (0.0%)
volatility_regime:     non-null 0 (0.0%)
atr_percentile_20d:    non-null 0 (0.0%)
```

`_maybe_add` keys off **column presence, not content**, so these enter the feature frame as all-NULL → the
preprocessor imputes them to a constant → five dead features. This is a degenerate/collapsed-output
condition hidden across the producer→consumer handoff: the consumer believes it has rich Layer-1 regime
context; it has zeros.

### 2.3 Two writers, one table, divergent footprints

Both producers upsert on the same conflict target `("timestamp", asset_id, granularity)`. The HMM writer's
`ON CONFLICT DO UPDATE` set list (lines 170-182) does **not** touch `session_volume_z`/`atr_value`-context
columns the KMeans writer owns, and vice-versa. Running the documented script "to refresh regimes" would
flip `regime_model` back to a KMeans label, blank `regime_raw/regime_smoothed/prob_*`, and silently change
the meaning of `regime_label` for every consumer — an un-versioned, un-guarded data corruption path.

---

## 3. Root cause

A System-1 HMM engine superseded the original Layer-1 K-Means engine but the documentation, the ERD, and
the second writer were never retired or reconciled. The shared physical table has no producer guard
(no `regime_model`-aware ownership, no advisory lock, no "single writer" contract), and the Layer-3 feature
selector trusts column *presence* as a proxy for column *validity*.

---

## 4. Proposed fix

1. **Declare a single canonical producer.** Make `src/system1/regime/hmm_regime.py` the authoritative
   writer; update CLAUDE.md + `ERD_ACTIVE_SCHEMA_2026.md` to match, and either retire
   `src/layer1_regime/Fact_market_regime_v2.py` or have it refuse to write to the live table (guard on
   `regime_model`).
2. **Stop feeding dead features.** In `_maybe_add`, gate inclusion on **non-null coverage** (e.g. require
   ≥ X% non-null over the training window), not mere column existence. Log every column dropped for low
   coverage so the gap is visible, not silent.
3. **Either populate or drop the NULL columns.** If `h4_trend_direction/d1_trend_direction/
   trend_alignment_score/volatility_regime/atr_percentile_20d` are part of the contract, the HMM producer
   must write them; if not, drop them from the schema/feature list so no consumer is misled.
4. **Add a producer-ownership guard** so two engines cannot silently overwrite each other's columns.

---

## 5. Validation plan

- Re-query non-null coverage after the producer change; assert the five regime features are either
  ≥ threshold populated or absent from the feature frame.
- Layer-3 dry-run feature manifest must no longer list any all-NULL regime feature.
- Doc check: CLAUDE.md / ERD name the HMM engine and its written column set.

---

## 6. Rollout / risk

- **Rollout:** doc + selector change is non-destructive and immediate; producer retirement is a one-line
  guard. No live-trade impact.
- **Risk if not fixed:** the gatekeeper's "regime awareness" is partly a fiction (5 constant features), and
  an innocent "refresh the regimes" run with the documented script would corrupt the live table's semantics.

---

## 7. One-paragraph summary

`fact_market_regime_v2` is populated 100% by an **undocumented HMM** (`hmm_regime.py`, `regime_model='HMM'`),
not the K-Means script CLAUDE.md/ERD call the producer — proven by `session_volume_z` (KMeans-only) being
0% populated while `prob_*` (HMM-only) is 100%. Because Layer-3's feature selector keys off column presence,
it pulls five regime features (`h4_trend_direction`, `d1_trend_direction`, `trend_alignment_score`,
`volatility_regime`, `atr_percentile_20d`) that are **100% NULL**, feeding dead constants to the ML
gatekeeper. Two writers also share one conflict target with disjoint column sets, so running the
"documented" producer would silently corrupt live regime semantics. Fix: name one canonical producer, gate
Layer-3 feature inclusion on non-null coverage (not existence), and populate-or-drop the NULL columns.
