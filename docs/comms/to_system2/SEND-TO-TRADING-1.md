# SEND THIS TO THE SYSTEM 2 AGENT

*Placed at the repo root deliberately, at the owner's request, so it is not lost.
`STRUCTURE.md` otherwise keeps the root closed — this is the exception, not a precedent.*

**Status when written: 2026-08-23. One defect stands between here and a demo trade.**

---

## Copy everything below this line

---

Connect to `trading-1` (europe-west1-b, RUNNING) and do the following.

### The three steps

1. **Port the P0 assertion and the P2 reload fix.** Both are already written and both are
   machine-independent, so port them rather than rewriting.
2. **Repoint `QUEUE_LOCAL_PATH`** to `/opt/scalablebrain/shared/queue/queue.db`, delete the
   backslash-named file, restart `python -m system2`.
3. **Confirm fd 4 matches System 3's.**

### Four things to know before you start

**1. Your startup assertion probably does NOT catch this case. Fix it first.**

You verified `_assert_shared_queue` against five shapes: missing, 0-byte, non-SQLite,
SQLite without a `queue` table, and a platform-foreign path. The bogus file is none of
those. Measured:

```
/opt/scalablebrain/system2/system-2-execution-engine/C:\Users\emman\...\queue.db
  4096 bytes · valid SQLite · has a queue table · held open by pid 406532 on fd 4/5/6
```

Your own code created it, so of course it has the table. **It passes all five checks and is
still the wrong file.** The distinguishing property is *identity*, not shape:

- compare the resolved absolute path against the configured expectation, and/or
- compare `os.stat(path).st_ino` against `/opt/scalablebrain/shared/queue/queue.db` —
  same inode means same file, which is the thing you actually need.

Add that before deploying, or the assertion will bless the exact failure it exists to
prevent.

**2. Stop the process before deleting the file.** pid 406532 holds fds 4, 5 and 6 on the
bogus `queue.db`, `-wal` and `-shm`. Deleting while open only unlinks it — the process keeps
writing to a file with no name. Order: stop → check (3) → delete all three → repoint →
start. Check what supervises the process first, or it may restart on the old config.

**3. Check the bogus file for rows before deleting it.** It has been System 2's queue since
2026-08-20. Almost certainly empty at 4 KB, but if anything is in there nobody has ever
seen it:

```bash
sudo sqlite3 'file:<bogus-path>?mode=ro' \
  "SELECT topic, state, COUNT(*) FROM queue GROUP BY topic, state;"
```

Empty: delete freely. Anything at all: copy it aside and report what was in it.

**4. After the fix, no order will arrive — and that is CORRECT. Do not read it as failure.**

System 1 published a live drill today, `S1-DRILL-20260822T234641Z`. It went
Pub/Sub → your relay → System 3's local queue, was **accepted** (`state=done`, not
dead-lettered), and System 3 ran the full gate on it:

```
outcome            REJECTED
rejected_at_layer  I
reason             weekend_window        weekday 5
latency            9 ms
already sized      12,205 units · risk 84.01 CAD
prior_source       s1_baseline:cache · prior_win_rate 0.696
```

It sized a real order and declined it purely because the market is shut. Layer I working as
designed. **Links 1 and 2 are already proven. Nothing reaches `ams-outbound` until the
market reopens Sunday 21:00 UTC.**

### Verify the fix without waiting for an order

```bash
sudo ls -l /proc/$(pgrep -f 'python -m system2')/fd/ | grep -i queue
sudo ls -l /proc/$(pgrep -f 'ams.service.main')/fd/ | grep -i queue
```

Both must resolve to `/opt/scalablebrain/shared/queue/queue.db`. That is the proof, and it
is available immediately. Stronger still: after restart, have System 2 read any row from a
topic System 3 wrote — seeing System 3's data means you are on the same file.

### Leave `EXEC_SHADOW=true` through the first live order

When one does arrive, let shadow mode log what it *would* have sent, then compare against
System 3's `approved_units` for the same `signal_id`. If they match, the chain is proven and
the flag can come off.

Owner's position: **demo only.** `mode: demo`, `stage: paper`, practice endpoint, no live
account configured. Turning shadow off is the test, not the risk — but do it after one clean
drill, not before.

### Measured state on trading-1, so you do not re-derive it

```
310346  s2s3_bridge.py                     up 7d
332090  pubsub_signal_relay.py             up 5d
406495  system2.artifact_sync.downloader   up 2d
406532  python -m system2                  up 2d   <- holds the WRONG queue file
406547  ams.service.main (System 3)        up 2d
407010  telemetry_publisher.py             up 2d

S3 fd 4 -> /opt/scalablebrain/shared/queue/queue.db   95 MB · live · WAL active
S2 fd 4 -> ...C:\Users\emman\...\queue.db             4 KB · private · empty
```

Everything is running. System 3 is healthy and gating correctly in 9 ms. System 1 is
publishing valid signals. **The single defect is which file System 2 has open.**

Full detail: `gs://scalable-brain-artifacts/handoff/adr001/` (nine files), or
`docs/comms/` in the System 1 repo.
