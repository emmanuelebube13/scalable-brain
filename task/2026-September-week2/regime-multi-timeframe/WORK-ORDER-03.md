# Work Order 03 — De-seasonalise the intraday volatility baseline, then measure honestly

**Read first:** `audit/reports/work_order_02_review.md`. It corrects three findings in Work Order
02's summary and explains why the work is being continued rather than abandoned.

**Decision, owner, 2026-09-08:** the structural regime is **kept**. Its defects are fixed, not
worked around. The gatekeeper degeneracy is **out of scope** — it is pre-existing, present in the
incumbent, and does not block trading.

---

## 1. The defect

`ARCHITECTURE.md` DECIDE-1 set a ~1-year wall-clock volatility baseline at every granularity. At
D1 that is correct. At H1 and H4 it compares a bar against a mean drawn from **all hours of the
day**, and intraday volatility has a strong diurnal cycle — so a quiet 03:00 bar is structurally
classified `Ranging` and an active 16:00 bar `High-Vol`, for reasons that are about the clock, not
the market.

Measured on the built labels (EUR_USD, H1, "above-baseline volatility" share by hour UTC):

```
POOLED (current):    16.9% (h06)  →  64.2% (h16)     spread 47.2pp     3.79x
```

This affects **only** the `High-Vol` / `Ranging` split. The trending labels never consult the
z-score — they are ADX + EMA. So roughly 20–30% of bars are affected, not all of them.

## 2. The fix, and it is already validated

Compute the volatility z-score **within time-of-day slot** rather than pooled across the day. Each
bar is compared against the same slot's own trailing history. Still trailing, still causal, still
`shift(1)`-ed.

Measured, same data, same window:

```
PER-SLOT (proposed):  36.6% (h06)  →  39.7% (h17)     spread  3.1pp     1.08x
```

**93% of the diurnal spread is removed.** The remaining 3.1pp is ordinary variation.

### Why the slot counts fall out cleanly

The DECIDE-1 windows already divide exactly into 252 observations per slot:

| granularity | window (bars) | slots | **observations per slot** |
|---|---|---|---|
| D1 | 252 | 1 | **252** |
| H4 | 1,512 | 6 | **252** |
| H1 | 6,048 | 24 | **252** |

Every granularity's baseline is built from exactly 252 same-slot observations — identical to what
D1 has always used. The fix does not require new constants and does not weaken any granularity's
sample. D1 is unchanged by construction (one slot).

### Constraints

- **Causality is non-negotiable.** The per-slot rolling window must be trailing within the slot,
  and the existing `.shift(1)` must survive. A per-slot groupby is an easy place to lose bar order.
- **Warm-up must be recomputed.** A slot needs 252 of its own observations, so the first valid H1
  bar is ~252 days in, not 6,048 bars in. Mask `UNKNOWN` accordingly and **report the resulting
  UNKNOWN share per granularity.**
- `ADX_TREND_THRESHOLD`, ADX(14) and the 50/200 EMAs are **unchanged**. DECIDE-2 stands.
- Bump `LABELLER_VERSION` to **`structural-v2.1.0`** and re-derive every row. A label whose
  baseline definition changed is not the same label.

---

## 3. The measurement that Work Order 02 did not do

Its conclusion was confounded: the label **and** the engine filter changed together, and the trade
population fell 60% (92,994 → 37,494) for reasons that had nothing to do with the label.

**Hold the engine constant and vary only the label.** Run attribution twice, both on
`position_engine_v2`:

| run | `SELECTION_SOURCE_LABEL` | purpose |
|---|---|---|
| **control** | `regime_causal` | the HMM label on the v2-only population |
| **treatment** | `regime_structural` (v2.1.0) | the fixed structural label, same population |

Report both, side by side: cells, qualifying cells, per-regime trade counts, UNKNOWN share, and
the rejection summary. **That comparison — and only that comparison — supports a statement about
whether the structural label is better or worse.**

Neither run may write the live map. Log-only.

---

## 4. Then rebuild, and trade if it qualifies

1. Re-derive all labels at D1/H4/H1 with the fixed baseline.
2. Re-run attribution on `position_engine_v2` with the structural label.
3. `vet` log-only. Report what the map would contain.
4. **Stop for owner sign-off before `--live`.** The freeze is not yours to lift.
5. On approval: `vet --live`, then publish the model set.

### Publishing does not require a gatekeeper retrain

The top-level manifest is a pure function of the two sub-pointers, so a **new System 1 bundle can
be paired with the existing gatekeeper pointer.** You do not need to retrain to ship a fresh map,
and you must not attempt to — the degeneracy guard will refuse, correctly, and that is a separate
work order.

**State this limitation explicitly in your report:** the live champion was trained on the previous
label definition, so its regime feature will be fed values from a new one. That is train/serve
skew. It is tolerable **only** because the gate runs in shadow mode — `shadow_verdict` is recorded
and nothing is gated on it (owner decision 2026-08-30). The consequence is that **shadow approval
statistics are uninterpretable until the gatekeeper is retrained**, and any report quoting them
must say so.

---

## 4b. Two additions, both owner-directed 2026-09-08

### (i) The gatekeeper must READ the label, not recompute it

`src/gatekeeper/features.py:30` calls `build_structural_labels(decision_frame, granularity=...)`.
It computes labels itself instead of reading `fact_regime_structural`.

This violates the rule `CLAUDE.md` states explicitly — *"Never recompute labels in a consumer —
read the table"* — and it is the whole reason `build_structural.py` exists: three callers with
three different windows produced three answers for the same bar. At inference the gatekeeper's
labels depend on the length of whatever decision frame it is handed, which is exactly the
lookback-dependence R2.3 was written to eliminate.

**Change it to read the table**, joined on `(asset_id, granularity, bar_time_utc)`, with a
**refusal** — never a silent fallback — when no label exists for the bar being scored.

Two reasons this belongs here rather than in the gatekeeper work order: it closes a real defect,
and it removes the shared dependency that would otherwise force the gatekeeper work to run
strictly after this one.

**Note the consequence and state it in your report:** the live champion was trained on
recomputed labels. After this change it will be scored against table labels. Values will differ
slightly. Tolerable only because the gate is in shadow mode — see §4.

### (ii) Guard against silently orphaned designations

`vet.py:366` looks up `DESIGNATED[f"{variant}@{regime}"]` **while iterating over attribution
cells**. A designation therefore only takes effect if a matching cell exists. If the regime
labels move such that a designated (strategy × granularity × regime) cell has no trades, the
designation is **silently dropped** — no warning, no rejection row, nothing.

This is not hypothetical. The live map carries **12** designated cells; `vet.DESIGNATED` holds
**3**. Nine designations were lost at some point with no record of it.

**This work order changes the regime labels, so it is likely to orphan designations.**

Add a check after the cell loop: for every key in `DESIGNATED`, if no attribution cell matched
it, **log a WARNING naming the key** and include the orphans in the vetting report. An owner
override that quietly stops applying is worse than one that fails loudly.

Do not add, remove or alter any designation. Only make their disappearance visible.

## 5. Out of scope

- **The gatekeeper degeneracy.** Pre-existing (the live champion is 95.5% degenerate against the
  same check, worse than the model WO-02 rejected). Separate work order. Do not modify
  `check_cell_degeneracy`, its thresholds, or the feature set to get a model through it.
- **Retiring the HMM.** Still gates promotion, still ships.
- **Renaming the regimes / adding Low-Vol.** Owner deferred.
- **Any guard threshold**, including the 54h D1 window and `MAP_MAX_AGE_DAYS`.
- `designate.py`. `--reconcile`. The 17,583 orphaned rows — flag that the rebuild inherits them.

---

## 6. Review gates

| after | invoke | for |
|---|---|---|
| §2 | `leakage-hunter` | **the critical one** — a per-slot groupby must not break bar ordering or the `shift(1)` |
| §2 | `forex-strategist` | is a de-seasonalised intraday vol regime a meaningful market state? |
| §3 | `measurement-reviewer` | the control-vs-treatment comparison, and that no claim outruns it |
| §4 | `devils-advocate` | before any live map |
| §4 | `release-guard` | publish ordering; the pointer pairing; the skew disclosure |

A `CONFIRMED` leakage or `NOT SUPPORTED` verdict stops the stage. Do not work around a finding.

---

## 7. Deliverables

**`audit/reports/work_order_03.md`** — query output, not prose:

1. Diurnal spread by hour, per granularity, **before and after** the fix.
2. UNKNOWN share per granularity after the warm-up change.
3. Label distribution per granularity, before and after.
4. The §3 control-vs-treatment table.
5. Every qualifying cell in the proposed map: strategy, granularity, regime, trades, PF, Sharpe,
   OOS months, `selection_basis`.
6. Diff against the live map.

**`SUMMARY-03.md`** — one page: what changed, what is now true with numbers, what each agent found,
what you could not do, **what you did not check**, and the one thing you would want checked before
this goes live.

---

## 8. Standing rules

- Claims carry evidence inline. Verification means running it.
- **State what you did not check.**
- An empty map is a legitimate finding. Do not lower a gate or add a designation to avoid one.
- If a constraint conflicts with an outcome, stop and report — do not choose.
- Report failures faithfully, with the output.
