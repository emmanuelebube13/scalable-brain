# ADDENDUM — before you run the trading-1 fix

From: System 1 (Computer 1)
Date: 2026-08-23
Append this to the owner's three-step instruction. Read §1 first — it may invalidate a
check you already built.

---

## 1. Your startup assertion probably does NOT catch this case

You verified `_assert_shared_queue` against five wrong-path shapes: missing, 0-byte,
non-SQLite, SQLite without a `queue` table, and a platform-foreign path.

**The bogus file on `trading-1` is none of those.** Measured directly:

```
/opt/scalablebrain/system2/system-2-execution-engine/C:\Users\emman\...\queue.db
  4096 bytes, owned by trader, held open by pid 406532 on fd 4/5/6
```

4,096 bytes is a valid SQLite file, created by your own code, and it will contain a `queue`
table because your code created that too. It exists, it is non-empty, it is SQLite, it has
the table. **It passes all five checks and is still the wrong file.**

The property that actually distinguishes right from wrong here is *identity*, not shape:

- compare the **resolved absolute path** against the configured expectation, and/or
- compare the **inode** of the file you opened against `/opt/scalablebrain/shared/queue/queue.db`
  (`os.stat(path).st_ino`) — same inode means same file, which is the thing you need.

Please add that before deploying, or the assertion will bless the exact failure it was
written to prevent.

## 2. Stop the process before deleting the file

`pid 406532` holds fds 4, 5 and 6 on the bogus `queue.db`, `-wal` and `-shm`. Deleting
while open only unlinks it — the process keeps writing to a file with no name, and you get
a confusing partial state.

Order: **stop `python -m system2` → check §3 → delete the three files → repoint → start.**

Also check how it is supervised before you stop it. It has been up 2 days; if something
restarts it automatically, it may come back on the old config before you have edited it.

## 3. Check the bogus file for unflushed data first

It is 4 KB, so almost certainly empty — but it has been System 2's queue since 2026-08-20,
and if anything *was* written there it is data nobody has seen:

```bash
sudo sqlite3 'file:<bogus-path>?mode=ro' \
  "SELECT topic, state, COUNT(*) FROM queue GROUP BY topic, state;"
```

Empty result: delete freely. Anything at all: copy it aside and tell us what was in it
before you delete.

## 4. Do not misread the weekend as failure

**This is the one most likely to waste your evening.** After the fix, no order will arrive,
and that will be correct.

System 1 published a live drill today (`S1-DRILL-20260822T234641Z`). It traversed
Pub/Sub → your relay → System 3's local queue, was **accepted** (`state=done`, not
dead-lettered), and System 3 ran the full gate on it:

```
outcome            REJECTED
rejected_at_layer  I
reason             weekend_window       weekday 5
latency            9 ms
units it had already sized   12,205        risk 84.01 CAD
prior_source       s1_baseline:cache      prior_win_rate 0.696
```

It sized a real order and then declined it purely because the market is shut. Layer I doing
its job. **So links 1 and 2 are already proven, and nothing will reach `ams-outbound` until
the market reopens Sunday 21:00 UTC.**

### A verification that does work on a weekend

Do not wait for an order to prove the fix. Prove it by identity instead:

```bash
sudo ls -l /proc/$(pgrep -f 'python -m system2')/fd/ | grep -i queue
sudo ls -l /proc/$(pgrep -f 'ams.service.main')/fd/ | grep -i queue
```

Both must resolve to `/opt/scalablebrain/shared/queue/queue.db`. That is the proof. A
stronger one: after restart, have System 2 read any row from a topic System 3 wrote —
if it can see System 3's data, they are on the same file.

## 5. Leave `EXEC_SHADOW=true` through the first live order

When the market opens and an order does arrive, let shadow mode log what it *would* have
sent. Compare that against System 3's `approved_units` for the same `signal_id`. If they
match, the whole chain is proven and the flag can come off.

Owner's position: **demo only.** `mode: demo`, `stage: paper`, practice endpoint, no live
account configured. Turning shadow off is the test, not the risk — but do it after one
clean drill, not before.

## 6. Current state on trading-1, measured, so you do not re-derive it

```
310346  s2s3_bridge.py                       up 7d
332090  pubsub_signal_relay.py               up 5d
406495  system2.artifact_sync.downloader     up 2d
406532  python -m system2                    up 2d   <- holds the WRONG queue file
406547  ams.service.main (System 3)          up 2d
407010  telemetry_publisher.py               up 2d

S3 fd 4 -> /opt/scalablebrain/shared/queue/queue.db   95 MB, live, WAL active
S2 fd 4 -> ...\C:\Users\emman\...\queue.db            4 KB, private, empty
```

Everything is running. The single defect between here and a demo trade is which file
System 2 has open.
