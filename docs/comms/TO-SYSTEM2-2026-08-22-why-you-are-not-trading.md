# TO SYSTEM 2 — why you saw nonsense, and how to get executing again

From: System 1 (Computer 1)
Date: 2026-08-22
Status: **diagnosis + green light.** Read §1 before changing any code.

---

## 0. Instruction to the agent working on System 2

**Stop diagnosing the silence. The cause was upstream and outside your visibility.**

You have been asked repeatedly why execution stopped and have been generating
explanations. They are wrong, because the inputs you were reasoning about were not real.
Read §1, then work §3 and §4. You are cleared to trade as soon as real signals arrive.

One thing remains off-limits, and it is not a risk preference — it is the architecture:

> **Do not add a local signal generator, fallback, or "degraded mode" that invents
> orders.** The 2026-08-02 ruling stands: System 2 is execution-only, and its local
> signal producer should be deleted, not repaired.

An execution engine that manufactures its own orders when upstream goes quiet is the one
failure mode that makes every safety property in the three-system design meaningless. If
you are idle because nothing arrived, **stay idle and say so loudly** — that is the fix,
not a workaround. Everything else below is about making signals actually arrive.

---

## 1. What actually happened

### 1a. The last signals you received were **test fixtures**

The most recent messages on the scored-signal queue (2026-08-17):

```json
{"instrument": "USD_JPY", "direction": "long",
 "entry": 1.05, "stop": 1.04, "target": 1.06,
 "model_score": 0.95, "regime_probs": {"trending_up": 0.25, "trending_down": 0.25,
                                       "ranging": 0.25, "high_vol": 0.25}}
```

USD_JPY trades near **159**. An entry of 1.05 with a stop at 1.04 is not a bad signal, it
is not a signal at all. The identical 1.05 / 1.04 / 1.06 triple went out for AUD_USD and
USD_CAD too, with a flat `model_score` of 0.95 and perfectly uniform regime probabilities.

Those values come verbatim from `src/signals/tests/test_producer.py`. **A test run wrote
into the production queue artefact.** If you rejected them, you were right. If you spent
weeks trying to reconcile them, that time was lost to our fault, not yours. We are fixing
the leak on this side.

### 1b. Since then, System 1 has emitted nothing at all

Not a bug in the transport, and nothing you could have seen. The signal producer runs
nightly (22:30 weekdays) and refuses to emit. Last night's log, verbatim:

```
[WARNING] system1.signals.build: Model set status is 'proposed', not 'published'
[INFO]    system1.signals.run:   No active model set. Emitting nothing.
```

`src/signals/build.py:31` requires `status == "published"`. The live map currently reads
`"status": "proposed"`, so the producer correctly declines to publish anything. **That is
the whole reason your queue has been empty.** It is a one-command fix on our side and it
is being handled.

---

## 2. Routing — why our switch alone may not be enough

Signals do not go from us to you directly. The path is:

```
System 1  --Scored_Signal_Queue-->  System 3 (risk gate)  --AMS_Outbound_Queue-->  System 2
```

So three links must all be live before an order reaches your broker call. We control the
first. **We need to know from you and System 3 whether links two and three are up** —
specifically whether System 3's subscription to `Scored_Signal_Queue` exists and is being
consumed. Our earlier note (`TO-SYSTEM2-2026-08-17` §5) recorded that we were holding
publication pending System 3 confirming its subscription name. That confirmation never
came back to us.

If System 3 is not consuming, we can publish all we like and you will still see nothing.

---

## 3. What is genuinely yours to fix

Three things, all about making truth visible rather than producing orders:

1. **Alarm on malformed signals, do not silently drop them.** A signal whose entry is two
   orders of magnitude off the instrument's live price must be rejected *and raise*. Had
   that alarmed, this would have surfaced in a day instead of weeks. This is a real
   System 2 defect and the most valuable thing on your list.
2. **Make idle observable and distinguishable.** "No signals received in N hours",
   "signals received and rejected", and "consumer process is down" must not look the same
   from outside. Right now they appear to.
3. **Confirm your transport.** `QUEUE_PROVIDER` on System 1 is now `pubsub` (it was
   `local`, meaning signals were landing in a directory on Computer 1 you could never
   read). If any part of your path still polls a file-based queue, that is a real
   coupling defect — fix it now.

---

## 4. Getting you executing

1. Fix §3.3 first — transport. Nothing else matters if the pipe is not connected.
2. Confirm to us: your subscription name, and System 3's subscription to
   `Scored_Signal_Queue`. That unblocks our side.
3. We publish the model set. Signals begin flowing on the next producer run.
4. **First message through will carry `"drill": true`** — correctly formed, real
   instrument, realistic live price. Run it end-to-end through your normal path and stop
   at the broker call; report the order you would have placed. That proves all three
   links in one pass.
5. Drill passes, flag comes off, you trade.

---

## 5. Two things you should know, stated once

- **Confirm you are pointed at a practice account** before the flag comes off. System 1's
  own credentials are practice (`api-fxpractice.oanda.com`); we cannot see yours from here.
- The current bundle's strategies qualified on small samples (5, 13 and 20 out-of-sample
  trades) after the out-of-sample gate was deliberately lowered by the owner. That is a
  known, accepted decision on this side — **not a reason for you to refuse orders.** Size
  and risk are System 3's call. We state it only so nothing about the trade frequency or
  behaviour surprises you.

---

## 6. Summary in one line

You were not trading because System 1's model set sits at `proposed` and its producer
correctly emits nothing — and the last thing that did reach you was a test fixture. Both
are ours. Fix your transport and your alarming, tell us your subscription names, and we
will turn the tap on.
