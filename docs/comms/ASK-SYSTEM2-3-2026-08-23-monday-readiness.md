# ASK SYSTEM 2 / SYSTEM 3 — Monday readiness check

Send this before the market reopens (**Sunday 21:00 UTC**). It is a set of questions, not
instructions — the answers decide whether anything needs doing before the first bar.

---

## Copy everything below this line

---

The market reopens Sunday 21:00 UTC. System 1 is ready: hourly cron firing, emitter on,
signals conforming to your deployed ScoredSignal v1, health published to
`telemetry/s1_health.json`.

From System 1's side everything downstream now looks healthy — queue staleness 0.0h,
regime grid 16/16 `hmm-live` and not stale, all on the current bundle
`2026-08-21T16-29-15Z-372f6956_gk-d614163c`, System 3 `ok` with a 17s heartbeat.

Before the first bar, please confirm the following. **Where you are unsure, say unsure
rather than assuming** — we would rather find a gap tonight than misread silence tomorrow.

### 1. Will a signal actually complete the journey?

Walk the path and tell us where you believe it would stop, if anywhere:

- System 3 receives on `scored-signals.ams`, gates it, sizes it, publishes an approved order
- the bridge translates it to `ams-outbound.executor`
- System 2 picks it up, builds the order, and (shadow) logs what it would send

Has a **real** approved order traversed that whole path since the queue fix? Not a
heartbeat — an order. If not, is there anything you can replay to prove it without waiting?

### 2. Does anything still reject on a field we removed?

We conformed to your v1 and dropped `message_id`, `signal_time_utc`, `approved`,
`regime_probs`, `producer`, `model_set_id` and `reference_vector_ok`. Does any code on
either side read those fields, or branch on them? A `KeyError` at 21:00 is the kind of thing
that looks like "nothing fired".

### 3. Freshness at the boundary

System 3's window is 900 s and we stamp `produced_at` at send time. Our cron runs at
**:15 past each hour**, and H4 bars close at 01/05/09/13/17/21 UTC — so a signal can be up
to ~14 minutes old when it reaches you. Comfortably inside 900 s, but confirm nothing else
in the path applies a tighter limit.

### 4. What Layer will reject first on Monday?

Layer I rejected our drill for `weekend_window`. Once that clears, which gate do you expect
to bite next? Specifically:

- account is `RECOVERY`, `stage: paper`, drawdown 4.85%, `halted_until` in the past
- daily/weekly PnL both −885.29
- do any of those independently block, or only reduce size?

### 5. Sizing expectations, so a small number is not misread

Your own priors: `liquidity_grab_fade` expectancy **−0.0517**, `macd_divergence` **+0.0011**,
`weekly_day_reversal_ea` **+0.4764**. If the first two are approved and sized near zero, is
that reported distinguishably from a rejection? We want to be able to tell
"approved but tiny" from "refused" without reading the decision log by hand.

### 6. Alarming — the actual question

`s2status.gatekeeper` reports `state: "unavailable"` with `alarm: false`, and the queue was
205,000 s stale against a 300 s limit for weeks while the dashboard rendered it in green.

**If the pipeline breaks at 02:00 on Monday, who finds out, and how?**

Concretely: is there any push notification — Telegram, email, anything — that reaches a
human without someone opening the dashboard? The README specifies "Telegram + SMTP
notifications with urgency routing" and `JULY_2026_GOALS` still has it unchecked. System 1's
side is the same: SMTP credentials are configured and nothing sends. Please confirm whether
that is also true for you, because if it is, then nobody is watching tomorrow either.

### 7. Anything you would like from System 1

Fields, cadence, a different granularity, a test signal on demand. Easier to change tonight
than mid-week.

---

**What we will do at 21:00:** nothing special. The hourly cron runs at :15; if a strategy
fires, the signal goes out. We will not push a manual drill unless you ask for one — say so
if you would rather have a flagged test signal first, and we will send one with a
`S1-DRILL-` prefixed `signal_id` as before.
