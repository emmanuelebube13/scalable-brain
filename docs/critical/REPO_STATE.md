# REPO STATE — the volatile facts

**Read at:** 2026-08-29 20:45Z · **Refresh by re-running the commands below, not by editing prose.**

> **Measured while another session was editing `src/monitoring/`.** Source-file mtimes moved
> between readings taken minutes apart and the test totals moved with them. Everything below
> is the last quiescent reading. If a decision depends on one, re-run its command.

This file exists because `CLAUDE.md` was carrying it. Instructions and state have different
lifetimes: a rule is true until it is changed, a state fact is stale within hours. Mixing
them is why `CLAUDE.md` needed a "last updated" stamp and a supersession note to be readable.

**Everything here is a snapshot.** If a decision depends on any of it, re-read the source.
Every row names its source command or file.

---

## How to refresh

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate

python -m src.monitoring.heartbeat --json          # freshness, all checks
python -m src.monitoring.model_card --verify       # what is actually live on GCS
cat results/state/signal_emitter_state.json        # emission
cat results/state/outcomes_writer_state.json       # the fact_trade_outcomes writer
cat results/state/cron_holds.json                  # declared holds
crontab -l                                         # the INSTALLED schedule, not the backup
python -m pytest src -q --ignore=src/layer0/strategies/research/tests
```

---

## Heartbeat — `python -m src.monitoring.heartbeat --json`

Evaluated `2026-08-29T20:49:51Z` · **overall `WARN`, exit 1**

Earlier the same day this was `CRITICAL` (exit 2): `outcomes` was 14.1 days behind, having
crossed its critical threshold at `2026-08-29T00:00Z`. The writer has since been run and
the table is current. See FIX-S1-017.

| Check | Status | Held | Detail |
|---|---|---|---|
| `prices` | OK | — | through 2026-08-28 20:00Z, the last market close |
| `outcomes` | OK | — | through 2026-08-28 19:00Z, 1.0 h inside the 168 h grace; written 2026-08-29 20:45Z |
| `outcomes_writer` | **WARN** | — | **12 strategies failed to instantiate; 17,583 orphaned rows for 3 strategies the run did not produce** |
| `regimes` | OK | **held** | underlying **CRITICAL**: 4.5 days behind the last market close |
| `champion_bundle` | OK | — | `2026-08-24T10-08-20Z-cb697b59`, 9 artifacts, all SHA256 verified |
| `telemetry` | OK | — | `latest-vm.json` written 2026-08-29 20:49Z |
| `retrain_state` | OK | **held** | underlying **CRITICAL**: last outcome `skipped_gates_failed` |
| `cron_liveness` | OK | **held** | underlying **CRITICAL**: retrain log untouched for 650 h |
| `imports` | OK | — | all 4 critical modules import |
| `holds` | OK | — | 1 active, expires in 17 d |

`outcomes_writer` is new (FIX-S1-017). It measures the **writer**; `outcomes` measures the
**table**. Both are needed: a crashing nightly job and a job that was never scheduled leave
the table identical, so the table alone cannot tell them apart. Its WARN is not a
regression — it is two pre-existing defects becoming visible for the first time. Details in
`results/state/outcomes_writer_state.json`; tracked as O-3 and O-4 in `task/OPEN.md`.

**How the writer actually behaves** — the previous revision of this section got this wrong
in a way that would misdirect a rebuild:

- It is `INSERT … ON CONFLICT DO UPDATE`, **not** `DELETE`-then-rebuild. It never removes a
  row. That is exactly why orphaned rows accumulate, and why no snapshot is required.
- The default is `--lookback-years 10`, not 5. Passing nothing discards nothing.
- A full rebuild of the registry takes **~4 minutes** (measured: 233.7 s, 75,344 rows,
  48 of 67 strategies producing trades).

Rebuild with `python -m src.outcomes.persist_all`, then re-run attribution and vetting. The
scheduled caller that prevents a recurrence is written and verified but **not yet
installed** — see the Cron section, FIX-S1-017 / O-1.

## Holds — `results/state/cron_holds.json`

One active hold, declared by `emmanuel` on 2026-08-02, **expires 2026-09-15**:

> hourly retrain cron disabled at Computer-2 request (S2-REPLY-2026-08-02 §4) — a weekly
> promoter against the shared bucket during their remediation is a single point of failure
> behind one flag. **Re-enable ONLY when Computer 2 asks explicitly.**

Covers `cron_liveness`, `retrain_state`, `regimes`. Evidence:
`results/state/crontab.backup-20260802.txt`.

**A hold is not a fix.** But this one did **not** cause the outcomes staleness, and lifting
it would not have fixed it — a claim to the contrary stood in this file and is wrong.
`orchestrator._default_pipeline()` runs `hmm_regime.run` → `attribute.run` → `vet.run`, and
all three only `SELECT` from `fact_trade_outcomes`. The retrain never wrote that table; the
writer simply had no scheduled caller at all (FIX-S1-017 §1).

What the expiry does create is a **deadline**: on 2026-09-15 the re-enabled retrain will
re-run vetting and republish a map. That republish must land on fresh evidence, or it
launders stale trades under a new `generated_at_utc`. Install the outcomes cron (O-1) and
re-vet (O-2) first. When it expires, either the underlying problem is resolved or the hold
is renewed with a fresh reason. Silent renewal makes it an open issue in disguise.

## Signal emission — `results/state/signal_emitter_state.json`

Read `2026-08-29T20:23Z`

| Field | Value |
|---|---|
| `signals_published_total` | **49** |
| `last_signal_emitted_at` | `2026-08-28T19:15:17Z` |
| `last_run_at` | `2026-08-29T20:23:16Z` |
| `last_run_outcome` | `no_signals_generated` |
| `consecutive_faults` | 0 |
| `emitter_enabled` | `true` |

`last_signal_emitted_at` is the **load-bearing field**. A green heartbeat with a null value
here is the FIX-S1-016 failure mode. `no_signals_generated` on a given run is usually correct
— watcher staleness rejects bars outside market hours, and the read above is a Saturday.

Corroborated at the far end for 2026-08-28 (Cloud Monitoring,
`pubsub.googleapis.com/topic/send_message_operation_count` on `scored_signal_queue`): one
publish in the 17:15–17:20Z bucket, two in the 19:00–20:00Z hour. Those three are what took
the counter to 49. **This metric is the only way to confirm from this machine that a message
actually left it** — the emitter counter says a publish was attempted, not that it landed.

## The drill — **the 2026-08-28 message never left this machine**

`results/state/queue/scored_signal_queue/log.jsonl` holds one message, `drill: true`,
`produced_at 2026-08-28T17:36:07Z`, stamped `producer: system-1` and
`bundle_id: 2026-08-24T10-08-20Z-cb697b59_gk-d614163c`. It did **not** reach Pub/Sub:

- Those two files are the *local durable* backend's log and dedup set.
  `src/common/queue/pubsub.py` writes no local files, so a real publish leaves no such trace.
- Cloud Monitoring for 17:00–18:00Z on `scored_signal_queue`, in 5-minute buckets, shows
  exactly one publish, at **17:15** — the hourly cron signal, matching
  `last_signal_emitted_at 2026-08-28T17:15:31Z` as it stood then. Nothing at 17:35–17:40.
- Its idempotency key ends `:drill-run-2026-08-28`. `emit_drill` generates `drill-<uuid4>`,
  and that literal appears nowhere in the tree — it was typed by hand. Its prices
  (1.0850 / 1.0800 / 1.0950) are round synthetic numbers, not market data.

So `task/OPEN.md` is right that the first real drill has not been fired, and this artifact is
a local rehearsal, not a sent message. **The real drill stays held until after Sunday's open,
2026-08-30 21:00 UTC** — System 2 parks anything earlier as out-of-session before it reaches
the drill check.

Related: both queue files are **git-tracked machine-written artifacts**, so a purely local
rehearsal shows up as a working-tree diff. They belong in `.gitignore`.

## Regime-strategy map — `results/state/regime_strategy_map.json`

Generated `2026-08-24T10:20:53Z` · `status: published` (**vetting's own field — not a
publication state**) · `qualification_run_id: 7fde532c-bae1-4d43-a687-13166858af4d` ·
`regime_model_version: hmm-v1.0.0`

| Regime | Cells |
|---|---|
| Trending-Up | 4 |
| Trending-Down | 4 |
| High-Vol | 7 |
| Ranging | **0 — empty** |
| **Total** | **15** |

**By selection basis: 12 `designated`, 3 `qualified`.** A designated cell is an **owner
override of a failed gate** and carries `designated_reason`, `ci_mean_r`,
`pairs_passed_fraction`, `tail_dependence`. Read those reasons before touching them — and
read this ratio before citing the map as evidence of measured edge, because four fifths of it
is override. The three qualified cells are `liquidity_grab_fade@H4` (30, Trending-Down),
`macd_divergence@H4` (34, High-Vol), `weekly_day_reversal_ea@D1` (55, High-Vol).

## Model set — **verified 2026-08-29**

`python -m src.monitoring.model_card --verify` → `ok: true`, parity OK:

```
live_model_set_id   : 2026-08-24T10-08-20Z-cb697b59_gk-d614163c
mirror_model_set_id : 2026-08-24T10-08-20Z-cb697b59_gk-d614163c
pinned_sha256       : b58a94d039c6c31bdb133648dc6d54de9dcaf58cb444dc8600a6fab948a847cb
```

This supersedes both `CLAUDE.md`'s older `2026-08-23T18-12-43Z-1a029257_gk-d614163c` reading
and the previous revision's "not verified in this pass". Note that the heartbeat's
`champion_bundle` check reports the **gatekeeper sub-pointer**, which is not the same thing as
the top-level model-set manifest — only the command above reads the manifest. The local
`model-artifacts/latest.json` is **not** authoritative; the backend is.

## Tests — re-measured 2026-08-29: GREEN, no known reds

```bash
python -m pytest src -q          # 898 passed, ~24 s   (no --ignore needed)
python -m pytest src -q --ignore=src/layer0/strategies/research/tests   # 621 passed, ~22 s
```

**The previous known-red list is retired.** It recorded 2 collection errors and 19
stale-assertion failures as of 2026-08-23; none of them reproduce. The whole suite passes
with and without the `--ignore` flag, so the flag is no longer required — it only narrows
the run. Both counts here were measured, not carried forward.

**Any red you see is yours.** That is a change from the previous state of this file: there
is no longer a standing list to attribute a failure to.

The last four reds went green on 2026-08-29, and the cause is worth keeping because it
inverts the usual assumption: `test_model_card.py`'s `_Frame` stub faked columns
`asset_id_x` / `granularity_x`, but the real joined frame from `train.build_frame` carries
plain `asset_id` / `granularity` (verified against the live frame, 18,023 rows — both
point-in-time joins select a non-overlapping right-hand side, so `merge_asof` never
suffixes). **The module was right and the test was asserting against a frame shape that does
not exist.** Those tests now also pin `_asset_symbols`, so the module's no-DB promise is
enforced rather than accidental.

## Known-broken

| Thing | State |
|---|---|
| Retrain cron | **Not installed** — under the hold above |
| `shell/cron_persist_outcomes.sh` | **Written and verified, not installed** — see Cron / O-1. `outcomes` is green only because the writer was run by hand on 2026-08-29; it will go stale again without this |
| 12 of 67 strategies | **Fail to instantiate** — 9 × `*_RA` import the deleted `src.regime_aware`; 3 × `Range_Bollinger_*` are not in `get_all_strategies()`. Stale `dim_strategy` rows. O-3 |
| 17,583 rows in `fact_trade_outcomes` | **Orphaned** — strategy_ids 7/8/9, which no rebuild reproduces. The upsert never deletes. Removable with `persist_all --reconcile` (destructive). O-4 |
| ~~`python -m src.analytics.publish_regime`~~ | **Fixed.** Imports cleanly as of 2026-08-29 — the `src.regime_aware.families` ImportError is gone. *Import verified; not run end to end.* |
| ~~Pub/Sub `scored-signals.heartbeat`~~ | **Fixed.** The topic is `scored_signal_heartbeat` (underscores) and it exists; `producer.emit_heartbeat` defaults to that name. The last 404 in `logs/cron_hourly_signals.log` is **2026-08-23 20:15**. The dashed name never existed anywhere but in an old default |

Topics in project `scalable-brain` (`gcloud pubsub topics list`, 2026-08-29):
`scored_signal_queue`, `scored_signal_dlq`, `scored_signal_heartbeat`, `AMS_Inbound_Queue`,
`AMS_Outbound_Queue`.

## Cron — re-read from `crontab -l` on 2026-08-29

```
15 * * * *      shell/cron_hourly_signals.sh          # ingest → signals → health → model-card mirror
30 22 * * 1-5   shell/cron_daily_ingest_and_signals.sh
40 5 * * *      shell/cron_publish_strategy_stats.sh
0 6 * * *       shell/cron_heartbeat_daily.sh
0 0 * * 6       shell/cron_oanda_ingest_saturday.sh
```

`cron_publish_strategy_stats.sh` was installed and **missing from this list** until
2026-08-29 — it is the job that republished the risk document daily throughout the outcomes
freeze. Read this section from `crontab -l`, not from memory.

**NOT yet installed — `shell/cron_persist_outcomes.sh` (`0 2 * * 2-6`).** Written and
verified 2026-08-29 (FIX-S1-017); until it is added to the crontab, `fact_trade_outcomes`
still has no scheduled writer. Tracked as O-1 in `task/OPEN.md`.

`results/state/crontab.backup-20260802.txt` lists only 3 jobs and is stale. That drift is
what left `monitoring/freshness.py` modelling a Saturday-only ingest cadence long after the
daily job was added — see FIX-S1-017 §4.

The hourly cadence exists because H4 bars close six times a day and the watcher's 8 h 30 m
staleness threshold would discard five of six otherwise. `flock`-guarded
(`results/state/hourly_signals.lock`) and self-limiting: outside market hours everything is
stale, the watcher refuses, and the run is a no-op.

---

*Durable rules live in `CLAUDE.md` and `GOVERNANCE.md`. Standing findings — the ones that
constrain interpretation rather than describe today — stay in `CLAUDE.md`. If a fact here
stops changing, promote it there.*
