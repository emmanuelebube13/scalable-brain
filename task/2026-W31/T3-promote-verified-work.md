# T3 — Promote the Verified Work (sign-off + `beats_incumbent` ratchet fix)

> Paste this whole file as the prompt. Repo: `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`. Venv active.
> **First action: read `task/2026-W31/STATE.md`.** Requires T1 = DONE (fresh outcomes → honest OOS numbers). If T1 is not DONE, stop and say so.

## Mission

Seven verified System-1 fixes (S1-001, 002, 004, 005, 006, 009, 010) sit "log-only, pending sign-off" — the live champion and strategy map still reflect the pre-fix world. Run one clean gated retrain on post-T1 data, present the evidence for sign-off, promote through the orchestrator (the ONLY promotion path), and fix the `beats_incumbent` ratchet: the gate currently re-armed at a `0.965` factor that ratchets — each promotion raises the bar the next challenger must clear, which will eventually block all promotions including strict improvements.

## Read first

- `docs/proposed-fixes/system-1/` — FIX-S1-001/002/004/005/006/009/010 status blocks (what exactly is unsigned)
- `src/system1/gatekeeper/promote.py` + `src/system1/scheduler/orchestrator.py` — where `beats_incumbent` and `MIN_UPLIFT` live; find the 0.965 factor and how the incumbent baseline is stored/compared
- `results/state/retrain_state.json` + latest `retrain_log_*.json` — current gate outcomes
- `CLAUDE.md` "CURRENT MODEL STATE" + "Open findings A–D"

## Agent team

- **Agent A (Explore):** locate the exact ratchet mechanics — what number is stored as the incumbent baseline, what the challenger is compared against, and prove (with the code path) whether repeated promotions monotonically raise the bar. Output a 10-line explanation with file:line refs.
- **Agent B (general-purpose):** implement the ratchet fix + tests.
- **Agent C (general-purpose):** run the gated retrain, assemble the sign-off evidence package, and (only after the user-visible evidence is produced) promote.

## Execution plan

1. **Ratchet analysis (Agent A).** Confirm or refute the ratchet hypothesis from code. If comparison is `challenger >= incumbent_metric * 0.965`, the anti-flapping intent is fine but verify the *stored baseline* doesn't compound (e.g. baseline updated to challenger's score each promote → bar climbs forever). Record the finding in STATE.md.
2. **Fix (Agent B).** Make `beats_incumbent` compare the challenger against the **current live incumbent's re-measured OOS metric on the same evaluation window** (not a historical high-water mark), with the 0.965 tolerance as a symmetric anti-churn band. Keep fail-closed semantics (missing incumbent metrics ⇒ challenger must pass absolute gates, not free promotion). Add tests: (a) strictly-better challenger promotes, (b) marginally-worse challenger (within band) does not flap, (c) three successive promotions do NOT raise the required bar beyond `live_incumbent * 0.965`.
3. **Gated retrain (Agent C).** `python -m src.system1.scheduler.orchestrator --force`. Single-flight lock rules apply; if locked, investigate staleness before removing anything. Capture the resulting `retrain_log_*.json`.
4. **Sign-off evidence package (Agent C).** Write `task/2026-W31/T3-signoff-evidence.md`: for each of the 7 fixes, one paragraph — what it changed, the guard test proving it, and the fresh retrain's gate results (`regime_accuracy_ok`, `non_empty_map`, `oos_uplift_ok`, `beats_incumbent`) with numbers. Include the proposed map diff vs live (which strategy×regime×gran cells qualify now vs before) and open findings A–D status. **Present this to the user and get explicit "promote" confirmation before step 5 — promotion of the live model is the one step in this week that is not autonomous.**
5. **Promote.** Only via the orchestrator's gated path (if step 3's forced run already promoted because all gates passed, that IS the promotion — record the bundle version). Verify: backend `latest.json` (GCS is authoritative, not local `model-artifacts/latest.json`) points at the new bundle; `previous.json` archived; SHA256 verify happened before the flip (check logs).
6. **GATEKEEPER_AUTOPROMOTE decision.** Do not switch it on. Write a short recommendation (in the evidence package) for when it should be armed: e.g. after N consecutive clean weekly retrains + T4 heartbeat live. This is a user decision — present it, don't take it.

## Validation

```bash
pytest src/system1 -v                        # includes the new ratchet tests
python - <<'EOF'
# read backend latest.json via the storage abstraction and print bundle version + sha
from src.common.storage import build_storage
s = build_storage()
print(s.read_text('latest.json'))
EOF
```

- The promoted bundle version matches the retrain log; all 4 gates show PASS with the fresh-data numbers.
- A `--dry-run` gatekeeper train after promotion still produces `proposed_champion_*` only (safety defaults intact).

## Acceptance criteria

- [ ] Ratchet mechanics documented with file:line evidence; fix implemented + 3 tests green
- [ ] One clean gated retrain on post-T1 data; evidence package written
- [ ] User explicitly confirmed promotion; bundle promoted via orchestrator only
- [ ] Backend pointer verified (version + checksum); local pointer NOT treated as authoritative
- [ ] Fix-doc statuses updated from "log-only pending sign-off" → promoted/live with date
- [ ] AUTOPROMOTE recommendation written, switch left OFF

## Deliverables (required — task is not DONE without them)

Write to `task/2026-W31/deliverables/T3/` (the sign-off evidence package from step 4 lives here too — move `T3-signoff-evidence.md` in):

1. **`DELIVERABLE.md`** — detailed report: the ratchet mechanics with file:line evidence and the fix diff summary; the retrain's four gate results with actual numbers vs thresholds; the promoted bundle version + SHA256; pointer verification output; the seven fix-doc status changes; commit SHAs.
2. **Visuals (2 PNGs):**
   - `gates_dashboard.png` — one bar per deployment gate (`regime_accuracy`, `oos_uplift`, `beats_incumbent`, map coverage): challenger's measured value vs the threshold line, green/red per gate. Shows at a glance why promotion did (or didn't) happen.
   - `map_diff_heatmap.png` — strategy × regime grid (10×4), cells colored: qualified-before-and-after, newly qualified, dropped, never qualified. Annotate granularity in qualified cells. This is the picture of what actually changed in the live model.
3. **`EXECUTIVE_SUMMARY.md`** — max 1 page: seven verified fixes were sitting unpromoted; a fresh gated retrain on honest (post-T1) data was run; the ratchet that would eventually block all promotions is fixed; the live model is now <bundle version> with <N> qualified cells (vs 4 all-one-strategy before); AUTOPROMOTE recommendation and what's still a user decision.

## On failure

Gate failures are information, not errors — if a gate rejects the challenger on honest data, record WHY (which gate, what number vs threshold) in `## Failure log` and in the evidence package, and stop; do not weaken a gate to force promotion. Update STATE.md and name which task file to re-run after the underlying issue is addressed.

## Failure log

(empty)
