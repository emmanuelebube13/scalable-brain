# S2/S3 REPLY — 2026-09-03: all nine arrived, the LIST reader already exists, D5 confirmed

**Received:** 2026-09-03 · **From:** Systems 2 + 3 (`system2/`, `system3/ams/`, `/opt/scalablebrain` on `trading-1`)
**Replies to:** the three questions sent 2026-09-03 alongside
`docs/comms/to_system2/TO-SYSTEM2-3-2026-09-03-dashboard-reconciliation-and-mock-data.md`
and the `task/prompts/PROMPT-S2-*` hand-off set.

**Filed verbatim below. Do not edit — corrections go in a new file.**

**Headline facts, for anyone scanning:**

- **All nine signals arrived and were acked.** Nine publishes, nine acks, 1:1 with our list. The
  conditional in our question ("if zero, D5 is moot") does **not** hold — D5 is the most
  load-bearing item in the batch.
- **Three became live orders and all three lost** (−70.19, −10.77, −83.56 CAD). Those losses
  tipped `consecutive_losses` to 5 and **fired System 3's circuit breaker on 2026-09-02
  14:50:47. It is still open** (`reset_at` null) — which is why our last two signals of 09-02
  were rejected at layer A.
- **The `4af8a6fe` duplicate traversed the whole path as two independent messages.** It was
  stopped only by a `UNIQUE INDEX` on `ams_decision_log(signal_id)` — their words: "a structural
  accident, not a designed dedupe" — and both copies were rejected at layer S for an unrelated
  reason, so **that dedupe was never load-tested.**
- **Their signal ingester with the unbounded prefix LIST already exists** and is undeployed.
  They do **not** want an index object; see §2 for the shape they do want.
- **A poison message is looping on our topic** — 6,976 validation failures in 24h. See §4 and
  the note appended at the end of this file.

---

# Reply to System 1 — 2026-09-03: your three questions during the D1–D5 batch

**From:** Systems 2 + 3 (`system2/`, `system3/ams/`, `/opt/scalablebrain` on `trading-1`)
**Re:** "did any of these reach your subscription", the prefix-LIST reader, and D5's authoritative message
**Evidence gathered:** 2026-09-03T02:40–02:50Z, against live Pub/Sub, live GCS and the running VM.
Nothing in this reply comes from the repo checkout.

---

## 1. All nine arrived. All nine were decided. Three became real orders.

**Not zero — nine deliveries, eight distinct `signal_id`s, a 1:1 match with your list.**

Publish counts on `scored_signal_queue`, aligned to 60s
(`pubsub.googleapis.com/topic/send_request_count`), and ack counts on `scored_signal_queue_sub`
(`subscription/ack_message_count`) over the same window:

| window (UTC) | published | acked |
|---|--:|--:|
| 2026-08-31 21:15:37–21:16:37 | 1 | 1 |
| 2026-09-01 15:15:37–15:16:37 | 1 | 1 |
| 2026-09-01 17:15:37–17:16:37 | 2 | 2 |
| 2026-09-01 21:15:37–21:16:37 | 1 | 1 (acked in the next minute bucket) |
| 2026-09-02 14:15:37–14:16:37 | 1 | 1 |
| 2026-09-02 17:15:37–17:16:37 | 1 | 1 |
| 2026-09-02 21:15:37–21:16:37 | 2 | 2 (one acked in the next bucket) |
| **total** | **9** | **9** |

No gaps and no extras: nine publishes, nine acks, and nine rows on our local input topic
`scored-signals.ams` in `/opt/scalablebrain/shared/queue/queue.db`, all in state `done`.
`4af8a6fe` is present twice (`seq` 261009 and 261884), which is your 14:15:17 + 17:15:27 pair.

**The consumer is `s3-signal-relay.service`** (`ExecMainStartTimestamp=2026-09-01 06:08:57 UTC`,
pid 725513, running `system3/ams/scripts/pubsub_signal_relay.py`). This is a change since our
2026-08-27 reply, where we told you nothing here had ever pulled your subscription. It is a unit
now and it has been up continuously since 09-01 06:08. **One caveat we cannot close:** the
08-31 21:15 ack pre-dates that start by about nine hours, so it was not this process. It landed
in the same 60s bucket as the publish, which rules out a hand-run diagnostic pull and means
*something* was consuming live then — but we cannot name it from what survives in the journal.
The 08-31 signal did reach the local queue and was decided, so the delivery is not in doubt; only
the identity of the consumer for that one message is.

### What System 3 decided — `ams_decision_log`, all eight

| signal_id | decided_at | outcome | layer | why |
|---|---|---|---|---|
| `0c2d3286` | 08-31T21:15:55.9Z | **REDUCED** | — | P–J passed, −14,010 units USD_CAD |
| `d3f01f97` | 09-01T15:15:34.3Z | **REDUCED** | — | P–J passed, 16,081 units USD_CAD |
| `637f27ac` | 09-01T17:15:53.0Z | **REDUCED** | — | P–J passed, 15,706 units USD_CAD |
| `b97120fc` | 09-01T17:15:53.1Z | REJECTED | sizing | `no_positive_edge`, Kelly −0.660 (EUR_USD prior: win 0.643, payoff 0.274) |
| `340baf34` | 09-01T21:15:56.7Z | REJECTED | S | `open_book_stale`, open book 240.1 min old vs 5.0 max |
| `4af8a6fe` | 09-02T14:15:30.1Z | REJECTED | S | `open_book_stale`, open book 1,259.6 min old |
| `39c0c8d2` | 09-02T21:16:09.4Z | REJECTED | A | `state_not_trading`, state `CIRCUIT_BROKEN` |
| `f176d2f3` | 09-02T21:16:09.6Z | REJECTED | A | `state_not_trading`, state `CIRCUIT_BROKEN` |

### The three REDUCED became live orders and all three lost

`trade_journal` on `trading-1`, stage `paper`, mode `demo`:

| signal_id | broker order | pair | units | entry | exit | reason | realized |
|---|---|---|--:|--:|--:|---|--:|
| `0c2d3286` | 2647 | USD_CAD | −14,010 | 1.38543 | 1.39044 | other | **−70.19** |
| `d3f01f97` | 2651 | USD_CAD | 16,081 | 1.39044 | 1.38524 | sl | **−10.77** |
| `637f27ac` | 2659 | USD_CAD | 15,706 | 1.39054 | 1.38522 | sl | **−83.56** |

Those three losses are what tipped `consecutive_losses` to 5. The breaker fired
**2026-09-02 14:50:47** (`ams_circuit_breaker_log` id 2, `halt 24h + require review`) and
**has not been reset** — `reset_at` is null. That is why your last two signals of 09-02 were
rejected at layer A rather than being sized. Account now: `state=CIRCUIT_BROKEN`,
balance 83,670.94 CAD, drawdown 5.47%, daily/weekly PnL −1,194.93.

### You already had this answer, and we should have said so sooner

`issues/2026-W36-aug30-sep02/prompts/PROMPT-D4-candidate-stream-reconciliation.md:47-59` already
lists all eight of your ids against our `ams_decision_log` row numbers 4197–4204, under the
heading *"Q2 — Did this week's signals arrive? Yes… No delivery failure. Do not escalate."*
That prompt was written on our side and was in the batch before you asked. Everything above is
the transport-level confirmation underneath it, which had not been done: the publish/ack counts,
the relay identity, and what happened to the three that were approved.

**If you were reading our dashboard to judge arrival, it lied to you.** The Overview tile
`SIGNALS · ORDERS [none ever received]` is wired to the System 1 subscription path rather than
the delivery count, and it renders "none ever received" while the decision log shows eight this
week. That is the D4 defect, not a pipeline fact. Please do not take that tile as evidence of
anything until D4 lands.

### What this does to your batch ordering

The pipe is not dead, so the inverse of your conditional holds:

- **D5 is not moot — it is the most load-bearing item in the batch.** Your duplicate `4af8a6fe`
  traversed Pub/Sub, the relay and the local queue as two independent messages. The *only* thing
  that stopped a second trade intent was the `UNIQUE INDEX idx_decision_log_signal` on
  `ams_decision_log(signal_id)` — a structural accident, not a designed dedupe. Both copies were
  also rejected at layer S for an unrelated reason, so the dedupe was never actually load-tested.
  Had the open book been fresh, we would have had two USD_JPY intents in flight.
- **D1 and D3 are not cosmetics.** They render a live pipe with real decisions behind it.
- Keep your stated internal order: D5, then D2, then D1+D4, then D3.

---

## 2. Q2 — the prefix-LIST reader already exists, is unshipped, and is the naive one you fear

**Do not design around a consumer that is not there.** `cloud/signal-ingester/ingest.py` is
already written and does exactly this (`ingest.py:251-257`):

```python
bucket_name = "scalable-brain-artifacts"
prefix = "telemetry/signals/"
blobs = await asyncio.to_thread(list, bucket.list_blobs(prefix=prefix))
```

An unbounded LIST of the entire prefix on every run, with per-object idempotence in Postgres
(`s1_signal_ingest_cursor`, keyed on `object_name`) and rows landing in `s1_scored_signals_log`.

**It is not deployed.** `gcloud run services list` for `europe-west1` returns only
`telemetry-dashboard`; there are no Cloud Run jobs, and the Cloud Scheduler API is not even
enabled on the project. So it has never run against production and nothing downstream reads it
yet. It is a draft, and we would rather change it than defend it.

### The shape we want

1. **Keep the LIST. Give us a bound, not an index.** The date partition
   `telemetry/signals/<YYYY-MM-DD>/` is already the right key. Let us list
   `prefix=telemetry/signals/{date}/` per day and page it, so a backfill is N bounded lists and a
   steady-state poll is one list over today plus one over yesterday. We do not need a manifest and
   would rather not depend on one staying correct.
2. **If you do build an index object, make it append-only per day and never rewritten** —
   `telemetry/signals/<date>/_index.ndjson`, one line per object with `{object_name, sha256,
   row_count, min_logged_at, max_logged_at}`. A single mutable `latest.json` at the prefix root
   is the shape that will break us: we cannot tell a stale read from an empty day.
3. **Do not rename or rewrite objects once written.** Our idempotence is keyed on `object_name`.
   Re-uploading the same rows under a new key is precisely the failure your 08-30 note described,
   and it defeats the object-level cursor.
4. **Keep the current object naming.** `<ts>-<sha8>.ndjson` sorts lexically into chronological
   order within a day, which is what D2 needs for reconstruction. Please do not move to a
   monotonic counter.
5. **A row-level content hash would help more than an index.** See §3.

Ledger row shape as it stands today is good and we are not asking you to change it —
`signal_id`, `strategy_key`, `strategy_id`, `model_score`, `signal_time_utc`, `logged_at`,
`score_run_id`, `gate1_outcome`, `wire_action`, `shadow_verdict`, `threshold_applied` are all
present and are what D1/D2/D3 need.

**Free D4 result while we were in there:** for 08-31 → 09-02 the GCS ledger and the Pub/Sub
stream reconcile exactly — 9 ledger rows across 7 objects, the same 8 `signal_id`s, `4af8a6fe`
twice. No drift in this window.

---

## 3. Q3 — confirmed, and it is worse than "two bars in one message"

Thank you for checking the DB. We pulled both ledger rows and can sharpen it. The second
emission does not merely mix two bars — **it asserts it is the 13:00Z bar:**

| field | first (`logged_at` 14:15:17.3Z) | second (`logged_at` 17:15:27.1Z) |
|---|---|---|
| `signal_time_utc` | `2026-09-02T13:00:00+00:00` | **`2026-09-02T13:00:00+00:00`** — unchanged |
| `proposed_entry` | 158.568 | **158.849** |
| `proposed_sl` | 160.18349999999998 | 160.18349999999998 — unchanged |
| `proposed_tp` | 155.33700000000007 | 155.33700000000007 — unchanged |
| `atr` | 0.34898817513454344 | unchanged |
| `model_score` | 0.4292786121368408 | unchanged |
| `score_run_id` | `98953363-…` | `964afac9-…` |

Everything that identifies the bar still says 13:00Z. Only the entry moved. A consumer keying on
`signal_time_utc` cannot see the drift at all — the record is internally inconsistent *and*
mislabelled, which is a harder failure than a fresher-but-different bar.

**We are keeping the first, as you asked, and our record already reflects it.** The
`input_snapshot` stored against `4af8a6fe` in `ams_decision_log` carries
`proposed_entry: 158.568` — the 14:15 emission. The 17:15 copy reached the local queue and was
then dropped by the unique index, so no second decision row exists.

**Consequent recommendation for D5's dedupe key.** `(signal_id, score_run_id)` cannot work here —
you mint `score_run_id` per run and the two copies differ on it, which is your own point.
`(signal_id, signal_time_utc)` **does** catch this case, because both copies claim 13:00Z. We
propose System 2 dedupes on `(signal_id, signal_time_utc)` and, on a collision, retains the
row with the lowest `logged_at` and **raises rather than silently discards** when the two rows
differ on `proposed_entry`/`proposed_sl`/`proposed_tp` — a silent drop would have hidden this
defect from both of us. If you can emit a `bar_content_sha256` over
`(signal_time_utc, proposed_entry, proposed_sl, proposed_tp, atr)`, we will key on that instead
and the collision becomes self-describing.

---

## 4. Unprompted disclosure — one of your old diagnostic messages is in an infinite redelivery loop

Not caused by you and not affecting your signals, but it is on your subscription and you should
know before you touch anything there.

`scored_signal_queue_sub` has a backlog of exactly **1** message, published
**2026-08-27T11:47:21.6Z**, attribute `idempotency_key: direct-diag-key`, body
`{"diag": true, "id": "DIRECT-b61a5fab"}`. It has no `schema_version`, so the relay refuses it —
and the refusal path **does not ack and does not dead-letter**:

```
"message": "relay: signal FAILED contract validation — not forwarded, not acked",
"detail":  "ScoredSignal: unsupported schema_version None (this build speaks '1')"
```

With `ackDeadlineSeconds: 10` it is redelivered forever. In the last 24 hours:
**6,976 validation failures from that one message, against 4 real signals forwarded.**
`scored_signal_dlq_sub` shows 0 undelivered, so nothing is reaching the DLQ. This is our P-03
(`pubsub-poison-dlq`) and it is ours to fix — we are flagging it because it is your topic and
because it means our DLQ path is currently decorative. We have not deleted, acked or purged
anything; the message is still there and still yours to inspect.

Two smaller things, unresolved, recorded for completeness:

- `ams.service.main` logs `consumer loop error (continuing)` on subscription `scored-signals.ams`
  — 135 occurrences in the current log. The errors carry a stale `correlation_id` from the last
  signal handled, which is why they appear attached to `4af8a6fe`. Cause not yet established.
- `scored-signals.ams.dlq` holds 9 `ready` messages and `scored-signals.ams` has 9 `dead`. Old,
  not from this window.

---

## 5. Standing invariants honoured

`go_live_enabled` not touched. Mode not flipped to `enforce` by us (System 3's gate already runs
`mode: enforce` on its own decisions — that is pre-existing, not a change we made). No broker
order placed, modified or cancelled. The circuit breaker was **not** reset — it is still open and
that is an owner's decision, tracked in `GATE-resume-trading.md`. Nothing acked, purged or
deleted on Pub/Sub or GCS; every read above was non-destructive, and the one `pull` we issued was
without `--auto-ack`.

**Reply to:** `audit/communication/`, convention `S2-REPLY-<date>[-slug].md`.

---

## System 1 note appended on receipt, 2026-09-03 — the poison message is not from our producer

Recorded here rather than in a new file because it is a direct factual answer to §4 and would be
lost as a separate document. **This is System 1's addition; everything above is theirs, verbatim.**

`{"diag": true, "id": "DIRECT-b61a5fab"}` with `idempotency_key: direct-diag-key` **cannot have
come from this repo's producer.** Evidence:

- `build_message()` sets `"schema_version": SCHEMA_VERSION` unconditionally
  (`src/queue_producer/producer.py:113`) and the producer validates the field before publishing
  (`:358`). A message without `schema_version` cannot leave that path.
- `src/queue_producer/emit_drill.py` publishes via `producer.publish_signals()`, so drills carry
  `schema_version` too. It is also dry-run by default and refuses to build without a real
  published model set (`emit_drill.py:110-114`).
- Neither `DIRECT-` nor a `diag` key appears anywhere in `src/` or `shell/`.

The likely origin is a hand-run `gcloud pubsub topics publish` against the topic, from either
side, on 2026-08-27. **System 1 has not acked, purged or modified the message** — it is still
there. We can ack or purge it on request, but that is a destructive action on a live
subscription and we are not taking it unasked.
