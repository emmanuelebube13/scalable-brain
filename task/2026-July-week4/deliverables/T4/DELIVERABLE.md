# T4 — Freshness Heartbeat · Technical Report

**Date:** 2026-07-29 · **Status:** COMPLETE · **Commits:** `b34aca5`, `<deliverables>`

Two System-1 failures ran silently this summer while the pipeline reported success:
the OANDA price ingest was dead for **16 days** (2026-07-04 → 07-20), and
`fact_trade_outcomes` was frozen for **five weeks** (2026-06-23 → 07-29, repaired in T1).
Neither was caught by a check — one surfaced during an audit, the other during this week's
repair. This task adds one daily watchdog so the next one is caught within 24 hours.

---

## 1. The threshold design — and why T4's original numbers were wrong

The task specified *"H1 > 26h behind now"* for price freshness. **That would have fired six
days out of seven.**

Measured evidence: at the time of writing, the newest H1 price bar is `2026-07-24 20:00Z` —
**110 hours old by wall clock**, and completely healthy. Two facts make it so:

1. **The FX market is shut** from Friday ~21:00 UTC to Sunday ~21:00 UTC.
2. **The price ingest is weekly, not hourly** — `cron_oanda_ingest_saturday.sh` runs
   `0 0 * * 6`. Nothing else advances price data.

So freshness cannot be measured in wall-clock hours. It is measured against
**the last market close that the last scheduled ingest should have covered**:

```
expected_coverage(now) = last_market_close(last_scheduled_ingest(now)) - 1h
```

The trailing `-1h` matters: bars are stamped at their **open**, so the final H1 bar before a
21:00 close is stamped 20:00. Without it, perfectly current data reads as one hour short —
which is exactly what the first implementation reported.

A monitor that is permanently yellow is a monitor nobody reads, so anything inside the grace
band reports **OK**, not WARN.

### Final thresholds

| # | Check | Source | Tolerance | Evidence for the number |
|---|---|---|---|---|
| 1 | `prices` | `fact_market_prices` max ts (H1/H4/D1) | shortfall vs expected coverage; OK ≤26h, WARN ≤52h, else CRITICAL | 26h covers the Saturday ingest run plus the final partial bar |
| 2 | `outcomes` | `fact_trade_outcomes` max ts **and** max `created_at` | coverage grace 7d; **write recency** warn ≥8d / critical ≥14d | Trades are sparse events — no trade need open in the final bar. See §2 |
| 3 | `regimes` | `fact_market_regime_v2` max ts | same as prices (26h) | Derived from prices; cannot be fresher than them |
| 4 | `champion_bundle` | backend `latest.json` + SHA256 of every artifact | pass/fail | Unreadable pointer or checksum mismatch is always CRITICAL |
| 5 | `telemetry` | `telemetry/latest-vm.json` mtime | warn ≥24h / critical ≥72h | The VM publisher writes continuously; **not** `latest.json`, which is dead |
| 6 | `retrain_state` | newest `retrain_log_*.json` mtime + outcome | warn ≥8d / critical ≥14d, or outcome contains fail/error | Hourly evaluation; 8d survives a quiet week |
| 7 | `cron_liveness` | `logs/cron_system1_retrain.log` mtime | warn ≥2h / critical ≥6h | The retrain cron is hourly |
| 8 | `imports` | subprocess import of 4 critical modules | pass/fail | The exact failure that froze the feedback loop |

### Two design decisions worth keeping

**Coverage alone cannot detect a dead outcomes writer.** The writer replays history from a
backtest, so `max(timestamp)` stays plausible even when nothing has been written for weeks —
which is precisely why the five-week freeze was invisible. The `outcomes` check therefore
tests **`created_at` recency** as well; that is the actual liveness signal.

**Each check reports `budget_used`**, the fraction of its own tolerance consumed. The checks
measure incomparable things (wall-clock age, shortfall-against-close, pass/fail), so
`age_hours / threshold_hours` is meaningless across the set. `budget_used` is what the
dashboard plots.

---

## 2. Implementation

```
src/system1/monitoring/
├── freshness.py       pure threshold + FX-calendar logic (no DB, no clock, no network)
├── heartbeat.py       the 8 checks, runner, alert contract, CLI
└── tests/             27 tests
```

```bash
python -m src.system1.monitoring.heartbeat            # table + exit code
python -m src.system1.monitoring.heartbeat --json     # machine-readable snapshot
python -m src.system1.monitoring.heartbeat --check prices
```

### Alert contract

| Artifact | Meaning |
|---|---|
| exit `0` / `1` / `2` | all fresh / warnings / critical or blocked |
| `results/state/heartbeat_latest.json` | always written — full snapshot with per-check status, age, threshold, budget |
| `results/state/HEARTBEAT_ALERT` | **the signal.** Present ⇒ something is stale. Auto-deleted once healthy again |
| `logs/heartbeat_alerts.log` | append-only dated history of every non-green run |

`BLOCKED` (a check that cannot be evaluated — DB down, no credentials) **fails the run with
exit 2**. It is never skipped: an unevaluated check that looks like a pass is the failure
mode this whole task exists to remove. A check that raises is caught and reported as
BLOCKED, so one broken check cannot take the monitor down with it.

### Incidental fix

`StorageBackend.head()` returned no modification time on **either** backend, so the telemetry
check could not be written. Both now expose `updated`; the first heartbeat run reported
`BLOCKED: object exists but the backend exposed no modification time`, which is the intended
behaviour working on its first day.

### A silent misconfiguration found while building this

`build_storage()` reads `os.environ` and **defaults to `STORAGE_PROVIDER=local`** when `.env`
has not been loaded. A process that forgets `load_dotenv()` therefore validates the stale
local `model-artifacts/latest.json` (a June bundle) instead of the live GCS pointer — and
reports success. The heartbeat calls `_load_env()` explicitly and names the provider in its
output (`bundle … on gcs: 7 artifacts, all SHA256 verified`) so the wrong-backend case is
visible rather than plausible.

---

## 3. First real run (2026-07-29 10:26Z)

```
  [PASS] prices           covers through 2026-07-24 20:00Z (last market close 2026-07-24 20:00Z)
  [PASS] outcomes         covers through 2026-07-24 19:00Z, 1.0h inside the 168h grace; written 2026-07-29 01:47Z
  [PASS] regimes          covers through 2026-07-24 20:00Z (last market close 2026-07-24 20:00Z)
  [PASS] champion_bundle  bundle 2026-07-26T00-27-51Z-b48f48d3 on gcs: 7 artifacts, all SHA256 verified
  [PASS] telemetry        latest-vm.json written 2026-07-29 10:26Z (0.0h ago, warn ≥24h / critical ≥72h)
  [PASS] retrain_state    outcome='no_trigger_or_cooldown'; written 2026-07-29 10:13Z
  [PASS] cron_liveness    cron_system1_retrain.log touched 2026-07-29 10:00Z (0.4h ago)
  [PASS] imports          all 4 critical modules import

  PASS=8 · overall: OK (exit 0)
```

**No source is genuinely stale.** Notably, `telemetry` PASSES — the VM publisher is actively
writing `latest-vm.json`, contradicting the concern that it might be dead. The champion
bundle on GCS (`2026-07-26T00-27-51Z-b48f48d3`) verified all 7 artifacts against their
SHA256.

---

## 4. Forced-failure demonstration (step 6)

A stale price timestamp was injected **without touching the real table**, simulating the
July 4–20 ingest outage:

```
  [CRIT] prices  14.0 days behind the last market close (2026-07-24 20:00Z);
                 latest row 2026-07-10 20:00Z
  PASS=7 · CRIT=1
  overall: CRITICAL (exit 2)
EXIT=2

$ cat results/state/HEARTBEAT_ALERT
2026-07-29 10:23:46Z overall=CRITICAL
CRITICAL prices: 14.0 days behind the last market close (2026-07-24 20:00Z); latest row 2026-07-10 20:00Z

$ tail -1 logs/heartbeat_alerts.log
2026-07-29T10:23:46Z CRITICAL prices=CRITICAL: 14.0 days behind the last market close …
```

Healthy state was then restored and the flag auto-cleared. **The real outage would have been
caught on day one instead of day sixteen.**

---

## 5. Cron

`shell/cron_heartbeat_daily.sh`, styled after the existing cron scripts (venv activation,
`tee` logging, `flock` single-flight). It deliberately does **not** use `set -e`: a non-zero
exit is the heartbeat *reporting* a problem, not the script failing, and must still be logged.

Installed crontab entry (previous entries unchanged):

```
  0 0 * * 6  …/shell/cron_oanda_ingest_saturday.sh   >> logs/cron_oanda_ingest.log 2>&1
  0 * * * *  …/shell/cron_system1_retrain.sh         >> logs/cron_system1_retrain.log 2>&1
+ 0 6 * * *  …/shell/cron_heartbeat_daily.sh         >> logs/cron_heartbeat.log 2>&1
```

Remove with `crontab -e` if unwanted; a backup of the prior crontab was taken before install.

---

## 6. Tests — 27, all green

`test_freshness.py` (threshold + calendar, everything injected):
`last_market_close` ×5 · `last_scheduled_ingest` ×3 · bar-open stamping ·
**fresh-prices-midweek-do-not-warn** (the real 110h case) · **monday-morning-no-false-alarm** ·
**one-missed-weekly-ingest-is-critical** · warn-before-crit band · empty table ·
long-dead-ingest-is-critical-not-merely-warn · age bands · never-negative-age · aggregation
and exit codes.

`test_heartbeat.py` (alert contract): healthy run writes no alert · failing run raises flag +
logs · **recovery clears a stale flag** · warnings exit 1 · **a crashing check is reported,
not propagated** · **BLOCKED fails the run** · render · check registry.

Full suite after the change: **242 passed** (`src/system1` + `src/layer0/tests`).

---

## 7. Follow-ups

1. **Detection latency is capped by the weekly ingest.** The heartbeat runs daily, but price
   data only advances on Saturdays, so a dead ingest is provably detectable only after the
   next missed Saturday — up to ~8 days, not 24h. The 24h figure holds for outcomes,
   telemetry, cron liveness, imports, and bundle integrity. Moving the ingest to daily would
   close that gap; that is a scheduling decision, not a monitoring one.
2. **No notification channel.** The contract is a flag file and a log. Nothing emails or
   pages anyone — if no one looks, it is still silent. A trivial next step is having the
   hourly retrain cron refuse to run (or shout) while `HEARTBEAT_ALERT` exists.
3. `M15`/`M30`/`W1` price granularities are months stale (M15/M30 stop 2026-05-01, W1
   2026-06-12). They are **not** in the System-1 path (which uses H1/H4/D1), so the check
   deliberately ignores them — but if anything starts consuming them, they are dead data.
