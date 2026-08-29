# GOVERNANCE — how work is produced, placed, and accepted

**Status:** active, 2026-08-28 · **Applies to:** every contributor, human or agent, in this repo.

`STRUCTURE.md` says **where** a file goes. This file says **how it must be made and what it
must prove before anyone believes it.** The two are meant to be read together and neither
repeats the other.

---

## Why this exists

Between 2026-08-02 and 2026-08-15 this system produced four results that looked like edges
and were not. Every one of them passed the checks in force at the time. That pattern is
written up in `docs/design/STRATEGY_EXPERIMENT_STANDARD.md`, which fixed it **for strategy
claims only**.

The same failure mode applies to everything else this repo produces — code, migrations,
reports, messages sent to Computers 2 and 3. A publish that skipped its checksum step, a
threshold hardcoded into a rejection string, a `status` field read as the wrong `status`
field: each cost real time, and none of them was a strategy claim. This document is the
general form of that standard.

**Governing principle, unchanged from the experiment standard:**

> A result must survive being *tried to be broken* before it is believed.

---

## The three mechanisms — do not conflate them

Guidance in this repo is carried by three different things. They are not
interchangeable, and putting content in the wrong one is why it gets ignored.

| Mechanism | Where | Loads when | Holds |
|---|---|---|---|
| **`CLAUDE.md`** | Repo root, plus six folders | Automatically, when a file in that subtree is read or edited | **Constraints.** "In this folder, never do X." Standing facts that are not visible in the code |
| **Skills** | `.claude/skills/<name>/SKILL.md` | On demand, when the described task comes up | **Procedures.** A repeated multi-step operation that has a correct order |
| **Agents** | `.claude/agents/<name>.md` | When explicitly invoked, in their own context window | **Roles.** A second opinion, with its own tools and its own read of the evidence |

There is **no such thing as an agent that activates because you opened a folder.** Folder
knowledge is a nested `CLAUDE.md`. An agent is a separate reader you call on purpose — which
is exactly what makes an auditor or a devil's advocate worth having, and what would make a
"folder agent" pointless.

Corollaries:

- A nested `CLAUDE.md` is capped at **~40 lines** and contains only what is *not* derivable
  by reading the code beside it. There are six. Adding a seventh needs a reason.
- If you are writing the same instructions into a prompt for the third time, it is a **skill**.
- If the thing you want is a challenge to a conclusion, it is an **agent**, and it must not
  be the same context that produced the conclusion.

---

# Part 1 — Data governance: where output goes

## 1.1 The placement rule

`STRUCTURE.md` is authoritative. Read it before creating any file. The short form:

- **Nothing new at the repo root.** The root is a fixed allowlist.
- Runtime Python → `src/`. Prose → `docs/`. Work with a done condition → `task/`.
  Problems noticed in passing → `issues/`. Machine output → `results/`.
- If nothing fits, that is a signal the thing is new. Say so and propose a folder — do not
  default to the root.

## 1.2 The four classes of output

Every file this repo produces is one of four things. The class determines who may write it,
whether it may be edited afterwards, and how long it is kept.

| Class | Examples | Written by | Mutable? | Retention |
|---|---|---|---|---|
| **Authored** | Docs, task records, `CLAUDE.md`, fix specs | Human or agent | Yes — edit in place, note the date | Permanent |
| **Transmitted** | `docs/comms/**` | Human or agent, sent once | **No.** Frozen on send | Permanent |
| **Machine** | `results/**`, `logs/**`, `models/**`, feature store | Code only | Overwritten by the next run | See 1.4 |
| **Contract** | `contracts/*.json` | Human, deliberately | Yes — but it is a cross-system change | Permanent, versioned |

**The one-writer rule.** Every machine artifact has exactly one governed writer. The
orchestrator is the only path that promotes a champion. `publish_model_set` is the only
writer of the top-level `latest.json`. Do not add a second writer to anything in this class;
if you need one, that is a design change, not an implementation detail.

**Never hand-edit a machine artifact.** If `results/state/regime_strategy_map.json` is wrong,
the run that produced it is wrong. Editing the output hides the defect and the next run
silently reverts your fix.

## 1.3 Provenance — the header every generated artifact carries

Any file written by a run must be traceable to that run without asking anyone. For JSON,
that means these fields; for Markdown, the same facts in a header block:

```
generated_by     the module path, e.g. "src.vetting.vet"
generated_at     UTC, ISO-8601 with Z
run_id           the id that appears in the log for this run
inputs           what it was derived from (table, version, upstream artifact)
status           where applicable — and see the warning below
```

> **Two `status` fields exist and must never be conflated.** On the model-set manifest,
> `status` is `published` / `withdrawn` and means *is this live*. On
> `regime_strategy_map.json`, `status` is `proposed` / `published` and is vetting's own
> field — it is **not** a publication state. Reading one as the other is FIX-S1-016 and it
> cost weeks of silent non-emission.

## 1.4 Retention

`results/` and `logs/` are machine-written and currently unbounded.
`results/state/` holds **~600 `retrain_log_*.json` files** spanning July–August 2026, most of
them from a cron that no longer runs. That is not a crisis, but it is the reason a listing of
that folder is unreadable and why nobody notices a new file appearing in it.

Standing rule: **anything written on a cadence needs a stated retention.**

| Path | Keep |
|---|---|
| `results/state/retrain_log_*.json` | Last 30, plus every log for a run that promoted. Archive the rest |
| `results/state/*.bak-*` | Until the change that motivated the backup is confirmed, then delete |
| `logs/` | 30 days. Git-ignored in full |
| `archieved/` | Permanent — `.zip` + `.sha256` only, never an unpacked tree |

A backup file with no expiry is not a safety measure, it is clutter that looks like one.

## 1.5 Secrets

`.env`, `secrets/`, `configuration/` are git-ignored and stay that way. Credentials never
appear in a doc, a comms message, a log line, or a task record — not even redacted, because
a redaction tells a reader where to look. Reference the *path* to the credential, never its
value.

---

# Part 2 — The output standard: what makes a result acceptable

This is the acceptance bar. It applies identically to a human and to an agent, which is the
point of writing it down — "an agent produced it" is not a defect, and it is not a defence
either.

## 2.1 The five rules

### Rule 1 — A claim carries its evidence inline

Every factual claim about this system states how it was established, in the same paragraph:
the command run, the run id or artifact path, and the actual output. Not "tests pass" —
the count and the invocation. Not "the map has four cells" — the file read and when.

> Failure this prevents: a rejection message with a hardcoded `< 60mo` threshold sent a
> downstream agent on a real investigation into a gate that was working correctly. When a
> threshold appears in a string, read it from the constant.

### Rule 2 — Verification means running it, not reading it

A docstring, a comment, a README, and a plan are all statements of intent. None is evidence
that the behaviour exists. If you say something works, you ran it and you are showing the
output. If you could not run it, say so explicitly and mark the claim unverified.

### Rule 3 — Dry-run is the default for anything that promotes, publishes, or writes live state

`vet --live`, `train` without `--dry-run`, `publish_gatekeeper`, `publish_model_set`,
`designate`, `--withdraw`: each changes what downstream computers act on. The first run is
always the dry run, and its output is read before the live one. `--withdraw` is CLI-only with
a mandatory human `--reason` and is never automated.

### Rule 4 — State what you did not check

An answer that lists only its findings reads as complete. The scope you did not cover, the
test you skipped, the file you could not open — those are part of the result. Report
outcomes faithfully: if tests fail, say so with the output; if a step was skipped, say that.

### Rule 5 — An adversarial pass, by someone who did not produce the work

Before a result is believed, someone tries to break it, and it is not the author. For
strategy and measurement claims the specific checks are the eight rules in
`docs/design/STRATEGY_EXPERIMENT_STANDARD.md`. For everything else, that reader is the
`auditor` or `devils-advocate` agent, and the question is always the same: **what is the
boring explanation for this result?**

## 2.2 The definition of done

A work item is done when all six hold. Fewer than six means in flight, and saying so is not
a failure.

1. It runs, and the output that proves it is in the record.
2. Tests are green, or the reds are named and shown to be pre-existing.
3. Output landed where `STRUCTURE.md` says it goes.
4. Docs that the change made wrong were updated **in the same change set**.
5. An adversarial pass happened, and what it found is recorded — including "nothing".
6. `task/OPEN.md` reflects the new state.

## 2.3 Escalating rather than guessing

When two documents disagree, or a rule blocks something that clearly needs doing, stop and
say so. Do not pick the reading that is convenient.

Precedence when sources conflict:

```
running code  >  contracts/*.json  >  CLAUDE.md  >  GOVERNANCE.md / STRUCTURE.md  >  docs/  >  comments
```

Implementation wins. But a divergence between code and this file is a defect in one of them
— fix it in the same change set rather than noting it and moving on.

---

# Part 3 — The agent roster

Nine agents live in `.claude/agents/`. **All nine are read-only** — they have no `Edit` or
`Write` tool. They report; the main session decides and writes. An auditor that can edit the
thing it audits is not an auditor.

| Agent | Invoke it when | Its one question |
|---|---|---|
| `auditor` | A result is about to be believed, published, or sent | Does the evidence support the claim? |
| `devils-advocate` | A result is surprising, positive, or convenient | What is the boring explanation? |
| `leakage-hunter` | Any change to features, labels, backtests or strategies | Does this touch information it could not have had at the time? |
| `measurement-reviewer` | A number is being compared to another number | Does this measurement mean anything? |
| `forex-strategist` | Working in `src/layer0/strategies/` | Is this how the market actually behaves? |
| `release-guard` | Anything is about to be published to GCS | Was the publish contract followed in order? |
| `db-guardian` | Writing SQL or touching `src/common/db.py` | Is this idempotent, parameterised, and schema-aware? |
| `structure-warden` | A change set adds or moves files | Is everything where `STRUCTURE.md` says it goes? |
| `comms-liaison` | Drafting for Computer 2 or 3 | Is this accurate, addressed correctly, and safe to freeze? |

**Roles deliberately not created.** A "banker" or capital-allocation role has no home here:
sizing, account state and risk-of-ruin belong to System 3, and this repo is barred from
adding them. The legitimate part of that question — *does this model set deserve real
money?* — is the `auditor`'s job at promotion time. A general "financial analyst" and
"data scientist" collapse into `measurement-reviewer` and `forex-strategist`, which are
narrow enough to be checkable.

---

# Part 4 — Communication standard

Messages to Computers 2 and 3 are the only output this repo produces that **cannot be
retracted**. Other repos cite them by path. `docs/comms/` is append-only in spirit:
a correction is a new file, never an edit.

Full conventions live in `docs/comms/CLAUDE.md`. The three that matter most:

1. **Frozen on send.** Once committed, the content represents what was actually transmitted.
2. **State the evidence, not the conclusion.** The receiving operator cannot run your
   commands. Give them the artifact path, the run id, and the numbers.
3. **Never send a threshold you did not read from the code.** See Rule 1.

---

# Part 5 — Reliability and availability

System 1 is not always-on, and that is by design — it is a factory, not a service. What must
be continuously true is narrower: **the artifacts it publishes are valid, and their staleness
is visible.**

| Property | Enforced by | Failure mode it prevents |
|---|---|---|
| Freshness is measured | `src/monitoring/heartbeat.py` — exit 0/1/2, daily cron | Silent staleness |
| Freshness is published | `publish_health.py` → `telemetry/s1_health.json` | Downstream cannot tell if we are alive |
| Publishes are atomic | The four-step publish contract, pointer flip last | A half-written model set going live |
| A known failure is declared, not silenced | `results/state/cron_holds.json` — reason, evidence, expiry | A red check being ignored until it is background noise |
| Concurrency is bounded | `flock` + single-flight lock | Two runs promoting different champions |

**Default-safe is inviolable:** missing, stale, or errored input ⇒ REJECT. Never a guess,
never a fallback to a cached value, never "probably fine".

**A hold is not a fix.** Every entry in `cron_holds.json` carries an expiry and, when it
expires, either the underlying problem is fixed or the hold is renewed with a fresh reason.
A hold that has been silently renewed three times is an open issue wearing a disguise.

---

## Keeping this file true

This document is *authored* class: edit it in place, and date the change. It is worth having
only for as long as it describes what actually happens.

- A rule that has been violated three times without consequence is not a rule. Delete it or
  enforce it.
- A rule with no failure behind it is speculation. Every rule above traces to something that
  already went wrong here.
- When a rule changes, the agent or skill that encodes it changes in the same change set.

*Companion documents:* `STRUCTURE.md` (where things go),
`docs/design/STRATEGY_EXPERIMENT_STANDARD.md` (the eight rules for strategy claims),
`CLAUDE.md` (repo constraints), `docs/critical/REPO_STATE.md` (current volatile state).
