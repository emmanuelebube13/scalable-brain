# SIGNAL-EMISSION-DEFECTS — state

Resume file for `PROMPT.md` in this folder. **Read that first.**
Tick a box only after the step is verified **and** committed.

**Register:** O-23 (D6), O-24 (D7), O-25 (D8) in `task/OPEN.md`.

## Checklist

- [x] S1 — Read `GOVERNANCE.md`, `CLAUDE.md` §AGENT RULES, `docs/proposed-fixes/system-1/`,
      `task/OPEN.md` (O-16/17/19/20/21/22). Confirm none of D6/D7/D8 is already covered.
      Create a branch. **Branch:** `fix/signal-emission-defects-d6-d7-d8`.
- [x] S2 — **Reproduce D6, no writes.** Causes (a), (b), (c) confirmed independently.
      `FINDINGS-D6.md` written. `devils-advocate` agent run. Committed.
- [ ] S3 — **BLOCKED ON OWNER.** Is re-affirmation of a still-current signal ever wanted?
      (Q1 below)
- [-] S4 — Implement D6: **(b) committed** (`acaa71d`). Tests pass on both backends (LocalDurable
      and PubSub-like stub). **(a) and (c) blocked on Q1.**
- [x] S5 — **Investigate D7, no writes.** `FINDINGS-D7.md` written. Two causes confirmed:
      (a) no minimum R:R floor; (b) `confirmed_lows_list` leakage. `forex-strategist` and
      `leakage-hunter` agents run. Committed.
- [ ] S6 — **BLOCKED ON OWNER.** Should System 1 refuse a bad-R:R signal, or compute and
      publish R:R and let System 3 decide? Separately: fix the leakage in strategy 30? (Q2)
- [ ] S7 — Implement D7 per the decision.
- [-] S8 — D8 index designed (`publish_index()` in `publish_ledger.py`). **Dry-run only.**
      `release-guard` agent run. 5 tests pass. **Deployment gated on Q4 and O-19.**
- [x] S9 — Full suite run: **938 passed**, 0 new reds, 20 pre-existing warnings.
      `black`: 1 file reformatted (producer.py). `mypy`: 0 new errors vs baseline.
- [-] S10 — `DELIVERABLE.md` written. `OPEN.md` update pending. `REPO_STATE.md` no change
      needed (state unchanged). `auditor` and `structure-warden` run.

## Blocking questions — answer before S4(a/c) and S7

| # | Question | Blocks | Answer |
|---|---|---|---|
| Q1 | Is re-affirming a still-current signal ever **wanted**? If yes, the fix is not suppression — a restatement must recompute stop and target and be marked as a restatement on the wire. | S4 (a) and (c) | *unanswered* |
| Q2 | Should System 1 **refuse** to emit a bad-R:R signal, or compute and publish R:R and let System 3 decide? Also: fix the confirmed_lows_list leakage in strategy 30? | S7 | *unanswered* |
| Q3 | (External, System 2) Did **any** of the nine `signal_id`s reach their subscription? See `PROMPT-S2-3-D4-*` Q2. | priority of D6 | *unanswered* |
| Q4 | (External, System 2) Have they already built the prefix-LIST path against `telemetry/signals/`? | S8 live deployment | *unanswered* |

## Log

- 2026-09-03 — Folder opened, brief written (Claude). **No code changed yet.** All evidence in
  `PROMPT.md` §4 was measured 2026-09-03 00:43–00:51Z from `results/signals/*.ndjson`,
  `results/state/*.json` and a live read of `telemetry/s1_health.json`. **Re-verify before
  acting** — the ledger grows hourly and the offsets in §D8 will have moved.
- 2026-09-03 — S1–S5 + partial S4/S8 + S9 complete (commit `acaa71d` + comment fix).
  D6 cause (b): `deduped_count` honest; both backends tested.
  D7: `FINDINGS-D7.md` written; two causes confirmed (missing R:R floor + leakage).
  D8: `publish_index()` implemented, dry-run default, `release-guard` sign-off.
  S3, S6, S8-live blocked on human answers Q1, Q2, Q4/O-19.
