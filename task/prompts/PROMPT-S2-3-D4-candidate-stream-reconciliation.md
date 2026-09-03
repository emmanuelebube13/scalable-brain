# Agent prompt — D4: 4,102 Gate-2 drops against 58 signals ever published

**Run this in the System 2 / System 3 repos.** This one is a **question first and a fix second**
— System 1 cannot see your side, and we are not asserting a defect.

**Priority:** P1 · **Owner:** System 2 and System 3 · **Source:** `docs/comms/to_system2/TO-SYSTEM2-3-2026-09-03-dashboard-reconciliation-and-mock-data.md` §D4

**Answer question 2 before doing any other dashboard work.** It changes the priority of
everything else in this batch.

> **⚠ Read `PROMPT-S2-D0-where-to-work.md` before touching any dashboard code.** The live app is
> **`telemetry-dashboard/src/App.tsx`**; `src/App.jsx`, `src/screens/*.jsx` and `src/main.jsx`
> are a dead second app, and `CONNECTIONS.md` documents that dead one.
>
> **But note:** this item is a *question first*. Its answer lives in System 2's Pub/Sub
> subscription and System 3's Gate-2 counters — **probably not in the dashboard at all.** Start
> there, not in the frontend.

---

## The arithmetic that does not close

From the Live Telemetry overview at 2026-09-03 00:51:54Z:

```
GATE-2 RISK DROPS      4,102     heaviest bucket: "Account state (2,721)"
header:  SIGNALS · ORDERS        [none ever received]
```

From System 1, same moment, confirmed in both the local state file and the published
`telemetry/s1_health.json`:

```
signals_published_total    58      ← the entire operating life of System 1
signals published this week  9      (8 distinct signal_id)
DLQ count, all reasons       0      ← nothing was NACKed on our side
```

**4,102 execution blocks cannot be derived from 58 candidates.** And `[none ever received]`
directly contradicts 58 published messages.

Both cannot be true of the same stream. Either the counters describe different streams, or one
of them is wrong.

## The three questions

### 1. What candidate stream is Gate-2 evaluating?

4,102 drops with a heaviest bucket of "Account state (2,721)" implies a high-frequency candidate
source. System 1 emits roughly **9 signals per week**. Identify what is feeding Gate-2.

### 2. Did *any* of this week's 9 messages arrive on your subscription? — ANSWER THIS FIRST

The nine `signal_id`s System 1 published this week:

```
0c2d3286-65d3-5652-b503-0801e9ead4be    2026-08-31T21:15:30Z  USD_CAD H1 short
d3f01f97-e6e8-595f-954f-b57ad0455c46    2026-09-01T15:15:17Z  USD_CAD H1 long
637f27ac-50fe-5e1f-8535-f3ccc5ccc4fe    2026-09-01T17:15:28Z  USD_CAD H1 long
b97120fc-25d4-57ad-8f6e-8775c250f2a6    2026-09-01T17:15:30Z  EUR_USD H4 short
340baf34-e49c-5136-b18b-f2c6c33f858e    2026-09-01T21:15:38Z  GBP_USD D1 short
4af8a6fe-d8f8-5eec-97af-b9e2c793338f    2026-09-02T14:15:17Z  USD_JPY H1 short
4af8a6fe-d8f8-5eec-97af-b9e2c793338f    2026-09-02T17:15:27Z  USD_JPY H1 short  ← same id, see D5
39c0c8d2-a736-5b82-be86-9fb5424e56dd    2026-09-02T21:15:30Z  AUD_USD H1 long
f176d2f3-f5d0-5187-84f4-02e9da62d783    2026-09-02T21:15:30Z  USD_CAD H1 short
```

Query your `scored_signal_queue` subscription and your execution records for these ids.

**Report the count that arrived — even if it is zero.** Zero is a valid and important answer.

**If the answer is zero, stop and escalate.** It means we have a delivery failure that neither
side's telemetry currently surfaces, System 1's `wire_action: "published"` is not meaning what
we both assumed, and **D5 becomes moot** — you cannot double-fill messages that never arrive.
That would also make D1 and D3 low-priority cosmetics against a live outage.

### 3. Is System 2's local signal producer still running?

The standing architectural ruling of **2026-08-02** is that System 1 owns entry logic and
System 2 is **execution-only** — its local signal producer should be **deleted, not repaired**.

A live local producer would explain both anomalies at once: a high-frequency candidate stream
for Gate-2 to reject (4,102), and a `SIGNALS: [none ever received]` counter that is wired to the
System 1 subscription and correctly reporting nothing on it.

Check whether that producer is running. If it is, that is the finding, and it is a governance
matter for the owner before it is a code change. **Do not delete it unilaterally** — report it.

## What to change once the questions are answered

This depends entirely on the answers. Likely shapes:

- **If a local producer is live** → report to the owner, and label the dashboard's trade and
  Gate-2 counters with which system originated them. Today the page presents them as one stream.
- **If messages are arriving but `SIGNALS [none ever received]` is wired to the wrong counter**
  → fix the counter. A "never received" indicator that is wrong is worse than absent, because it
  will suppress investigation of a real outage.
- **If messages are genuinely not arriving** → joint incident with System 1. Their DLQ is 0 and
  their producer reports success, so the failure would be in transport or subscription config.

## Acceptance criteria

- [ ] A written answer to all three questions, delivered to the System 1 owner.
- [ ] For Q2 specifically: a count, and the ids that arrived, out of the nine listed above.
- [ ] The origin of the 4,102 Gate-2 drops is named.
- [ ] If the counters describe different streams, the dashboard labels which is which.

## What System 1 has already ruled out

So you do not re-investigate our side:

- **DLQ is 0** across every reason (`BUILD_ERROR`, `SCHEMA_INVALID`, `BAD_REGIME`, `QUEUE_FULL`,
  `PUBLISH_NACK`). Nothing was dead-lettered.
- **The hourly signal cron fired 24/24 hours** on 2026-08-30, 08-31 and 09-01. No missed runs.
- **Price coverage is complete and gap-free** for the week: H1 75 bars × 5 pairs, H4 18, D1 3,
  zero incomplete bars.
- **`wire_action: "published"` does not mean "reached the broker"** — this caveat was given in
  `TO-SYSTEM2-3-2026-08-30-signal-ledger-and-rfc-corrections.md` §5 and still stands. It means
  System 1's producer returned success.
- Under Pub/Sub, System 1's `dead_letter()` publishes nothing to a DLQ topic — it increments an
  in-process counter and logs locally. A DLQ of 0 is therefore **weaker evidence than it looks**;
  it rules out a *detected* drop, not an undetected one.
