# Work Order 03B — Resume Work Order 03. The stop is overturned. Take it live.

**Owner decision, 2026-09-09: SHIP IT.** The system has been on maintenance and not trading since
2026-09-04. Getting a fresh, admissible, honestly-labelled map live is the priority. A hotfix
after the fact is acceptable; continued non-trading is not.

**You did the right thing stopping.** The rule said a `NOT SUPPORTED` verdict halts the stage, and
you halted, did not work around it, and published nothing. That is exactly the discipline asked
for. The verdict itself was wrong — that is not your error.

---

## 1. The `forex-strategist` verdict is OVERTURNED

It gave two reasons for `DEFINITIVELY BROKEN`. Both were measured by the reviewer on 2026-09-09
and both are false.

**"Breaks temporal persistence, flickers hour by hour."** EUR_USD H1, full history:

| baseline | flicker | mean run | median run |
|---|---|---|---|
| pooled (incumbent) | 0.0752 | 13.30 bars | 7 |
| **per-slot (rejected)** | **0.0733** | **13.63 bars** | 7 |

The rejected version is **more** persistent.

**"Arbitrarily spans a full calendar year, smearing macro environments."**

```
pooled   6048 consecutive H1 bars = 252 days = 1.00 trading years
per-slot  252 same-hour observations = 252 days = 1.00 trading years
```

Identical span. The critique applies equally to the incumbent, so it cannot favour it.

**The proposed remedy makes the defect worse.** A pooled 1–2 week window still spans all 24 hours:

| baseline | diurnal bias |
|---|---|
| pooled 1 year (incumbent) | 3.79× |
| pooled 2 weeks (proposed remedy) | **7.75×** |
| pooled 1 week (proposed remedy) | **9.08×** |
| per-slot (rejected) | **1.08×** |

`forex-strategist` has been amended: `DEFINITIVELY BROKEN` now requires a measured failure, a
measured comparison against the alternative, and a measured remedy. An unmeasured concern is
`QUESTIONABLE`, which does not stop work.

## 2. What still stands, and is the real question

`measurement-reviewer`'s finding is **not** overturned: coverage reached 100% but there is no
evidence map *quality* improved, and gate failures rose slightly.

That is correct, and it was expected — `ARCHITECTURE.md` §8 says so outright: *"This change is a
correctness fix, not a performance fix. Do not expect it to make money."*

The control-vs-treatment table settles the practical question:

| | control (HMM) | treatment (structural v2.1.0) |
|---|---|---|
| **qualifying cells** | **6** | **6** |
| UNKNOWN share | 79.96% | **0.00%** |

**Same qualifying cell count, on five times the labelled evidence.** The owner has weighed this
and elected to ship.

---

## 3. Resume here

### Stage D — generate the map

1. `vet` **log-only**. Report every qualifying cell: strategy, granularity, regime, trades, PF,
   Sharpe, OOS months, `selection_basis`. Report the orphaned-designation warnings from
   WO-03 §4b(ii) — name every designation that found no cell.
2. Diff it cell-by-cell against the live map (`generated_at_utc 2026-08-24`, 14 cells).
3. **Run `devils-advocate`.** It was skipped when the stage aborted and it is the gate that
   matters most before a live map.
4. Report, then proceed — the owner has pre-authorised the live write, so you do not stop again
   for sign-off unless a gate fires.

### Stage D-live — write the live map

The freeze exists because the map was selected on HMM labels while routing ran on structural ones.
**That condition no longer holds:** selection and routing are both `regime_structural`, so the
map's `source_label` will match `ROUTING_SOURCE_LABEL` and it will be admissible.

```
REGIME_MAP_WRITES_FROZEN=false python -m src.vetting.vet --live
```

Set it **on that invocation only.** Do not export it, do not put it in `.env`, do not leave the
freeze off afterwards.

Then confirm, as command output: the new map's `source_label`, `expires_at_utc`, `status`, and
`qualification_run_id`.

### Stage E — publish the model set

**Do NOT retrain the gatekeeper.** Its degeneracy guard refuses, correctly, and that is Work Order
04. Pair the new System 1 bundle with the **existing** gatekeeper pointer — the top-level manifest
is a pure function of the two sub-pointers, so this is a supported pairing.

Use the `publish-model-set` skill. Do not reconstruct the ordering: versioned prefix → SHA256
round-trip verify → archive previous → **pointer flip last**.

**Run `release-guard` before the flip.** It was skipped too.

**State this in your report:** the live champion was trained on the previous label definition and
will now score `structural-v2.1.0` labels. That is train/serve skew, tolerable only because the
gate is in shadow mode and nothing is gated on the score. **Shadow approval statistics are
uninterpretable until WO-04 completes** and any report quoting them must say so.

### Stage F — confirm trading resumes

1. Run `shell/cron_hourly_signals.sh` and capture the outcome.
2. **Success is `last_run_outcome` no longer `risk_off` for a map reason.** A refusal for a
   *different* reason is a new finding — report it, do not fix it silently.
3. If the market is closed or no strategy fires, that is a quiet market, not a failure. Say which.
4. Report `signal_emitter_state.json` in full.

---

## 4. Rollback — read this before you publish

The owner has accepted a hotfix path, which means you must leave one open.

**Before the pointer flip:** confirm `previous.json` was archived. That is the rollback.

**If the map goes live and is wrong:**
```
python -m src.serializer.publish_model_set --withdraw --reason "<why>"
```
CLI-only, mandatory human reason, **never automated**. If you believe a withdrawal is needed,
**say so and stop** — the owner runs it.

**Do not** attempt to repair a bad live map by hand-editing `results/state/regime_strategy_map.json`.
A map was hand-edited on 2026-09-05 and its justification did not reproduce; that edit is still
live and is why the register carries an orphaned-designation item.

**Rollback is not failure.** Shipping and withdrawing cleanly is a better outcome than not
shipping.

---

## 5. Constraints — unchanged

- **Do not retrain the gatekeeper.** Do not relax `MAX_DEGENERATE_CELL_SHARE` or any guard.
- **Do not change a vetting gate** to admit a cell. If the map is thin, that is the finding.
- **Do not run `designate.py`, `--reconcile`, or `--withdraw`.**
- Do not leave `REGIME_MAP_WRITES_FROZEN` unset after the run.
- Do not hand-edit anything under `results/`, `models/`, `model-artifacts/`.

## 6. Gates for this work order

| after | invoke | note |
|---|---|---|
| Stage D | `devils-advocate` | **skipped last run — mandatory now** |
| Stage D-live | `db-guardian` | the live write and the new `qualification_run_id` |
| Stage E | `release-guard` | **skipped last run — mandatory now.** Publish ordering, pointer pairing, the two `status` fields, the skew disclosure |
| before close | `structure-warden` | sweep: place files, fix references, run the suite |
| last | `auditor` | verify deliverables and claims, on the final layout |

A `DEFINITIVELY BROKEN` verdict now requires measured evidence (see §1). A gate that returns it
without measurement is not a stop — report the gate's failure to meet its own standard and
continue.

## 7. Deliverables

Append to `audit/reports/work_order_03.md` — do not start a new file; the earlier sections are
cited by this one. Add:

1. The map as generated: every qualifying cell, full metrics.
2. Cell-by-cell diff against the 2026-08-24 live map.
3. Orphaned designations, by name.
4. Publish output: version prefix, SHA256 verification, `previous.json` archived, pointer flip.
5. `signal_emitter_state.json` after the first post-publish run.
6. What `devils-advocate` and `release-guard` returned.

Update `SUMMARY-03.md` with a short "03B" section: what changed, whether trading resumed, and
**what you would want watched over the next 24 hours.**
