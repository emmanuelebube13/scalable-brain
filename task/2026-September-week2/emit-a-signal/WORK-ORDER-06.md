# Work Order 06 — Emit a signal. Nothing else.

**PRIORITY P0. Every other work order this week is parked until this one closes.**

The system has not emitted a signal since **2026-09-04T21:15:44Z**. The map is live and
admissible, the model set is published, risk-off is cleared. None of that matters while nothing
reaches the wire.

**Scope is one sentence: get a signal emitted, and keep the hourly cadence running.** If you find
something else — however real — write it in `issues/September-Week-2/` and keep going. Do not fix
it. Do not open a stage for it.

---

## What is already known — start from here, do not re-derive it

**The producer hangs.** On 2026-09-09 a run started 10:15Z and was still alive at 11:15Z on **2
seconds of CPU**, with five sockets to Google in `CLOSE-WAIT` — the remote end had closed, the
client never noticed, nothing timed it out. A second run reproduced the stall.

**One hang stopped the whole cadence.** `cron_hourly_signals.sh` takes a **non-blocking** `flock`,
so every later run exited with `previous hourly run still active — skipping`. That line reads like
normal operation. It was a silent outage.

**Two guards have been added by the reviewer — do not remove them:**

| fix | where | what it does |
|---|---|---|
| `future.result(timeout=30)` | `src/common/queue/pubsub.py` | a stuck publish now fails and returns False instead of blocking forever |
| `timeout 10m` on the producer | `shell/cron_hourly_signals.sh` | a stuck run costs **one** run, not all of them |

**The watcher is five days behind.** This is the lead, and it was found last:

```
watcher cursor   D1 2026-09-03T21:00Z    H1 2026-09-04T20:00Z
newest label     D1 2026-09-07T21:00Z    H1 2026-09-09T10:00Z
```

The watcher only advances on a **successful** run, which is the correct fail-safe. It has not
advanced since 2026-09-04, so there is now a backlog of roughly **110 H1 bars × 5 pairs × ~41
strategies ≈ 22,000 strategy-bar evaluations** waiting for the first run that completes.

**That may be the whole story, and it must be the first hypothesis you test.** A run that is
working through five days of backlog is *slow*, not *hung*, and it looks identical from outside.

**The map is not structurally dead.** Current structural labels can satisfy live cells right now:
`Trending-Up @ H1` (EUR_USD, GBP_USD, AUD_USD), `Trending-Down @ D1` (EUR_USD),
`High-Vol @ D1` (USD_CAD). Cells matching regimes is not the problem.

---

## STAGE 1 — ANSWERED 2026-09-09. It is STUCK, not slow.

**Do not re-run this diagnosis. Start from the finding.**

A guarded run was measured end to end on 2026-09-09T11:26Z:

```
real  10m47.466s
user   0m38.899s      <-- 39 seconds of CPU across 10 minutes of wall clock
sys    0m01.160s
```

**~6% CPU utilisation. The producer is blocked on I/O for roughly 90% of its life.**

That **falsifies the backlog hypothesis.** Grinding through ~22,000 strategy-bar evaluations would
be compute-bound and would peg a core. This does not. The five-day watcher backlog is a
*consequence* of runs never completing, not the cause.

It is also confirmed reproducible and it is confirmed to be after the model set loads — the last
line before the stall is always:

```
08:26:06 system1.signals.build: Loaded model set 2026-09-09T04-06-47Z-74fb9f9c_gk-d614163c
[then nothing for 10 minutes]
```

The guards behaved correctly: terminated at 10m (`rc=124`), cadence preserved, telemetry still
published, script exited clean. **Leave them in place.**

### What Stage 1 now needs: WHERE does it block?

One question only. Six sockets to Google are open during the stall, so it is a network call, and
39s of CPU says some work does happen — so it is likely a call **inside a loop**, not a single
hang at the top.

Cheapest route, in order:

1. **`faulthandler.dump_traceback_later(60, repeat=True)`** at the start of `run_once`. No
   elevated permissions needed, unlike `py-spy` on this host. Run it, let it stall, read the
   repeated traceback. The frame that appears every time is the answer.
2. If that is inconclusive, log a timestamp per granularity and per strategy batch and find which
   step consumes the wall clock.

**Name the exact call.** Then stop and report before changing anything — the fix depends entirely
on which call it is, and guessing here is how the last three work orders went sideways.

### Deliverable

One sentence, backed by a traceback: **"the producer blocks at `<file>:<line>`, in `<call>`."**
Nothing else from this stage.

## STAGE 2 — Get one signal out, and confirm the cadence

1. Let the backlog drain — a manual run is fine, and expect it to be long.
2. **Confirm `last_signal_emitted_at` advances past 2026-09-04T21:15:44Z.** That is the deliverable
   of this entire work order.
3. Confirm the watcher cursor advances to current.
4. Then let **three consecutive scheduled runs** complete without a skip. Report each one's
   outcome and duration.

### If no signal is emitted even after the backlog clears

Then the question changes and you stop. Report which of these it is, with evidence:

- No strategy produced a candidate (a quiet market — legitimate)
- Candidates were produced and dropped before the ledger — **O-20**: `build_signals` discards at
  ~12 points before `signal_id` is minted, including a bare `except` per (bar × strategy), so a
  crashing strategy leaves **no trace at all**
- Candidates reached the wire and the publish failed

These are three different problems. **Do not guess between them, and do not fix any of them in
this work order** — report which one it is and stop.

Note while you are there: strategy 58 `xard_ma_cross_daily_open` was hotfixed on 2026-09-09 for a
`NameError` on its emit path (WO-02 deleted its pip definition). It holds 2 of the 6 live cells
including the only Trending-Up cell. If it still fails, that is the highest-value thing to report.

---

## Constraints

- **Do not touch the gatekeeper, the holdout, the regime labels, the map, or the model set.**
  All are out of scope and all are parked.
- **Do not remove the two guards** described above.
- **Do not widen `LATENCY_THRESHOLDS`** in `signals/watcher.py` to force bars through. If the
  watcher is rejecting bars as stale, that is a finding, not a setting to change.
- Do not run `designate.py`, `--reconcile`, `--withdraw`, or any publish.
- Anything else you find goes in `issues/September-Week-2/<date>.md`. Not fixed.

## Gates

Deliberately minimal — this is an operational fix, not a modelling change.

| after | invoke | why |
|---|---|---|
| Stage 1 | none | diagnosis only; report the finding |
| Stage 2 | `db-guardian` | **only if** you change a query or the watcher's persistence |
| close | `auditor` | that a signal was genuinely emitted and the cadence genuinely held |

`structure-warden` only if you create a file.

## Deliverable

**`audit/reports/work_order_06.md`** — short. Query output, not prose:

1. Stage 1 verdict: slow or stuck, with the evidence.
2. `signal_emitter_state.json` before and after.
3. Watcher cursors before and after.
4. Three consecutive scheduled runs: outcome and duration each.
5. If no signal emitted: which of the three cases, with evidence.

No summary document. One report, and stop.
