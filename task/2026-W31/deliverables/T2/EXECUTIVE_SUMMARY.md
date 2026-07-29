# T2 — Secrets Hygiene · Executive Summary

**2026-07-29 · FIX-XC-003**

## What was wrong

The password to the live trading database was written in plain text inside the project's own
files — 27 times, across 11 files, in the repository since **25 April 2026**. Anyone with a
copy of the repo had full access to `ForexBrainDB`.

Two of the leaking files were the security documents themselves: the very report describing
this problem quoted the password seven times, and so did the roadmap task titled "secrets
management and rotation."

## What was done

- **The password was changed.** A new 28-character credential was generated and applied to
  the database.
- **The old one was verified dead** by trying it: `password authentication failed for user
  "sa"`. Not assumed — tested.
- **All 27 copies were removed** from the project files, replaced with a pointer to the
  private settings file.
- **A setup template (`.env.example`) was added**, so the project can be configured on a new
  machine without anyone needing to share a password.
- Everything still works: the retrain scheduler and both scheduled jobs run clean, because
  they read the password from the private settings file rather than having their own copy.

## What is still exposed — and why that's acceptable

The old password remains visible in the project's **history** (8 past commits). It cannot be
removed without rewriting that history, which would break every existing copy of the project
on every machine.

This is a deliberate decision, not an oversight. **The old password no longer opens
anything.** A dead credential in an archive is not a risk. Erasing history would cost real
disruption to eliminate a theoretical one.

If you would rather have it erased anyway, that is your call to make — it needs your explicit
go-ahead, and it would have to be done on all three computers plus any backup at the same
time.

## Confirmed with you during this work

You confirmed that System 2 and System 3 on your other computers do **not** connect to this
database. That is why the rotation could proceed immediately without coordinating a
changeover — nothing remote broke, and there is no pending action for you here.

## One recommendation

Nothing currently stops this from happening again — the password was pasted into
documentation eleven separate times over three months and nothing objected. An automatic
check that refuses to save a file containing a password would have caught all 27. The project
already has a secret scanner in its model-publishing step that could be reused for this.
Suggested for next week.
