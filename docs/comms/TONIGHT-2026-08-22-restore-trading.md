# Tonight — restore trading. Sequencing across all three computers.

Date: 2026-08-22
Owner runs this. Each step has a check that must pass before the next one starts.

---

## Send order

1. **`TO-SYSTEM3-2026-08-22-restore-signal-flow.md`** → System 3. **Send first.**
   System 3 is the blocking link and everything else waits on its reply.
2. **`TO-SYSTEM2-2026-08-22-why-you-are-not-trading.md`** → System 2. Send at the same
   time; its §3 work (transport, alarming) is independent and can proceed in parallel.

---

## Step 1 — System 3 replies with subscription names

**Blocking.** Signals route `S1 → Scored_Signal_Queue → S3 → AMS_Outbound_Queue → S2`.
We publish to link 1. Links 2 and 3 are unverified and we are blind to them: System 1's
service account is publisher-only and cannot list topics or subscriptions.

Needed: S3's subscription name on `Scored_Signal_Queue`, confirmation a consumer is
actually pulling it, and the topic it publishes approved orders to.

**Check:** a written reply naming all three. Not "it should be set up."

## Step 2 — System 2 confirms transport

Independent of step 1, can run in parallel.

`QUEUE_PROVIDER` on System 1 is now `pubsub`. It was `local` until recently, which meant
signals landed in a directory on Computer 1 that no other machine could ever read. If any
part of System 2's path still polls a file-based queue, it can never receive anything.

**Check:** System 2 states which topic/subscription it consumes and confirms the process
is running.

## Step 3 — System 1 raises the producer cadence

**This is ours and it is not yet done.** The producer currently runs from
`cron_daily_ingest_and_signals.sh` at **22:30, weekdays only** — once per day.

Two of the three live strategies are **H4** (six bars a day). A once-daily batch will
emit signals for bars that closed up to twenty hours earlier, which is useless for
execution. The producer needs to run at least hourly for H4 to be actionable, and
`src/signals/run.py` already supports a continuous mode (60-second loop).

**Decision needed from the owner:** hourly cron, or continuous service. Recommend hourly
cron first — it is the smaller change, it is restartable, and it matches the existing
operational pattern.

**Check:** `crontab -l` shows the producer running at least hourly during market hours.

## Step 4 — Drill signal

Once steps 1–3 pass. System 1 publishes one correctly-formed signal on a real instrument
at a realistic live price, carrying `"drill": true`.

- System 3 processes it through the full risk path and forwards it **with the flag intact**.
- System 2 runs it to the broker call and **stops**, logging the order it would have sent.
- Both report back.

**Check:** the same `signal_id` is visible at all three systems, and System 2's logged
order matches what System 1 sent.

## Step 5 — Live

Drop the drill flag. Practice account throughout — **confirm all three systems point at
`api-fxpractice.oanda.com` before this step.**

Market reopens Sunday 21:00 UTC. First H4 bars close shortly after.

---

## Known and accepted, stated once

The three live strategies qualified on **5, 13 and 20 out-of-sample trades** after the
owner deliberately lowered the OOS gate from 60 months to 12. System 1 has no minimum
trade-count gate, which is why cells that thin passed. The profit factors (6.8–13.6) and
the near-zero drawdowns (0.02%–1%) are small-sample artefacts, not established edges.

**This is a knowingly accepted risk on a practice account, not a defect, and it is not a
reason for System 2 or System 3 to refuse orders.** Sizing is System 3's call.

Revisit after the pipe is proven working — the missing minimum-trade-count gate is worth
adding regardless of where the `oos_months` value lands.

---

## What is fixed and verified as of tonight

- **FIX-S1-016** — the producer could never emit. It checked publication status on the
  wrong artifact (a condition nothing could ever satisfy), and separately crashed on
  import because the causal routing label had been deleted with a retired experiment.
  Both fixed; verified end to end against the live GCS bundle.
- Model set `2026-08-21T16-29-15Z-372f6956_gk-d614163c` is published and loads correctly.
- The producer runs to completion. It is quiet at time of writing because it is Saturday:
  H1/H4 are past their freshness thresholds and two of three strategies are H4.

## Still open, not blocking tonight

- A test run once wrote fixtures into the production queue artefact (the `entry: 1.05`
  messages System 2 saw). The leak is not yet closed.
- `src/registry/` retains imports of the removed `regime_aware` package, gated behind the
  `regime_aware_port` universe. Latent, will not fire for the current three strategies.
