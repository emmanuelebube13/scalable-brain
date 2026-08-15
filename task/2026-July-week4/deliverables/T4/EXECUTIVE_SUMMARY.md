# T4 — Freshness Heartbeat · Executive Summary

**2026-07-29 · System 1**

## The problem

The system broke twice this summer without telling anyone.

- The **price feed died for 16 days** (4–20 July).
- The **trade-results recorder was frozen for five weeks** (23 June – 29 July, repaired
  earlier this week).

In both cases every scheduled job kept reporting success. Neither failure was found by a
check — one turned up during an audit, the other during this week's repair work. The system
had no way to notice it had stopped learning.

## What now exists

A single daily watchdog, running at **06:00 UTC**, that checks eight things and refuses to
stay quiet when one of them is stale:

1. **Price data** — is it current to the last market close?
2. **Trade results** — are they current, *and* was anything actually written recently?
3. **Market regimes** — current?
4. **The live model bundle** — readable, and does every file still match its fingerprint?
5. **Telemetry from the trading VM** — still being published?
6. **Retrain state** — running, and not reporting failure?
7. **The hourly scheduler** — actually alive?
8. **The code itself** — do the critical modules still load? (This is the exact break that
   froze the feedback loop.)

## How you will know something is wrong

If anything is stale, the watchdog leaves a file called **`HEARTBEAT_ALERT`** in
`results/state/`, naming what failed and when, and appends a line to
`logs/heartbeat_alerts.log`. The file deletes itself once things are healthy again. **If that
file is there, something needs attention.**

This was proven, not assumed: a dead price feed was simulated, and the watchdog produced a
CRITICAL result, the alert file, and a log entry. That is the July outage — it would have
been caught the same day instead of sixteen days later.

## Today's result: everything green

All eight checks pass. Two things worth knowing:

- **The trading VM's telemetry is alive** and publishing — that had been in question.
- **The live model bundle verified cleanly** — all seven files match their fingerprints.

Nothing is being hidden by a lenient threshold. Where a check is generous, the report says so
and why.

## Two honest limitations

**The price check can't promise 24-hour detection.** Price data only updates once a week (the
Saturday job), so a dead feed can't be *proven* dead until the next Saturday is missed — up
to about eight days. Everything else — trade results, telemetry, the scheduler, the code, the
model bundle — is genuinely within 24 hours. Moving the price import to daily would close
that gap, and is worth considering.

**Nothing sends you a message.** The watchdog writes a file and a log entry; it does not
email or text anyone. If nobody looks, it is still silent. The cheapest next step would be
making the hourly retrain job refuse to run while an alert is outstanding — so a stale system
stops quietly training on stale data.

## Why this was worth doing

The most expensive failures this system has had were not wrong answers. They were **correct
answers computed from data that had stopped arriving**, with everything reporting success.
This is the cheapest insurance available against that pattern.
