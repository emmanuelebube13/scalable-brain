# T5 — De-risk the Money Layer (VM sizing code into git + S3 unit-confusion fix package)

> Paste this whole file as the prompt. Repo: `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`.
> **First action: read `task/2026-W31/STATE.md`.** Independent of T1–T4; parts of this task are expected to end BLOCKED on user/VM access — that is a valid outcome, record it precisely.

## Mission — and a hard boundary

The Layer-5 live sizing gate + telemetry publisher run **only on the VM** with no version-controlled source, and every System-3 fix is still "Proposed" — including two wrong-units position-sizing bugs (S3-002 exposure cap unit confusion, S3-004 risk caps in quote-currency units), which are the class of bug that blows up accounts.

**Boundary (from CLAUDE.md):** this machine must NOT edit or run System-2/System-3 code as live systems. What this task produces here is: (a) the VM sizing code captured into version control, and (b) a complete, reviewed **fix package** (patches + tests + apply instructions) that the user applies on Computer 3 / the VM. Do not pretend to have fixed the live system from here.

## Read first

- `docs/proposed-fixes/system-3/` — S3-001…005 and the S3-006 lockout PDF (read the PDF via the Read tool)
- `OtherSystems/system-3-account-management/` — reference copy: architecture + task specs (read-only context)
- `deployment-guide/` — how the VM/System-3 are set up; where sizing code lives on the VM
- Memory: telemetry bucket layout, service-account access, `latest-vm.json`

## Agent team

- **Agent A (Explore):** access reconnaissance — can this machine reach the VM (ssh config, gcloud compute, known hosts) or its artifacts (GCS)? Where per the deployment guide does the sizing code live on the VM? Read-only.
- **Agent B (general-purpose):** VM code capture (step 2).
- **Agent C (general-purpose):** S3-002 + S3-004 fix package (steps 3–4).
- **Agent D (general-purpose):** S3-006 lockout + remaining fixes triage (step 5).
C and D can run in parallel once A is done; B depends on A.

## Execution plan

1. **Recon (Agent A).** Determine concretely: `ls ~/.ssh/config`, `gcloud compute instances list` (if authed), what the deployment guide names as the sizing code path on the VM. Output one of: `REACHABLE via <method>` or `BLOCKED: user must run <exact command> on the VM and place the tarball at <path>`. Record in STATE.md.
2. **Capture the VM code (Agent B).** If reachable: copy the sizing gate + telemetry publisher source off the VM (read-only fetch, e.g. `scp`/`gcloud compute scp`) into a NEW top-level folder `live-vm-capture/layer5-sizing/` in this repo, with a `PROVENANCE.md` (hostname, path, date, sha256 of each file, "captured as-running, unreviewed"). Commit as-is FIRST (pristine capture), then a second commit adding a README describing what each file does. If blocked: write the exact user instructions into STATE.md (one command block they can paste on the VM) and continue to step 3 — the fix package can be drafted from the reference copy + fix docs.
3. **Unit-confusion fixes (Agent C) — S3-002 and S3-004.** For each: read the fix doc, locate the defect in the reference copy (`OtherSystems/system-3-account-management/`) or captured code, and produce in `task/2026-W31/T5-fix-package/`:
   - `S3-002.patch` / `S3-004.patch` — minimal diffs
   - `test_s3_002.py` / `test_s3_004.py` — unit tests that FAIL against the unpatched code and PASS with the patch, with hand-computed expected values for at least: one USD-quote pair, one JPY-quote pair (2-decimal pip), one cross pair — units are the whole bug, so the tests must assert units explicitly (account currency vs quote currency vs pips)
   - `APPLY.md` — exact commands to apply + test on Computer 3, and a rollback command
4. **Verify the packages here.** Run the tests against a local copy of the relevant module (pure-math functions should be runnable in isolation on this machine — that is not "running System 3", it's testing arithmetic). Red-before/green-after both demonstrated and captured in the package.
5. **Lockout + triage (Agent D).** Read S3-006 (the 2026-07-22 live sizing-gate lockout PDF): write a one-page root-cause + fix recommendation into the fix package. Then triage S3-001 (correlation gates blind), S3-003 (Kelly inert/stale edge), S3-005 (auditor leakage): for each, a half-page — severity, fix sketch, and whether it belongs in this week or next. Do not implement these three this week unless trivially small.
6. **Hand-off summary.** `task/2026-W31/T5-fix-package/HANDOFF.md`: ordered checklist for the user's Computer-3 session — apply S3-002, run tests, apply S3-004, run tests, address lockout, restart service, verify telemetry shows sane sizes. Include a "how to verify in production" section: expected position-size magnitude for a known account balance so a wrong-units regression is visible at a glance.

## Validation

```bash
ls live-vm-capture/layer5-sizing/ 2>/dev/null && cat live-vm-capture/layer5-sizing/PROVENANCE.md  # if unblocked
ls task/2026-W31/T5-fix-package/            # patches, tests, APPLY.md, HANDOFF.md all present
pytest task/2026-W31/T5-fix-package/ -v     # green (against patched copies)
```

Red-before evidence: package contains the failing-test output captured against unpatched code.

## Acceptance criteria

- [x] **BLOCKED** — no SSH config; gcloud authed as a storage-only service account (`Required 'compute.instances.list' permission` → 0 items). Precise <5-minute unblocking command in `deliverables/T5/DELIVERABLE.md` §1.
- [x] `fx_units.py` reference arithmetic + `APPLY.md` diffs; 23 tests green covering USD-quote, JPY-quote (2-decimal pip), CAD-quote and cross pairs; `RED-BEFORE.txt` captures 6 failing invariants against the unpatched formulas
- [x] `S3-006-ROOT-CAUSE.md` (all five findings) + `TRIAGE.md` with an ordering recommendation
- [x] `HANDOFF.md` — 7-step session incl. how to spot a wrong-units regression at a glance
- [x] `OtherSystems/` untouched (no files modified 2026-07-29); no live system touched

## Deliverables (required — task is not DONE without them)

Write to `task/2026-W31/deliverables/T5/` (the fix package itself stays in `T5-fix-package/`; these are the reports about it):

1. **`DELIVERABLE.md`** — detailed report: capture provenance (or the exact BLOCKED instruction), the S3-002/S3-004 defects explained with the wrong-vs-right formula side by side, red-before/green-after test evidence, S3-006 root cause, triage table for S3-001/003/005, what the user must do on Computer 3 and in what order, commit SHAs.
2. **Visuals (2 PNGs):**
   - `sizing_error_magnitude.png` — grouped bar chart: for a fixed example account (e.g. $10,000, 1% risk), the position size the UNPATCHED code computes vs the CORRECT size, for one USD-quote pair, one JPY-quote pair, one cross pair. The gap between bars IS the account-blowing bug — this chart is the whole argument for urgency.
   - `s3_risk_matrix.png` — 2×2 severity/effort matrix placing all six S3 items (001–006), colored by status (packaged this week / triaged for next / blocked). Shows the money-layer risk landscape at a glance.
3. **`EXECUTIVE_SUMMARY.md`** — max 1 page: the code that sizes real-money positions had no source control and two unit-confusion bugs; what's now in git, what's packaged and proven by tests, what you must do on Computer 3 (the HANDOFF checklist, summarized), and what risk remains until you do it.

## On failure

Log to `## Failure log`; distinguish FAILED (something here is wrong — fix and re-run) from BLOCKED (needs user/VM — record the unblocking action and move on). Update STATE.md either way.

## Failure log

**2026-07-29 — step 2 (VM capture) BLOCKED, not failed.**
No `~/.ssh/config`; `gcloud` is authenticated as `system1-rw@…` (artifact storage only) and
`compute.instances.list` is denied. The `deployment-guide/` the task names is not in this repo
(it is at `../OtherSystems/deployment-guide/`), and the System-3 reference copy contains only
`docs/` and `tasks/` — **no source**. Unblocking command recorded in `deliverables/T5/DELIVERABLE.md` §1.

**2026-07-29 — step 3's premise was better than expected.**
The task assumed the defects would have to be located in the reference copy. They are present
**verbatim in this repo**: `src/layer4_executor/live_pipeline.py:1108-1112` (S3-002) and
`src/layer7/oanda_executor.py:246,402` (S3-004). The fix package is therefore grounded in the
actual defective source, not a reconstruction.

**2026-07-29 — S3-006 reframes the task (read before applying anything).**
The PDF records **10 realised trades, all losers**: profit factor 0.0, expectancy −367.37
CAD/trade, lifetime −15,934.81 CAD. Its own warning: the jammed gates are *currently the only
thing preventing further loss*, and fixing them without addressing the negative edge "would
convert a stalled system into a reliably losing one". The package therefore sequences the
correctness fixes but explicitly does **not** recommend unblocking the lockout.
