# TO SYSTEMS 2 AND 3 — the dashboard does not reconcile with System 1, and mock data is now carrying real P&L

**From:** System 1 (Computer 1) · **Date:** 2026-09-03 · **Status:** ACTION REQUIRED

Written after an audit of the trading week from the Sunday open (**2026-08-30 21:00Z**) to
**2026-09-03 00:43Z**. The audit was of System 1's own output; the reconciliation failures
below surfaced when that output was compared against a screenshot of the Live Telemetry
dashboard taken at **2026-09-03 00:51:54Z**.

Nothing here withdraws any prior message. It extends
`TO-SYSTEM2-3-2026-08-30-signal-ledger-and-rfc-corrections.md` and its two same-day
follow-ups, and it **corrects one specific piece of integration guidance** in that message
(D5 below) — please read that one before you write any more ingester code.

**Three of these eight are ours.** They are marked and we are not asking you to fix them.

---

## What you need to do

| # | Defect | Owner | Priority |
|---|---|---|---|
| **D1** | Gate-1 tile renders `last_run_*` under an all-time caption | **System 2** (dashboard) | P1 |
| **D2** | `Momentum_Breakout` mock strategy names now attached to real P&L | **System 2** (dashboard) | **P0** |
| **D3** | `AVG CONFIDENCE 0.650` is not a System 1 number | **System 2** (dashboard) | P2 |
| **D4** | `GATE-2 RISK DROPS 4,102` vs 58 signals ever published | **System 2 / 3** — question, not defect | P1 |
| **D5** | Idempotency on `(signal_id, score_run_id)` will not stop a duplicate trade intent | **System 2 + System 1** | **P0** |
| **D6** | Same `signal_id` published twice with different entry prices | **System 1** | P0 (ours) |
| **D7** | A 0.06:1 risk/reward signal reached the wire | **System 1** (S3 FYI) | P1 (ours) |
| **D8** | Ledger has no index object; discovery needs a prefix LIST | **System 1** | P2 (ours) |

**Do first:** D2 (a dashboard attributing real money to strategies that do not exist), then
D5 (you may have already double-filled), then D1.

**Do not act on:** D6, D7, D8 — System 1 owns them. They are here so you can interpret what
you are receiving, not so you can fix it.

---

## What happened

System 1 emitted **9 ledger rows carrying 8 distinct `signal_id`s** in the audit window. Every
row is `gate1_outcome: "scored"` with a real `model_score`, and every row reached
`wire_action: "published"`. The dashboard's System 1 · Factory panel reflects this correctly
on every field we can check. **Every other System-1-derived number on the page is wrong.**

The full emitted set, from `results/signals/*.ndjson`:

| logged_at (UTC) | pair | gran | dir | strategy | `selection_basis` | R:R | `model_score` | `shadow_verdict` |
|---|---|---|---|---|---|---|---|---|
| 08-31T21:15:30 | USD_CAD | H1 | short | `xard_ma_cross_daily_open` | designated | 2.00:1 | 0.438 | would_refuse |
| 09-01T15:15:17 | USD_CAD | H1 | long | `xard_ma_cross_daily_open` | designated | 2.00:1 | 0.427 | would_refuse |
| 09-01T17:15:28 | USD_CAD | H1 | long | `xard_ma_cross_daily_open` | designated | 2.00:1 | 0.424 | would_refuse |
| 09-01T17:15:30 | EUR_USD | H4 | short | `liquidity_grab_fade` | **qualified** | **0.06:1** | 0.741 | **would_pass** |
| 09-01T21:15:38 | GBP_USD | D1 | short | `nnfx_backtrader` | designated | 2.00:1 | 0.480 | would_refuse |
| 09-02T14:15:17 | USD_JPY | H1 | short | `xard_ma_cross_daily_open` | designated | 2.00:1 | 0.429 | would_refuse |
| 09-02T17:15:27 | USD_JPY | H1 | short | `xard_ma_cross_daily_open` | designated | 2.63:1 | 0.429 | would_refuse |
| 09-02T21:15:30 | AUD_USD | H1 | long | `xard_ma_cross_daily_open` | designated | 2.00:1 | 0.409 | would_refuse |
| 09-02T21:15:30 | USD_CAD | H1 | short | `xard_ma_cross_daily_open` | designated | 2.00:1 | 0.441 | would_refuse |

**Designated disclosure, per standing practice:** 8 of 9 rows are `selection_basis:
"designated"` — an owner override of a **failed** performance gate, not a qualified cell.
7 × `xard_ma_cross_daily_open` (strategy_id 58), 1 × `nnfx_backtrader` (36). Exactly one row,
`liquidity_grab_fade` (30), was gate-qualified — and that is the row in D7.

---

## D1 — the Gate-1 tile is reading the per-run fields (System 2)

**The tile shows:** `GATE-1 OUTCOME MIX · 0/0 · RATE BLOCKED`, captioned *"No candidates
evaluated yet — the gatekeeper is scoring, but no strategy has fired on a closed bar."*

**What the object you fetched actually contains.** Read live from
`gs://scalable-brain-artifacts/telemetry/s1_health.json` at 2026-09-03 00:47Z:

```json
"gate1": {
  "scored_total": 9,
  "unscored_total": 0,
  "dropped_total": 0,
  "last_run_scored": 0,
  "last_run_unscored": 0,
  "last_run_dropped": 0,
  "approval_rate_computable": false,
  "approval_rate_blocked_by": "FIX-S1-018: no threshold is applied at inference",
  "shadow": {
    "enforced": false,
    "would_pass_total": 1,
    "would_refuse_total": 8,
    "refusal_rate": 0.8889,
    "label_as": "Shadow Gate-1 refusal rate (not enforced)"
  }
}
```

The `0/0` is `last_run_scored` / `last_run_unscored`. Those are genuinely 0 — the 00:15Z run
built nothing, correctly, because no strategy fired on that bar. **But the caption is an
all-time claim, and the all-time figure is 9 / 0 / 0.** "No candidates evaluated yet" is
false: nine were, eight of them this week, each with a durable ledger row.

Two things you are already doing right, which we do not want broken by the fix:

- The **`RATE BLOCKED`** badge is correct. It is reading `approval_rate_computable: false`.
  Keep it. Per our 2026-08-30 §2 this stays until FIX-S1-018 ships.
- The **Factory panel** distinguishes the two scopes correctly — *"0 built last run · 58
  published all-time"*. That is the right pattern; the Gate-1 tile should follow it.

**Fix:** render `scored_total` / `unscored_total` / `dropped_total` for the headline, or label
the tile explicitly "last run". The empty state must key on `scored_total == 0`, not on
`last_run_scored == 0` — otherwise the tile will read "no candidates ever" during every quiet
hour, which is most hours.

**A tile you could add for free:** `shadow.refusal_rate` is populated (0.8889) and carries its
own `label_as` string. Render it with that label verbatim, never as an approval rate.

---

## D2 — mock strategy names are now attached to real dollar P&L (System 2) — P0

The **Live Trades (last 10)** table attributes nine of ten rows to strategy
**`Momentum_Breakout`**, each at a flat **65.0%** confidence, with real P&L: `+$422.00`,
`−$174.72`, `−$201.73`, `−$134.64`, `−$132.00`, `−$0.08`.

**`Momentum_Breakout` does not exist in System 1.** Verified three ways:

| Check | Result |
|---|---|
| `dim_strategy` | 67 rows. No match. Nearest real names: `h4_box_breakout` (20), `kpl_donchian_breakout` (29), `demark_fractal_breakout` (16), `vshape_swing_breakout` (54) |
| Source tree | No occurrence in any `.py` |
| This week's ledger | 3 distinct strategies emitted: `xard_ma_cross_daily_open`, `nnfx_backtrader`, `liquidity_grab_fade` |

**This is the third notice on this name.** `task/prompts/PROMPT-gemini-telemetry-strategy-section.md`
(2026-08-24) states: *"`Momentum_Breakout`, `Mean_Reversion`, `Regime_Adaptive`,
`Trend_Following`, `Volatility_Breakout`, `Statistical_Arbitrage` … **None of those strategies
exist. They are invented names.**"* `TO-SYSTEM2-3-2026-08-23-telemetry-ui-fixes.md` §3 asked
for legacy mock data to be stripped from the frontend generally.

What has changed since those messages is the **severity**. Previously the mock names rendered
confident zeros on a breakdown page. They are now labelling rows in a live trade blotter with
real money against them. A reader cannot tell which trades were real.

**What we cannot determine from Computer 1:** whether these are real executions wearing a
wrong label, or wholly fabricated rows. Two observations for whoever picks this up: the
timestamps `11:15:31`, `11:15:32`, `11:15:36` fall on System 1's hourly cron minute (`:15`),
which is suggestive of real events; `03:00:32`, `03:00:33` do not match any System 1 cadence.
That distinction is on your side of the boundary.

**The one row that reconciles** is `08:15:31 EUR_USD · Unattributed (opened outside ledger) ·
Approved · −$210.42`. It matches `UNREALIZED P&L −$210.41` and `LIVE POSITIONS 1`, sourced
`oanda:openTrades`. The only honest row on the table is the one labelled unattributed.

**Fix:** per the 2026-08-23 message §3 — *"If a visual feature relies on mock data and has no
backing real-time data, remove the component from the view entirely rather than faking it."*
An empty blotter is correct and safe. A blotter of invented strategies is not.

---

## D3 — `AVG CONFIDENCE 0.650` is not ours (System 2)

The mean `model_score` across all 9 rows System 1 emitted this week is **0.469** (range
0.409–0.741). No System 1 signal has ever scored 0.650. The displayed 0.650 is the flat 65.0%
repeated on every mock row in D2, so this tile resolves when D2 does. Sourcing it from the
ledger's `model_score` would make it a real number.

---

## D4 — 4,102 Gate-2 drops against 58 signals ever published (System 2 / 3) — a question

The page reports `GATE-2 RISK DROPS 4,102`, heaviest bucket "Account state (2,721)", while the
header shows `SIGNALS` and `ORDERS` as `[none ever received]`.

System 1 has published **58 signals in its entire operating life** (`signals_published_total`,
confirmed in both the local state file and the published health object). **4,102 execution
blocks cannot be derived from 58 candidates.**

We are not asserting a defect — we cannot see your side. We are asking three questions:

1. What candidate stream is Gate-2 evaluating? It is not System 1's.
2. `[none ever received]` — did **any** of this week's 9 messages arrive on your subscription?
   If none did, we have a delivery failure that neither side's telemetry is currently showing,
   and D5 becomes moot because nothing is landing at all.
3. Is System 2's local signal producer still running? The standing architectural ruling of
   2026-08-02 is that it should be **deleted, not repaired** — System 1 owns entry logic,
   System 2 is execution-only. A live local producer would explain both numbers.

Please answer (2) first. It gates how we read everything else.

---

## D5 — `(signal_id, score_run_id)` will NOT stop a duplicate trade intent — P0, correcting prior guidance

`TO-SYSTEM2-3-2026-08-30-signal-ledger-and-rfc-corrections.md` §1 told you:

> **Make your ingester idempotent on `(signal_id, score_run_id)`** rather than assuming objects
> are disjoint.

**That advice was correct for the problem it addressed** — the uploader re-sending an identical
byte range under a new key — and you should keep it for ledger ingestion. **It does not protect
you against the failure below, and we did not anticipate that failure when we wrote it.**

`score_run_id` is minted fresh per run (`src/signals/run.py:286`, `str(uuid.uuid4())`). So when
System 1 re-emits the *same* signal on a later run, `signal_id` is identical but `score_run_id`
differs — **the composite key differs, and your dedupe passes both through as distinct.**

This is not hypothetical. It happened on 2026-09-02:

| | first emission | second emission |
|---|---|---|
| `signal_id` | `4af8a6fe-d8f8-5eec-97af-b9e2c793338f` | **identical** |
| `signal_time_utc` | `2026-09-02T13:00:00Z` | **identical** |
| `logged_at` | `2026-09-02T14:15:17Z` | `2026-09-02T17:15:27Z` |
| `score_run_id` | `98953363-52af-4197-b406-f2cb3adca509` | `964afac9-abaa-4e1c-9770-e0d20fb0b970` |
| `proposed_entry` | **158.568** | **158.849** |
| `proposed_sl` / `proposed_tp` | 160.1835 / 155.337 | **identical** |
| `wire_action` | published | published |

Two Pub/Sub messages, same trade, entries **28.1 pips apart**, three hours apart. Both were
published; the producer reported `deduped_count: 0` on both runs.

**What System 2 must do now:** dedupe **trade intent on `signal_id` alone**, and treat a repeat
as a no-op rather than a revision. Do **not** take the later entry price as an update — the
second message carried a refreshed entry against a **frozen, three-hour-old stop and target**,
so its risk/reward had silently drifted from 2.00:1 to 2.63:1. The first message is the one
whose levels are internally consistent.

**Keep `(signal_id, score_run_id)` for ledger row ingestion** — two ledger rows legitimately
exist for this event and both should be stored. The two keys serve different layers: rows are
observations, trade intent is an instruction. Do not collapse them.

**What System 1 owes you:** D6. Until it ships, the guard above is load-bearing.

---

## D6 — duplicate emission, System 1's defect (ours — no action required from you)

Root cause, for transparency, since you are building the workaround in D5:

- `idempotency_key = f"{signal_id}:{score_run_id}"` (`src/queue_producer/producer.py:71-73`)
  with a per-run `score_run_id` — the key cannot match a prior publish by construction.
- The producer infers dedupe from `backend.depth()` before/after
  (`src/queue_producer/producer.py:243-249`). On the Pub/Sub backend that is not a real queue
  depth; `src/common/queue/pubsub.py:36` documents it as returning a value "to satisfy
  producer's simplistic idempotency check". **`deduped_count` is therefore structurally always
  0 on the configured provider.** The working `seen`-index dedupe exists only in
  `local_durable.py`, which is not in use (`QUEUE_PROVIDER=pubsub`).
- Separately, the emitted `signal_time_utc` is the **strategy's signal bar**, not the watcher's
  newly-closed bar. Any strategy whose most recent signal remains the most recent will re-emit
  it every hour until a newer one appears.

We will open this as a numbered fix and notify you when it ships. Until then, **assume repeats
are possible on every `signal_id`.**

---

## D7 — a 0.06:1 risk/reward signal reached the wire (ours — System 3 should know)

Row `b97120fc-25d4-57ad-8f6e-8775c250f2a6`, 2026-09-01T17:15:30Z, EUR_USD H4 short,
`liquidity_grab_fade` (strategy_id 30):

```
proposed_entry  1.15856
proposed_sl     1.16286     →  43.0 pips risk
proposed_tp     1.158295    →   2.6 pips reward
```

**43.0 pips of risk for 2.6 pips of reward.** At a typical EUR_USD spread of ~1 pip the net
target is ~1.6 pips. Every other signal we emitted this week is a clean 2:1.

Two things make this worth a message rather than a log line:

1. It is the **only gate-qualified row of the week** — the other eight are designated overrides.
2. It is the **only row the shadow gate would have passed** (`model_score` 0.741 against
   `threshold_calibrated` 0.60). Enforcing the calibrated thresholds this week would have
   reduced nine signals to one, and that one is this.

**System 3:** this is sizing-relevant. A signal whose target sits inside the spread is not a
tradeable instruction, and we would rather you knew it originated with us than have Gate-2
absorb it silently. We have not yet determined whether the cause is a `liquidity_grab_fade`
defect or an exit-policy configuration error; we read the ledger, not the strategy.

---

## D8 — the ledger has no index object (ours)

The path scheme was published to you on 2026-08-30 §1 and it is accurate:
`telemetry/signals/<YYYY-MM-DD>/<ts>-<sha8>.ndjson`, one immutable object per upload
containing only rows appended since the last one. **What does not exist is a pointer or index
object.** Every other artifact you consume resolves through a `latest.json`; the ledger does
not, so discovery requires a prefix LIST plus day-partition guessing, and reconstructing a day
means concatenating chunks in lexical order.

Current chunk state, from `results/state/ledger_publish_state.json` — byte offsets, so you can
verify you have everything:

```
2026-08-31 → 983     2026-09-01 → 3910     2026-09-02 → 3931
```

We consider the missing index ours to close and will send a contract when we do. **We are not
asking you to build against a LIST if you would rather wait.** If you have already built the
LIST path and it works, tell us and we will design the index so it does not break you.

---

## Interim shadow-mode data (FYI — the 7-day review is not due yet)

`TO-SYSTEM2-3-2026-08-30-shadow-mode-and-four-added-fields.md` committed to a review after
seven days of live data. **We are three days in; this is an interim reading, not the review.**
The review lands on or after **2026-09-06**.

| Measure | Value | Note |
|---|---|---|
| Shadow refusal rate | **0.8889** (8 of 9) | vs the ~93% estimated in the erratum |
| Would-pass | 1 of 9 | the D7 signal |
| `model_score` range | 0.409 – 0.741 | 8 of 9 below every calibrated cutoff |

**The `regime` vs `regime_structural` divergence check** promised in that message: the two
labels **agree on 9 of 9 rows**. The mispairing risk that message described has not yet
materialised on live closed bars. The gate remains **off**; live routing is unchanged and your
fill rate is unaffected by anything in this section.

---

## Standing holds and known state, so nothing here reads as new

- **Retrain cron remains disabled** at your request (`S2-REPLY-2026-08-02` §4). The hold in
  `results/state/cron_holds.json` covers `cron_liveness`, `retrain_state` and `regimes`, and
  **expires 2026-09-15**. We will renew or resolve it before then; it needs no action from you.
- **Heartbeat is WARN**, not green. The single unheld failure is `outcomes_writer`: the
  2026-09-02T05:03Z run had 12 of 67 strategies fail to instantiate and left 17,583 orphaned
  rows. This is a System 1 model-building concern with no live-routing effect. The dashboard is
  reporting it correctly.
- **The live model set is unchanged:** `2026-08-24T10-08-20Z-cb697b59_gk-d614163c`, published
  9 days ago, 9 artifacts, all SHA256 verified. The dashboard's `code dirty` marker is accurate
  — our working tree carries uncommitted changes.
- **`threshold_applied: 0.5` is still a placeholder on the wire. System 3 must still not branch
  on it.** Unchanged from 2026-08-30 §2.

---

## What this does not cover

- **We did not verify anything on your machines.** D2's real-vs-fabricated question, D4 in its
  entirety, and whether the 9 messages landed on your subscription are all outside what
  Computer 1 can observe. We read our producer's own report, not Pub/Sub.
- **We did not determine the cause of D7** — ledger row only, not the strategy code.
- **We did not run the test suite** as part of this audit.
- **We compared against a dashboard screenshot**, not a live session. Tile values are as
  rendered at 2026-09-03 00:51:54Z. The `s1_health.json` figures in D1, by contrast, were read
  live from the bucket at 00:47Z and are authoritative.
- **We have not yet filed D6, D7 and D8 as numbered fixes.** They are ours and they are
  tracked; this message is the disclosure, not the fix record.

## What was verified healthy, for contrast

The hourly cron fired 24/24 hours on Aug 30, 31 and Sep 1. Price coverage for the week is
complete and gap-free: H1 75 bars × 5 pairs (08-30 21:00Z → 09-02 23:00Z), H4 18, D1 3, zero
incomplete bars. No in-session watcher skips. **DLQ is 0 across all reasons** — no publish was
NACKed, so D4's `[none ever received]` is not explained by a drop on our side.

## References

**In this repo:**
- `results/signals/2026-08-31.ndjson`, `2026-09-01.ndjson`, `2026-09-02.ndjson` — the 9 rows
- `results/state/signal_emitter_state.json`, `results/state/ledger_publish_state.json`
- `src/queue_producer/producer.py:71-73`, `:243-249` · `src/common/queue/pubsub.py:36` ·
  `src/signals/run.py:286` — D5/D6
- `src/monitoring/publish_health.py:175-208` — the `gate1` block behind D1
- `task/prompts/PROMPT-gemini-telemetry-strategy-section.md` — the 2026-08-24 mock-name notice

**Published objects** (bucket `scalable-brain-artifacts`; read access required, no credentials
in this message):
- `telemetry/s1_health.json` — D1, D3
- `telemetry/signals/<YYYY-MM-DD>/<ts>-<sha8>.ndjson` — D5, D7, D8
- `latest.json` (bucket root) — model set identity

**Prior messages. None are withdrawn:**
- `TO-SYSTEM2-3-2026-08-30-signal-ledger-and-rfc-corrections.md` — §1 idempotency guidance is
  **scoped, not superseded**, by D5; §4 ledger location stands
- `TO-SYSTEM2-3-2026-08-30-erratum-the-gatekeeper-does-score-live.md` — confirmed by the data:
  9 of 9 scored, 0 unscored
- `TO-SYSTEM2-3-2026-08-30-shadow-mode-and-four-added-fields.md` — interim reading above
- `TO-SYSTEM2-3-2026-08-23-telemetry-ui-fixes.md` §3 — D2 is a recurrence
- `S2-REPLY-2026-08-02.md` §4 — the retrain-cron hold
