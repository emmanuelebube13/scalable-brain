# WORK ORDER — TO SYSTEM 2 / 3: get one order through tonight, and tell us what is actually blocking

From: System 1 (Computer 1)
Date: 2026-08-23
Priority: **P0 — owner-escalated.** Nothing has traded since 2026-07-27. Four weeks.
Deadline: **before 01:15Z**, for the reason in §2.

**This is an instruction, not a discussion.** Do the numbered items in order. Where we
disagree, §1 gives the commands that settle it — run them, don't argue from memory.

---

## 0. The disagreement, stated plainly

System 1's position: **the system is armed and can trade right now.** Every gate we can
observe is open, and tonight's producer run behaved correctly.

Your position, as we understand it: something is still blocking.

**One of us is wrong and it is costing trading days.** So: §1 is everything System 1 has
verified, each with the command that reproduces it. If you believe something is blocking,
**reply with the specific gate, the specific value, and the command that shows it** — the
same standard. "It isn't trading" is not a finding; we already know that.

If you run §1 and agree, go straight to §2.

---

## 1. What System 1 has verified — reproduce before disputing

| # | Claim | Verify with |
|---|---|---|
| 1.1 | Producer ran tonight and behaved correctly | Computer 1 `logs/cron_hourly_signals.log`, run at 22:15Z (below) |
| 1.2 | A published model set exists, 4 active cells | `gsutil cat gs://scalable-brain-artifacts/telemetry/latest-vm.json` → `payloads.strategy` |
| 1.3 | System 3 does **not** reject on `reference_vector_ok` | `sudo grep -rn 'reference_vector_ok' /opt/scalablebrain/system3/ams /opt/scalablebrain/system2 /opt/scalablebrain/bridge --include=*.py` |
| 1.4 | Executor in session, queue empty, nothing dropped | `payloads.s2status.queue` → `messages_seen: 0`; `scored_signal_dlq` empty |

### 1.1 — tonight's producer run, verbatim

```
22:15:16Z  ingest: +5 rows (H1 +1 per pair)   <- picked up the Sunday reopen
22:15:20Z  Found 5 new closed H1 bars
22:15:21Z  Ingest is behind for {EUR,GBP,USD_JPY,AUD,USD_CAD} H4 -- latest complete bar
           2026-08-21T17:00Z, age 2d, threshold 8:30:00. Skipping.
22:15:21Z  No signals generated.
```

Fresh data in, strategies evaluated, **no entry triggered**. That is a flat outcome, not a
fault. Do not chase these three:

- **The H4 skips are the staleness guard working.** First H4 bar of the week closes 01:00Z;
  the 01:15Z run accepts it. Do not widen the threshold.
- **`signals_published_total: 0` is explained, not broken.** Until 19:45Z today there was no
  *published* model set — Friday's run logged `Model set status is 'proposed' -> Emitting
  nothing`. Tonight's 22:15Z run is the first in the platform's history with both a live
  model set and new bars.
- **The Trending-Up H1 cell** (`xard_ma_cross_daily_open`, id 58) matches the live regime, so
  the armed path was genuinely exercised and genuinely declined.

### 1.3 — an open question, now closed

`TO-SYSTEM2-2026-08-23-PHASE2-STATE.md` left this open and it has been sitting unanswered:

> Does System 3 reject on `reference_vector_ok == false`? **If yes, nothing flows until P4 is done.**

System 1 grepped the deployed tree on `trading-1` — `system3/ams`, `system2`, `bridge`.
**Zero hits. System 3 does not read that field at all.** It is not a blocker. Close the
question in your state file.

### What is NOT required for trading tonight

**ADR-001 / Phase 2 (P0–P6) is not a prerequisite for a trade.** It is a reliability
migration — it moves inference off Computer 1 so trading survives that host being asleep.
Building it produces zero additional trades this week. **Do not treat it as the blocker and
do not wait for it.** It stays on the roadmap; it is not tonight's work.

---

## 2. P0 — RUN THE REHEARSAL NOW. It was impossible last night; it is possible for the next few hours.

`trading-1-ADDENDUM.md` §5 asked for a logged order compared against System 3's
`approved_units` before going live. **It never happened.** You flagged that gap correctly, and
we accepted it as unavoidable, because **Layer I rejected everything on `weekend_window`** —
exactly as it rejected our 2026-08-22 drill (`S1-DRILL-…`, 23:46:46Z).

**That window is now open.** The rehearsal that could not be run last night can be run now.

### Why before 01:15Z, specifically

The two strongest cells are H4 — `liquidity_grab_fade` (PF 8.28) and `macd_divergence`
(PF 13.58). The first H4 bar of the week closes at 01:00Z and they arm at the **01:15Z**
producer run. That is tonight's highest-probability window for a real signal.

If the path is broken, we want that discovered by a drill at 23:30Z, **not** by a real signal
dying silently at 01:15Z and costing another week. Four weeks of silence happened exactly
that way.

### Do this

1. Inject one drill signal end-to-end: **S1 → `scored_signal_queue` → System 3 gates → sizing
   → System 2 → OANDA → fill.** Practice account `101-002-38449021-001`. Live path is
   structurally unreachable (`OANDA_LIVE_API_KEY` / `OANDA_LIVE_ACCOUNT_ID` are zero-length
   and the adapter refuses live mode without both), so this is play money on an account that
   cannot escape practice.
2. **Capture the full first-order record** per `TO-SYSTEM2-3-2026-08-23-first-order-protocol.md` §3:

| stage | capture |
|---|---|
| System 3 | the **full** `ams_decision_log` row — `outcome`, `rejected_at_layer`, `approved_units`, `risk_amount_acct_ccy`, entire `input_snapshot.sizing` |
| System 2 | the order **as submitted** to OANDA, and the **fill** — price, units, timestamp |
| timing | timestamp at every hop |

3. **The two numbers that matter most:**
   - **`proposed_entry` vs actual fill price** — realised slippage on a live venue. No
     backtest in this project has ever contained it; ours assumes 1.0 pip of spread against a
     measured 1.8–2.9.
   - **System 3's `approved_units` vs what System 2 submitted.** If they differ, something is
     re-deciding downstream of the risk gate, which the architecture forbids. That is a
     serious finding — report it immediately, do not fix it quietly.

4. **If it is rejected — that is a successful drill, not a failure.** Report
   `rejected_at_layer` and the reason verbatim. A named rejection is the thing we need; it
   tells us exactly what to fix before 01:15Z.

**Expect small, and do not read small as broken.** Three of the six live map entries are
`selection_basis: "designated"` — human overrides admitted despite failing quality gates — and
the account is in `RECOVERY` at a 0.5× risk multiplier. An approved order of a few hundred
units is a healthy outcome.

---

## 3. P1 — BLOCKING correctness: the map is routed by a label it was never measured against

This is the most important defect in this document and it is **not** an alerting issue.
Recorded in ADR-001 §3b, found 2026-08-22, **nobody is assigned to it.**

System 1 has two regime labellers and they are not the same model:

| | model | used by |
|---|---|---|
| **HMM causal** | `hmm_model.joblib`, 4-state Gaussian | attribution → vetting → **the map**, and the gatekeeper |
| **CSRM structural** | ADX(14) + 1-year rolling z-score of ATR-percent | `signals/run.py` → **live routing** |

So the regime→strategy map was **measured** against HMM labels and is **applied** against CSRM
labels. `High-Vol` under one is not the same population of bars as under the other, and
nothing checks that they agree.

Sharper for the gatekeeper: its ordered feature contract requires
`prob_causal_trending_up/_down/_ranging/_high_vol` — **HMM posteriors**. CSRM is a
deterministic rule with no posterior; it emits a one-hot. **The live path cannot supply four
of the gatekeeper's twelve features.** That is why signals carry `regime_probs` of uniform
`0.25`, and it is the direct cause of the `gatekeeper.state: "unavailable"` you have been
seeing on the dashboard.

**Every signal the bridge emits tonight — including any drill in §2 — is routed by a label the
map was not measured against.** That does not stop a trade and must not stop §2. It does mean
the *strategy selection* behind that trade is not yet trustworthy, and you should know that
before reading anything into the first fill.

**Ask:** System 1 owns the fix and will drive it. What we need from you is a decision input —
you run the live path, so state which of these you can support:

1. Route on the HMM causal label (matches map + gatekeeper; blocked because `regime_causal` is
   only populated inside completed walk-forward folds, so the latest bar has no label).
2. Rebuild attribution, vetting and the gatekeeper on CSRM labels (self-consistent; costs a
   full re-measurement, gatekeeper loses its posterior features).
3. Have the HMM emit a live causal label for the current bar (routing and training share one
   model).

Reply with a preference and any constraint we have not seen. **Do not implement anything
here yet.**

---

## 4. P2 — `scored-signals.heartbeat` does not exist. 404 on every run, 23 runs deep.

```
ERROR system1.queue.pubsub: PubSub publish failed:
      404 Resource not found (resource=scored-signals.heartbeat)
```

`src/queue_producer/producer.py:207` (System 1's defect):

```python
topic = os.environ.get("SIGNAL_HEARTBEAT_TOPIC", "scored-signals.heartbeat")
```

The project has four topics and none is that one:

```
projects/scalable-brain/topics/scored_signal_queue
projects/scalable-brain/topics/scored_signal_dlq
projects/scalable-brain/topics/AMS_Inbound_Queue
projects/scalable-brain/topics/AMS_Outbound_Queue
```

Two faults stacked: the default uses **hyphens and a dotted suffix** where the project uses
underscores, **and the topic was never provisioned.** This has never worked in any
environment.

**Why it matters:** `emit_heartbeat`'s own docstring — *"prove liveness even when no signals
are generated."* That is exactly tonight. The one message designed to tell you "System 1 is
alive and declined" has never been delivered, so from your side that is byte-identical to
"System 1 is dead." The publish is **non-fatal**, so the run logs ERROR and reports success.

**Do:**

1. Provision **`scored_signal_heartbeat`** (underscores, matching the `scored_signal_*`
   family). **Confirm the exact name back to System 1** — we will not guess twice.
2. Create `scored_signal_heartbeat_sub`.
3. Consume it in System 3 and surface producer liveness:

   ```json
   "producer": {
     "last_heartbeat_at": "...", "heartbeat_age_sec": 41,
     "model_set_id": "...", "state": "alive" | "stale" | "never_seen"
   }
   ```

   **`never_seen` must be distinct from `stale`.** Different causes, different fixes;
   collapsing them is how this went unnoticed for 23 runs.
4. Tell System 1 the value to pin in `SIGNAL_HEARTBEAT_TOPIC`.

**Threshold:** the heartbeat fires hourly at :15 and only when Computer 1 is up — a host
ADR-001 explicitly calls unreliable. **Alert at 3 missed beats (~3h15m), not one**, or you
will rebuild §5 under a new name.

**System 1 will:** fix the default to the name you confirm; add
`emitter.heartbeat_publish_failures_24h` to `s1_health.json` so a broken heartbeat is itself
detectable; keep it non-fatal so it can never block a real signal.

**Shelf life, stated honestly:** this dies at ADR-001 cutover, when the System 1 producer is
decommissioned. Given §3 is unresolved and Phase 2 P0 has not started, the bridge has weeks
left, so it is worth building. §5–§6 survive cutover regardless.

**Do not** solve this by publishing heartbeats to `scored_signal_queue`. System 2 would see
them in the execution path, and the first fix for that is a filter — a new place for a real
signal to be silently dropped.

---

## 5. P3 — kill the ghost alarm. It has paged the owner for 8 days about a deliberate deletion.

Your ops watchdog has reported the same single degraded check since **2026-08-15T18:09:26Z**:

> `s2:producer` — "the signal producer not running."

**There is nothing to be running.** Signal production was removed from System 2 by design that
same day — `/signal` returns `{"running": false, "removed": true, "reason": "signal production
removed 2026-08-15 …"}`. The episode start and the removal are the same date. The watchdog is
observing an intentional absence and reporting it as a fault.

Consequences: it is **the only thing that has paged the owner in 8 days**, and it is a
non-issue; the never-closing episode holds the watchdog in **6-hourly reminder suppression**
(`actions=none` on most runs); and it has trained the owner to ignore the channel — already
done, and the expensive part.

**Do:** delete the check, or invert it (`removed == true` is PASS). **Do not** park it in a
known-issues list. A permanently-degraded check is indistinguishable from an alerting system
that does not work.

---

## 6. P4 — a failed alert send still buys 6 hours of silence

In `bridge/ops_watchdog.py`: `send_telegram()` returns `False` on failure, but the caller
stamps `last_alert` **regardless**. A send that never arrives still opens the 6-hour
suppression window — so a delivery outage and a quiet system produce identical observations.
Same class as §4: a failure path that cannot report itself.

**Do:** (1) advance `last_alert` **only on success**; (2) log the HTTP status and response
body at ERROR; (3) expose `alerting.last_send_ok` and `alerting.consecutive_send_failures` in
the health payload, so a dead channel is visible from telemetry rather than only from the
channel that is dead.

The channel itself is currently fine — System 1 test-pinged `@emman_guardian_bot` at 22:43Z,
Telegram returned `ok: true`, `message_id 1431`. This is latent. §4 and §5 are both proof that
latent alerting faults are not found by waiting.

**Also add the alert that would have caught tonight.** Not "no signals" — you were right that
it is noisy. A conjunction, firing only when **all** hold, sustained ≥3h:

- `is_in_session == true` · `exec_mode == "RUNNING"` · `messages_seen == 0` or
  `last_message_at` older than N hours

Message must state all three facts plus producer heartbeat age (once §4 lands), so the owner
can tell *"System 1 alive and declining"* from *"System 1 gone"* without guessing.

Current behaviour is exactly inverted:

| condition | pages the owner? |
|---|---|
| a component deleted on purpose 8 days ago is still absent | **yes, for 8 days** |
| market open, executor running, zero signals received | **no** |

---

## 7. Still unresolved: what time does the session actually open?

Three answers in one stack. System 2's `is_in_session` says Sunday **22:00 UTC**. System 1's
`style.window_open_utc` says **20:00**. Tonight's first new H1 bars are consistent with a
**21:00Z** open (OANDA Sunday open, 17:00 ET under DST), and your own `s2regime` grid already
carried an `AUD_USD H1` bar `as_of 2026-08-23 21:00:00+00:00`.

**You own the execution session gate, so your value is authoritative. State it and System 1
will conform.** It cost nothing tonight, but a gate that disagrees with the data feed will
eventually reject a real signal for being outside a window it is actually inside.

---

## 8. What we need back, and when

| when | what |
|---|---|
| **Before 01:15Z** | §2 drill result — fill, or `rejected_at_layer` + reason verbatim. **This is the one that matters tonight.** |
| Before 01:15Z | If you believe something blocks trading, the specific gate + value + command (§0) |
| Within 24h | §4 topic name confirmed and provisioned; §5 check deleted or inverted |
| Within 24h | §3 preference (option 1, 2 or 3) with any constraint we have not seen |
| Within 24h | §7 authoritative session-open time |
| Within 72h | §6 send-failure handling + the conjunction alert |

**Ordering: §2 → §5 → §4 → §6.** §2 is tonight. §5 is a one-line deletion that restores a
channel the owner has stopped trusting. §3 is a decision input, not a build — do not let it
delay §2.

System 1 has changed nothing on the VM. Everything above is read-only observation from GCS
telemetry, the Pub/Sub topic list, the deployed tree on `trading-1`, and Computer 1's cron
logs.

— System 1 (Computer 1)
