# Core verification — findings and fix plan (2026-09-16)

**Context.** Owner decision 2026-09-16: System 1 runs 24/7 as a continuous signal publisher;
live money is entering; the core is capital growth. Owner asked for verification of
(1) regime structure + published artifacts, (2) strategy calculation + regime placement,
(3) cron/automation — then a prioritized fix plan.

**Evidence base:** three read-only verification passes (regime/artifacts, strategy/placement,
automation), findings filed in `issues/September-Week-3/2026-09-16.md`. Items already in
`task/OPEN.md` are cited by O-number, not duplicated. Promote a P-item into `OPEN.md` when
work on it starts — this file is the plan, not a competing register.

---

## What verified CLEAN (worth stating — it is most of the core)

- **Structural labeller is causal** (`regime/structural.py`): everything `shift(1)`-ed,
  lagged vol baseline, NaN-masked warmup, validated frame preconditions. No `center=True`
  anywhere reachable.
- **Routing is regime-correct by construction**: attribution measures a cell in a regime →
  vet places it in that regime → `build.py` routes only map-cell strategies under the live
  structural label → fail-closed on UNKNOWN/missing/expired/wrong-label (map contract R1
  enforced in code).
- **The two firing strategies are clean**: `reference_pullback_continuation` (43) and
  `xard_ma_cross_daily_open` (58) pass `assert_no_lookahead_v2`; `nnfx_backtrader` kernels
  verified strictly backward-looking. The banned `detect_swing_points(center=True)` survives
  only in an unregistered strategy family — unreachable from the pipeline.
- **Outcomes writer is alive**: daily cron, 75k rows, `fact_trade_outcomes` current to
  2026-09-16; the June freeze is over. Engine partitioning works via `dim_strategy.engine`.
- **`nnfx_backtrader` is no longer live** — the premise "id 36 routes signals" is stale; the
  backend map (2026-09-11) has 8 cells, 6 qualified / 2 designated.

## P0 — before Friday 2026-09-18 (live-money exposure)

| # | Item | Definition of done | Decision needed |
|---|---|---|---|
| P0-1 | **Map-expiry blackout.** Published map expires 2026-09-18T18:41Z; nothing automated flips the top-level pointer; next Sunday window is after expiry. | A model set vetted on current evidence is published via the `publish-model-set` skill before expiry, OR the owner explicitly accepts the blackout. Then decide the standing cadence: `MODEL_SET_AUTOPUBLISH=true` (removes the human veto) vs a weekly manual publish ritual vs longer `MAP_MAX_AGE_DAYS`. | **Owner: publish cadence.** |
| P0-2 | **Re-emission of one setup as N signals** (strategy 43: 15 wire messages, one pending level; S3's 90-min Layer-R window clears each one). | Dedup on economic content (strategy, pair, direction, entry_price) suppresses unchanged re-arms; a changed (sl,tp) re-emits with a re-affirmation marker. Subsumes the O-23 Q1 question. | **Owner: Q1 — is re-affirmation ever wanted?** Recommend: no re-publish of unchanged setups. |
| P0-3 | **Gatekeeper shadow review is overdue.** 37 of 38 scored signals since 2026-08-30 carry `shadow_verdict: would_refuse` and were published anyway (O-16, review was due ~09-06); the scorer also runs an unpublished drifted champion (O-17). | Shadow data read against O-17; explicit owner re-decision recorded (stay permissive / activate / partial). Do not activate as a bug fix. | **Owner: activation stance.** |

## P1 — evidence correctness (what qualification stands on)

| # | Item | Definition of done |
|---|---|---|
| P1-1 | **`vet.py` exits wipe** (`vet.py:461`): every published cell ships `exits: {}`; re-runs erase designated exits. | Either populate from the strategy's own declared exits or remove the field from the map contract; contract schema tightened so `{}` no longer validates; designated exits survive a `vet --live` re-run (test). |
| P1-2 | **T6 ATR case mismatch** (O-12): v1 stops warmup-dependent; contaminates `fact_trade_outcomes` → attribution → gates. Now that vetting is v2-authoritative the blast radius is research verdicts, not the live path — but rank_all/reporting still read v1 rows. | One casing; the tolerating test (`test_position_engine.py:256-283`) asserts exactness; `persist_all` rebuild for v1 strategies; note in FIX register. |
| P1-3 | **Degenerate causal labels** (`hmm_regime.py:104-115`): verify whether `fact_market_regime_v2` still holds the acc=1.000 fold-collapse labels and whether run `21d6d29b` attributed on them. | A dated query result in the record; if contaminated, re-run `hmm_regime` + attribution + vetting before the next publish. |
| P1-4 | **Manifest guard**: `publish_model_set` refuses `qualification_run_id: null` (one-line check + test). |
| P1-5 | **O-3 / O-4 cleanup** before the next qualification: deactivate the 12 dead `dim_strategy` rows; owner-gated `persist_all --reconcile` for the 17,583 orphaned rows (they are 18.6% of the OOS bank). |
| P1-6 | **Structural vol window**: make `build_structural_labels` honour its granularity argument (wire `get_vol_window`) or delete the parameter and the dead function; document that H4/H1 run on a 252-slot window today. Any change relabels history → re-attribution before next vet. |
| P1-7 | **Cross-system comms** (after verifying against the running hosts, via `write-comms`): S2 fails open on missing manifest `status`; S2's `regime_mapping.py` is the retired rank-based rule; the map/`qualification_run_id` are downloaded but unread. Also send the owed O-7/O-8 messages. |

## P2 — automation hardening for 24/7

| # | Item | Definition of done |
|---|---|---|
| P2-1 | **Record the 24/7 decision** (doc + amend `GOVERNANCE.md:252` and `cron_signal_producer_daily.sh`'s rationale). Flag: 24/7 uptime does not overturn ADR-001 (S2 runs inference) — if the producer is now permanent rather than a bridge, that is an explicit ADR revisit. |
| P2-2 | **Keep the hourly cron as the 24/7 mechanism** (recommended) rather than the unsupervised `while True` loop — the cron already gives timeout, flock, job records, health publishing, and restarts a dead producer within the hour. If a tighter loop is ever wanted, it ships as a systemd unit with `Restart=`, `WatchdogSec`, and the cron's wrappers, not bare Python. |
| P2-3 | **Alerting for Computer 1**: schedule `job_runs check` (the built absence detector has no caller); on CRITICAL, notify — cheapest path is the existing Telegram channel (extend ops-watchdog to read `s1_health.json` age, or a small S1-side sender). **Discord**: no code exists; if wanted, scope as a new small deliverable (webhook post from `publish_health` / signal emit). |
| P2-4 | **Crontab timezone**: add `CRON_TZ=UTC` (or re-write lines in local time deliberately), re-snapshot the backup, correct `shell/README.md` + `job_runs.py` comments, and check `freshness.py` assumptions before the 2026-11-01 DST shift. |
| P2-5 | **VM-side gaps** (verify on `trading-1` with the commands in the audit): missing S2 `pg_dump`/S3 SQLite backup jobs that the deployment guide promises; `s3-signal-relay` has no unit template in the repo; two conflicting unit-file sets — declare one authoritative; watchdog does not cover `s2-downloader`/`s3-command-poller`. |
| P2-6 | Register hygiene: O-27's "unset/not-installed" claims are stale (engine chosen, retrain cron installed) — update the row in place per register rules. |

## Deliberately NOT proposed

- Activating the gatekeeper threshold as a "fix" (O-16 decision stands until the owner
  re-decides with the shadow data).
- Building regime-filtering intelligence — regimes still do not discriminate
  (`n_discriminating: 0/10`, standing finding); the regime map is placement bookkeeping,
  not edge, until evidence says otherwise.
- Restoring `demark_fractal_breakout` to candidacy without work: it is causally clean but
  structurally unemittable (trailing-only exits, no TP price → `build.py:412` refuses 3,501/3,501).
- Any direct edit to Systems 2/3 from this machine (comms + host verification instead).
