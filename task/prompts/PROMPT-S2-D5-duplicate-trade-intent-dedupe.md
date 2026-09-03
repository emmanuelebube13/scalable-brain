# Agent prompt — D5: `(signal_id, score_run_id)` will not stop a duplicate trade intent

**Run this in the System 2 repo** (signal ingestion and execution), **and review in System 3**
(the risk gate sees the same duplicate).

**Priority: P0.** This corrects integration guidance System 1 already sent you. If you built
against that guidance, **you may have already double-filled a position.**

**Owner:** System 2, with a System 1 fix behind it (their D6) · **Source:** `docs/comms/to_system2/TO-SYSTEM2-3-2026-09-03-dashboard-reconciliation-and-mock-data.md` §D5

> **This is NOT a dashboard change.** D0–D4 concern `telemetry-dashboard/`; this one does not.
> It is signal ingestion and execution — deduping trade intent on `signal_id`. **Do not start in
> `App.tsx`.** Nothing here should change what the dashboard renders, except indirectly, by
> there being one trade where there were two.

---

## What you were told, and why it is not enough

`TO-SYSTEM2-3-2026-08-30-signal-ledger-and-rfc-corrections.md` §1 told you:

> **Make your ingester idempotent on `(signal_id, score_run_id)`** rather than assuming objects
> are disjoint.

**That advice was correct for the problem it addressed** — the ledger uploader re-sending an
identical byte range under a new object key after a failed offset persist. **Keep it for ledger
row ingestion.**

**It does not protect you against re-emission, and System 1 did not anticipate re-emission when
they wrote it.**

`score_run_id` is minted fresh on every producer run (`uuid.uuid4()`, once per run). So when
System 1 re-emits the **same signal** on a later run:

```
signal_id       IDENTICAL
score_run_id    DIFFERENT      ← a new uuid4 on every run
(signal_id, score_run_id)  →  DIFFERENT KEY  →  your dedupe passes both through
```

## This already happened — 2026-09-02

| | first emission | second emission |
|---|---|---|
| `signal_id` | `4af8a6fe-d8f8-5eec-97af-b9e2c793338f` | **identical** |
| `signal_time_utc` | `2026-09-02T13:00:00Z` | **identical** |
| `logged_at` | `2026-09-02T14:15:17Z` | `2026-09-02T17:15:27Z` |
| `score_run_id` | `98953363-52af-4197-b406-f2cb3adca509` | `964afac9-abaa-4e1c-9770-e0d20fb0b970` |
| `pair` / `granularity` / `direction` | USD_JPY / H1 / short | **identical** |
| `proposed_entry` | **158.568** | **158.849** |
| `proposed_sl` | 160.1835 | **identical** |
| `proposed_tp` | 155.337 | **identical** |
| `model_score` | 0.4292786 | **identical** |
| `wire_action` | published | published |

Two Pub/Sub messages, **the same trade**, entries **28.1 pips apart**, three hours apart. System
1's producer reported `deduped_count: 0` on both runs — its own suppression is inoperative
(that is their D6 to fix).

**Note what changed and what did not.** The entry was refreshed to the price at the moment of
the second run. The stop and target were **not** — they stayed frozen on the original 13:00Z
bar. So the trade's risk/reward silently drifted:

```
first  message:  risk 161.5 pips / reward 323.1 pips  =  2.00:1
second message:  risk 133.4 pips / reward 351.2 pips  =  2.63:1
```

The second message is **not a better version of the trade.** It is an internally inconsistent
one — a current entry paired with three-hour-old levels.

## What to change

1. **Dedupe trade intent on `signal_id` alone.** Not the composite. A repeat `signal_id` is a
   **no-op**, not an update.

2. **Treat the first message as authoritative.** Its entry, stop and target were computed
   against the same bar and are mutually consistent. **Do not take the later entry price as a
   revision** — you would be pairing a fresh entry with stale levels.

3. **Keep `(signal_id, score_run_id)` for ledger row ingestion.** Two ledger rows legitimately
   exist for this event and both should be stored. **The two keys serve different layers:**

   | Layer | Key | Semantics |
   |---|---|---|
   | Ledger rows (`s1_scored_signals_log`) | `(signal_id, score_run_id)` | rows are **observations** — keep both |
   | Trade intent / execution | `signal_id` | an **instruction** — act once |

   **Do not collapse these two.** Deduping ledger rows on `signal_id` alone would destroy the
   audit trail; deduping trade intent on the composite lets a duplicate order through.

4. **Log every suppressed repeat.** You need the count to tell System 1 how often their D6 is
   firing in production. They cannot measure it from their side — their `deduped_count` is
   structurally 0 on the Pub/Sub backend.

5. **Backfill check — do this before shipping the fix.** Search your execution records for any
   pair of fills sharing a `signal_id`. Specifically check
   `4af8a6fe-d8f8-5eec-97af-b9e2c793338f` (USD_JPY, 2026-09-02). If a double-fill occurred, that
   is a live position-sizing incident, not a data-quality one — escalate it to the owner rather
   than closing it in code.

## System 3 — what this means for you

The same duplicate reaches the risk gate. Two consequences:

- **Do not size the second message as a new position.** If Gate-2 evaluates them independently,
  a single System 1 trade idea consumes two allocations.
- **`threshold_applied: 0.5` is still a placeholder, not an enforced cutoff.** Unchanged from
  the 2026-08-30 message §2. Do not branch on it. It is identical on both duplicates and tells
  you nothing about which to prefer.

## Acceptance criteria

- [ ] Replaying both USD_JPY messages above through the ingester produces **one** trade intent.
- [ ] The retained intent carries entry `158.568` (the first), not `158.849`.
- [ ] Replaying both through the **ledger** ingester produces **two** stored rows.
- [ ] The suppression is counted and logged, and that count is queryable.
- [ ] A written answer on the backfill check: did any duplicate fill occur, and for which ids.
- [ ] System 3 confirms a repeat `signal_id` does not consume a second allocation.

## Assume this recurs

System 1's D6 fix is not shipped. The root cause on their side has two parts, both structural:

- Their idempotency key is `f"{signal_id}:{score_run_id}"` with a per-run `score_run_id` — it
  cannot match a prior publish by construction.
- Their producer infers dedupe from a queue-depth delta, which is not meaningful on the Pub/Sub
  backend. Their working `seen`-index dedupe exists only in a local-durable backend that is not
  in use.

There is also a second contributing behaviour: the emitted `signal_time_utc` is the **strategy's
signal bar**, not the newly-closed bar. Any strategy whose most recent signal remains the most
recent will re-emit it **every hour** until a newer signal appears. The USD_JPY case is that
behaviour, not a one-off race.

**Until System 1 confirms D6 has shipped, treat repeats as possible on every `signal_id`.**
