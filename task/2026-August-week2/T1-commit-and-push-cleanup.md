# T1 — Commit and push the 2026-08-14 cleanup pass

**Engineer:** Gemini Pro
**Reviewer:** Claude (will verify after you report)
**Repo:** `/home/emmanuel/Documents/Scalable_Brain/scalable-brain` (branch `main`, remote `origin` = `git@github.com:emmanuelebube13/scalable-brain.git`)
**Estimated time:** 15 min. **Risk:** none — this is commit + push of work that already exists on disk.

---

## Why this matters

The week-folder rename pass (`2026-W31` → `2026-July-week4`, `2026-W32` → `2026-August-week1`) plus 175
in-repo reference rewrites exist **only on this disk**. Nothing is pushed. A disk failure or an
accidental `git checkout .` loses a full cleanup pass. Get it into history and onto the remote.

You are not fixing, refactoring, or improving anything. **Do not edit file contents.** The only
acceptable file-content change in this task is zero. Your job is staging, committing, pushing.

---

## What is pending (verified state as of 2026-08-15, re-verify before you act)

| Bucket | Count | Nature |
|---|---|---|
| Staged renames under `task/` | 194 files | pure renames, 0 insertions / 0 deletions |
| Unstaged edits **outside** `src/` | 55 files | rewritten path references + new prose in `task/README.md`, `STRUCTURE.md`, `.gitignore` |
| Unstaged edits **under** `src/` | 28 files | comment-only path references (`task/2026-W31/...` → `task/2026-July-week4/...`) |
| Deleted + untracked pair | 2 entries | `task/2026-07-28.md` deleted, `task/2026-July-week4/2026-07-28.md` untracked — one unrecorded rename |

No staged rename touches `src/`. That makes the two-batch split clean: **everything except `src/`**
is batch 1, **`src/` only** is batch 2.

---

## Steps

### 0. Orient

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
git status --short
git diff --stat
git diff --cached --stat
git log --oneline -3
```

Confirm the counts above still hold. If they do not — if there are new files, or if anything under
`src/` shows a non-comment change — **stop and report** instead of improvising a different split.

### 1. Safety check: nothing sensitive goes in

Run all three. All three must come back clean.

```bash
# a) no secret-bearing paths in the pending set
git status --porcelain | grep -Ei '\.env$|\.env\.|secrets/|\.pem$|\.key$|credential' || echo "OK: no sensitive paths"

# b) no secret-shaped strings in any added line
{ git diff; git diff --cached; } | grep -E '^\+' | grep -v '^+++' \
  | grep -EiC0 'password[[:space:]]*=|passwd|api[_-]?key|BEGIN [A-Z ]*PRIVATE KEY|AIza|sk-[A-Za-z0-9]{20}|xox[baprs]-' \
  || echo "OK: no secret-shaped strings"

# c) confirm .gitignore still excludes the regenerable handoff dir under its NEW name
git diff -- .gitignore
```

Expected for (c): the ignore entry moved from `task/2026-W32/fleet/upload/` to
`task/2026-August-week1/fleet/upload/`. If that rename did **not** happen in `.gitignore`, the
handoff zips would become trackable — stop and report.

Note: `docs/proposed-fixes/cross-cutting/FIX-XC-003-db-password-committed-in-tracked-files.md` is in
the change set. That is a *report about* a historically committed password; its pending diff is a
one-line path reference only. It is not a new secret. Do not act on it here.

### 2. Batch 1 — the renames and the doc side

```bash
git add -A -- ':!src'
git status --short -- ':!src' | cut -c1-2 | sort | uniq -c   # sanity: expect R/M/A/D counts, no surprises
git diff --cached --stat | tail -3
```

Commit message:

```
task/: rename ISO week folders to month-and-week form

ISO week numbers (2026-W31, 2026-W32) are unreadable without a calendar.
Renamed to YYYY-Monthname-weekN, filed under the month containing that
week's Monday, and rewrote every in-repo reference to match.

- task/2026-W31/ -> task/2026-July-week4/
- task/2026-W32/ -> task/2026-August-week1/
- task/2026-07-28.md -> task/2026-July-week4/2026-07-28.md
- .gitignore: repoint the fleet/upload/ exclusion at the new path
- task/README.md, STRUCTURE.md: document the naming rule, record the
  rename, and note that finished week folders do not move again

Renames and reference rewrites only. No content was rewritten.
```

### 3. Batch 2 — the source comments

```bash
git add -- src
git diff --cached --stat | tail -3
```

Before committing, prove it is comment-only:

```bash
git diff --cached -- src | grep -E '^[+-]' | grep -v '^[+-][+-][+-]' | grep -vE '^\s*[+-]\s*#' | head
```

That should print **nothing**. If it prints a line, a real code change slipped in — stop and report.

Commit message:

```
src/: update task-folder paths in comments

Comment-only. Points the "see task/..." references in layer0 and system1
at the renamed week folders. No behaviour change.
```

### 4. Push

```bash
git push origin main
```

### 5. Verify

```bash
git status                       # must be "nothing to commit, working tree clean"
git log --oneline -3
git log origin/main --oneline -3 # the two new commits must appear here
git diff origin/main --stat      # must be empty
```

---

## Hard constraints

- **No `Co-Authored-By:` trailer.** Not for Claude, not for Gemini, not for any agent. This repo's
  owner removed agent contributors from GitHub deliberately.
- **No `git rebase`, no `git reset --hard`, no history rewrite, no force push.** History here is
  shared with other machines.
- **No new files at repo root.** The root is closed; `STRUCTURE.md` is the map.
- **Do not touch file contents.** If you spot something you want to fix, write it down in the report
  and leave it alone.
- Two commits exactly. Not one, not five.

---

## Done when

- `git status` is clean (no modified, no staged, no untracked).
- Exactly two new commits sit on top of `fcf6dd4`, in the order above.
- `git diff origin/main --stat` is empty — the remote has both.

## Report back with

1. The output of `git log --oneline -3` and `git status` after the push.
2. The three safety-check results from step 1.
3. The output of the comment-only proof in step 3 (should be empty — say so explicitly).
4. The final file counts in each commit (`git show --stat --oneline <sha> | tail -1`, both commits).
5. Anything you noticed and deliberately did not touch.
