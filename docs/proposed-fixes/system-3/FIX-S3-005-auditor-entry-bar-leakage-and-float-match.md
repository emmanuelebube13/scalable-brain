# FIX-S3-005 — Trade auditor scans the path from the entry bar inclusive (pre-fill leakage) + brittle float-equality patch

**Severity:** P2 (outcome reconciliation can mislabel WIN/LOSS from pre-entry price action; patch can miss rows)
**Status:** Proposed
**Author:** Claude (System-3 risk-engine / decay-auditor audit)
**Date raised:** 2026-06-26
**Scope:** `src/layer6_auditor/trade_auditor.py` — `determine_outcome_m1_chunked`, `main` UPDATE;
`src/layer6_auditor/tools/patch_actual_outcome.py`
**Category:** (6) look-ahead/leakage · (5) contract/handoff
**Risk to live trading:** Patched `Actual_Outcome` (which Layer 3 retraining and decay analysis
consume) can be wrong at the entry-bar boundary, biasing the labels that feed the ML gatekeeper.

---

## 1. Executive summary

The Layer 6 auditor reconciles each unresolved `Fact_Live_Trades` row by replaying M1 candles from
the entry time and recording WIN (TP touched) or LOSS (SL touched). Two issues:

1. **The scan starts at `entry_time` inclusive**, so the entire entry bar's high/low — including
   intrabar movement that occurred *before* the fill — can trigger SL/TP. If the recorded `timestamp`
   is the signal bar's open while the fill happened later in/after that bar, the auditor can assign an
   outcome from price action the trade was never exposed to (a backward leakage at the boundary).
2. **The UPDATE matches rows by float equality on `Entry_Price`** (`AND Entry_Price = %s` with a
   Python `float`), which is fragile across float/Numeric round-trips and can silently fail to patch.

A minor contract gap: the documented helper `tools/patch_actual_outcome.py` is a **0-byte empty
file**, so any workflow relying on it is a no-op.

---

## 2. Evidence

```
trade_auditor.py:81   current_start = entry_time          # scan begins AT entry bar
trade_auditor.py:101-121  for c in candles: ... if low<=sl: LOSS  elif high>=tp: WIN
```
`determine_outcome_m1_chunked` requests M1 candles `from = current_start (= entry_time)` and evaluates
the first candle at/after `entry_time`. Nothing advances the start past the entry bar or past the
fill timestamp, so the entry bar's full range is in scope.

Within a single candle the order is **SL checked before TP** (`if low<=sl: return LOSS elif high>=tp:
return WIN`), so any candle that straddles both is always scored LOSS — a conservative but arbitrary
tie-break that, combined with including the entry bar, can convert a real win into a recorded loss.

```
trade_auditor.py:174-184  UPDATE Fact_Live_Trades SET Actual_Outcome=%s
                          WHERE "timestamp"=%s AND Asset_ID=%s AND Strategy_ID=%s AND Entry_Price=%s
```
`Entry_Price` is bound as `float(entry)`; equality on a floating point column is non-robust. (The
unique key on the table is `(timestamp, asset_id, strategy_id, signal_value)` — the auditor keys on
`Entry_Price` instead of `signal_value`, so it both risks float-mismatch and ignores the actual unique
constraint.)

```
$ wc -l src/layer6_auditor/tools/patch_actual_outcome.py
0   src/layer6_auditor/tools/patch_actual_outcome.py     # empty utility referenced in CLAUDE.md
```

(`Fact_Live_Trades` is currently empty, so this is a latent label-quality bug, not yet realized — but
it governs the labels that train Layer 3, so it matters before any live history accumulates.)

---

## 3. Root cause

The auditor treats the recorded bar `timestamp` as the exact moment of exposure and starts the path
scan there, with no offset for the fill time and no decision on entry-bar inclusion. The patch then
identifies the row by a float price instead of the table's real unique key.

## 4. Proposed fix

1. **Start the path strictly after the entry**: scan M1 candles with `time > fill_time` (or at minimum
   `> entry_bar_close`), excluding the entry bar's pre-fill range. Record and use a fill timestamp
   distinct from the signal bar timestamp.
2. **Key the UPDATE on the real unique constraint** `(timestamp, asset_id, strategy_id, signal_value)`
   instead of `Entry_Price`; drop the float-equality predicate.
3. **Resolve the empty helper**: either implement `tools/patch_actual_outcome.py` or remove it from
   the codebase and CLAUDE.md so no workflow silently relies on a no-op.
4. Optionally make the intrabar SL-before-TP tie-break explicit/configurable and documented, since on
   M1 granularity straddling candles are rare but not impossible.

## 5. Validation plan

- Unit test with a synthetic M1 path where SL is touched only in the entry bar's pre-fill minutes:
  assert the corrected auditor returns PENDING/correct outcome, not the spurious LOSS today.
- Test the UPDATE keys on `signal_value` and patches the intended row when two rows share an
  `Entry_Price`.

## 6. Rollout / risk

Read-mostly: the auditor only writes `Actual_Outcome`. Changes are additive and can be validated on a
replay before re-running against live rows. No order placement involved. Because labels feed Layer 3,
re-audit historical rows after the fix so training data is consistent.

## 7. One-paragraph summary

The Layer 6 auditor replays M1 candles starting at the entry bar inclusive, so price action *before*
the actual fill (and the always-SL-first intrabar tie-break) can assign a WIN/LOSS the trade never
experienced — a boundary leakage into the very `Actual_Outcome` labels that retrain the ML gatekeeper.
It also patches rows by fragile float equality on `Entry_Price` instead of the table's real unique key
`(timestamp, asset_id, strategy_id, signal_value)`, risking missed updates, and the documented
`tools/patch_actual_outcome.py` helper is a 0-byte no-op. Fix: scan strictly after the fill timestamp,
key the UPDATE on the unique constraint, and implement-or-remove the empty helper.
