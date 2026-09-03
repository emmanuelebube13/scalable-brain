# SIGNAL-EMISSION-DEFECTS — agent brief (D6, D7, D8)

**Week:** `2026-September-week1` (Mon 31 Aug – Sun 6 Sep) · **Opened:** 2026-09-03
**Register:** O-23, O-24, O-25 in `task/OPEN.md` · **Resume file:** `STATE.md` in this folder

Read `STATE.md` before starting and tick a box only after the step is **verified and
committed**. If you are resuming, `STATE.md` is the truth about where things stand — not this
file.

---

## 1. The goal, and why we are doing this

**Goal:** make what System 1 puts on the wire match what System 1 intends to put on the wire —
once per trade, with internally consistent levels, and discoverable afterwards.

**Why now.** On 2026-09-03 an audit of the trading week (Sunday open 2026-08-30 21:00Z → 09-03
00:43Z) compared System 1's own output against the Live Telemetry dashboard. Eight defects came
out. Five were System 2's and have been sent to them as
`task/prompts/PROMPT-S2-*` under cover of
`docs/comms/to_system2/TO-SYSTEM2-3-2026-09-03-dashboard-reconciliation-and-mock-data.md`.

> **Scope boundary.** D1–D5 are fixed in the System 2/3 repo — the dashboard tree
> (`telemetry-dashboard/src/App.tsx`) and their FastAPI backend, **neither of which exists on
> this machine.** See `task/prompts/PROMPT-S2-D0-where-to-work.md`. **Nothing in D6/D7/D8
> touches a dashboard.** If you find yourself looking for frontend code, you are on the wrong
> item.

**These three are ours.** They matter for one reason each:

- **D6** can cause a **duplicate fill at a worse price**. It already fired in production once.
- **D7** put a trade on the wire whose target sat **inside the spread** — 43 pips of risk for
  2.6 pips of reward — and it was the only gate-qualified signal of the week.
- **D8** is why Systems 2/3 cannot show per-signal data at all: the ledger is durable and
  checksum-verified, but has no index, so nobody can find it.

The through-line: System 1's product is a **model set, never a direct order**, but the live
signal bridge is currently the thing trading depends on. Every defect here is the bridge
telling a downstream system something slightly untrue. The repo's standing principle is
**preservation over profit** and **default-safe**. Two of these three fail that today.

**What success looks like in one sentence:** a downstream operator can take any signal we
emitted, find its ledger row, and be certain it was sent once and that its entry, stop and
target were computed against the same bar.

---

## 2. Before you touch anything

**Read, in this order:**

1. `GOVERNANCE.md` — the output standard. Claims carry evidence inline; verification means
   running it, not reading a docstring; state what you did **not** check.
2. `CLAUDE.md` §AGENT RULES — the DO NOT list is load-bearing here.
3. `docs/proposed-fixes/system-1/` — **check before "discovering" a bug.** It may be known,
   fixed, or in flight.
4. `task/OPEN.md` — O-16, O-17, O-19, O-20, O-21, O-22 are all adjacent to this work. **O-19
   and O-20 in particular constrain D8 and D6.** Do not re-solve them; do not contradict them.

**Hard constraints:**

- **The hourly signal cron runs the working tree.** An uncommitted, half-finished edit to
  `src/signals/` or `src/queue_producer/` is executing in production within the hour. **Work on
  a branch.** This is not a style preference.
- **Never hand-edit `results/`, `models/`, `model-artifacts/`, `feature-store/`.** If the output
  is wrong, the run is wrong. Editing the file hides the defect and the next run reverts it.
- **Do not add an enforcing gate to the live path as a bug fix.** The FIX-S1-018 shadow-mode
  decision (owner, 2026-08-30) exists precisely to stop that. See D7.
- **`contracts/*.json` are read at runtime by other machines.** Changing one is a cross-system
  change and needs its own notice with a cutover date — not a code commit.
- **`docs/comms/` is append-only in spirit.** A correction is a new file, never an edit.
- Dry-run is the default for anything that promotes or publishes.

**Tooling:**

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate
python -m pytest src -q --ignore=src/layer0/strategies/research/tests   # ~20s
black src/ && mypy src/
```

There is a **standing set of known-red tests** enumerated in `docs/critical/REPO_STATE.md`.
Read it before reporting a red as new, and **distinguish your reds from those** before claiming
tests pass.

---

## 3. Skills and agents to use

**Skills** (`Skill` tool — use the skill, do not reconstruct the procedure):

| Skill | When |
|---|---|
| `close-a-task` | **At the end, mandatory.** The six-point definition of done and the adversarial pass |
| `log-an-issue` | Anything you notice in passing that you will not fix here |
| `write-comms` | Only if D6 changes the wire contract — then a message to Systems 2/3 is required |

**Review agents** — all read-only; they report, they never write. Invoke them at the points
marked, not all at the end:

| Agent | Use it for | At which step |
|---|---|---|
| `devils-advocate` | The mundane explanation. **Required** before you accept any "fixed" claim | S3, S6, S9 |
| `auditor` | Verifies a claim is supported by the evidence offered. **Required** before anything is believed | S10 |
| `forex-strategist` | D7 — is the R:R actually broken, or does the framing misrepresent a legitimate scalp? Market realism, stop placement, spread | S5 |
| `leakage-hunter` | D7 — you will be reading `src/layer0/strategies/`. Mandatory on any change there | S5, S6 |
| `measurement-reviewer` | D7 — if you compare one number to another to justify a decision | S6 |
| `release-guard` | D8 — the publish contract, the four ordered steps, SHA256 round-trip, the two pointer levels | S8 |
| `structure-warden` | Any file you add, move or rename | S10 |
| `comms-liaison` | Reviews any draft message before it goes into `docs/comms/` | only if S4 triggers |

**Do not** invoke agents you were not asked for. Each spawn starts cold and re-derives context.

---

## 4. The work

### D6 — the same `signal_id` published twice, with a different entry price (P0)

**Evidence.** `results/signals/2026-09-02.ndjson`, rows 6 and 7. `signal_id
4af8a6fe-d8f8-5eec-97af-b9e2c793338f`, USD_JPY H1 short, bar `2026-09-02T13:00:00Z`, published
at `14:15:17Z` and again at `17:15:27Z`:

| | first | second |
|---|---|---|
| `proposed_entry` | 158.568 | **158.849** |
| `proposed_sl` / `proposed_tp` | 160.1835 / 155.337 | **unchanged** |
| `score_run_id` | `98953363-…` | `964afac9-…` |
| resulting R:R | 2.00:1 | **2.63:1** |

Both `wire_action: "published"`. Both runs reported `deduped_count: 0`.

**Three causes. Keep them separate — they need different fixes.**

**(a) The idempotency key cannot match a prior publish.**
`src/queue_producer/producer.py:71-73` builds `f"{signal_id}:{score_run_id}"`;
`src/signals/run.py:286` mints `score_run_id = str(uuid.uuid4())` once per run. Same signal on a
later run ⇒ different key ⇒ never suppressed.

**(b) `deduped_count` is structurally always 0 on the configured backend.**
`src/queue_producer/producer.py:243-249` infers dedupe from a `backend.depth()` delta.
`src/common/queue/pubsub.py:36` documents its return value as existing to satisfy "producer's
simplistic idempotency check". The working `seen`-index dedupe lives only in
`src/common/queue/local_durable.py`, and `QUEUE_PROVIDER=pubsub`. **The producer's duplicate
metric has never been able to report a duplicate.** That is measurement blindness, not just a
suppression failure — and reporting a fabricated `0` is worse than reporting `None`. This is
the same class as the status conflation in FIX-S1-016.

**(c) The re-emission itself — this is the actual bug.**
`signal_time_utc` is the **strategy's signal bar**, not the watcher's newly-closed bar
(`src/signals/build.py:429,438`). Any strategy whose latest signal remains the latest re-emits
it every hour until a newer one appears. The entry is recomputed at emission time
(`build.py:356-360`, falling back to the bar close) while stop and target stay on the original
bar — which is exactly why the two messages disagree on entry but agree on levels.

**Fix (c) first.** (a) and (b) are the safety net that failed to catch it. A net that only ever
catches a bug you have already fixed is worth less than it looks — but fix them anyway, because
the next bug is the one you cannot predict.

> **⚠ STOP — owner decision required before you write code for (c).**
> **Is re-affirmation ever wanted?** A strategy holding a view across several bars is not
> obviously wrong to restate. If restatement IS wanted, the fix is not suppression — it is that
> a restatement must recompute stop and target too, and must be marked as a restatement on the
> wire so System 2 does not read it as a new trade. **This is a trading-semantics decision, not
> a code decision. Do not pick one in code.** Put the question to the owner and wait.

**Coordination you must not break:** System 2 has been told (`PROMPT-S2-D5-*`) to dedupe trade
intent on `signal_id` alone and keep `(signal_id, score_run_id)` for ledger rows. Do not ship
anything that breaks that without a superseding message.

**Also true and must stay true:** two ledger rows for this event are **correct**. The ledger
records what happened. Suppressing the second row hides the defect instead of fixing it.

---

### D7 — a 0.06:1 risk/reward signal reached the wire (P1)

**Evidence.** `results/signals/2026-09-01.ndjson`, row 4. `signal_id
b97120fc-25d4-57ad-8f6e-8775c250f2a6`, 2026-09-01T17:15:30Z, EUR_USD H4 short,
`liquidity_grab_fade` (strategy_id 30), `selection_basis: "qualified"`:

```
proposed_entry  1.15856
proposed_sl     1.16286     →  43.0 pips risk
proposed_tp     1.158295    →   2.6 pips reward      R:R = 0.06:1
```

At a typical EUR_USD spread of ~1 pip the net target is ~1.6 pips. **Every other signal that
week is a clean 2:1.** It is also the only row the shadow gate would have passed (`model_score`
0.741 vs `threshold_calibrated` 0.60).

**What is not known.** We read the ledger, not the strategy. Unresolved: strategy defect,
exit-policy misconfiguration, or a legitimate scalp target that the R:R framing misrepresents.
**Establish which before writing any fix.**

**Investigation path:** reproduce `liquidity_grab_fade` on EUR_USD H4 around
`2026-09-01T13:00:00Z`; compare its target derivation against strategies 58 and 36, which
produce clean 2:1. The 2:1 uniformity elsewhere suggests a shared ATR-multiple path that
strategy 30 does not use, or uses differently.

> **⚠ STOP — owner decision required before any live-path guard.**
> **Should System 1 refuse to emit a bad-R:R signal at all?** "Default-safe" points one way;
> "System 1 never knows if it is live" points the other. A hard refusal is a **new live-path
> gate**, and every existing live gate is off or in shadow by owner decision.
> **Do not add an enforcing gate as a bug fix.**
> A softer option: compute the R:R, record it in the ledger, and let System 3 decide. That
> respects "no downstream recomputation" **only if System 1 computes and publishes it** — S3
> must never derive it.

**Traps:**
- `liquidity_grab_fade` is currently the **only gate-qualified strategy emitting**. Changing or
  disqualifying it takes live output from 1 qualified + 8 designated to **0 qualified**. That is
  an owner-visible trading-activity change, not a silent fix.
- Check `INTEGRITY_DISQUALIFIED` and the **FIX-S1-013 precedent** before concluding "the
  backtest looks fine". A strategy whose attribution rows come from a look-ahead backtest looks
  healthy for exactly the wrong reason. Run `leakage-hunter`.

---

### D8 — the ledger has no index object (P2)

**Evidence.** `src/signals/publish_ledger.py:50,161` writes only
`telemetry/signals/<YYYY-MM-DD>/<ts>-<sha8>.ndjson`. No pointer, no index — unlike every other
artifact Systems 2/3 consume, which resolve through a `latest.json`. Each object holds only rows
appended since the previous upload, so reconstructing a day means LISTing the prefix and
concatenating chunks in lexical order. Offsets in `results/state/ledger_publish_state.json`:

```
2026-08-31 → 983      2026-09-01 → 3910      2026-09-02 → 3931
```

**The path scheme itself was correctly communicated** (2026-08-30 §1/§4). This is a missing
convenience that turned out to be load-bearing — **not** an undisclosed gap. Do not write it up
as though we withheld it.

**Approach.** Publish an index — e.g. `telemetry/signals/index.json` — listing available days,
the chunk keys in each, and a checksum per chunk so a consumer can verify completeness.

**Decide first:**
- **An index is mutable and rewritten hourly; the chunks are immutable.** `delete_prefix` is an
  **undelimited string-prefix match** — O-19 already flags that any lifecycle rule must be
  scoped to `telemetry/signals/`, never `telemetry/` or `system1/`. An index inside that prefix
  must not become collateral of a retention sweep.
- **Coordinate with O-19.** Remote retention is *stated* (365d) but **not enforced**, and no GCS
  lifecycle rule exists in this repo. An index listing chunks a lifecycle rule later deletes is
  worse than no index. Decide retention and index together.
- **Ask System 2 whether they already built the LIST path.** The D2/D3 prompts tell them to say
  so. An index that breaks a working consumer is a regression.

**Trap:** `put_object` **refuses to overwrite** — that is why the ledger is chunked at all. An
hourly-rewritten index needs `atomic_pointer_update`. Check what `src/common/storage/` actually
offers before designing the format. Run `release-guard`.

**The index must never become the source of truth.** Chunks are the record; the index is a
convenience. A consumer that can only read via the index has a new single point of failure.

---

## 5. Steps

Tick these in `STATE.md`. Do not skip S1.

| # | Step | Gate |
|---|---|---|
| **S1** | Read §2 and confirm none of D6/D7/D8 is already covered in `docs/proposed-fixes/system-1/`. Create a branch. | Record what you read |
| **S2** | **Reproduce D6 with no writes.** Replay the two USD_JPY rows; confirm (a), (b), (c) independently. → `FINDINGS-D6.md` | `devils-advocate` |
| **S3** | Put the D6 re-affirmation question to the owner. **Wait.** | **Owner decision** |
| **S4** | Implement D6 per the decision: (c) first, then (a), then (b). Tests for each, on **both** `local_durable` and `pubsub`. | If the wire contract changes → `write-comms` + `comms-liaison` |
| **S5** | **Investigate D7 with no writes.** Reproduce strategy 30 at the bar. → `FINDINGS-D7.md` | `forex-strategist`, `leakage-hunter` |
| **S6** | Put the D7 guard question to the owner. **Wait.** | **Owner decision** · `measurement-reviewer`, `devils-advocate` |
| **S7** | Implement D7 per the decision. | `leakage-hunter` if `src/layer0/` changed |
| **S8** | D8: settle the O-19 retention question and System 2's LIST answer, then design and implement the index. Dry-run first. | `release-guard` |
| **S9** | Full suite + `black` + `mypy`. Distinguish your reds from the standing reds in `REPO_STATE.md`. | `devils-advocate` |
| **S10** | `close-a-task` skill. Update `OPEN.md` (O-23/24/25), `REPO_STATE.md` if state changed, and this folder's `DELIVERABLE.md`. | `auditor`, `structure-warden` |

**S3, S6 and S8 are blocking on humans.** Do everything that does not depend on the answer
first, then stop and ask. Do not guess and proceed.

---

## 6. Acceptance criteria

**D6**
- [ ] Replaying both USD_JPY messages produces **one** wire message, not two.
- [ ] The retained message carries entry `158.568` — or, if the owner chose restatement, the
      second message carries **recomputed** stop and target and is **marked as a restatement**.
- [ ] Replaying both through the ledger still writes **two** rows. The audit trail is intact.
- [ ] The wire idempotency key is a pure function of the signal, not of the run.
- [ ] `deduped_count` reports a real value on the Pub/Sub backend, or reports `None` — **never a
      fabricated `0`**.
- [ ] A test exercises the duplicate case on **both** queue backends and fails without the fix.
- [ ] Nothing breaks the guidance in `PROMPT-S2-D5-*`, or a superseding message was sent.

**D7**
- [ ] `FINDINGS-D7.md` states the cause: strategy defect, config error, or correct-but-misframed.
      "Unclear" is an acceptable answer **only** with the evidence that made it unclear.
- [ ] If a guard shipped, it is **not** an enforcing live gate unless the owner explicitly chose
      one, in writing.
- [ ] If R:R is now published, System 1 computes it — System 3 is not asked to derive it.
- [ ] Any change to strategy 30 states its effect on live output (currently 1 qualified cell).

**D8**
- [ ] A consumer can enumerate every ledger day and chunk **without** a prefix LIST.
- [ ] The index carries a per-chunk checksum, and completeness is verifiable against it.
- [ ] The index is written with a primitive that permits overwrite; `put_object` was not abused.
- [ ] Any retention rule is scoped to `telemetry/signals/` and **cannot** reach `telemetry/` or
      `system1/`. Verified, not assumed.
- [ ] The chunks remain the source of truth; the index is provably optional.
- [ ] System 2 confirmed the change does not break a LIST path they already built.

**All three**
- [ ] Full suite run, output in the record, your reds distinguished from the standing reds.
- [ ] `black` and `mypy` green.
- [ ] An adversarial pass happened and what it found is recorded — **including "nothing"**.
- [ ] `task/OPEN.md` reflects the new state of O-23, O-24, O-25.
- [ ] You have stated what you did **not** check.

---

## 7. Result overview — what lands where

| Artifact | Path |
|---|---|
| D6 reproduction and root cause | `task/2026-September-week1/signal-emission-defects/FINDINGS-D6.md` |
| D7 investigation and verdict | `task/2026-September-week1/signal-emission-defects/FINDINGS-D7.md` |
| Closing summary — what shipped, what did not, what is still open | `.../DELIVERABLE.md` |
| Progress log, ticked per step | `.../STATE.md` (already exists — update it, do not replace) |
| Code | `src/signals/`, `src/queue_producer/`, `src/common/queue/`, `src/common/storage/` |
| Tests | beside the module, in its `tests/` folder |
| Register | `task/OPEN.md` — O-23, O-24, O-25 **updated in place** |
| A message to Systems 2/3, **if and only if** the wire contract changed | `docs/comms/to_system2/TO-SYSTEM2-3-<date>-<slug>.md` via the `write-comms` skill |

**Do not** create a new open-items list, put anything at the repo root, or move a finished week
folder. `STRUCTURE.md` is the map.

**If you finish fewer than three:** say so plainly, in `DELIVERABLE.md`, with what blocked each.
Fewer than six points of done means in flight. Saying so is not a failure; claiming six when you
have four is.
