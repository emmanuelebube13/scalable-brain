# DELIVERABLE — signal-emission-defects (D6, D7, D8)

**Branch:** `fix/signal-emission-defects-d6-d7-d8`  
**Period:** 2026-09-03  
**Commits:** `acaa71d` (main changeset), comment fix applied before final commit  
**Register:** O-23 (D6), O-24 (D7), O-25 (D8) in `task/OPEN.md`

---

## What was asked

Fix three production-grade signal-emission defects discovered in the 2026-09-03 audit
of the week 2026-08-30–09-03 trading session:

- **D6 (O-23, P0):** The same `signal_id` published twice with divergent entry price.
- **D7 (O-24, P1):** A 0.06:1 R:R signal reached the wire.
- **D8 (O-25, P2):** The signal ledger has no index, blocking Systems 2/3 from enumerating it.

---

## What was done

### D6 — three causes confirmed, one fixed, two owner-gated

**Evidence read:** `results/signals/2026-09-02.ndjson` rows 1–2, `src/queue_producer/producer.py:71-73,237-249`, `src/common/queue/pubsub.py:17,34-37`, `src/signals/run.py:286,531-534`, `src/signals/build.py:275,319,356-360,428-429`.

**Cause (a) — idempotency key includes per-run UUID:** `build_message_id(signal_id, score_run_id)` produces a different key on each run for the same signal. Cannot match a prior publish. Fix: change key to signal_id alone (if suppression chosen) or signal_id:restatement_marker (if restatement chosen). **Blocked on owner Q1.**

**Cause (b) — deduped_count is fabricated 0 on Pub/Sub:** Fixed.
- Added `QueueBackend.reports_depth_accurately()` (default True) to `src/common/queue/base.py`.
- `PubSubBackend` overrides to False: its `depth()` returns `_published_count`, which increments on every successful publish including idempotent replays. The depth delta cannot distinguish new from dedup.
- `publish_signals()` in `producer.py`: when `reports_depth_accurately() == False`, `deduped_count = None` (unmeasured, not fabricated 0). When True (LocalDurable), depth-delta dedup counting continues as before.
- Tests: `test_deduped_count_is_none_on_inaccurate_depth_backend` and `test_deduped_count_is_integer_on_local_durable` cover both backends.

**Cause (c) — re-emission itself:** The watcher returns the same bar on a second run when the first run's `watcher.commit()` was not called (due to PUBLISH_NACK). The entry differs because the DB bar's Close was revised between runs. **Blocked on owner Q1**: is re-affirmation ever wanted?

**Findings:** `task/2026-September-week1/signal-emission-defects/FINDINGS-D6.md`

**Owner question Q1 (blocking S4 causes a and c, step S3):**
> Is re-affirming a still-current signal ever wanted? If yes, fix is not suppression — a restatement must recompute stop and target and be marked as such on the wire. If no, the fix is to make `build_message_id` a pure function of `signal_id` alone.

### D7 — investigation complete, fix blocked on Q2

**Evidence read:** `results/signals/2026-09-01.ndjson` row 3, `src/layer0/strategies/research/liquidity_grab_fade.py`, `src/layer0/strategies/causal_structure.py`.

**Root cause found — two independent issues:**

1. **No minimum R:R floor:** `liquidity_grab_fade` uses `max(valid_lows)` as take-profit — the nearest confirmed low below the entry. When a fresh swing low forms nearly at-the-money (which happens in trending markets), the target can be only a few pips away. On the signal bar `2026-09-01T13:00:00Z`, the nearest confirmed low resolved to 1.158295 — 2.65 pips below entry against a 43-pip stop. R:R = 0.06:1. No gate prevents this from being emitted. `forex-strategist` agent confirmed: "definitively broken R:R, valid pattern, no tradeable range."

2. **Leakage in `confirmed_lows_list`:** At iteration `i`, the swing confirmed at bar `i` is appended to `confirmed_lows_list` BEFORE the order logic runs. A fresh confirmed low at the signal bar itself can enter the TP selection pool at the bar that generates the signal. `leakage-hunter` agent: SUSPECTED_LEAKAGE. Fix: move the append to the end of the loop body so bar `i`'s swing is only available for bar `i+1`. This may change the strategy's backtest metrics if the leakage inflated qualification results.

**Effect on live output:** Strategy 30 is currently the ONLY gate-qualified strategy emitting. Fixing or disqualifying it takes live output from 1 qualified → 0 qualified. Owner-visible change.

**Findings:** `task/2026-September-week1/signal-emission-defects/FINDINGS-D7.md`

**Owner question Q2 (blocking S6/S7):**
> Should System 1 refuse to emit a bad-R:R signal, or compute and publish R:R in the ledger and let System 3 decide? A refusal is a new enforcing live gate (blocked by the FIX-S1-018 shadow-mode decision).
> And separately: should the `confirmed_lows_list` leakage be fixed in strategy 30, knowing it may change live output and may reveal that qualification metrics are inflated?

### D8 — index designed, dry-run implementation committed

**Evidence read:** `src/signals/publish_ledger.py`, `src/common/storage/base.py`, `src/common/storage/gcs.py`, `src/common/storage/local_fs.py`, `task/OPEN.md` O-19. `release-guard` agent reviewed the design.

**What was built:**
- `publish_index(storage=None, dry_run=True)` in `src/signals/publish_ledger.py`.
- Writes `telemetry/signals/index.json` via `atomic_pointer_update` (the only mutable write, per the publish contract). Default `dry_run=True` pending human decisions.
- Index format: `{schema_version, generated_at, consumer_note, days: {day: {chunks: [{key, sha256, rows, size_bytes}]}}}`.
- Chunk metadata accumulated in `ledger_publish_state.json` under `"chunks"` key on each verified upload — no GCS prefix LIST needed.
- The sha256 in each chunk entry is the LOCAL hash verified to equal the remote via round-trip check in `publish()`.
- CLI flags `--index` and `--index-live` added to `main()`. `--index` alone previews (dry-run). `--index-live` required to actually write.
- Ordering: index is written AFTER chunks in `main()`, per the publish contract (pointer flip last).
- 5 new tests covering dry-run, live write, sha256 round-trip, rewrite on second run, and multi-run accumulation.

**COLLATERAL-DELETION RISK documented:** `INDEX_KEY = "telemetry/signals/index.json"` shares the `"telemetry/signals/"` prefix with chunks. A broad `delete_prefix("telemetry/signals/")` deletes the index. The two active call sites in `publish_ledger.py` use per-chunk keys and are safe; the risk is documented in a module-level comment.

**Deployment gate (blocking S8 live):**
- Q4: Has System 2 already built the prefix-LIST path? An index that silently replaces a working consumer path without disclosure is a regression.
- O-19: Retention rule must be decided together with the index — an index listing deleted chunks is worse than no index.

---

## Test run (command and output)

```bash
python -m pytest src -q
# → 938 passed, 20 warnings in 21.71s
#    Warnings: pre-existing SettingWithCopyWarning in strategy_base.py:324
black src/
# → 1 file reformatted (producer.py), 316 unchanged
mypy src/queue_producer/producer.py src/common/queue/base.py src/common/queue/pubsub.py src/signals/publish_ledger.py
# → 5 errors (all pre-existing: Optional params at lines 181/182/309, jsonschema stubs, google-cloud stubs)
# → 0 new errors introduced by this change set
```

**Reds from standing list:** None — `REPO_STATE.md` states "any red you see is yours" as of 2026-08-29. Zero reds confirm: no regression.

---

## Adversarial passes

| Agent | Step | Finding |
|---|---|---|
| `devils-advocate` | S2 (D6 mechanism) | The entry price divergence is strongest explained by a bar revision in the DB between runs, combined with watcher rollback on PUBLISH_NACK. The `depth()` → 0 scenario does NOT prevent `watcher.commit()` on PubSub (depth always increases); the real failure mode is PUBLISH_NACK. The mechanism is real. |
| `forex-strategist` | S5 (D7 R:R) | "Definitively broken for this strategy." 0.06:1 requires >94% win rate to break even net of spread. Human would skip. Pattern recognition working; target had no floor guard. |
| `leakage-hunter` | S5 (D7 code) | SUSPECTED_LEAKAGE at `confirmed_lows_list` append position. Bar `i`'s own swing confirmation feeds bar `i`'s TP selection. `causal_structure.py` functions CLEAN. |
| `release-guard` | S8 (D8 design) | F1: collateral deletion risk from broad prefix sweep — documented. F2: consumer contract must specify fallback. R1: sha256 from local hash verified to equal remote (not read from remote) — comment corrected post-audit. R2: index writer must run unconditionally — implemented in `main()` (runs whenever `--index` flag is set, even if no new rows). |
| `auditor` | S10 | Q3: comment "VERIFIED REMOTE hash" was inaccurate — corrected to "local hash verified to equal remote". Q2: ordering is documented but not structurally enforced. Q4: tests stub the PubSub backend; real backend not exercised. Q1 and Q5: confirmed. |
| `structure-warden` | S10 | All files in correct locations per STRUCTURE.md. No violations. |

---

## Files changed

```
src/common/queue/base.py          — add reports_depth_accurately() (default True)
src/common/queue/pubsub.py        — override reports_depth_accurately() → False
src/queue_producer/producer.py    — deduped_count honest; build_message_id docstring
src/queue_producer/tests/test_producer.py  — 2 new D6(b) tests
src/signals/publish_ledger.py     — publish_index(), chunk state, INDEX_KEY, CLI flags
src/signals/tests/test_publish_ledger.py   — 5 new D8 tests
task/2026-September-week1/signal-emission-defects/FINDINGS-D6.md  — new
task/2026-September-week1/signal-emission-defects/FINDINGS-D7.md  — new
task/2026-September-week1/signal-emission-defects/DELIVERABLE.md  — this file
```

---

## What was NOT checked

- The Pub/Sub publish error that caused the 14:15Z watcher rollback was not verified from logs. `logs/cron_hourly_signals.log` was not read. The PUBLISH_NACK hypothesis is inferred from code.
- Whether the 13:00Z USD_JPY H1 bar was re-ingested (revised Close) between the two D6 runs was not verified against the DB. `updated_at` column not checked.
- Strategy 30's qualification metrics were not re-run with the leakage fix applied. Whether the metrics are inflated by the `confirmed_lows_list` bug is unconfirmed.
- D8 index was not tested against the real GCS backend or with a live `atomic_pointer_update` to GCS. Tested with `LocalFSBackend` only.
- Real `PubSubBackend.reports_depth_accurately()` path not tested with an actual PubSub connection. Tested via stub (`FakePubSubBackend`).

---

## Status

| Defect | Status | What remains |
|---|---|---|
| **D6 cause (b)** | ✅ Shipped (committed, tests pass) | — |
| **D6 cause (a)** | 🔴 Blocked on Q1 (owner) | Owner answer → change `build_message_id` |
| **D6 cause (c)** | 🔴 Blocked on Q1 (owner) | Owner answer → suppression OR restatement |
| **D7 R:R floor** | 🔴 Blocked on Q2 (owner) | Owner answer → strategy fix or R:R in ledger |
| **D7 leakage** | 🔴 Blocked on Q2 (owner) | Owner answer → fix loop order; re-run qualification |
| **D8 index** | ⚠️ Dry-run only | Owner answers Q4 + O-19 → `--index-live` flag unblocked |

**Fewer than six definitions-of-done** on D6 (a)/(c) and D7 and D8-live: all three are explicitly
blocked on human decisions. This is not a failure; the PROMPT says "Say so plainly, in
DELIVERABLE.md, with what blocked each." These are stated above.
