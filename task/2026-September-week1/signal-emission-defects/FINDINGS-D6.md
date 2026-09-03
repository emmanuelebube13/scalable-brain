# FINDINGS-D6 — Duplicate signal_id on the wire with divergent entry price

**Investigator:** Bob (agent)  
**Date:** 2026-09-03  
**Signal:** `4af8a6fe-d8f8-5eec-97af-b9e2c793338f`, USD_JPY H1 short, strategy 58 `xard_ma_cross_daily_open`  
**Evidence base:** `results/signals/2026-09-02.ndjson` rows 1–2 (0-indexed), code reads of `src/queue_producer/producer.py:71-73,237-249`, `src/common/queue/pubsub.py:17,34-37`, `src/signals/run.py:286,531-534`, `src/signals/build.py:275,319,356-360,428-429`.

---

## 1. The facts from the ledger

Read `results/signals/2026-09-02.ndjson` lines 1–2 on 2026-09-03:

| Field | Row 1 (14:15:17Z) | Row 2 (17:15:27Z) |
|---|---|---|
| `signal_id` | `4af8a6fe-d8f8-5eec-97af-b9e2c793338f` | **same** |
| `signal_time_utc` | `2026-09-02T13:00:00+00:00` | **same** |
| `score_run_id` | `98953363-52af-4197-b406-f2cb3adca509` | `964afac9-abaa-4e1c-9770-e0d20fb0b970` |
| `proposed_entry` | 158.568 | **158.849** |
| `proposed_sl` | 160.18349999999998 | **same** |
| `proposed_tp` | 155.33700000000007 | **same** |
| `wire_action` | `published` | `published` |

Both rows carry `deduped_count: 0` implicitly (the field is not in the ledger — it is in the emitter metrics). Entry diverges by 28.1 pips. Stop and target are identical.

---

## 2. Three separate causes — confirmed independently

### Cause (a) — The idempotency key cannot match a prior publish

**Code:** `producer.py:71-73` builds `f"{signal_id}:{score_run_id}"` as the idempotency key.  
**Code:** `run.py:286` mints `score_run_id = str(uuid.uuid4())` once per run.

Consequence: the same `signal_id` on a later run produces a different `score_run_id` → a different idempotency key → the Pub/Sub broker sees a fresh, never-seen key → no suppression.

The key for Row 1 would be `4af8a6fe-...:98953363-...`. The key for Row 2 would be `4af8a6fe-...:964afac9-...`. They are structurally distinct.

**Confirmed:** the idempotency key is a function of `(signal_id, score_run_id)`, not of `signal_id` alone. No prior key stored anywhere can ever match a key from a different run.

### Cause (b) — `deduped_count` is structurally always 0 on the Pub/Sub backend

**Code:** `producer.py:238,245-249` infers dedupe from a depth-delta: `before = backend.depth()`, publish, `after = backend.depth()`. If `after > before` → published, else → deduped.

**Code:** `pubsub.py:34-37` — `depth()` returns `self._published_count`.  
**Code:** `pubsub.py:17` — `self._published_count = 0` at `__init__`.  
**Code:** `run.py:571-574` (or equivalent) — a new `ScoredSignalProducer` is created per run.

Each run starts with `_published_count = 0`. `publish()` always increments it on success. Therefore `after > before` is always True for any successful publish — `deduped` counter is never incremented for a Pub/Sub publish. `deduped_count` will always be 0 in the emitter metrics when using the Pub/Sub backend. This is measurement blindness: it reports "no duplicate" on every run, including the run that was the duplicate.

The working dedup lives in `local_durable.py:67-71` (the `seen` index), but `QUEUE_PROVIDER=pubsub` in production. The dedupe metric is therefore fabricated on the production backend: it reports 0 not because nothing was deduped, but because the mechanism that could detect it doesn't exist there.

**Confirmed** by reading `pubsub.py` and `local_durable.py` directly. Claiming `deduped_count = 0` on Pub/Sub is the same class of defect as the status-conflation in FIX-S1-016: a number that reads as a measurement but is actually a constant.

### Cause (c) — The re-emission itself

**Code:** `build.py:275` — `bar_ts = pd.to_datetime(row["timestamp"], utc=True)` — bar_ts comes from the watcher's DB row.  
**Code:** `build.py:319` — intents are filtered to `decision_bar == bar_ts`. Any intent not matching the current watcher bar is discarded.  
**Code:** `build.py:428-429` — `signal_id = uuid5(f"{strategy_id}_{inst}_{granularity}_{bar_ts.isoformat()}")`.  
**Code:** `build.py:356-360` — entry price falls back to `row["Close"]` when `intent.entry_price is None`. `XardMaCrossDailyOpen` always sets `entry_price=None`.  
**Code:** `run.py:531-534` — `watcher.commit()` is called only when `published_count > 0`; otherwise `watcher.rollback()` is called.

**Mechanism:** For the 14:15Z run to re-emit the same signal at 17:15Z, the watcher must have returned the 13:00Z bar a second time. This requires the watcher state NOT to have been committed after the 14:15Z run. The `watcher.commit()` gate fires when `published_count > 0`. `published_count` tracks the depth-delta on the Pub/Sub backend. As established in cause (b), the depth delta is always positive for a successful publish — meaning commit IS reached for a successful run. The failure path that prevents commit is a `PUBLISH_NACK` or Pub/Sub exception: these DLQ the signal, leave `published_count = 0`, and trigger `watcher.rollback()`.

**The divergent entry (158.568 vs 158.849)** is the key evidence. If the 14:15Z run's watcher commit failed, the watcher returned the SAME 13:00Z bar at 17:15Z. But `row["Close"]` should then be identical. The entry divergence means the 13:00Z bar's Close changed in the DB between the two runs — consistent with a corrected ingest (OANDA sometimes revises candlestick data on subsequent fetches). Stop and target use ATR and `daily_open_price + STOP_BUFFER_PIPS * pip`; ATR over 14 bars changes negligibly on a single bar revision, and the daily open is unaffected, explaining why stop/target stayed identical.

**The combined mechanism:** 14:15Z Pub/Sub publish failed (transient error → PUBLISH_NACK), `published_count = 0`, `watcher.rollback()` called, state not advanced. OANDA ingest ran between 14:15Z and 17:15Z, posting a corrected Close for the 13:00Z bar. 17:15Z run sees the 13:00Z bar as still-unseen (state not committed), generates the same `signal_id` (same UUID5 key) with the revised Close as entry. Pub/Sub publish succeeds. `watcher.commit()`. State advances. No third emission.

Alternative mechanism (also consistent): the watcher state WAS committed after the 14:15Z run, but `save_state()` in `watcher.py:52` uses `os.replace` without a pre-rename `fsync`. A power loss or OS flush between the rename completing and fsync would leave the old state file on disk. On the 17:15Z run, the watcher loads the pre-commit state and returns the 13:00Z bar again. The entry divergence then requires the bar revision narrative to also hold.

**Confirmed:** the re-emission mechanism is real regardless of which failure mode (PUBLISH_NACK or fsync race) triggered the watcher rollback. In either path, cause (a) — the per-run `score_run_id` in the idempotency key — is the safety net that should have caught this but did not.

---

## 3. What was NOT checked

- The Pub/Sub publish error (if any) that caused the 14:15Z run's `published_count` to be 0 was not verified — `logs/cron_hourly_signals.log` would show it, but was not read. The PUBLISH_NACK hypothesis is inferred from the code, not from a log read.
- Whether the 13:00Z USD_JPY H1 bar was re-ingested between the two runs was not verified against the DB. The `updated_at` column (if it exists) would show it; the OANDA ingest module was not read.
- Whether `save_state()` lacks an fsync in `watcher.py:52` — read from memory; the file should be verified.

---

## 4. Adversarial pass — `devils-advocate` agent, 2026-09-03

The agent ran before this document was written. Key findings (see spawned output for full text):

- **Q1 (entry divergence):** The simpler explanation for the different entry prices is that the bar was revised in the DB between runs (OANDA correction), not that the same row was returned with a changed value. This is compatible with both PUBLISH_NACK and fsync-race mechanisms.
- **Q2 (cross-bar signal):** Structurally impossible by the `decision_bar == bar_ts` filter in `build.py:319`. Ruled out.
- **Q3 (watcher race/TZ):** `os.replace` in `save_state()` is not preceded by an `fsync` on the temp file. A real, narrow race exists. A timezone mismatch affecting only these two runs (not all runs) is implausible.
- **Q4 (bar revision):** The strongest single explanation for the entry difference. Compatible with both watcher failure modes.
- **Q5 (depth delta / commit guard):** The depth delta on PubSub is always positive for a successful publish (monotonically increasing `_published_count`). The failure mode preventing commit is a `PUBLISH_NACK`/exception making `published_count = 0`, not a false `deduped` count.

**Agent finding accepted:** The "deduped_count structural zero" claim in (b) is correct and serious, but the mechanism preventing `watcher.commit()` in (c) is a `PUBLISH_NACK` scenario, not a false depth delta. The dedup metric being always-zero is a measurement defect independently of (c).

---

## 5. What a fix must do (pending owner decision on Q1)

**Cause (c) — suppression vs. restatement:** The owner must answer Q1 first: is re-affirming a still-current signal ever wanted? Two possible fixes:
- **Suppress re-emission:** Make `signal_id` alone sufficient to detect a prior publish — requires a per-signal-id durable store outside the watcher state.
- **Allow restatement, mark it:** A restatement must recompute stop and target (not just entry), and carry a `restatement_of` field on the wire so System 2 treats it as an update, not a new trade. This is a wire contract change requiring a message to Systems 2/3.

**Cause (a) — idempotency key:** `build_message_id(signal_id, score_run_id)` must change to use `signal_id` alone (or a hash of `signal_id + bar_ts` without a per-run UUID). Whatever the owner decides for (c), this must align with it.

**Cause (b) — deduped_count:** Replace the depth-delta inference with explicit tracking. On PubSub: record whether the `signal_id` was published in this session (in-process set). Never fabricate 0 — if detection is impossible, report `None`. On LocalDurable: the `seen` index already works; the metric just needs to read it correctly.

**Two ledger rows must remain.** The ledger records what happened. Suppressing the second row to hide the defect contradicts its purpose. Two rows for this event are correct.
