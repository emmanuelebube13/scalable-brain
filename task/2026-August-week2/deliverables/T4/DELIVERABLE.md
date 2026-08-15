# T4 Deliverable — Make the alarm honest (declared cron holds)

## What changed
- **`src/system1/monitoring/holds.py`**: Added this new file containing pure logic to parse holds from JSON, validate against the schema and `HOLDABLE` constraints, apply holds to check results, and summarize the overall state of holds.
- **`src/system1/monitoring/tests/test_holds.py`**: Added unit tests for `holds.py` covering all semantics (parsing, missing keys, invalid types, naive timestamps, expiration, etc.).
- **`src/system1/monitoring/freshness.py`**: Extended `CheckResult` with `held_reason` and `underlying_status` fields, updating its `to_dict()` to serialize them.
- **`src/system1/monitoring/heartbeat.py`**: Wired in the `holds.py` logic. Implemented `_load_holds()`, modified `run_checks()` to apply parsed active holds to results and append the `holds` meta-check, and updated `main()` to support the `--holds` flag for printing active declarations. Updated the module docstring.
- **`src/system1/monitoring/tests/test_heartbeat.py`**: Updated `test_a_crashing_check_is_reported_not_propagated` to expect a length of 2 instead of 1, because the holds check is now unconditionally appended.
- **`shell/cron_heartbeat_daily.sh`**: Updated the header comment to mention `results/state/cron_holds.json`.
- **`docs/goals/SYSTEM1_METRICS_AND_TARGETS.md`**: Updated the "Cron liveness" and "Alerts that are actionable" rows to mention `cron_holds.json` and that holds suppress noise.

**Test count**: increased from 27 to 40 passing tests.

## Acceptance Test Outputs

**=== B. the hold works ===**
```
System-1 freshness heartbeat — 2026-08-15 11:22:56Z

  [PASS] prices           covers through 2026-08-14 20:00Z (last market close 2026-08-14 20:00Z)
  [PASS] outcomes         covers through 2026-08-14 16:00Z, 4.0h inside the 168h grace on the last close (2026-08-14 20:00Z); written 2026-08-15 07:34Z
  [CRIT] regimes          3.3 days behind the last market close (2026-08-14 20:00Z); latest row 2026-08-11 13:00Z
  [PASS] champion_bundle  bundle 2026-07-26T00-27-51Z-b48f48d3 on gcs: 7 artifacts, all SHA256 verified
  [PASS] telemetry        latest-vm.json written 2026-08-15 11:22Z (0.0h ago, warn ≥24h / critical ≥72h)
  [PASS] retrain_state    HELD until 2026-09-15 (31d left); underlying: outcome='no_trigger_or_cooldown'; retrain_log_20260802T180001631182Z.json written 2026-08-02 18:00Z (305.4h ago, warn ≥192h / critical ≥336h)
  [PASS] cron_liveness    HELD until 2026-09-15 (31d left); underlying: cron_system1_retrain.log touched 2026-08-02 18:00Z (305.4h ago, warn ≥2h / critical ≥6h)
  [PASS] imports          all 4 critical modules import
  [PASS] holds            1 hold active, soonest expires in 31d

  PASS=8 · CRIT=1
  overall: CRITICAL (exit 2)
```

**=== C. the hold is visible ===**
```
Checks: cron_liveness, retrain_state
Reason: hourly retrain cron disabled at Computer-2 request (S2-REPLY-2026-08-02 §4) — a weekly promoter against the shared bucket during their remediation is a single point of failure behind one flag. Re-enable ONLY when Computer 2 asks explicitly.
By: emmanuel on 2026-08-02
Expires: 2026-09-15 (31d left)
Evidence: results/state/crontab.backup-20260802.txt
```

**=== D. lifting the hold makes it red again ===**
```
System-1 freshness heartbeat — 2026-08-15 11:23:01Z

  [PASS] prices           covers through 2026-08-14 20:00Z (last market close 2026-08-14 20:00Z)
  [PASS] outcomes         covers through 2026-08-14 16:00Z, 4.0h inside the 168h grace on the last close (2026-08-14 20:00Z); written 2026-08-15 07:34Z
  [CRIT] regimes          3.3 days behind the last market close (2026-08-14 20:00Z); latest row 2026-08-11 13:00Z
  [PASS] champion_bundle  bundle 2026-07-26T00-27-51Z-b48f48d3 on gcs: 7 artifacts, all SHA256 verified
  [PASS] telemetry        latest-vm.json written 2026-08-15 11:23Z (0.0h ago, warn ≥24h / critical ≥72h)
  [WARN] retrain_state    outcome='no_trigger_or_cooldown'; retrain_log_20260802T180001631182Z.json written 2026-08-02 18:00Z (305.4h ago, warn ≥192h / critical ≥336h)
  [CRIT] cron_liveness    cron_system1_retrain.log touched 2026-08-02 18:00Z (305.4h ago, warn ≥2h / critical ≥6h)
  [PASS] imports          all 4 critical modules import
  [PASS] holds            no holds declared

  PASS=6 · WARN=1 · CRIT=2
  overall: CRITICAL (exit 2)
```

**=== E. an expired hold is LOUD, not silent ===**
```
System-1 freshness heartbeat — 2026-08-15 11:23:06Z

  [PASS] prices           covers through 2026-08-14 20:00Z (last market close 2026-08-14 20:00Z)
  [PASS] outcomes         covers through 2026-08-14 16:00Z, 4.0h inside the 168h grace on the last close (2026-08-14 20:00Z); written 2026-08-15 07:34Z
  [CRIT] regimes          3.3 days behind the last market close (2026-08-14 20:00Z); latest row 2026-08-11 13:00Z
  [PASS] champion_bundle  bundle 2026-07-26T00-27-51Z-b48f48d3 on gcs: 7 artifacts, all SHA256 verified
  [PASS] telemetry        latest-vm.json written 2026-08-15 11:23Z (0.0h ago, warn ≥24h / critical ≥72h)
  [WARN] retrain_state    outcome='no_trigger_or_cooldown'; retrain_log_20260802T180001631182Z.json written 2026-08-02 18:00Z (305.4h ago, warn ≥192h / critical ≥336h)
  [CRIT] cron_liveness    cron_system1_retrain.log touched 2026-08-02 18:00Z (305.4h ago, warn ≥2h / critical ≥6h)
  [PASS] imports          all 4 critical modules import
  [CRIT] holds            hold on cron_liveness/retrain_state expired 14d ago and nobody renewed it

  PASS=5 · WARN=1 · CRIT=3
  overall: CRITICAL (exit 2)
```

**=== F. a corrupt file suppresses nothing ===**
```
System-1 freshness heartbeat — 2026-08-15 11:23:11Z

  [PASS] prices           covers through 2026-08-14 20:00Z (last market close 2026-08-14 20:00Z)
  [PASS] outcomes         covers through 2026-08-14 16:00Z, 4.0h inside the 168h grace on the last close (2026-08-14 20:00Z); written 2026-08-15 07:34Z
  [CRIT] regimes          3.3 days behind the last market close (2026-08-14 20:00Z); latest row 2026-08-11 13:00Z
  [PASS] champion_bundle  bundle 2026-07-26T00-27-51Z-b48f48d3 on gcs: 7 artifacts, all SHA256 verified
  [PASS] telemetry        latest-vm.json written 2026-08-15 11:23Z (0.0h ago, warn ≥24h / critical ≥72h)
  [WARN] retrain_state    outcome='no_trigger_or_cooldown'; retrain_log_20260802T180001631182Z.json written 2026-08-02 18:00Z (305.4h ago, warn ≥192h / critical ≥336h)
  [CRIT] cron_liveness    cron_system1_retrain.log touched 2026-08-02 18:00Z (305.4h ago, warn ≥2h / critical ≥6h)
  [PASS] imports          all 4 critical modules import
  [BLKD] holds            hold[0]: missing keys declared_at_utc, declared_by, evidence, expires_utc, reason

  PASS=5 · WARN=1 · CRIT=2 · BLKD=1
  overall: BLOCKED (exit 2)
```

## `cron_holds.json` contents
```json
{
  "schema_version": 1,
  "holds": [
    {
      "checks": [
        "cron_liveness",
        "retrain_state"
      ],
      "reason": "hourly retrain cron disabled at Computer-2 request (S2-REPLY-2026-08-02 §4) — a weekly promoter against the shared bucket during their remediation is a single point of failure behind one flag. Re-enable ONLY when Computer 2 asks explicitly.",
      "declared_by": "emmanuel",
      "declared_at_utc": "2026-08-02T18:00:00Z",
      "expires_utc": "2026-09-15T00:00:00Z",
      "evidence": "results/state/crontab.backup-20260802.txt"
    }
  ]
}
```

## `regimes` state observed
I observed **green-except-regimes**: `cron_liveness` and `retrain_state` were successfully masked as OK, while `regimes` remained CRITICAL (3.3 days behind the last market close), leading to an overall CRITICAL exit status.

## Out of Scope Observations
None. Everything was working as defined, and the data observed exactly matched what was described in the task spec. 

## Trust Limits
The heartbeat is a vital signal of freshness but it still cannot tell us whether the data being written is *correct*, just that it is recent. It blindly trusts that a cron run which touches a file actually performed meaningful work, and trusts that an ingested row is not filled with NaN or leaked values. Furthermore, while the monitor now exposes holds honestly, it remains completely dependent on a human to write down accurate JSON to suppress an alert; it can verify the schema of a hold, but it cannot verify if the human’s `reason` maps to reality.
