# HOST RULING — `trading-1` is the System 2 that trades

From: System 1 (Computer 1)
Date: 2026-08-23
Decided by: the owner
**Read this before doing any more work. Some of P0 was done on the wrong machine.**

---

## 1. The ruling

**`trading-1` (europe-west1-b) is System 2.** The Windows workstation is not, and should
not be brought toward trading.

We have been debugging two machines as though they were one. That is why the diagnosis kept
appearing to contradict itself.

## 2. What this changes, bluntly

The P0 work was completed on the **Windows** box. On that host the agent verified
`QUEUE_LOCAL_PATH` already resolved to a live 3.2 MB shared queue with 9,325 rows and
correctly refused to repoint it. **That judgement was right for that host and irrelevant to
this one.**

On `trading-1`, the original evidence stands and was reported independently by both System 2
and System 3:

```
S2 .env   QUEUE_LOCAL_PATH=C:\Users\emman\OneDrive\...\shared\queue\queue.db
S3 .env   QUEUE_LOCAL_PATH=/opt/scalablebrain/shared/queue/queue.db

/proc/406532/fd/4  (system2) -> .../system-2-execution-engine/C:\Users\...\queue.db  4 KB, EMPTY
/proc/406547/fd/4  (ams)     -> /opt/scalablebrain/shared/queue/queue.db             92 MB, live
```

A Windows path on a Linux host is not a path — it is a filename containing backslashes, and
`sqlite3.connect` happily created a private empty database of that name. **On `trading-1`
the queue path IS broken and must be repointed** to
`/opt/scalablebrain/shared/queue/queue.db`.

## 3. What to do on `trading-1`

1. **Port the P0 work from the Windows box.** It is good work and should not be redone from
   scratch — the `_assert_shared_queue` startup check (verified against five wrong-path
   shapes: missing, 0-byte, non-SQLite, SQLite without a `queue` table, and a
   platform-foreign path) and the purge of `LIVE_SIGNAL_ENABLED` / `SIGNAL_*`.
2. **Then repoint `QUEUE_LOCAL_PATH`** to the Linux path above and delete the bogus
   backslash-named file. Note the ordering: with the assertion in place first, a wrong path
   fails loudly instead of silently creating another empty database.
3. **Confirm System 2 and System 3 hold the same file** — compare `/proc/<pid>/fd/` for both
   processes, as System 3 originally did. That is the check that actually proves link 3.
4. **Start System 2's processes.** The Windows report of "nothing is running" was about that
   host; establish separately what is and is not alive on `trading-1`.

## 4. Stand the Windows box down

Mark it explicitly non-trading so nobody keeps hardening a machine that is not in the path.
Its `EXEC_SHADOW=true` should stay on permanently. It is useful as a development host; it
is not System 2.

## 5. A drill signal is already waiting for you

System 1's publish path is verified working as of today — a real, schema-valid v1 message
was published to `scored_signal_queue` on Pub/Sub:

```
signal_id      S1-DRILL-20260822T234641Z
pair           EUR_USD        direction  long
proposed_entry 1.16766        proposed_sl 1.16266     proposed_tp 1.17766
atr            0.0042         regime      High-Vol
strategy_id    34 (macd_divergence)       model_score 0.68 / threshold 0.60
```

Real price, real ATR — not the `1.05` fixtures you saw in August.

**System 3's relay on `trading-1` may already have consumed it.** Your own report had
`scripts/pubsub_signal_relay.py` (PID 332090) pulling `scored_signal_queue_sub` at roughly
one pull per 6.6 s since 2026-08-17. If that process is still alive, this message has
already been forwarded to the local `scored-signals.ams` topic and is sitting there.

**That is the thing to look for first.** If it is in the local queue, links 1 and 2 are
proven and only link 3 — the one the queue path breaks — is outstanding.

## 6. Order of play

| # | step | why |
|---|---|---|
| 1 | Find `S1-DRILL-20260822T234641Z` in `scored-signals.ams` | proves links 1–2 with zero new work |
| 2 | Port P0 (assertion + flag purge) to `trading-1` | so step 3 fails loudly if wrong |
| 3 | Repoint `QUEUE_LOCAL_PATH`, delete the bogus file | fixes link 3 |
| 4 | Verify both processes hold the same fd | the real proof |
| 5 | Start System 2; let the drill traverse to the broker call | shadow mode logs the order it would place |
| 6 | Turn `EXEC_SHADOW=false` | **practice account** — this is the demo test, not a risk event |

## 7. Scope reminder

Owner's position: **demo only for now.** No live account, no real money. The safety catches
were calibrated for a real-money launch, and on a practice account they are the only thing
standing between you and the test that is actually the goal. Turning shadow off against
`api-fxpractice.oanda.com` is the experiment, not the risk.
