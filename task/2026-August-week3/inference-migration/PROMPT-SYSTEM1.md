# ADR-001 / SYSTEM 1 — make the bundle self-sufficient for inference

**Agent brief. Resumable. Repo: `/home/emmanuel/Documents/Scalable_Brain/scalable-brain` (System 1).**

Written to be stopped and resumed. If you hit a rate limit, context limit, or any
interruption, the next agent re-reads this file plus `STATE.md` in the same folder and
continues from the first unchecked box.

---

## 0. RESUME PROTOCOL — DO THIS FIRST, EVERY TIME

1. Read `STATE.md` in this folder. If absent, create it from the §6 checklist, all unchecked.
2. Find the first unchecked `[ ]`. That is your starting point. Everything above it is done.
3. Append to STATE.md `## Log`: `- <UTC timestamp> — starting S<n> — <your name>`
4. After completing each step: tick the box, append a Log line saying what changed and any
   surprise, then `git add -A && git commit -m "ADR001-S1 S<n>: <what>"`.
   **Commit after every step.** A committed step survives an interruption.
5. Never re-run a ticked step.

**One step, one verification, one commit.** Do not batch.

### Deploying specialised agents

You may delegate a *self-contained* step to a sub-agent (e.g. "write the determinism test
suite for step S5"). If you do:

- give it the step's text from §6 plus §3 (repo rules) — it does not inherit your context;
- require it to report back what it changed and what it verified;
- **you** tick the box and commit, only after you have checked its work yourself.

Do not delegate S1 (scoping) or S7 (the cutover plan). Those need whole-picture judgement
and a sub-agent starting cold will get them subtly wrong.

---

## 1. BLOCKING PRECONDITION

**Read `docs/design/ADR-001-where-inference-runs.md` in full before anything else.**

ADR-001 is **PROPOSED**, not accepted. It requires written APPROVE from **both** System 2
and System 3. Check `docs/comms/` for their replies.

- **Both approved** → proceed with everything.
- **Either rejected, or no reply yet** → do **S2 only** (the queue test-fixture leak,
  which is a real defect regardless of the ADR's outcome), then stop and report. Do not
  build bundle-carried code against an unapproved architecture.

If a reply raises an issue that changes the design, **stop and update the ADR** rather
than implementing around it.

---

## 2. WHAT THIS TASK IS

ADR-001 moves live inference from System 1 to System 2. System 1's side of that is one
thing: **make the published bundle sufficient to run inference, and provable.**

Today the bundle carries seven artifacts — `hmm_model.joblib`, `regime_strategy_map.json`,
`model_metadata.json`, `champion_model.pkl`, `champion_preprocessor.pkl`,
`champion_manifest.json` — which are models and metadata. The **strategy implementations
are Python source in this repo** and are not in the bundle at all.

If System 2 merely holds a copy of that source it can drift from the version System 1
measured, silently: the metrics in the map would describe one implementation while a
different one trades. Strategy code therefore becomes a versioned, checksummed bundle
artifact, verified exactly like the model files.

### Out of scope — do not do these

- **Do not delete or disable `src/signals/` or `src/queue_producer/`.** They are the bridge
  and stay running until System 2's inference is live and proven. Decommissioning is S7,
  and it is a *plan*, not an action.
- Do not edit `../system-2-execution-engine/` or `../system-3-account-management/`.
- Do not change the vetting gates, the `oos_months` value, or add a trade-count gate. The
  owner has ruled on those; they are a separate decision.
- Do not add new strategies or instruments.

---

## 3. REPO RULES

Read `CLAUDE.md` fully before the first change. Load-bearing here:

- DB only via `src/common/db.py`. Storage only via `src/common/storage`.
- Publish ordering is inviolable: **upload → SHA256 verify → only then flip the pointer.**
  Never weaken it.
- The orchestrator is the only governed champion-promotion path (FIX-S1-009). Do not add a
  second one.
- Parameterized SQL; type hints; `black src/ && mypy src/` clean before commit.
- Never commit `.env`, `secrets/`, or model binaries. Never log credentials.
- Python: `/home/emmanuel/Documents/Scalable_Brain/.venv/bin/python`

---

## 4. SAFETY

- The bundle is consumed by another machine that trades. A malformed bundle is worse than
  no bundle: **fail closed**, refuse to publish, leave the previous pointer intact.
- Test with `--dry-run` first. `publish_model_set` and `publish_gatekeeper` both support it.
- Publishing is reversible (`publish_model_set --withdraw --reason "..."`), but a consumer
  may already have synced. Treat every publish as observed.
- If a verification disagrees with this brief, **trust the verification** and record the
  discrepancy in STATE.md. This was written 2026-08-22.

---

## 5. RATE LIMITS

If your own agent/LLM limit interrupts you mid-step, nothing is lost provided you committed
the previous step. Record in STATE.md which step was in flight and what you had done.

---

## 6. THE WORK — checklist

Copy into `STATE.md` on first run.

### S1 — Scope what inference actually needs *(do not delegate)*
- [ ] Determine the exact set of modules System 2 must execute to reproduce a signal.
      Start from `src/signals/run.py` and `src/signals/build.py` and follow every import:
      the strategy modules named in the live map, `src/regime/structural.py`, the contract
      and position-engine code they rely on, the indicator library, the registry lookup.
- [ ] Write `INFERENCE-SURFACE.md` in this folder: every file, why it is needed, and its
      transitive third-party dependencies with pinned versions.
- [ ] Flag anything that reaches for the database or network at inference time. Those are
      the real blockers — System 2 has no access to Computer 1's PostgreSQL by design, and
      the ADR says it must not need it.

### S2 — Close the test-fixture leak *(do this even if the ADR is unapproved)*
- [ ] A test run wrote fixtures into the production queue artifact: the
      `entry: 1.05 / stop: 1.04 / target: 1.06` messages System 2 received for USD_JPY,
      which trades near 159. The values come from `src/signals/tests/test_producer.py`.
- [ ] Make tests physically unable to write to the real queue path — a `tmp_path` fixture,
      an injected queue root, or a guard that refuses a production path under pytest.
      Pick one and make it structural, not a convention.
- [ ] Add a test asserting the guard holds.

### S3 — Strategy code becomes a bundle artifact
- [ ] Package the S1 inference surface into a single versioned artifact (a zip or a
      content-addressed tree — your call, justify it in the commit).
- [ ] SHA256 it and add it to the model-set manifest alongside the existing seven.
- [ ] Include the pinned dependency set from S1 so System 2 can build a matching environment.
- [ ] The manifest must record the **git commit** the code came from.

### S4 — Verify on publish
- [ ] Extend `publish_model_set` so the code artifact goes through the same
      upload → verify → pointer-flip ordering.
- [ ] Refuse to publish if the code artifact is missing, fails checksum, or does not match
      the recorded commit. Fail closed.
- [ ] Test the refusal path — a corrupted artifact must abort with the pointer untouched.

### S5 — Determinism evidence *(delegable)*
- [ ] System 2 running the bundle must produce what System 1 validated. Assertion is not
      enough; produce evidence.
- [ ] Emit a **reference vector** into the bundle: a fixed set of input bars and the exact
      signals System 1's own code produces from them (instrument, direction, entry, stop,
      target, regime label).
- [ ] System 2 replays it after each sync and compares element-for-element. Document the
      comparison contract in `DETERMINISM.md` — including float tolerance, which must be
      stated explicitly rather than left to whoever writes the comparison.
- [ ] Add a System 1 test that regenerates the vector and asserts it is unchanged, so a
      code change that alters signals cannot pass silently.

### S6 — Publish and notify
- [ ] Dry run, inspect, then publish a bundle carrying the code artifact and reference vector.
- [ ] Write `docs/comms/TO-SYSTEM2-<date>-bundle-v2.md`: what is in it, how to verify it,
      how to replay the reference vector, the dependency set.

### S7 — Cutover plan *(do not delegate; a plan, not an action)*
- [ ] Write `CUTOVER.md`: the exact sequence for switching from the System 1 producer to
      System 2 inference.
- [ ] It must make **duplicate publishing impossible** — if both publish, System 3 receives
      two signals per bar with different `signal_id`s and idempotency will not catch it.
      The System 1 producer stops in the *same* change that starts System 2 inference.
- [ ] Include the rollback: what to do if System 2's inference disagrees with the reference
      vector after cutover.

### S8 — Tidy
- [ ] `src/registry/catalog.py` and `src/registry/allocate.py` still import the removed
      `src.regime_aware` package behind the `regime_aware_port` universe. Latent now;
      remove the branch or restore the dependency, and say which and why.
- [ ] `pytest src/ -q` — record the pass/fail count. **Pre-existing failures exist**
      (2 in `src/signals/tests/test_producer.py`, ~11 across vetting/gatekeeper/attribution/
      serializer). Confirm you have not added to them; do not silently fix them here.
- [ ] `black src/ && mypy src/` clean for files you touched.

### S9 — Report
- [ ] `DELIVERABLE.md`: what changed, what is verified, what a reviewer should re-run, and
      explicitly what you left undone.

---

## 7. DEFINITION OF DONE

- Bundle carries strategy code + pinned dependencies + reference vector, all checksummed.
- Publish refuses, fail-closed, on any integrity failure, pointer untouched.
- Determinism contract written and tested from System 1's side.
- Cutover plan makes double-publishing structurally impossible.
- Test fixtures can no longer reach the production queue.
- The bridge producer still runs and was not touched.
- Every step committed individually and ticked in STATE.md.

## 8. IF YOU GET STUCK

Record the blocker in STATE.md under `## Blockers` with the exact command and error, tick
nothing, and stop. Do not improvise around a failing verification: this bundle is executed
by a machine that places trades.
