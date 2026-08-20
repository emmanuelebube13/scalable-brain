# P4 — Gatekeeper cold-start policy

**Engineer:** Gemini Pro · **Reviewer:** Claude
**Est:** 2–3 h · **Risk:** low — policy plus tests, no live writes.
**Needs:** P0. Independent of P1–P3.

---

## Why

MODEL-006 scores signals from features keyed partly on `strategy_id`. A newly registered
strategy has no history, so the gatekeeper has nothing to say about it — and whatever it
outputs for an unknown id is an artefact of the model's internals, not a judgement.

System 2 already found this and closed it by removal: **F-103 — "the gatekeeper scores
unknown `strategy_id`s and NaN rows instead of refusing"**. Their note says it "must be
re-opened against any rebuilt gatekeeper." This is that re-opening.

---

## Hard constraints

1. **An unknown strategy must never receive a silently invented score.** Refuse, or apply a
   documented explicit policy. Never "whatever the model happens to output".
2. NaN feature rows are refused, not imputed.
3. The policy is decided in the open and written down, not inherited from behaviour.

---

## Execution plan

### Step 1 — Reproduce F-103

Feed the current gatekeeper an unknown `strategy_id` and a NaN row. Record exactly what it
does today in `STATE.md`. This is the evidence the fix is measured against.

### Step 2 — Choose the policy, and write the reasoning

Options, in the order I would consider them:

- **(a) Refuse to score; emit the signal `unscored`.** System 3 decides. Most honest, and
  it composes with P5 step 4 which already emits `unscored` when no champion exists.
- **(b) A documented conservative default score** below any sane threshold, so an unscored
  strategy is effectively held rather than approved.
- **(c) Retrain including the new strategy** before it can be scored. Correct in principle,
  but it means no strategy can ever be published without a retrain — a real coupling cost.

**Recommendation: (a), with (b) as the fallback if System 3 requires a numeric field.**
Ask the owner; record the answer.

### Step 3 — Implement, with the refusal explicit

The refusal must be a distinct, named outcome that appears in the message and the logs —
not an exception that a caller might swallow into a default.

### Step 4 — Tests

1. Unknown `strategy_id` → refusal, not a score.
2. NaN feature row → refusal.
3. The refusal is visible in the emitted message.
4. A known strategy with history is unaffected.
5. The policy is reachable from config/docs, not buried in a branch.

### Step 5 — Append to `STATE.md`, and note it for System 2 (F-103 closed by fix, not removal)

---

## Definition of done

- [ ] F-103 reproduced and recorded before the fix
- [ ] Policy chosen with the owner, reasoning written down
- [ ] Refusal is explicit and visible downstream
- [ ] Tests pass; state the count

## Reviewer will check

- That an unknown id genuinely cannot receive a number.
- That the refusal survives to the message rather than being caught and defaulted.

---

## Failure log

| Timestamp | Step | What went wrong | Root cause | Fix |
|---|---|---|---|---|
| | | | | |
