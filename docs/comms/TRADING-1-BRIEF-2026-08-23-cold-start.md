# trading-1 — cold-start brief

**For whoever is working on `trading-1` tonight. Assumes no prior context.**
From: System 1 (Computer 1) · 2026-08-23

---

## 1. Where things stand, in one paragraph

This platform has three systems. **System 1** (a separate machine) builds models offline and
publishes signals. **System 3** (on your box) gates and sizes every signal. **System 2** (also
on your box) executes approved orders on OANDA. Nothing has traded since **2026-07-27** —
four weeks — because of a chain of independent faults that have now all been fixed. The last
safety catch, `EXEC_SHADOW`, was set to `false` today. **The market reopens ~21:00 UTC and
this will be the first end-to-end transaction the platform has ever completed.**

## 2. It is a practice account and it cannot become a live one

Verify this yourself before doing anything — do not take it on trust:

- `OANDA_ENV=practice`, account `101-002-38449021-001` (OANDA practice prefix)
- `OANDA_LIVE_API_KEY` and `OANDA_LIVE_ACCOUNT_ID` are **zero-length**, and
  `oanda_adapter.py` refuses to start in live mode without both

Practice is therefore *unreachable to escape*, not merely selected. Balance reads
84,013.70 CAD; it is play money.

## 3. Nothing firing before 21:00 UTC is correct

Gate layer I rejects everything with `weekend_window` until the market opens. Silence
between now and then is the system working, not a fault. Do not debug it.

After the open, **small or absent is also correct**. Three of the six live strategies are
human overrides admitted despite failing their quality gates, and the account is in
`RECOVERY` at a 0.5× risk multiplier. An approved order of a few hundred units is a healthy
outcome. So is a quiet night.

## 4. If an order fires — capture it completely, once

This is the only thing we actually need from tonight. For **one** `signal_id`, collect:

| from | what |
|---|---|
| System 3 | the full `ams_decision_log` row: `outcome`, `rejected_at_layer`, `approved_units`, `risk_amount_acct_ccy`, and the entire `input_snapshot.sizing` block |
| System 2 | the order **as submitted** to OANDA, and the **fill** — price, units, timestamp |
| both | timestamps at each hop |

**The number that matters most: `proposed_entry` versus the actual fill price.** That is
realised slippage on a live venue. No backtest in this project has ever contained it — ours
assumes 1.0 pip of spread against a measured 1.8–2.9, and this fill is the first evidence of
which is closer to true.

**Second: System 3's `approved_units` versus what System 2 actually sent.** If they differ,
something is re-deciding downstream of the risk gate, which the architecture forbids. That
would be a serious finding.

## 5. If something goes wrong

Escalating, least drastic first:

1. `/pause` via the Telegram override bot (`ams/override/bot.py`) — stops new orders
2. `/flatten` — closes open positions
3. `EXEC_SHADOW=true` in `config/.env.system2` and restart System 2 — back to logging only.
   One `sed`, one restart. A backup of the pre-change file is at
   `/opt/scalablebrain/backups/exec-shadow-20260823T120230Z/`

Use `sed`, not Python, for that file — a previous edit mangled its non-ASCII characters.

## 6. Do not do these

- **Do not add a local signal generator, fallback, or "degraded mode" to System 2.** Its
  signal producer was deleted on 2026-08-15 for fabricating order direction from a regime
  label with no entry condition behind it. Entry logic belongs to System 1. If System 2 is
  idle because nothing arrived, **stay idle and say so loudly** — that is the fix, not a
  workaround.
- **Do not repoint `QUEUE_LOCAL_PATH`.** It was broken (a Windows path on a Linux host,
  silently creating a private empty database) and is now correct. All three processes must
  hold `/opt/scalablebrain/shared/queue/queue.db` — verify with
  `ls -l /proc/<pid>/fd/ | grep queue`, and compare inodes, not paths.
- **Do not "fix" a quiet market.** See §3.

## 7. Two things outstanding that someone should do

1. **Commit `system3/ams`.** It has ~700 uncommitted lines across 23 files, including
   ADR-001 queue work. If tonight goes wrong, "what changed?" currently has no answer. Even
   a single honest "state as found" commit is enough.
2. **Deploy the partial-delivery fix and the executor-silent detector** if they have not
   shipped. Both are observability-only. Note that the notification outbox has a real defect:
   306 rows report `status: sent` while only Telegram delivered and email never has — so
   "the alert was sent" is currently not trustworthy.

## 8. Where the detail lives

`gs://scalable-brain-artifacts/handoff/adr001/` — every document, readable with `gsutil cp`.
Start with `FIRST-ORDER-PROTOCOL.md` if you only read one.

System 1's own health is at `gs://scalable-brain-artifacts/telemetry/s1_health.json`,
refreshed hourly. In it, `emitter.last_signal_emitted_at` sitting null while
`emitter.last_run_at` advances every hour means System 1 is running and producing nothing —
which is the exact failure that hid for weeks. Tonight it should stop being null.
