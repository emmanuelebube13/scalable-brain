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
| O-1 | **Install the outcomes cron.** `shell/cron_persist_outcomes.sh` is written and verified, but **not in `crontab -l`**. Until installed, `fact_trade_outcomes` has no scheduled writer and will go stale again — it is green today only because it was run by hand on 2026-08-29. | FIX-S1-017 §1 | owner |
| O-2 | **Re-vet and republish the map on fresh evidence.** The live map (`generated_at_utc 2026-08-24T10:20:53Z`, `qualification_run_id 7fde532c…`) was vetted on trades stopping 2026-08-14. Owner elected to leave it live and re-vet rather than withdraw. The table is now current; this can proceed. Must land before O-5. | FIX-S1-017 §5 | owner |

## Correctness

| # | Item | Evidence | Owner |
|---|---|---|---|
| O-3 | **12 of 67 strategies fail to instantiate.** 9 × `*_RA` import `src.regime_aware`, **removed on purpose after the R3 trial concluded** (see O-9) — stale `dim_strategy` rows to deactivate, not code to restore. 3 × `Range_Bollinger_*` are active in the registry but absent from `get_all_strategies()`. | `results/state/outcomes_writer_state.json` → `failed_instantiate` | owner |
| O-4 | **17,583 orphaned rows** for strategy_ids 7/8/9 that no rebuild reproduces. They still feed attribution and vetting — the FIX-S1-013 shape by a different route. Removable with `python -m src.outcomes.persist_all --reconcile` (destructive, owner-gated). None are in the live map today; that is luck, not design. | FIX-S1-017 §3 | owner |
| O-12 | **T6 ATR case-mismatch** — `engine_adapter` writes `df["atr"]`, `StrategyBase` reads `df["ATR"]`, so T6 stops are warmup-dependent. No FIX doc. Research verdicts only, not the live path. | carried from the previous register | — |
| O-13 | **`layer2_config_adapter` emits un-runnable T-SQL.** Long-standing, unchanged. | carried from the previous register | — |

## Scheduled

| # | Item | Evidence | Owner |
|---|---|---|---|
| O-5 | **Retrain hold expires 2026-09-15.** It never gated the outcomes writer and did not cause the staleness. On expiry the retrain republishes a map — that republish must land on fresh evidence, so O-1 and O-2 come first. Either the underlying reason is resolved or the hold is renewed with a fresh one; silent renewal is an open issue in disguise. | `results/state/cron_holds.json` | owner |
| O-6 | **Re-snapshot the crontab backup.** `results/state/crontab.backup-20260802.txt` lists 3 jobs; `crontab -l` has 5. That drift is what left the freshness model assuming a Saturday-only ingest. | `crontab -l` | owner |

## Announce

| # | Item | Evidence | Owner |
|---|---|---|---|
| O-7 | **Tell System 2/3 about the additive contract fields.** `data_through_utc`, `evidence_age_days`, `outcomes_written_at_utc` now appear on the regime map, weights, and strategy-stats documents. Additive and optional, so nothing breaks — but `contracts/README.md` requires the change be agreed and documented in `docs/comms/`. Message is drafted and unsent. | `docs/comms/to_system2/TO-SYSTEM2-3-2026-08-29-evidence-age-fields.md` | owner |
| O-8 | **Note to Computer 2 on the M2 answer.** Deferred by owner decision; they were holding their pipeline pending this exact decision and the answer now exists. Still unsent. | carried from the previous register | owner |

## Deferred by decision

| # | Item | Evidence | Owner |
|---|---|---|---|
| O-9 | **R3 regime-aware trial — experiment complete, decision open.** Framework works (equivalence test passes); the result does not support regime conditioning as an edge — the winning arm was pair selection, and every profitable cell had a PF confidence interval straddling 1.0. The durable output is `docs/design/STRATEGY_EXPERIMENT_STANDARD.md`. `src/regime_aware/` has since been removed, which is what orphaned the 9 `*_RA` registry rows in O-3. Decide: adopt the standard / port more strategies / consider it closed. | `task/2026-August-week2/deliverables/T3-regime-aware/README.md` | owner |
| O-10 | **v2 promotion gap is undocumented.** Decided NOT to build the promotion path (correctly — don't build the door before anyone comes through it), but the gap itself was never written down, so it stays invisible until someone hits it. | carried from the previous register | owner |
| O-11 | **Repo cleanup** — `task/BACKLOG-repo-structure-and-cleanup.md`. Parked deliberately. | carried from the previous register | owner |
| O-14 | **Finding A — weight starvation** at 8e-8. Genuinely premature: cannot matter until M2. | carried from the previous register | — |
