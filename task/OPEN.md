# OPEN — the open-items register

**Update this file in place. Do not start a competing list.**
Each item names its evidence. Close an item by deleting its row and recording the outcome
where the evidence lives (a FIX doc, a worklog entry, a comms message).

---

**Rebuilt 2026-08-29.** The previous revision had been truncated to 0 bytes in the working
tree, so nothing was tracking these items. Its committed content was a 2026-08-14 session
log carrying an open-items section — recoverable with `git show HEAD:task/OPEN.md`, and its
narrative substance already lives in `docs/worklog/2026-08-14.md`. The still-open items from
its §3 are carried forward below (O-8 … O-13); the items it marked DONE are dropped.

> One claim from that file was **wrong and had propagated into `docs/critical/REPO_STATE.md`**:
> that `persist_all` is "`DELETE`-then-rebuild with no transaction, so snapshot first" with a
> "default 5 that silently discards half the history". It is `INSERT … ON CONFLICT DO UPDATE`
> — it never deletes — and the default is `--lookback-years 10`. Both corrected 2026-08-29.
> The belief that the writer was dangerous to run is part of why it was only ever run by hand.

---

## Blocking

| # | Item | Evidence | Owner |
|---|---|---|---|
| O-2 | **Re-vet and republish the map on fresh evidence.** The live map (`generated_at_utc 2026-08-24T10:20:53Z`, `qualification_run_id 7fde532c…`) was vetted on trades stopping 2026-08-14. Owner elected to leave it live and re-vet rather than withdraw. The table is now current; this can proceed. Must land before O-5. Use the `run-vetting` skill. | FIX-S1-017 §5 | owner |
| O-15 | **Confirm the first unattended cron run.** Installed 2026-08-29; first firing is Tue 2026-09-01 02:00 UTC (Sun/Mon are not in `2-6`). Check `logs/cron_persist_outcomes.log` and that `last_healthy_run_at` in the writer state advances on its own. Every run so far has been hand-started. | `crontab -l`; FIX-S1-017 §1 | owner |

## Correctness

| # | Item | Evidence | Owner |
|---|---|---|---|
| O-3 | **12 of 67 strategies fail to instantiate.** 9 × `*_RA` import `src.regime_aware`, **removed on purpose after the R3 trial concluded** (see O-9) — stale `dim_strategy` rows to deactivate, not code to restore. 3 × `Range_Bollinger_*` are active in the registry but absent from `get_all_strategies()`. | `results/state/outcomes_writer_state.json` → `failed_instantiate` | owner |
| O-4 | **17,583 orphaned rows** for strategy_ids 7/8/9 that no rebuild reproduces. They still feed attribution and vetting — the FIX-S1-013 shape by a different route. Removable with `python -m src.outcomes.persist_all --reconcile` (destructive, owner-gated). None are in the live map today; that is luck, not design. | FIX-S1-017 §3 | owner |
| O-16 | **The gatekeeper applies no threshold at inference — the live gate is inert.** `Scorer.score()` returns only `{status, score}` and never loads the manifest; `run.py` stamped a hardcoded `0.5`, below every calibrated cutoff (0.60–0.80), and that placeholder goes on the wire as `threshold_applied`. No below-threshold refusal exists, so the runtime approval rate Systems 2/3 asked for is **undefined, not zero**. Compounded: `MISSING_FEATURE` is universal, so nothing scores live at all. The Gate-1 ledger now records `threshold_calibrated` beside `threshold_applied` on every row as standing evidence. | `docs/proposed-fixes/system-1/FIX-S1-018-*.md`; `results/signals/*.ndjson` | owner |
| O-17 | **The live scorer runs an unpublished champion.** `Scorer` loads the `models/` directory, not a pointer, so `champion_model.pkl` (`23b6d4ca…`, written 2026-08-24T01:30Z, never published) is not the artifact the wire claims — `bundle_id` names `gk-d614163c` (`8845b442…`). The 2026-08-24T10:26 retrain did not promote (`oos_uplift_ok` failed), so this is drift, not a promotion. The ledger records `gatekeeper_model_sha256` beside `bundle_id` so it is now visible per signal. | `models/champion_manifest.json` vs `models/gatekeeper/latest.json`; FIX-S1-018 §Related | owner |
| O-20 | **The ledger does not record what System 1 decided not to BUILD.** `build_signals` discards candidates at ~12 points before the ledger sees them — no structural regime, no stop declared, no take-profit, **no ATR available**, undecodable direction, plus a bare `except` per (bar × strategy). `signal_id` is minted at `build.py:429`, after all of them, so none leave a row. The no-ATR path is the one `build.py:186-191` records as having once dropped 100% of signals silently, and it is still unledgered. Closing it means minting the id earlier in `build_signals`. **Until then, absence of a ledger row is not evidence a candidate never existed.** Found by the 2026-08-30 audit; scope of the ledger is now stated honestly in its docstring. | `src/signals/ledger.py` docstring; `src/signals/build.py:241-477` | owner |
| O-21 | **Ledger rows can outlive their counters on a mid-run crash.** `run.py` writes ledger rows per granularity as it goes, but `record_emitter_state` is called once at the end with no `try/finally`. If `get_new_closed_bars("H4")` raises after H1 wrote rows, the process dies and no counter ever sees them. Also unreconciled by design: a failed ledger append still increments the tally (owner decision — emission is never blocked), so row count and counters diverge in opposite directions for different reasons. Both are detectable by reconciling `results/signals/*.ndjson` against `signal_emitter_state.json`; neither is currently alarmed. | 2026-08-30 audit, claims 1c/2a/2b | — |
| O-22 | **Publish `dlq_count` into `s1_health.json` — promised in a sent message.** Under Pub/Sub `dead_letter()` publishes nothing to `scored_signal_dlq`; it increments an in-process counter and logs one ERROR line locally (`src/common/queue/pubsub.py:43-46`). So Systems 2/3 currently **cannot** tell a lost wire message from a dead-letter, and `TO-SYSTEM2-3-2026-08-30-*.md` §5 tells them so and commits us to fixing it. Until then they have been asked not to build automated wire-drop alerting. A commitment in a frozen message; closing it is not optional. | the sent message §5; `src/common/queue/pubsub.py:43-46` | owner |
| O-12 | **T6 ATR case-mismatch** — `engine_adapter` writes `df["atr"]`, `StrategyBase` reads `df["ATR"]`, so T6 stops are warmup-dependent. No FIX doc. Research verdicts only, not the live path. | carried from the previous register | — |
| O-13 | **`layer2_config_adapter` emits un-runnable T-SQL.** Long-standing, unchanged. | carried from the previous register | — |

## Scheduled

| # | Item | Evidence | Owner |
|---|---|---|---|
| O-19 | **`telemetry/signals/` is written hourly with no ENFORCED retention.** GOVERNANCE.md §1.4 requires a stated retention for anything on a cadence. The local side is stated and enforced (90 days, `publish_ledger --prune`); the remote side is stated only — `REMOTE_RETENTION_DAYS = 365`, `REMOTE_RETENTION_ENFORCED = False`. No GCS lifecycle rule exists anywhere in this repo and `system1-rw` is storage-scoped, so it may lack the bucket-admin right to set one. Sharpened by the local prune: from day 91 the unbounded remote is the sole archive of record. **Scope any lifecycle rule to `telemetry/signals/`, never `telemetry/` or `system1/`** — `delete_prefix` is an undelimited prefix match and the wider prefixes hold `s1_health.json` and the model bundles. | `src/signals/publish_ledger.py` REMOTE_RETENTION_*; structure-warden pass 2026-08-30 | owner |
| O-5 | **Retrain hold expires 2026-09-15.** It never gated the outcomes writer and did not cause the staleness. On expiry the retrain republishes a map — that republish must land on fresh evidence, so O-2 comes first. Either the underlying reason is resolved or the hold is renewed with a fresh one; silent renewal is an open issue in disguise. | `results/state/cron_holds.json` | owner |
| ~~O-6~~ | ~~Re-snapshot the crontab backup.~~ **DONE 2026-08-29** — `results/state/crontab.backup-20260829.txt`, taken before installing the outcomes job. The 2026-08-02 backup listed 3 jobs against 5 installed; that drift is what left the freshness model assuming a Saturday-only ingest. **Re-snapshot whenever the crontab changes.** | `results/state/crontab.backup-20260829.txt` | — |

## Announce

| # | Item | Evidence | Owner |
|---|---|---|---|
| O-7 | **Tell System 2/3 about the additive contract fields.** `data_through_utc`, `evidence_age_days`, `outcomes_written_at_utc` now appear on the regime map, weights, and strategy-stats documents. Additive and optional, so nothing breaks — but `contracts/README.md` requires the change be agreed and documented in `docs/comms/`. Message is drafted and unsent. | `docs/comms/to_system2/TO-SYSTEM2-3-2026-08-29-evidence-age-fields.md` | owner |
| O-8 | **Note to Computer 2 on the M2 answer.** Deferred by owner decision; they were holding their pipeline pending this exact decision and the answer now exists. Still unsent. | carried from the previous register | owner |
| ~~O-18~~ | ~~Reply to the Signal-Telemetry RFC.~~ **SENT 2026-08-30** — `docs/comms/to_system2/TO-SYSTEM2-3-2026-08-30-signal-ledger-and-rfc-corrections.md`, seven corrections. RFC filed as received at `docs/comms/replies/S2-3-RFC-2026-08-30-decoupled-signal-telemetry.md`. A `comms-liaison` pass before send caught two false claims (designated count 11→12; a `scored-signals.heartbeat` 404 fixed on 2026-08-23) that would have frozen permanently. **Follow-up owed:** publish `dlq_count` into `s1_health.json` — §5 tells them wire-drop detection is impossible without it. | the sent message | owner |

## Deferred by decision

| # | Item | Evidence | Owner |
|---|---|---|---|
| O-9 | **R3 regime-aware trial — experiment complete, decision open.** Framework works (equivalence test passes); the result does not support regime conditioning as an edge — the winning arm was pair selection, and every profitable cell had a PF confidence interval straddling 1.0. The durable output is `docs/design/STRATEGY_EXPERIMENT_STANDARD.md`. `src/regime_aware/` has since been removed, which is what orphaned the 9 `*_RA` registry rows in O-3. Decide: adopt the standard / port more strategies / consider it closed. | `task/2026-August-week2/deliverables/T3-regime-aware/README.md` | owner |
| O-10 | **v2 promotion gap is undocumented.** Decided NOT to build the promotion path (correctly — don't build the door before anyone comes through it), but the gap itself was never written down, so it stays invisible until someone hits it. | carried from the previous register | owner |
| O-11 | **Repo cleanup** — `task/BACKLOG-repo-structure-and-cleanup.md`. Parked deliberately. | carried from the previous register | owner |
| O-14 | **Finding A — weight starvation** at 8e-8. Genuinely premature: cannot matter until M2. | carried from the previous register | — |
