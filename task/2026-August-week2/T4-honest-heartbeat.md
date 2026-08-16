# T4 — Make the alarm honest (declared cron holds)

**Engineer:** Gemini
**Reviewer:** Claude (will verify after you report)
**Repo:** `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`
**Venv:** `source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate`
**Estimated time:** 30–40 min
**Risk:** low — you are adding a read-only input to a monitor. No pipeline stage, no DB write, no
promotion path, no crontab edit. The one way this task can do damage is by making the heartbeat
quieter than the truth, which is exactly what the acceptance test below exists to prevent.

**Depends on:** nothing. Can be done in any order relative to the data-refresh tasks.

> **Naming collision, read this once:** the *existing* heartbeat was itself built under a task
> called "T4" in the week of 2026-07-28 — that is why `heartbeat.py` opens with
> `"""T4 — daily freshness heartbeat"""`. This document is a *different* T4, in the week of
> 2026-08-11. Do not "fix" that docstring's task number, and do not assume any file already
> referencing T4 is yours.

---

## Why this matters

The daily heartbeat (`0 6 * * *`) is the only thing in System 1 that will tell you a pipeline died
without you asking. This morning it reported three problems:

| check | status | is it true? |
|---|---|---|
| `regimes` | CRITICAL | **yes** — regime rows stop 2026-08-11 13:00Z, prices reach 2026-08-14 20:00Z |
| `retrain_state` | WARN | no — the last retrain log is 303h old *because you turned the cron off* |
| `cron_liveness` | CRITICAL | no — same reason: the cron was disabled on purpose on 2026-08-02 |

The hourly retrain cron was commented out at Computer 2's request (`S2-REPLY-2026-08-02 §4`: a
weekly promoter against the shared bucket during their remediation was a single point of failure
behind a single flag). That decision stands. The backup of the pre-change crontab is at
`results/state/crontab.backup-20260802.txt`.

So two thirds of the board is the monitor reporting a decision back to you as a failure. That is
worse than useless: it is training. Every morning the flag file is there, every morning you know
in advance why, and on the morning `regimes` or `imports` or `champion_bundle` is the real reason,
the flag file will look exactly the same as it did the previous thirteen mornings.

The fix is not to raise the thresholds and it is not to delete the checks. It is to let the system
carry the fact it already knows — *this is paused on purpose, until this date* — and to make
"paused on purpose" expire, so that the silence you buy is rented, not sold.

**The trap to avoid:** a hold that never expires is not a fix, it is the same failure with better
manners. The whole value of this task is in step 3.

---

## Verified state as of 2026-08-15 09:00 UTC (re-verify before you act)

```
heartbeat cron        0 6 * * *   shell/cron_heartbeat_daily.sh          ACTIVE
retrain cron          0 * * * *   shell/cron_system1_retrain.sh          COMMENTED OUT 2026-08-02
ingest cron           0 0 * * 6   shell/cron_oanda_ingest_saturday.sh    ACTIVE

results/state/heartbeat_latest.json   evaluated 2026-08-15T09:00:01Z, overall CRITICAL, exit 2
results/state/HEARTBEAT_ALERT         present (written 09:00Z)
logs/cron_system1_retrain.log         last touched 2026-08-02 18:00Z  (303h)
newest retrain_log_*.json             retrain_log_20260802T180001631182Z.json, outcome
                                      'no_trigger_or_cooldown'          (303h)

fact_market_prices        max ts 2026-08-14 20:00Z
fact_market_regime_v2     max ts 2026-08-11 13:00Z   (H1 08-11 13:00, H4 08-11 09:00, D1 08-09 21:00)

pytest src/system1/monitoring -q     27 passed
```

Non-OK checks right now: `regimes` CRITICAL, `retrain_state` WARN, `cron_liveness` CRITICAL.

---

## What you are building

A declaration file the heartbeat reads, plus the logic that honours it and the logic that stops
honouring it.

### 1. The file — `results/state/cron_holds.json`

Hand-edited, version-controlled (it is **not** in `.gitignore`; the sibling
`heartbeat_latest.json` is, this one must not be). It is an audit record of a human decision, so
it is committed alongside the code.

```json
{
  "schema_version": 1,
  "holds": [
    {
      "checks": ["cron_liveness", "retrain_state"],
      "reason": "hourly retrain cron disabled at Computer-2 request (S2-REPLY-2026-08-02 §4) — a weekly promoter against the shared bucket during their remediation is a single point of failure behind one flag. Re-enable ONLY when Computer 2 asks explicitly.",
      "declared_by": "emmanuel",
      "declared_at_utc": "2026-08-02T18:00:00Z",
      "expires_utc": "2026-09-15T00:00:00Z",
      "evidence": "results/state/crontab.backup-20260802.txt"
    }
  ]
}
```

Rules, all enforced by the parser:

- Every field above is **required** on every hold. A hold with no `reason` is a mute button, and
  in six weeks nobody will remember which. An unknown key is an error, not something to ignore.
- `checks` must be a non-empty list of names that exist in `heartbeat.CHECKS`.
- Timestamps must be ISO-8601 and timezone-aware. A naive timestamp is an error — do not "assume
  UTC" and carry on.
- `expires_utc` must be no more than **90 days** after `declared_at_utc` (`MAX_HOLD_DAYS = 90`).
  A five-year hold is a deleted check with extra steps.
- A missing file means "no holds declared". That is the normal, healthy state and must be silent.

### 2. Which checks may be held

```python
HOLDABLE = {"prices", "outcomes", "regimes", "telemetry", "retrain_state", "cron_liveness"}
```

`champion_bundle` and `imports` are **not** holdable, and a hold naming either is a
configuration error. Those two do not measure staleness — they measure whether the artifact you
would ship is intact and whether the code still imports. Nobody ever *intends* a SHA256 mismatch
or a broken import chain, so there is no honest declaration to make about them. Put this
reasoning in a comment; it is the part a future reader will want to argue with.

### 3. Semantics — the whole task is this table

| situation | affected check reports | `holds` meta-check reports |
|---|---|---|
| hold active (`now < expires_utc`) | **OK**, detail `HELD until 2026-09-15 (28d left): <reason>; underlying: <the real detail>` | OK — `1 hold active, soonest expires in 28d` |
| hold active, expires in ≤ 7 days | OK (as above) | **WARN** — `hold on cron_liveness/retrain_state expires in 3d — renew it or lift it` |
| hold **expired** | its real status (so `cron_liveness` goes back to CRITICAL) | **CRITICAL** — `hold on cron_liveness/retrain_state expired 4d ago and nobody renewed it` |
| file missing | its real status | OK — `no holds declared` |
| file unparseable, or any malformed hold | its real status — **no hold from a bad file is applied** | **BLOCKED** — with the specific reason (`hold[0]: expires_utc is naive`) |
| hold names `imports` / `champion_bundle` / an unknown check | its real status | **BLOCKED** — `hold[0]: 'imports' is not holdable` |

Two things that fall out of this table and are load-bearing:

- **Held ≠ forgotten.** The underlying measurement is still taken and still written to the
  snapshot; the hold changes the *status*, never the *measurement*. Preserve the true status in
  the JSON (see §5) so an audit six weeks from now can say what the box actually knew.
- **Fail loud, not open.** A broken holds file suppresses nothing. The default-safe posture in
  this repo is "missing / stale / error ⇒ the pessimistic answer", and a monitor is no exception.

### 4. Where the code goes

Follow the existing split — `freshness.py` is pure decision logic with no clock and no I/O,
`heartbeat.py` does the reading and writing. Do not break that.

- **New:** `src/system1/monitoring/holds.py` — the dataclass, `parse_holds(payload, now)` →
  `(holds_by_check, problems)`, `apply_hold(result, hold, now)` → `CheckResult`,
  `summarise(holds, problems, now)` → the `holds` `CheckResult`. Pure: `now` is passed in, the
  payload is passed in already deserialised. Every branch in the table above must be reachable
  from a unit test that constructs a dict, with no filesystem.
- **`heartbeat.py`:** a `HOLDS_FILE = STATE_DIR / "cron_holds.json"` constant, a `_load_holds()`
  that reads and JSON-decodes it (a read error becomes a `problems` entry, never an exception),
  and the wiring in `run_checks()`.
- **`freshness.py`:** extend `CheckResult` with two optional fields — `held_reason: str | None`
  and `underlying_status: Status | None` — both defaulting to `None`, and surface them in
  `to_dict()`. Existing positional construction across the file must keep working, so append
  them at the end.

The `holds` meta-check runs on **every** invocation, including `--check cron_liveness`. If it
only ran on full runs, a single-check invocation could report a serene OK while the holds file
was corrupt. It is not in the `CHECKS` dict (it takes different arguments and is not selectable);
append it to the results list in `run_checks()`.

### 5. Snapshot contract

`results/state/heartbeat_latest.json` gains three keys per check, and existing consumers must not
break — `status` keeps meaning "the status you should act on":

```json
{
  "name": "cron_liveness",
  "status": "OK",
  "underlying_status": "CRITICAL",
  "held": true,
  "held_reason": "hourly retrain cron disabled at Computer-2 request (S2-REPLY-2026-08-02 §4)…",
  "detail": "HELD until 2026-09-15 (31d left); underlying: cron_system1_retrain.log touched 2026-08-02 18:00Z (303.0h ago, warn ≥2h / critical ≥6h)",
  "age_hours": 303.0,
  "threshold_hours": 6,
  "budget_used": 50.5
}
```

For an unheld check: `"held": false`, `"held_reason": null`, `"underlying_status": null`.

### 6. CLI

Add `--holds`: print the declared holds — checks, reason, who, days remaining, and any parse
problems — then exit 0. Read-only.

**Declaring or lifting a hold is done by editing the JSON.** Do not build a `--hold-add` /
`--hold-clear` writer. A hold should cost thirty seconds of typing and leave a diff with your
name on it; a one-liner that silences a monitor is a footgun, and this task exists because of an
earlier footgun.

---

## Steps

1. **Re-verify the state block above.** Run
   `python -m src.system1.monitoring.heartbeat` and `crontab -l | tail -8`. If what you see
   differs from what is written above, say so in the deliverable and work from what you see.
2. Write `holds.py` and its tests first, before touching `heartbeat.py`. It is pure, so it is
   fully testable before any wiring exists.
3. Extend `CheckResult` in `freshness.py` (two optional fields + `to_dict`).
4. Wire `run_checks()` in `heartbeat.py`; add `HOLDS_FILE`, `_load_holds()`, `--holds`.
5. Create `results/state/cron_holds.json` with **exactly one** hold — the 2026-08-02 retrain hold,
   covering `cron_liveness` and `retrain_state`, expiring `2026-09-15T00:00:00Z`. Do not declare a
   hold on `regimes`; see Out of scope.
6. Run the acceptance test below and paste its real output into the deliverable.
7. Update the `heartbeat.py` module docstring to mention the holds file, and
   `shell/cron_heartbeat_daily.sh`'s header comment. Then
   `grep -rln "heartbeat" --include=*.md docs/ task/OPEN.md` and update anything that enumerates
   the checks — `docs/goals/SYSTEM1_METRICS_AND_TARGETS.md` is the likely one.
8. Commit **only your own files**. The tree has ~13 unrelated uncommitted files (FIX-S1-012/013/014)
   and a pile of deleted `docs/design/*` — none of that is yours. `git add` by explicit path,
   never `git add -A`. No `Co-Authored-By` trailer in the message.

---

## Acceptance test — run it, paste the output

```bash
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain

# A. unit + regression
python -m pytest src/system1/monitoring -q          # 27 existing must still pass, plus yours

# B. the hold works
python -m src.system1.monitoring.heartbeat ; echo "exit=$?"
#   expect: cron_liveness OK (HELD), retrain_state OK (HELD), holds OK
#   expect: regimes still CRITICAL  -> exit 2   (see the note below)

# C. the hold is visible
python -m src.system1.monitoring.heartbeat --holds

# D. lifting the hold makes it red again
mv results/state/cron_holds.json /tmp/hold.json
python -m src.system1.monitoring.heartbeat ; echo "exit=$?"
#   expect: cron_liveness CRITICAL, retrain_state WARN, holds OK ("no holds declared")
mv /tmp/hold.json results/state/cron_holds.json

# E. an expired hold is LOUD, not silent
python - <<'PY'
import json, pathlib
p = pathlib.Path("results/state/cron_holds.json")
d = json.loads(p.read_text())
d["holds"][0]["expires_utc"] = "2026-08-01T00:00:00Z"
pathlib.Path("/tmp/expired_holds.json").write_text(json.dumps(d, indent=2))
PY
cp results/state/cron_holds.json /tmp/hold.json
cp /tmp/expired_holds.json results/state/cron_holds.json
python -m src.system1.monitoring.heartbeat ; echo "exit=$?"
#   expect: holds CRITICAL, cron_liveness back to CRITICAL, exit 2
cp /tmp/hold.json results/state/cron_holds.json

# F. a corrupt file suppresses nothing
cp results/state/cron_holds.json /tmp/hold.json
echo '{ "schema_version": 1, "holds": [ {"checks": ["imports"]} ] }' > results/state/cron_holds.json
python -m src.system1.monitoring.heartbeat ; echo "exit=$?"
#   expect: holds BLOCKED, cron_liveness CRITICAL again, exit 2
cp /tmp/hold.json results/state/cron_holds.json

# G. leave the box in the state you found it, plus the hold
python -m src.system1.monitoring.heartbeat --json | head -40
```

**About `regimes`:** it is CRITICAL for a real reason — the regime table is 3.3 days behind the
price table — and it is **not yours to fix or to hold**. If a data-refresh task has already run by
the time you get here, the board will be all-green and step B exits 0. If it has not, the board is
green *except* `regimes` and step B exits 2. Both outcomes pass this task. What must be true either
way: **`cron_liveness` and `retrain_state` are OK, and `regimes` is untouched.** Report which of
the two you saw.

---

## Done when

1. `pytest src/system1/monitoring -q` is green, with new tests covering every row of the semantics
   table in §3 — including the expired, the malformed, and the not-holdable cases.
2. With `cron_holds.json` in place: `cron_liveness` and `retrain_state` report OK, and their
   detail lines say why they are held, until when, and what the underlying measurement was.
3. Removing the file makes both go red again (test D), and an expired hold makes the board go red
   *louder* than no hold at all (test E).
4. `heartbeat_latest.json` records `underlying_status` for every held check, so the true state is
   never lost.
5. The deliverable exists (below) and the commit contains only your files.

---

## Out of scope — do not do these

- **Do not re-enable the retrain cron.** It stays off until Computer 2 asks. This task makes the
  monitor agree with that decision; it does not revisit it.
- **Do not touch `crontab`** at all, in any direction.
- **Do not refresh regimes, prices or outcomes**, and do not declare a hold on `regimes` to make
  the board green. That check is telling the truth. Silencing it would be doing the precise thing
  this task is meant to end.
- **Do not change any threshold** in `freshness.py` (`warn_hours`, `critical_hours`, grace bands).
  If a threshold looks wrong to you, write it in the deliverable — do not edit it.
- **Do not add a hold-writing CLI**, a web view, a notification integration, or a second holds
  file for the other two systems.
- Do not touch `../system-2-execution-engine/` or `../system-3-account-management/`.

---

## Deliverable

`task/2026-August-week2/deliverables/T4/DELIVERABLE.md`, matching the T2/T3 format:

- What you changed, file by file, with the test count before (27) and after.
- The **real pasted output** of acceptance tests B, C, D, E and F — not a description of it.
- The contents of `cron_holds.json` as committed.
- Which of the two `regimes` outcomes you saw (green board or green-except-regimes).
- Anything you found that is wrong but out of scope, listed and left alone.
- One paragraph: what this monitor would *still* fail to tell you. The point of the task is a
  board you can trust at a glance; say plainly where that trust still does not extend.
