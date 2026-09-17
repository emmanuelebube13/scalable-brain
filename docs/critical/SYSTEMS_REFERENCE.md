# SYSTEMS REFERENCE — read access to Systems 2 and 3

**Established:** 2026-09-13 by owner request · **Refresh with**
`shell/check_systems_reference.sh`, not by editing prose.

This file exists because the reference channel the rest of the repo assumes did not exist.
`CLAUDE.md`, `README.md` and four other documents cite `../system-2-execution-engine/` and
`../system-3-account-management/` — **neither directory has ever been on this machine**, and
neither name matches a real repository. Agents working here had zero visibility into the two
systems this one publishes to. See `issues/September-Week-2/2026-09-13.md`.

---

## The real topology

**There is no Computer 2 and no Computer 3.** System 2 and System 3 run as two systemd services
on one GCP VM.

| | Value |
|---|---|
| Host | `trading-1`, zone `europe-west1-b`, `e2-medium`, project `scalable-brain` |
| Network | **Internal IP only** (`10.132.0.2`). SSH requires `--tunnel-through-iap` |
| Access | `gcloud compute ssh trading-1 --zone europe-west1-b --tunnel-through-iap` |

| System | Repo | Deployed at | Service | Port |
|---|---|---|---|---|
| S2 — The Hand | `github.com/emmanuelebube13/system2Executor` (**public**) | `/opt/scalablebrain/system2/system-2-execution-engine` | `system2.service` | `127.0.0.1:8002` → `/status` |
| S3 — The Guardian | `github.com/emmanuelebube13/scalablebrain-ams` (private) | `/opt/scalablebrain/system3/ams` | `s3-ams.service` | `127.0.0.1:8300` → `/health` |

Both endpoints bind to loopback — reachable only over the SSH tunnel, not from here directly.

---

## Local reference clones

**Path:** `/home/emmanuel/Documents/Scalable_Brain/systems-reference/` — deliberately *outside*
this repo. They are separate git repos with their own remotes; nesting them here would mean
gitignoring a tree that looks tracked, and `STRUCTURE.md`'s no-new-root rule applies to this
repo only.

```
/home/emmanuel/Documents/Scalable_Brain/
├── scalable-brain/       this repo
├── systems-reference/    ← S2 and S3, READ-ONLY by convention
│   ├── system2Executor/
│   └── scalablebrain-ams/
└── .venv/
```

### Pinned as of 2026-09-13

| Clone | Checked out | Why that ref |
|---|---|---|
| `system2Executor` | `fdbe980` (`main`, 2026-08-29) | Default branch tip |
| `scalablebrain-ams` | `5b66039` (**detached**) | The commit the live VM's `.git` records. *Not* the default branch, and **not** what the VM's files actually contain — see below |

### Two traps, both real

1. **`scalablebrain-ams`'s `origin/HEAD` points at `remediation/2026-W31-orchestrator-v2`
   (2026-08-23), not `main` (2026-08-29).** A plain `git clone` silently gives you a six-day-old
   branch that is behind `main`. Always state the ref you read.
2. **The deployed System 3 tree matches no single commit.** Its recorded HEAD is `5b66039`, but
   its `contracts/v1/ScoredSignal.schema.json` is the version from `0f51f21` (2026-08-29, on the
   unmerged `feat/adr001-reanchor-and-drills`). Files were updated in place without moving the
   ref. **Read the VM, not the repo, when the answer matters** — and see ISSUE-1 for why this is
   severity-1.

### Rules for these clones

- **Read-only by convention.** Never `push` from here.
- **To change S2 or S3: branch, push, open a PR on that repo.** Never edit
  `/opt/scalablebrain/...` in place — both are live services placing real orders, and in-place
  editing is exactly how the drift above happened.
- **Deploy by pulling on the VM**, never by file sync.
- Re-pin this file whenever the clones are refreshed.

---

## Contract alignment

The four schemas in this repo's `contracts/` are **System 3's**, adopted wholesale —
`contracts/signal-message-contract.json` carries
`$id: https://scalablebrain/ams/contracts/v1/ScoredSignal.schema.json` and a `required` list
identical to S3's. The old "mutually incompatible field names" finding in `CLAUDE.md` is
**resolved and stale**.

What remains is narrower: System 1 emits three fields (`producer`, `bundle_id`, `drill`) that
only the *unmerged* `feat/adr001-reanchor-and-drills` accepts. Both sides set
`additionalProperties: false`, so deploying S3 from `main` rejects every signal. ISSUE-1.

S3's canonical contract set is `contracts/v1/` in `scalablebrain-ams`:
`ScoredSignal`, `ApprovedOrder`, `AccountSnapshot`, `FillEvent`, `Command`. This repo mirrors
only the first. **S3 is the schema owner; System 1 adopts.**
