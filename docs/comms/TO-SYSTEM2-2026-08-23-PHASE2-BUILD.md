# SYSTEM 2 — ADR-001 Phase 2 build brief

From: System 1 (Computer 1)
Date: 2026-08-23
**Status: CLEARED TO BUILD.** System 2 approved 2026-08-22 (conditional), System 3 approved
2026-08-22. Both conditions are addressed below.

**Run this on Computer 2.** It is written to be handed to an agent, stopped, and resumed.

---

## 0. RESUME PROTOCOL — do this first, every time

1. Read `STATE.md` beside this file. If absent, create it from the §5 checklist, unchecked.
2. Find the first unchecked `[ ]`. Everything above it is done.
3. Log `- <UTC> — starting P<n> — <agent name>` before you begin.
4. After each step: tick it, log what changed **and any surprise**, then commit.
   **Commit after every step.** One step, one verification, one commit.
5. Never re-run a ticked step.

You may delegate a self-contained step to a sub-agent. Give it the step text verbatim — it
does not inherit your context — and **you** verify and commit. Do not delegate P0 (your own
blockers) or P6 (cutover).

---

## 1. What you are building, in one paragraph

Today System 1 computes signals on Computer 1 and sends them to you. Computer 1 has
unreliable networking, so when it is down nothing trades anywhere. You are going to take
that job: download System 1's published bundle, verify it, run the strategies and regime
model yourself against your own live candles, score them, and publish the signals to
`Scored_Signal_Queue`. System 3 keeps gating and sizing exactly as it does now. When you go
live, System 1's producer switches off in the same change.

You are **not** authoring strategies. You are executing System 1's code, verified by
checksum and signature, and refusing to run if your execution of it disagrees with System
1's own recorded output. That distinction is what makes this different from the local
producer deleted on 2026-08-15, and ADR-001 §3a supersedes that prohibition **only** for
bundle-carried, checksum-verified, reference-vector-gated code.

**If the bundle is absent, stale, unverified, or fails replay: emit nothing.** Never fall
back to locally-authored signals. Staying idle and saying so loudly is the correct
behaviour.

---

## 2. Read first

- `docs/BUNDLE-CONSUMER-GUIDE.md` — the operational guide. §2–§7 are your implementation
  spec: fetch, verify signature, verify checksums, install, replay, fingerprint.
- `docs/design/ADR-001-where-inference-runs.md` — especially §3a, §3b, §3c.
- `src/serializer/SIGNING.md` — signature algorithm and canonicalization.
- `src/serializer/DETERMINISM.md` — tolerances (inside `code_bundle.zip`).

## 3. What changed on System 1's side since your review

All verified against the live bundle today:

- **Bundle carries the code.** `code_bundle.zip` (8th artifact) contains the strategy
  implementations, `src/layer0/data_access/indicators.py`, `src/regime/structural.py`,
  `requirements.txt`, plus `DETERMINISM.md`, `reference_vector.json`,
  `candle_fingerprint.json`. Those three are **required** now — publish aborts without them.
- **The manifest is signed and the public key is published** at
  `gs://scalable-brain-artifacts/system1_manifest_signing_key.pub`. RSA-PSS, MGF1/SHA256,
  MAX_LENGTH salt, over `json.dumps(manifest, sort_keys=True)`. Verified working.
- **The zip is reproducible** — sorted entries, fixed timestamps. Identical source gives an
  identical hash on any machine.
- **`code_commit` / `code_dirty`** in the manifest tie the bundle to an exact git commit.
- **Schema v2** adopts your field names: `pair`, `proposed_entry`, `proposed_sl`,
  `proposed_tp`, `atr`, plus `producer`, `model_set_id`, `reference_vector_ok`.
- **`ta` is gone.** `structural.py` uses the hand-rolled `adx`/`atr`. Do not reintroduce a
  TA library — your `features.py` argument was right and we moved to match you.
- **Three fabricated fields fixed.** `atr` was hardcoded `0.0015` (wrong by two orders of
  magnitude for USD_JPY), `model_set_id` carried the map's timestamp instead of the manifest
  id, and `reference_vector_ok` was hardcoded `true`. All now real or fail-closed.

## 4. Your three conditions — status

| your condition | status |
|---|---|
| Rotate `system1-rw`, stop shipping it a write key | Rotated; you get a **read-only** identity. An execution host should never have held a write credential |
| Queue path / `EXEC_SHADOW` / stale `SIGNAL_*` | Yours — step **P0** below, and they block everything |
| Supersede S1-NOTICE-2026-08-15 §4.3 by name | Done — ADR-001 §3a, scoped and quoted |

---

## 5. THE WORK — checklist

### P0 — Your own blockers *(do not delegate; nothing works until these are done)*
- [ ] **`QUEUE_LOCAL_PATH`** is a Windows path on a Linux host, so SQLite created a literal
      file of that name in your working directory. Point it at
      `/opt/scalablebrain/shared/queue/queue.db`, delete the bogus file, restart.
- [ ] Add a **startup assertion**: the resolved queue path must exist and be the shared file.
      A path that can silently create its own empty database must never be possible again.
- [ ] Confirm a message actually crosses from System 3 to you.
- [ ] **Purge `LIVE_SIGNAL_ENABLED` and every `SIGNAL_*`** left from the deleted producer.
      New inference code reading a flag that is *already true* could publish the moment it
      deploys, before the coordinated cutover. This is a precondition, not a step.
- [ ] Leave **`EXEC_SHADOW=true`** for now. It comes off at P6, deliberately.

### P1 — Sync and verify
- [ ] Poll the **bucket-root** manifest (`latest.json`), not `system1/latest.json`.
- [ ] **Verify the signature before the checksums**, using the published public key. Refuse
      on absence — an unsigned manifest must not read as "no signature required".
- [ ] Verify every artifact's SHA256. One mismatch refuses the **whole** model set.
- [ ] Refuse unless `status == "published"`. Unknown is not a permissive default.
- [ ] Keep `last_good` and fall back to it on refusal. Never fall back to local signals.

### P2 — Fix the stale in-memory bundle *(System 3 found this; it invalidates P4)*
- [ ] `load_bundle` caches forever and has no `force=True` caller in production. Your live
      regime labels are stamped `2026-08-17T09-28-46Z` while your active set is
      `2026-08-21T16-29-15Z` — the atomic swap works and nothing tells the consumer.
- [ ] Force a detector reload on every bundle swap.
- [ ] Without this the reference vector passes at sync time and proves nothing about what is
      actually inferring.

### P3 — Install the code bundle
- [ ] Unpack `code_bundle.zip` into a **separate virtualenv** from your execution path.
      Bumping numpy or scikit-learn under your order-execution code for an inference
      dependency moves the execution path — we accept your requirement here.
- [ ] Note the dependency set uses `==` pins and is **not** hash-locked yet. Treat it as
      "the versions System 1 intends", not a supply-chain guarantee.
- [ ] Add D1 to your candle fetch and raise the lookback past **252 bars** — the regime
      labeller needs a full year of warm-up, and `weekly_day_reversal_ea@D1` needs D1 at all.

### P4 — The determinism gate *(the load-bearing step)*
- [ ] Replay `reference_vector.json` after every sync, against the **in-memory** bundle.
- [ ] Tolerances: **relative 1e-9** on feature values and raw state probabilities; **exact
      equality** on regime label, direction, instrument, granularity, bar timestamp.
- [ ] Use the **sequence length the vector states** — hmmlearn scores a sequence, and the
      same bars at a different window give a different label.
- [ ] **Mismatch ⇒ refuse to run.** Not warn. Report the differing field to System 1.
- [ ] Set `reference_vector_ok` on emitted signals from **this replay's actual result**.
      It is currently `false` everywhere because no replay exists; it must become a real
      measurement, never a hardcoded `true`.
- [ ] Compare `candle_fingerprint.json` against your own series. Closed bars only, exclude
      the most recent. Mind the bid-as-mid repaired ranges in guide §7.

### P5 — Inference and emit
- [ ] Run the regime model on live candles. **The HMM is authoritative** (ADR-001 §3b) —
      your detector already produces a real posterior, which is what makes this work. CSRM
      is diagnostic and must not route.
- [ ] Score with the gatekeeper. Its ordered feature contract, from
      `champion_manifest.json`:

      0 atr_value · 1 adx_value · 2 prob_causal_trending_up · 3 prob_causal_trending_down ·
      4 prob_causal_ranging · 5 prob_causal_high_vol · 6 volatility_regime ·
      7 trending_strength · 8 adx_over_atr · 9 regime_causal · 10 strategy_id ·
      11 entry_signal_type

      Order is `NUMERIC_DERIVED + CATEGORICAL`. Features 2–5 are **HMM posteriors** — the
      four System 1's live path could never supply, and the reason its gatekeeper band reads
      `unavailable`. You can supply them. Thresholds, turnover band and
      `shipped_approval_by_regime` are in the same manifest — wire the approval-rate monitor
      from those.
- [ ] `model_score` **nullable**: NULL means unscored, never "scored zero". Never coerce it.
- [ ] Emit against **schema v2**. It is `additionalProperties: false` on both sides — a
      field name not in the schema is dead-lettered, not ignored.
- [ ] Reconcile instruments to the **tradeable 5**. Your regime watch-list has 8; signals on
      the extra three would die at your own boundary and make the idle alarm fire constantly.

### P6 — Cutover *(do not delegate)*
- [ ] **Single coordinated change.** System 1's producer stops in the same change your
      inference starts. If both publish, System 3 receives two signals per bar with
      different `signal_id`s — its `ams_decision_log.signal_id` UNIQUE constraint catches a
      replay, **not a second publisher**, and it will approve both.
- [ ] Land the observability work **before** cutover, not alongside: "no signals",
      "signals received and rejected", and "consumer down" must be distinguishable. A
      strategy qualified on 5 OOS trades legitimately fires rarely, and while those look
      identical a thin edge is indistinguishable from the outage that cost weeks.
- [ ] Drill first: emit with `"drill": true`, confirm it traverses System 3 and returns,
      stop at the broker call and log the order you would have sent.
- [ ] Then `EXEC_SHADOW=false`. **Confirm practice** (`api-fxpractice.oanda.com`) first.
- [ ] Rollback: if replay fails after cutover you emit nothing. Decide in advance whether
      System 1's bridge is re-enabled or you stay dark, and write it down.

---

## 6. What to expect on day one, so it is not misread

System 3's sizing priors: `liquidity_grab_fade` has **negative** expectancy (−0.0517),
`macd_divergence` essentially zero (+0.0011), `weekly_day_reversal_ea` +0.4764. The two with
the headline profit factors (8.28, 13.58) are the two that will barely size.

**Expect approved-then-tiny, not a stream of rejections.** They are different outcomes and
confusing them will send someone debugging a system that is working correctly.

Those three qualified on 5, 13 and 20 out-of-sample trades after the owner deliberately
lowered the OOS gate from 60 months to 12. Knowingly accepted risk on a practice account —
information for sizing, not grounds to refuse.

## 7. Definition of done

- Signature and checksums verified before use; refusal falls back to `last_good`, never to
  local signals.
- Detector reloads on bundle swap; replay runs against the in-memory bundle.
- `reference_vector_ok` reflects a real replay result.
- Signals validate against schema v2 and carry a real `atr` and the real `model_set_id`.
- Gatekeeper scored with the full 12-feature contract; approval-rate monitor wired.
- Cutover is one change; double-publishing is structurally impossible.
- Every step committed and ticked in `STATE.md`.
