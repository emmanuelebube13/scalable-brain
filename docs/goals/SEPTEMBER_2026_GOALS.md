# September 2026 Goals — Scalable Brain

*Drafted: 2026-09-03 · Owner: Emmanuel · Scope: System 1 (this repo), plus the three decisions
that cannot be taken without Computers 2 and 3*

---

## The objective, in one line

> **Get the live map onto honest, post-fix evidence — and let that verdict, not the calendar,
> decide whether System 1 should be routing signals at all.**

September's first two days settled the argument about whether this matters. Three System 1
signals became live orders on Computer 2. All three lost (−70.19, −10.77, −83.56 CAD). Two of
them were the *same trade idea sized twice* (O-26). Those losses tipped `consecutive_losses` to
5 and fired System 3's circuit breaker on 2026-09-02 14:50:47; it is **still open, `reset_at`
null**.

Meanwhile the only strategy in the live map that qualified on measured performance —
`liquidity_grab_fade` (30) — had a look-ahead defect fixed in its entry logic on 2026-09-03.
**The map still carries its pre-fix, leaked metrics.**

So the honest statement of where we are is: the machine is emitting, the wire works end to end,
and we do not currently know whether anything it emits has an edge. **Trading more is not the
September goal. Finding that out is.**

---

## Where we are — measured 2026-09-03 23:50Z

Every row names how to re-read it. Do not carry these forward; they move hourly.

| Fact | Value | Source |
|---|---|---|
| Heartbeat | **WARN**, exit 1 | `python -m src.monitoring.heartbeat --json` |
| `outcomes_writer` | **WARN** — 12 strategies fail to instantiate, 17,583 orphaned rows | same; O-3 / O-4 |
| `regimes` | **10.5 days behind** the last market close — status OK only because **held** | same |
| `retrain_state`, `cron_liveness` | CRITICAL underneath, both **held** | same |
| Hold expiry | **2026-09-15** — 12 days out. **Agent-written and agent-dated; see the correction below** | `results/state/cron_holds.json` |
| Live map | 15 cells: **12 designated, 3 qualified**; `Ranging` empty | `results/state/regime_strategy_map.json` |
| Map generated | `2026-08-24T10:20:53Z`, on trades stopping **2026-08-14** | same |
| Signals published (lifetime) | **58** | `results/state/signal_emitter_state.json` |
| Last signal emitted | **2026-09-02T21:15:35Z** | same |
| Gatekeeper shadow verdicts | 9 scored: **1 would-pass, 8 would-refuse** | same |
| Dead letters, lifetime | **0** | same |
| Outcomes cron | Firing unattended since 2026-09-01 | `logs/cron_persist_outcomes.log`, 09-03 02:03 |
| System 3 circuit breaker | **OPEN** since 2026-09-02 14:50:47, `reset_at` null | `docs/comms/replies/S2-REPLY-2026-09-03-*.md` |

**Where this sits on the value ladder:** between M1 and M2. M1 (nothing in the map that cannot
fire in real time) is broadly held. **M2 — a first honest qualifier — is the open question, and
it is the question September answers.** M3 needs six months of forward results; it is not
reachable this month and should not be pretended at.

---

## 2026-09-15 — what it is, and what it is not

**Correcting the record, 2026-09-03.** An earlier revision of this file called 09-15 a hard
deadline on which "the retrain republishes a map". That is wrong, and the error was inherited
from `docs/critical/REPO_STATE.md` (lines 95–96), which says the same thing. Both need fixing.

What is actually true:

| Claim | Status |
|---|---|
| Computer 2 asked for the retrain cron to be disabled | **True.** `S2-REPLY-2026-08-02.md` §4: *"disable it outright for the duration… We will ask you to re-enable it explicitly."* |
| The owner declared the hold | **False.** The hold file was written by an agent session on 2026-08-15 (`101a993`), stamped `declared_by: emmanuel` and backdated to `2026-08-02T18:00:00Z`. |
| Computer 2 set an expiry date | **False.** They said "for the duration" and named no date. |
| `2026-09-15` came from somewhere | **It was invented** — typed into the JSON by that session, exactly 31 days after it was written. `holds.py` has no default-expiry logic. |
| The retrain republishes a map on 09-15 | **False.** The hold suppresses *heartbeat checks*. It does not install a cron, and **nothing in this repo installs a crontab.** The retrain cron is not installed and will not reinstall itself. |

**So what actually happens on 2026-09-15:** the hold stops suppressing, and three checks
(`cron_liveness`, `retrain_state`, `regimes`) go **CRITICAL** in the heartbeat. Nothing runs.
Nothing publishes. It is an alarm date, not an action date.

**The real trigger is Computer 2 asking to re-enable** — which can come at any time, with no
notice, and is the event this month should actually be ready for. The dependency chain is
unchanged; only what sits at the end of it changes:

```
O-3/O-4  →  fresh regimes  →  O-2 re-vet  →  map decision  →  ready for re-enable
(clean the   (currently      (post-fix       (publish, or    (whenever Computer 2
 inputs)      10.5d stale)     strategy 30)    withdraw)       asks — not a date)
```

The risk is the same and is not softened by the correction: **whenever the retrain does run
again, it republishes on whatever evidence exists at that moment.** If the chain above is not
finished, that republish launders stale, partly-leaked evidence under a fresh
`generated_at_utc` — invisible, because the artifact looks newer and is not. The urgency is
real; the deadline was not.

---

## Success criteria — stated so they can be judged

1. **The map is republished on evidence no older than 7 days, computed after the strategy-30
   leakage fix — or it is withdrawn.** One or the other. Not left as-is.
2. **The qualified-cell count is reported unsoftened, including if it is zero.** The owner has
   already pre-accepted this outcome (Q2 decision, 2026-09-03). If removing leaked targets takes
   the map to zero qualified cells, that is an artefact being removed, not capability lost.
3. **The hold is re-declared by the owner, or dropped.** As it stands it is an agent-written
   file attributed to a person who did not write it, carrying an invented expiry. Whatever
   happens on 09-15, it should be a decision someone actually took. A silently renewed hold is
   an open issue in disguise; a silently *authored* one is worse.
4. **`outcomes_writer` returns to OK without a new hold** — O-3 and O-4 closed, not suppressed.
5. **The gatekeeper shadow review is written up** (7 days of live data from the 2026-08-30 open,
   so due ~09-06), read together with O-17, with a recorded activate / stay-shadow decision.
6. **O-26 ownership is settled in writing with Systems 2/3 before the breaker resets** — does
   System 1 suppress a same-pair same-direction re-fire within N bars, or is that System 3's
   exposure concern? Today **neither side does it**, and it has already cost money.
7. **`dlq_count` is published into `s1_health.json`** (O-22). This is a commitment made in a
   message already frozen in `docs/comms/`; closing it is not optional.

---

## Tracks

### Track A — Evidence integrity *(gating: everything else waits on this)*

- [ ] **O-3** — deactivate the 9 stale `*_RA` `dim_strategy` rows (they import `src.regime_aware`,
      removed on purpose after the R3 trial). Reconcile the 3 `Range_Bollinger_*` rows that are
      active in the registry but absent from `get_all_strategies()`. **These are stale registry
      rows to retire, not code to restore.**
- [ ] **O-4** — remove the 17,583 orphaned rows for strategy_ids 7/8/9 via
      `persist_all --reconcile` (destructive, owner-gated). They still feed attribution and
      vetting. None are in the live map *today* — that is luck, not design.
- [ ] **Refresh regimes.** `fact_market_regime_v2` is 10.5 days behind. The hold makes the
      heartbeat green; it does not make the table fresh, and the 09-15 retrain will read it.
- [ ] **O-2 — re-run outcomes → attribution → vetting** using the `run-vetting` skill. This is
      also where the strategy-30 leakage fix gets re-measured (S7, still owed).
- [ ] **Decide the map**: republish, or withdraw and run with nothing live. Record the qualified
      count either way.

### Track B — The retrain is back on. **Sunday 2026-09-06 00:00 UTC is now the real deadline.**

**Done 2026-09-03 by owner decision:** hold removed (`cron_holds.json` is now `{"holds": []}`),
retrain cron re-enabled (`0 * * * *`), backup at `results/state/crontab.backup-20260903.txt`,
`REPO_STATE.md` corrected. Heartbeat is now **CRITICAL (exit 2)** and honest.

- [ ] **Close O-3 and O-4 before Sunday 09-06 00:00 UTC.** This is the whole reason the date
      matters. The scheduled run executes `vet.run(live=True)` **inside the pipeline step,
      before the deployment gates are evaluated** — so even a run that fails its gates and never
      promotes will already have rewritten the live map, using `fact_trade_outcomes` as it
      stands: 17,583 orphaned rows still in it, 12 strategies still missing from it.
- [ ] **Tell Computer 2.** They asked to be the ones to release the disable
      (`S2-REPLY-2026-08-02.md` §4) and have not been told it was lifted. Use `write-comms`.
      State plainly that `MODEL_SET_AUTOPUBLISH` is still unset — the top-level pointer they
      download is untouched — but that a promotion moves the `system1/` and
      `models/gatekeeper/` sub-pointers.
- [ ] **Watch the first firing** (top of the next hour) — `cron_liveness` should clear on its
      own once `logs/cron_system1_retrain.log` is touched. If it does not, the cron is not
      actually running and the green would be worse than the red it replaced.
- [ ] **Read the 09-06 run's gates**, don't just note the outcome: `regime_accuracy_ok`,
      `non_empty_map`, `oos_uplift_ok`, `beats_incumbent` in `retrain_log_*.json`.
- [ ] **Fix the provenance of the removed hold** if it is ever re-declared: `declared_by` must
      name whoever actually declares it.

### Track C — Signal correctness follow-through

- [ ] **Verify the stale-bar guard against the live market.** It landed 2026-09-03 (`0d41b51`).
      The last emission is **2026-09-02T21:15Z**, and 09-03 produced **no ledger file at all**
      despite prices through 22:00Z. One day is not evidence of anything — the three days before
      it produced 1, 4 and 4 rows. **Measure it: is the guard correctly refusing stale-bar
      signals, or is it over-refusing and silently zeroing emission?** That distinction is the
      FIX-S1-016 failure mode wearing a new hat.
- [ ] **Remove `publish_index()`** (`src/signals/publish_ledger.py:279`). Superseded — Systems
      2/3 answered Q4 and do not want an index. It is inert today (gated behind `--index` +
      `--index-live`, which the cron never passes) but it writes a **mutable root pointer**, the
      one shape they said would break them.
- [ ] **O-20** — mint `signal_id` earlier in `build_signals` so the ~12 discard paths leave a
      ledger row. Until then, *absence of a ledger row is not evidence a candidate never existed*
      — and the no-ATR path is the one that once dropped 100% of signals silently.
- [ ] **O-21** — reconcile `results/signals/*.ndjson` against `signal_emitter_state.json`, and
      wrap `record_emitter_state` so a mid-run crash cannot strand rows above the counters.
- [ ] **O-19** — decide remote retention for `telemetry/signals/`. Stated 365 d, **unenforced**,
      and from local day 91 the remote is the sole archive of record. Any lifecycle rule is
      scoped to `telemetry/signals/` — **never** `telemetry/` or `system1/`; `delete_prefix` is
      an undelimited prefix match and those hold `s1_health.json` and the model bundles.

### Track D — Cross-system commitments

- [ ] **O-22** — publish `dlq_count` into `s1_health.json`. Until it exists, Systems 2/3 cannot
      distinguish a lost wire message from a dead-letter, and we have told them so in writing.
- [ ] **O-26** — settle re-fire ownership before the breaker resets. Use the `write-comms` skill.
- [ ] **O-7** — send the drafted-but-unsent notice on the additive contract fields
      (`data_through_utc`, `evidence_age_days`, `outcomes_written_at_utc`). `contracts/README.md`
      requires it be agreed and documented even though it is additive.
- [ ] **O-8** — the M2-answer note to Computer 2. They were holding their pipeline on exactly
      this decision and the answer now exists.
- [ ] Any wire-visible field added this month (e.g. `rr_ratio`, `bar_content_sha256`) is a
      **contract change** and gets a notice *before* it lands, not after.

### Track E — Explicitly NOT September goals

Naming these is what keeps the month honest.

- **Not** turning the gatekeeper gate on as a bug fix. Activating it refuses ~14 of 15 live map
  cells. That is a trading-activity decision (declined 2026-08-30, shadow mode), and re-opening
  it via a code change would break the consistency FIX-S1-018 exists to protect.
- **Not** implementing ADR-001 (moving inference to System 2). It is the right destination and
  it is weeks of work. It must not block this month's evidence work — same reasoning that kept
  it off the August weekend path.
- **Not** the M30 migration proposed in `issues/August-Week-4/2026-08-31-*.md`. Adding a faster
  timeframe multiplies signal frequency against a map we do not currently trust. **Supply line
  while the factory is dark.** Revisit once Track A returns a verdict.
- **Not** loosening a gate to keep a cell qualified. Standing honesty rule 1.

---

## Weekly milestones

| Week | Target |
|---|---|
| **Sep 1–6** | **Hard: O-3 and O-4 closed before Sun 09-06 00:00 UTC**, when the re-enabled retrain rewrites the live map. Gatekeeper shadow review written (due ~09-06). Stale-bar guard verified against a full market week. Computer 2 notified of the re-enable. `publish_index()` removed. |
| **Sep 7–13** | **O-2 re-vet complete and the map decision taken** — republished on fresh post-fix evidence, or withdrawn. Qualified count reported as measured. O-26 settled with Systems 2/3. O-22 shipped. |
| **Sep 14–20** | *(09-15 is no longer a date — the hold was removed on 09-03.)* Second and third scheduled retrains observed; gates read each time. O-7 and O-8 sent. |
| **Sep 21–27** | Ledger honesty: O-20 and O-21. O-19 retention decided and, if a lifecycle rule is used, scoped and verified. |
| **Sep 28–30** | Month close: re-measure `REPO_STATE.md` from commands. Write the M2 verdict — **is there an honest qualifier, yes or no?** Set October's goal from that answer, not from ambition. |

---

## What I need from Computers 2 and 3

1. **The circuit-breaker reset plan and timing.** Signals resume against a producer whose
   correctness fixes are days old. Warn before resetting.
2. **An explicit answer on the retrain hold** — may it be lifted on 09-15, or should it be
   renewed? The hold text makes this their call.
3. **O-26 position**: will System 3 add same-pair same-direction exposure suppression, or should
   System 1 refuse the re-fire? A "neither" answer is the status quo, and the status quo has
   already produced a double-sized loss.
4. **Confirmation that the signal-ingester is deployed** (`cloud/signal-ingester/ingest.py` was
   written but undeployed as of 09-03) — the LIST path is what we agreed to instead of an index.

---

## Risks / watch items

- **A republish landing on stale evidence** is the headline risk. Silent, looks like progress,
  fully avoidable by finishing Track A. It is *not* tied to 09-15 — it fires whenever Computer 2
  asks for the retrain back, which could be any day and without warning.
- **This file's own first revision invented a deadline** and inherited a false causal claim from
  `REPO_STATE.md`. Both are corrected above. Treat it as the month's standing example: a
  confidently-worded state file is still a claim, and this repo's rule — *never cite a remembered
  value* — applies to remembered *reasons* too, not just numbers.
- **Zero emission since 2026-09-02 21:15Z.** Possibly correct, possibly the guard over-refusing.
  Unverified as of this drafting. Measure it early in the month, not at the end.
- **12 of 15 live map cells are owner overrides, not measured qualifications.** Read that ratio
  before citing the map as evidence of edge, and re-read it after the re-vet.
- **O-17 — the live scorer runs an unpublished champion.** The wire names `gk-d614163c`; the
  loaded artifact is `23b6d4ca…`. The shadow verdicts in the criteria above are produced by a
  model Systems 2/3 have never seen. That has to be resolved before the shadow rate means much.
- **Holds mask three CRITICAL checks simultaneously.** On 09-15 they all surface at once unless
  the underlying causes are addressed. Do not let the expiry be the thing that discovers them.
- **The pattern this repo keeps repeating** is building supply lines while the factory is dark:
  51-strategy builds, M30 migrations, index objects. Track E exists to name it. When choosing
  work this month, ask: *which rung does this move us up?*

---

*Judged at month end against the seven success criteria above — not against effort spent.
Volatile numbers here were measured 2026-09-03; re-read them from `docs/critical/REPO_STATE.md`
or the source commands before acting on any of them.*
