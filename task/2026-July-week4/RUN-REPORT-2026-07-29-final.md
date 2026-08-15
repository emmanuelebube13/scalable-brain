# RUN-REPORT — 2026-07-29 (final)

**All six tasks complete.** 33 commits, working tree clean, nothing pushed.
269 tests passing (1 skipped). Week rollup at `deliverables/WEEK-EXECUTIVE-SUMMARY.md`.

---

## 1. Status board

| Task | Status | Deliverables | Note |
|---|---|---|---|
| **T1** reconnect-feedback-loop | **DONE** | ✅ all | Outcomes current through 2026-07-24; 42 guard tests |
| **T2** secrets-and-env | **DONE** | ✅ all | Password rotated, verified dead, 27 occurrences purged |
| **T3** promote-verified-work | **DONE** | ✅ all | Owner signed off; `2026-07-29T11-46-42Z-55dacdbf` live |
| **T4** heartbeat-monitoring | **DONE** | ✅ all | 8 checks, daily cron, first run 8/8 PASS |
| **T5** derisk-money-layer | **DONE** (capture BLOCKED) | ✅ all | Fix package ready; VM capture needs you |
| **T6** research-strategy-engine | **DONE** | ✅ all | Sandbox live; pilot refused at the gate |
| **T7** archive-v1-cleanup | **NOT-STARTED** | — | Runs strictly last; has its own user checkpoint |

Every task has `DELIVERABLE.md`, `EXECUTIVE_SUMMARY.md` and its named charts.

## 2. Failures — all eleven were defects in the task prompts, not the code

Each was corrected in place with a `## Failure log` entry, so re-running any prompt now does
the right thing.

| # | Task | Problem | Correction |
|---|---|---|---|
| 1 | T1 | Root cause blamed space-named dirs that Python never imports | Mission rewritten with the real three-part cause |
| 2 | T1 | Described an `ON CONFLICT` backfill; the writer actually DELETEs then rebuilds | Step mandates a snapshot first |
| 3 | T1 | Omitted `--lookback-years`; the default silently halved history | Step mandates `10` and checking the **min** timestamp |
| 4 | T1 | Validated against `src/layer0/tests/`, which didn't exist | Created; validation now uses `src.common.db` |
| 5 | T2 | Embedded a literal fragment of the live password | Step 0 added; greps use `$OLD_DB_PASS` |
| 6 | T2 | Non-`-F` grep missed the worst exposure | All inventory greps use `-F` |
| 7 | T3 | "0.965 ratchet" doesn't exist — it's the live bundle's accuracy | Real mechanism documented; two fixes shipped |
| 8 | T3 | Step 3 (`--force`) would have promoted before your sign-off | Rewritten to a non-promoting evaluation path |
| 9 | T4 | "26h" price threshold would fire 6 days out of 7 | Rewritten against the weekly ingest + market calendar |
| 10 | T4 | Outcomes check couldn't detect the failure it was written for | Now asserts `created_at` recency |
| 11 | T6 | Told me to migrate `strategieStaged` — would have demoted the live model | Deliberately not done; adapter path recorded |

Plus one defect in **my own** code, logged rather than quietly fixed: T6's first metrics
implementation reimplemented drawdown and reported 1650%. Fixed by importing the live metrics —
the same discipline as not copying thresholds.

## 3. What to do next, in order

1. **Run the VM capture command** — `deliverables/T5/DELIVERABLE.md` §1. Five minutes. The code
   that sizes your real-money positions has no copy anywhere but that machine.
2. **Decide whether to publish the model set** so Systems 2/3 actually receive the bundle you
   promoted (`python -m src.system1.serializer.publish_model_set`). Until then they may still be
   on the 26 July version.
3. **Apply the money-layer fixes** on Computer 3 — `deliverables/T5/../T5-fix-package/HANDOFF.md`.
   Currency assertion → S3-004 → populate positions (S3-001) → S3-002. **Do not unblock the
   sizing lockout in the same session.**
4. **Paste `T7-archive-v1-cleanup.md`** — it is now unblocked (T1–T6 all DONE) and has its own
   mandatory checkpoint before any file moves.
5. **W32: answer why all ten live trades lost.** Everything else is now instrumented to support
   that question.

## 4. Decisions pending

| Decision | Recommendation |
|---|---|
| Publish the model set to Systems 2/3 | Your call — a rollout step, not a consequence of the promotion |
| Rewrite git history for the dead password | **No** — breaks every clone to remove a risk that no longer exists |
| `GATEKEEPER_AUTOPROMOTE` | **Not yet** — wait for the repaired gate to bind on ≥1 scheduled retrain |
| Unblock the S3-006 sizing lockout | **Not yet** — it is currently the only thing preventing further loss |
| Move price ingest from weekly to daily | Worth it — would cut dead-feed detection from ~8 days to 24h |
| Drop `fact_trade_outcomes_bak_20260729` | Safe now that T3 is signed off |

## 5. Week verdict

**Yes — the system is substantially closer to doing what it is meant to do, and the week also
revealed that the hard problem is somewhere else entirely.**

Four of the five first-principles moved decisively. The feedback loop is live after five weeks
frozen. The promotion gate performed its first genuine comparison in the project's history —
before this week it had *never* actually compared a challenger to the incumbent, on any
promotion. Failures are visible via a daily watchdog with thresholds that match how the system
actually runs. Secrets are out of the tree.

The money layer is the honest laggard, for a reason worth stating plainly: **the live account
has taken ten trades and lost all ten**, and the sizing gate that is jammed shut is the only
thing currently preventing further loss. Two real unit bugs were found — one of which *breaches
your hard risk cap* on cross pairs — and both are packaged, tested and ready. But applying them
makes sizing **correct**, not **profitable**, and correct sizing of a negative-edge strategy
loses money faster.

That connects the week's two ends. System 1's own findings say the live model is one strategy
and the regime classifier doesn't discriminate between strategies. Ten trades, ten losses is
that finding cashed out in money. This week built the machinery to *know the truth* — reliable
outcomes, a gate that actually gates, a sandbox that can test an idea without risking anything,
and monitoring that will say when any of it stops working.

**Whether the truth is good enough to trade is now the open question, and it is the right one
to be facing.**
