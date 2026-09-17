# DECISION — System 1 runs 24/7 (owner, 2026-09-16)

**Status:** ACTIVE. Supersedes the "System 1 is not always-on, and that is by design"
premise in `GOVERNANCE.md` §Systems and the rationale block in
`shell/cron_signal_producer_daily.sh` (both predate this decision; treat this file as
authoritative where they conflict).

## The decision

Computer 1 stays powered and connected continuously. System 1 publishes signals on a
continuous cadence ("we can be unforgiving to System 1"), and may additionally publish
signals to a chat channel (Discord was named; no Discord integration exists in the repo
yet — Telegram, on the VM watchdog, is the only built notification channel).

## What this does NOT change

- **ADR-001 stands.** "System 2 runs live inference" was approved by both systems on
  2026-08-22 and remains the ratified architecture. 24/7 uptime makes the temporary
  producer bridge (`src/signals/`, `src/queue_producer/`) more reliable; it does not make
  it the destination. Making the producer permanent would be an explicit ADR-001 revisit,
  in writing — do not infer it from this decision.
- **The mechanism stays the hourly cron, not the bare `while True` loop** in
  `signals/run.py:main`. The cron wraps the producer in `timeout 10m`, `flock`,
  `fact_job_runs` records, and the health/ledger/model-card publishing steps — none of
  which exist in the loop, and the loop would hang unsupervised on the 2026-09-09-shaped
  Pub/Sub stall (WO-06). An hourly cron IS continuous operation at this system's decision
  cadence (nothing closes faster than H1, and the watcher makes off-hours runs no-ops).
- **Fail-closed stays fail-closed.** An expired or inadmissible map still means no
  signals, loudly. 24/7 raises the bar on *renewal and alerting*, not on permissiveness.

## What changed with it (same change set, 2026-09-16)

- Weekly map renewal is automated: the Sunday retrain publishes the model set when the
  map gates pass (`MODEL_SET_AUTOPUBLISH=true` in `shell/cron_system1_retrain.sh`;
  map-renewal split in `scheduler/orchestrator.py`). Champion promotion stays gated and
  currently blocked (O-30/O-31) — `promoted_map_only` is the expected weekly outcome.
- Re-affirmation is never wanted (owner answer to the standing Q1): one economic setup
  reaches the wire once (`signals/setup_dedup.py`, D9).
- The job-absence check (`monitoring/job_runs.py check`) finally has a scheduled caller
  (inside `cron_heartbeat_daily.sh`).

## Gatekeeper stance (decided under the same authority, delegated to the session)

**Shadow mode continues; activation declined again.** Grounds: 37 of 38 scored signals
since 2026-08-30 carry `shadow_verdict: would_refuse`, so activation ≈ silencing the
system on a gate whose training target contradicts its promotion metric (O-31: `is_winner`
is win-rate, the gate is mean-R, and approved mean R beats rejected in only 4 of 5 OOS
folds); the live scorer also runs a drifted, never-published champion (O-17). Neither
"publish everything a calibrated gate distrusts" nor "trust a gate we can't yet defend" is
sound with live money — shadow keeps the evidence accumulating until the 2.0.0 retrain
resolves O-30/O-31. Revisit alongside those two register items, not before.

## Follow-ups this decision creates

- Alerting for Computer 1 (nothing pages a human when System 1 dies; the VM watchdog
  does not read `s1_health.json`). Cheapest path: extend the existing Telegram watchdog.
- If Discord publishing is wanted, it is a new small deliverable (webhook post fed by the
  signal ledger or `publish_health`), scoped separately.
- `GOVERNANCE.md` §"System 1 is not always-on" needs its premise updated to cite this
  decision (kept out of this change set to avoid rewriting governance mid-flight).
