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

## 1. STATUS — both systems approved; read their reviews first

**Read all of these before touching anything:**

1. `docs/design/ADR-001-where-inference-runs.md` — especially **§3a, §3b, §3c**, which were
   added *because of* the reviews and change the work substantially.
2. `docs/comms/TO-SYSTEM2-2026-08-23-ADR001-reply.md`
3. `docs/comms/TO-SYSTEM3-2026-08-23-ADR001-reply.md`

**System 2: conditional APPROVE. System 3: APPROVE.** Both verified against running hosts,
and between them they found seven things invisible from Computer 1. The approvals came with
conditions that are now steps in §6.

**The single most important thing to understand before you start:** the two signal schemas
are mutually incompatible and **every signal System 1 produces today would be rejected by
System 3**. Both are `additionalProperties: false` and they disagree on nearly every field
name. The severed queue meant this was never exercised. Schema v2 (step S3) is therefore
the gate on everything downstream — bundle work that produces unsendable signals is wasted.

If anything you discover contradicts the ADR, **stop and update the ADR** rather than
implementing around it. That is what both reviews did, and it is why the design is now
sound.

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

### S0 — Rotate `system1-rw` *(URGENT, ungated, do this first)*
- [ ] System 2 found `config/gcp-sa.json` at **mode 0666** on their VM holding the plaintext
      key for `system1-rw@scalable-brain.iam.gserviceaccount.com` — our bucket **write**
      identity, world-readable on a host that also runs System 3 and the relay.
- [ ] Rotate the key. Assume compromised, not merely exposed.
- [ ] Issue System 2 a **read-only** service account. An execution host syncs artifacts; it
      never publishes. `chmod` is not the fix — the credential should never have been there.
- [ ] Confirm `secrets/system1-rw.json` on Computer 1 still publishes after rotation.
- [ ] This is what makes manifest signing (S6) load-bearing rather than decorative: anyone
      holding that key can rewrite an artifact *and* its checksum.

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

### S3 — Schema v2 reconciliation *(BLOCKS EVERYTHING BELOW — do not skip ahead)*
- [ ] **Every signal System 1 emits today would be rejected by System 3.** Both contracts
      are `additionalProperties: false` and disagree on field names:

      | System 1 (`contracts/signal-message-contract.json`) | System 3 (`ScoredSignal.schema.json`) |
      |---|---|
      | `instrument` | `pair` |
      | `entry` / `stop` / `target` | `proposed_entry` / `proposed_sl` / `proposed_tp` |
      | *(not sent)* | **`atr`** — required |
      | **`regime_probs`** — required by us | not in their schema → DLQ |

- [ ] Produce a single reconciled v2 contract. **Adopt System 3's names** — `proposed_`
      correctly marks these as requests rather than facts. Do not defend ours.
- [ ] Add the three provenance fields System 3 asked for: `producer`, `model_set_id`,
      `reference_vector_ok`. The third lets them reject on unverified provenance rather than
      trusting that System 2 refused to start.
- [ ] Keep `selection_basis` **not required** — System 3 deliberately made a missing basis
      produce an auditable REJECT at Layer P rather than a silent DLQ.
- [ ] Settle **`atr`**: which period, which granularity, computed by whom. System 3's Layer K
      wants an ATR multiple, so this is load-bearing for their sanity check too.
- [ ] `model_score` must stay **nullable** — System 3 branches on NULL meaning "unscored",
      never "scored zero". It must never be coerced to a number.
- [ ] Send as a proposal with per-field rationale, get written sign-off from **both**
      systems, and ship it as one coordinated release. Never alongside a producer change.

### S3b — Regime ruling: HMM is authoritative, CSRM stops routing
- [ ] ADR-001 §3b is resolved (see §3c): the map, the weights and the gatekeeper were all
      measured on **HMM causal labels**, and the gatekeeper needs four HMM *posterior*
      features CSRM cannot produce. CSRM was only adopted because `regime_causal` is empty
      for the latest bar.
- [ ] Under ADR-001 that reason disappears — System 2's detector runs HMM inference on live
      candles and produces a real posterior. **CSRM becomes a diagnostic and does not route.**
- [ ] Make `src/regime/structural.py` non-routing, and make that explicit in its docstring
      so the next reader does not reintroduce it.
- [ ] Reconcile ADX/ATR to **System 2's hand-rolled implementations**, not `ta`. Theirs is
      the one pinned to MODEL-003 training; ours is the outlier. Drop the `ta` dependency
      rather than shipping a second implementation of the same indicators.

### S4 — Strategy code becomes a bundle artifact
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

### S5 — Determinism evidence *(delegable; needs S3b settled first)*
- [ ] Emit a **reference vector** into the bundle: fixed input bars plus the exact signals
      System 1's own code produces from them.
- [ ] **Tolerances, as System 2 specified and System 1 accepted:** relative **1e-9** on
      feature values and raw state probabilities; **exact equality** on every discrete
      output — regime label, direction, instrument, granularity, bar timestamp. A flipped
      label is a different trade and no tolerance makes that acceptable.
- [ ] **Must include a boundary-adjacent bar.** A vector of unambiguous bars proves nothing,
      because the boundary is the only place a tolerance failure changes an outcome.
- [ ] **Sequence length is part of the contract.** hmmlearn scores a *sequence*; the same
      bars at a different window length yield a different label, so a vector omitting it
      would pass while production diverged. State the exact window.
- [ ] **Replay must run against the bundle loaded in memory, not the symlink.** System 3
      found System 2's `load_bundle` caches forever with no `force=True` caller in
      production — live labels stamped `2026-08-17` against an active set of `2026-08-21`.
      A vector replayed at sync time proves nothing about what is actually inferring.
      System 2 owns the reload; the vector spec must state the requirement.
- [ ] `DETERMINISM.md` records all of the above.
- [ ] System 1 test that regenerates the vector and asserts it is unchanged, so a code change
      that alters signals cannot pass silently.

### S5b — Candle fingerprint *(delegable)*
- [ ] SHA256 over the last N **closed** bars per instrument × granularity across
      `(bar_time_utc, o, h, l, c)`, shipped in the bundle, compared by System 2 on sync.
- [ ] **Exclude the most recent bar** or boundary races produce false alarms.
- [ ] A gate, not a log line.
- [ ] Ship the **bid-as-mid repaired-range list**: before FIX-S1-015 the System-1 ingest
      wrote *bid* into the mid columns. W1 in full and 2026-05-03 → 2026-07-03 on D1/H4/H1
      are repaired; other rows written by the old path may still be half a spread low.
      System 2 fetches `price: "M"`, so a fingerprint over an unrepaired range disagrees by
      design. State the exact repaired ranges.

### S6 — Signing, then publish and notify
- [ ] **Detached signature over the manifest** (which already carries every artifact's
      SHA256, so one signature covers the tree). Signing key on Computer 1 only — never in
      the bucket, never on an execution host.
- [ ] System 2 verifies the signature **before** any checksum and refuses on absence. An
      unsigned manifest must not read as "no signature required".
- [ ] Ship a **hash-locked dependency set** as part of the code artifact. System 2 will
      install it in a **separate venv** — bumping numpy or scikit-learn under their
      execution path for an inference change would move the execution path, which is the
      wrong trade. Do not assume one environment.
- [ ] Dry run, inspect, then publish the bundle with code artifact, reference vector,
      candle fingerprint and signature.
- [ ] Write `docs/comms/TO-SYSTEM2-<date>-bundle-v2.md`: contents, verification steps,
      replay instructions, dependency set, repaired ranges.

### S7 — Cutover plan *(do not delegate; a plan, not an action)*
- [ ] Write `CUTOVER.md`: the exact sequence for switching from the System 1 producer to
      System 2 inference.
- [ ] It must make **duplicate publishing impossible** — if both publish, System 3 receives
      two signals per bar with different `signal_id`s. System 3 confirmed from their side
      that `ams_decision_log.signal_id` is UNIQUE, which catches a *replay* but **not two
      producers**: they would approve both and nothing downstream would catch it. The
      System 1 producer stops in the *same* change that starts System 2 inference.
- [ ] **Precondition, not a step:** System 2's stale `LIVE_SIGNAL_ENABLED=true` and
      `SIGNAL_*` config from the deleted producer must be purged **before** Phase 2. New
      inference code reading a flag that is already true could publish the moment it
      deploys, before the coordinated change.
- [ ] **Ordering, per System 2:** the observability work ("no signals" vs "received and
      rejected" vs "consumer down") lands **before** cutover, not alongside. A strategy
      qualified on 5 OOS trades legitimately fires rarely, and while those states are
      indistinguishable a thin edge looks exactly like the failure that cost weeks.
- [ ] Include the rollback: what to do if System 2's inference disagrees with the reference
      vector after cutover.
- [ ] Note for whoever reads the first days of output: System 3's sizing priors give
      `liquidity_grab_fade` **negative** expectancy (−0.0517) and `macd_divergence`
      essentially zero (+0.0011), so the two headline profit factors will size to almost
      nothing. Expect **approved-then-tiny, not rejections** — do not read the two as the
      same signal.

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

- `system1-rw` rotated; System 2 holds a read-only identity.
- **Schema v2 signed off by both systems and shipped as its own release.** Without this
  nothing else matters — today every System 1 signal would be rejected by System 3.
- CSRM no longer routes; ADX/ATR reconciled to System 2's implementation; `ta` dropped.
- Bundle carries strategy code + hash-locked dependencies + reference vector + candle
  fingerprint, all checksummed, under a detached manifest signature.
- Publish refuses, fail-closed, on any integrity failure, pointer untouched.
- Determinism contract written and tested, including the in-memory-bundle requirement.
- Cutover plan makes double-publishing structurally impossible, with the `SIGNAL_*` purge
  as a precondition and the observability work ordered before cutover.
- Test fixtures can no longer reach the production queue.
- The bridge producer still runs and was not touched.
- Every step committed individually and ticked in STATE.md.

## 7a. WHAT THE OTHER SYSTEMS OWE, AND WHY IT GATES YOU

Do not build past these. They are not System 1's to fix:

| owner | item | why it blocks |
|---|---|---|
| System 2 | `QUEUE_LOCAL_PATH` → `/opt/scalablebrain/shared/queue/queue.db` | link 3 severed; nothing System 3 approves reaches the broker. Why nothing has traded since 2026-07-27 |
| System 2 | `EXEC_SHADOW=true` decision | orders are constructed and never submitted |
| System 2 | force detector reload on bundle swap | otherwise the reference vector proves nothing |
| System 2 | purge `LIVE_SIGNAL_ENABLED` / `SIGNAL_*` | a stale true flag could publish before cutover |
| System 3 | Layer K (entry vs live market price) | Layer J checks internal consistency only; the 1.05 fixtures would pass it and be sized |
| System 3 | heartbeat topic contract | their `eval_not_trading` watchdog needs decisions to occur before it can report that decisions are not occurring |
| both | schema v2 sign-off | see S3 |

## 8. IF YOU GET STUCK

Record the blocker in STATE.md under `## Blockers` with the exact command and error, tick
nothing, and stop. Do not improvise around a failing verification: this bundle is executed
by a machine that places trades.
